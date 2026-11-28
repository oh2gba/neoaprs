"""The composition root: builds every part of the program in one place.

Wiring is in wiring.py, start and stop in controller.py. Radios are made from `Config.radios`,
again by the controller once the stored radios are read; a test may pass a line per radio id.
"""

import asyncio
import logging
import platform
import sys
from pathlib import Path
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from . import VERSION, ax25, pairsetting, stopfile
from .aprsis import AprsIs
from .bulletinlog import BulletinLog
from .claims import Claims
from .clock import Clock, utcnow
from .config import DEFAULTS, MESSAGE_RADIOS, Config
from .crossrule import reply_path
from .radioedits import kept_change
from .sendonrule import Kept
from .db import Db
from .gpsfeed import GpsFeed
from .interlock import Interlock
from .messagelog import MessageLog
from .ownlog import OwnLog
from .packet import IS, Packet
from .packetlog import PacketLog
from .policy import TNC_CHECK_SEC
from .radiodriver import RadioDriver, RunOverrides
from .radioregistry import LiveRadio, RadioRegistry, make_driver
from .radiospec import RadioId, RadioSpec, modem_radio
from .route import Deliveries
from .serialprobe import search_pattern
from .services.alerts import Alerts
from .services.aloha import Aloha
from .services.beacon import Beacon, BeaconError
from .services.beaconframe import BeaconFrames
from .services.memory import Remembered
from .services.bulletins import Bulletins
from .services.digipeater import Digipeater
from .services.generalask import GeneralAsk
from .services.gps import Gps
from .services.igate import Igate
from .services.keys import keyring_for
from .services.layers import Layers
from .services.satellites import Satellites
from .services.mapauto import MapAuto
from .services.mapfetch import MapFetch
from .services.messaging import Messaging
from .services.ownbulletins import OwnBulletins
from .services.ownobjects import OwnObjects
from .services.prefbook import PrefBook
from .services.pskreporter import PskReporter
from .services.answers import AnswerBudget
from .services.qru import Qru
from .services.qruask import QruAsk
from .services.queries import Queries
from .services.radiofinder import RadioFinder, candidates
from .services.radioset import AirRadio, first_sender
from .services.rigstatus import RigStatus
from .services.selfinstall import installer_for, release_key, release_source
from .services.selfupdate import SelfUpdate
from .services.sender import Sender
from .services.stationalerts import StationAlerts
from .services.frequencies import Frequencies
from .services.chat import ChatRoom
from .services.skeds import Skeds
from .services.updatecheck import UpdateCheck
from .signal import Signal
from .stationbook import StationBook, carries_path
from .store import Store
from .tasks import TaskSet
from .tnc import Tnc
from .updatefetch import fetch as fetch_update
from .mercury import SUGGESTED
from .versions import PLAIN_INSTALL, Frequency, InstallInfo, platform_name
from .weatherlog import WeatherLog

log = logging.getLogger("neoaprs.controller")

Radio = LiveRadio[Beacon]


class Frontend(Protocol):
    """The page's server: started after the radios, stopped before them."""

    async def start(self) -> bool: ...
    async def stop(self) -> None: ...
    def settings_changed(self, config: Config) -> None: ...
    def bound_port(self) -> int: ...


@dataclass(frozen=True)
class PositionFrames:
    """Our position packet for the radio an answer goes on."""

    made: Callable[[AirRadio | None], ax25.Frame]

    def frame(self, radio: AirRadio | None = None) -> ax25.Frame:
        return self.made(radio)


class Services:
    # Keep-alive quiet period in seconds; tests shorten it or set 0.
    check_sec: float = TNC_CHECK_SEC
    # Set when the stored radios could not be read: no radio is added until the next start.
    radios_unread = False

    def __init__(
        self,
        data_dir: Path,
        clock: Clock = utcnow,
        store: Store | None = None,
        port: str = "",
        pattern: str = "",
        install: InstallInfo = PLAIN_INSTALL,
        auto_map: bool = False,
        encryption: bool = False,
        hf_port: str = "",
        lines: Mapping[RadioId, Tnc] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.encryption = encryption
        self.clock = clock
        self.config: Config = replace(DEFAULTS, radios=())
        self.config_lock = asyncio.Lock()
        self.port_override = port
        self.hf_port_override = hf_port
        self.pattern_override = pattern
        self.store = store if store is not None else Store(clock)
        self.lines = dict(lines or {})
        claims = Claims()
        self.suggested_frequencies = [Frequency(band, dial) for band, dial in SUGGESTED]
        interlock = Interlock(lambda: self.config)
        # Only radios that may carry a path give routes; own copies heard back are ignored.
        self.stationbook = StationBook(
            clock,
            carries_path=lambda radio: carries_path(self.config.radios, radio),
            own_calls=lambda: pairsetting.own_calls(self.config.station_call, self.config.pairs),
        )
        self.radio_packet: Signal[[Packet]] = Signal("radio.packet")
        self.radio_changed: Signal[[RadioId]] = Signal("radio.changed")
        kept = Remembered(self.store)
        self.radios: RadioRegistry[Beacon] = RadioRegistry(
            claims,
            lambda spec: self._make_driver(spec, interlock),
            self._make_beacon,
            lambda: self.config,
            self.stationbook,
            lambda text: None if self.radios_unread else kept.put({MESSAGE_RADIOS: text}),
            kept.flush,
            clock=clock,
            run=lambda: self.run,
        )
        self._make_radio_parts(clock)
        self._make_logs(clock)
        self.aprsis = AprsIs(clock)
        self.igate = Igate(
            self.aprsis,
            lambda: self.config,
            self.beacon_frames.position_info,
            lambda: self.stationbook.me_position,
            clock,
        )
        self._make_messaging(clock)
        self._make_map_and_update(data_dir, install, auto_map, clock)
        self.digipeater = Digipeater(self.radios, lambda: self.config, clock)
        # The stations a Mercury radio hears directly, to PSK Reporter's map.
        self.pskreporter = PskReporter(
            lambda: self.config, lambda: self.stationbook.me_position, self.stationbook.get, clock
        )
        self.internet_packet: Signal[[Packet]] = Signal("internet.packet")
        # A Dummy radio makes up its traffic, so nothing goes to APRS-IS while one is on.
        self.igate.made_up = lambda: any(radio.line.is_dummy for radio in self.radios.enabled())
        self.config_changed: Signal[[Config]] = Signal("config_changed")
        self.web: Frontend | None = None
        self.db: Db | None = None
        self.tasks = TaskSet(log)
        self.running = False
        self.debug = False

    @property
    def run(self) -> RunOverrides:
        """Return the run-only overrides (neoaprs/radiodriver.py), read afresh each time."""
        return RunOverrides(
            self.port_override,
            self.pattern_override,
            self.hf_port_override,
            self.check_sec,
            modem_radio(self.config.radios),
        )

    def _make_driver(self, spec: RadioSpec, interlock: Interlock) -> RadioDriver:
        """Return the driver of the radio's type, using the line a test handed in for it, if any."""
        driver = make_driver(
            spec,
            self.radios.claims,
            self.clock,
            self.data_dir,
            self.lines.get(spec.id),
            search_lock=self.radios.search_lock,
        )
        driver.line.where = lambda: self.config.station_position
        driver.line.interlock = interlock
        return driver

    def _make_beacon(self, radio: Radio) -> Beacon:
        """Return a radio's beacon: interval, SmartBeaconing and on request, as its type allows."""
        return Beacon(radio, lambda: self.config, self.clock, memory=self.store, frames=self.beacon_frames)

    def moving_beacon(self) -> Beacon | None:
        """Return the beacon SmartBeaconing is read from (first radio that has it), else None."""
        return next((radio.beacon for radio in self.radios.beaconing() if radio.allowed.smart_beacon), None)

    def position_frame(self, radio: AirRadio | None = None) -> ax25.Frame:
        """Return our position frame for `radio` (the first sender if None); raise BeaconError."""
        radio = radio or first_sender(self.radios)
        if radio is None:
            raise BeaconError("there is no radio that is on")
        return self.beacon_frames.position(radio)

    def _make_radio_parts(self, clock: Clock) -> None:
        """Make what the beacons need: the GPS, the frame maker and the status report."""
        self.gps_feed = GpsFeed(clock)
        self.gps = Gps(self.gps_feed, lambda: self.config, clock, claims=self.radios.claims)
        self.beacon_frames = BeaconFrames(lambda: self.config, self.gps, clock)
        self.radios.sync(self.config)
        self.rigstatus = RigStatus(self.radios, lambda: self.config, self.beacon_frames, clock, memory=self.store)
        self.alerts = Alerts(lambda: self.config, clock)  # Runs the alert command for a message to us.

    def _make_logs(self, clock: Clock) -> None:
        """Make the parts that keep rows in the database."""
        self.packetlog = PacketLog(clock=clock)  # Every packet and the station cache.
        self.messagelog = MessageLog(clock=clock)  # Messages sent and received.
        self.prefbook = PrefBook(
            self.messagelog,
            lambda: self.config,
            self._deliveries,
            clock,
            paths=self.messagelog,
            gateway=self._gateway_path,
        )
        # Keys for encrypted messages: ours in the data folder, the stations' with the messages.
        self.keyring = keyring_for(self.data_dir, self.messagelog, clock, self.encryption)
        self.weatherlog = WeatherLog(clock=clock)  # Observations of the weather stations.
        self.bulletinlog = BulletinLog(clock=clock)  # The message board.
        self.bulletins = Bulletins(self.bulletinlog, clock)
        self.ownlog = OwnLog(clock=clock)  # Our own objects, items and bulletins.
        self.stationalerts = StationAlerts(self.stationbook, self.prefbook, lambda: self.config, clock)

    def _make_messaging(self, clock: Clock) -> None:
        """Make the scheduled senders, the QRU parts, messaging and the query answers."""
        self.sender = Sender(self.radios, lambda: self.config, clock)
        self.ownobjects = OwnObjects(
            self.sender, lambda: self.config, self.ownlog, self._is_station, clock, memory=self.store
        )
        self.ownbulletins = OwnBulletins(self.sender, lambda: self.config, self.ownlog, clock, memory=self.store)
        # Answer frames per minute, shared by the QRU server and the queries.
        answer_budget = AnswerBudget(clock)
        self.qru = Qru(
            self.radios,
            lambda: self.config,
            self.ownobjects,
            self.stationbook,
            self.prefbook.path_for,
            clock,
            budget=answer_budget,
        )
        self.qruask = QruAsk(self.radios, lambda: self.config, self.prefbook.path_for, clock)
        self.generalask = GeneralAsk(self.radios, lambda: self.config, self.stationbook, clock)
        self.messaging = Messaging(
            self.radios,
            lambda: self.config,
            self.messagelog,
            self.prefbook.path_for,
            clock,
            board=self.bulletins.heard,
            alert=self.alerts.alert,
            qru=self.qru.heard,
            qru_answer=self.qruask.answers,
            keyring=self.keyring,
        )
        self.queries = Queries(
            self.radios,
            lambda: self.config,
            PositionFrames(self.position_frame),
            self.rigstatus.status_frame,
            self.stationbook,
            self.prefbook.path_for,
            clock,
            objects=self.ownobjects,
            messages=self.messaging,
            heard=self.packetlog,
            igate=self.igate,
            budget=answer_budget,
        )

    def _make_map_and_update(self, data_dir: Path, install: InstallInfo, auto_map: bool, clock: Clock) -> None:
        """Make the base map, ALOHA, traffic layers, Find my radio and the update parts."""
        self.mapfetch = MapFetch(data_dir, lambda: self.config, clock)
        self.mapauto = MapAuto(self.mapfetch, lambda: self.config, self.store, auto_map)
        # ALOHA circles (rule 3.8) for each radio that is on and shares a 1200 baud channel.
        self.aloha = Aloha(self.stationbook, clock, radios=self.radios.enabled)
        self.radiofinder = RadioFinder(
            self._radio_ports,
            self.hold_radio,
            self.release_radio,
            claims=self.radios.claims,
            search_lock=self.radios.search_lock,
        )
        self.install = install
        where = platform_name(
            sys.platform, platform.machine(), install.kind == "appimage", container=install.kind == "container"
        )
        self.updatecheck = UpdateCheck(
            lambda: self.config,
            VERSION,
            where,
            fetch_update,
            memory=self.store,
            developer=install.kind == "source",
        )
        self.frequencies = Frequencies(VERSION, where, memory=self.store)
        self.skeds = Skeds(
            VERSION,
            where,
            lambda: self.config,
            lambda: self.suggested_frequencies,
            memory=self.store,
        )
        self.chat = ChatRoom(
            VERSION,
            where,
            lambda: self.config,
            self.skeds.token,
            memory=self.store,
        )
        self.layers = Layers(
            lambda: self.config,
            lambda: self.stationbook.me_position,
            VERSION,
            where,
            clock=clock,
        )
        self.satellites = Satellites(
            data_dir,
            lambda: self.stationbook.me_position,
            VERSION,
            where,
            clock=clock,
        )
        self.selfupdate = SelfUpdate(
            install,
            installer_for(
                install, data_dir, self.restart_into, encryption=self.encryption, leaving=self.note_page_port
            ),
            self._announced,
            release_source(),
            end=self._end_for_restart,
            key=release_key,
        )
        # Command to run in place of this process once it has ended (AppImage update).
        self.reexec: list[str] | None = None

    def hear_internet(self, packet: Packet) -> None:
        """Admit a packet received from APRS-IS and emit it on `internet_packet`, while its stations are shown.

        Raise ValueError for anything but an `is` packet; radio packets use the Tnc's signal.
        """
        if packet.via != IS or packet.direction != "in":
            raise ValueError("only a packet received from the internet (Packet.via is) enters here")
        # a login that only gates still gets messages to our call; nothing of it is kept
        if self.config.igate_enabled:
            self.internet_packet.emit(packet)

    def kept_change(self, before: Config, after: Config) -> tuple[Config, Kept]:
        """Return `after` with its ticks put in, and what the change keeps in force."""
        return kept_change(before, after, self.ownobjects.radio_sets(), self.ownbulletins.radio_sets())

    def keep(self, kept: Kept) -> None:
        """Send the objects and bulletins of `kept` out on their new radio sets from now on."""
        self.ownobjects.keep_radios(kept.objects)
        self.ownbulletins.keep_radios(kept.bulletins)

    def forget_radio(self, id: RadioId) -> None:
        """Drop what the parts keep in memory of a removed radio."""
        self.radios.forget_radio(id)
        self.ownobjects.forget_radio(id)
        self.ownbulletins.forget_radio(id)

    def _deliveries(self, call: str) -> Deliveries | None:
        """Return how the station's packets reached us (for a message path); None if unknown."""
        found = self.stationbook.get(call)
        return None if found is None else found.deliveries

    def _gateway_path(self, call: str, radio: RadioId) -> tuple[str, ...]:
        """Return the reply path to a station on a radio that carries no path (via its gateway)."""
        found = self.stationbook.get(call)
        if found is None:
            return ()
        return reply_path(
            found.heard_on(radio).last_path, pairsetting.own_calls(self.config.station_call, self.config.pairs)
        )

    async def _radio_ports(self) -> list[str]:
        """Return the ports Find my radio tries: the search's candidates, less held ones."""
        pattern = self.pattern_override or search_pattern(self.config.serial_pattern)
        return await asyncio.to_thread(candidates, pattern, self.config.serial_skip_paths)

    async def hold_radio(self, id: RadioId) -> None:
        """Stop a radio so that a search can open the ports."""
        radio = self.radios.get(id)
        if radio is not None:
            await radio.driver.stop()

    def release_radio(self, id: RadioId) -> None:
        """Hook: the controller gives the radio back what it holds."""
        pass

    def repoint(self, radio: RadioId) -> None:
        """Hook: the controller points the radio's line at the new ports after a modem restart."""
        pass

    def _announced(self) -> str | None:
        latest = self.updatecheck.latest
        return latest.version if latest is not None else None

    def restart_into(self, argv: list[str]) -> None:
        """Run `argv` in place of this process once the daemon has ended (neoaprs/daemon.py).

        Called from the Update now thread, which ends the daemon afterwards.
        """
        self.reexec = argv
        stopfile.mark_restart(self.data_dir)
        self.note_page_port()

    def note_page_port(self) -> None:
        """Note the page's port for the next daemon; a failed write is only logged."""
        try:
            stopfile.note_port(self.data_dir, self.web.bound_port() if self.web is not None else 0)
        except OSError as e:
            log.warning("the port of the page could not be noted for the restart (%s)", e)

    def _end_for_restart(self) -> None:
        """End the daemon as `neoaprs stop` does, if Update now has a command to run."""
        if self.reexec is not None:
            stopfile.request(self.data_dir)

    def _is_station(self, name: str) -> bool:
        """Return whether `name` is a station of the book (a heard call, not an object)."""
        found = self.stationbook.get(name)
        return found is not None and found.kind == "station"
