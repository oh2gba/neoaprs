"""The composition root: the parts of the program, made in one place. The data directory, the clock, the settings (`config`), the Store, the radios (the registry, `radios`, with each radio's driver, line and beacon), the station book, the GPS and its service, the beacon, the status, the message alert, messaging, the message board,
the objects and the bulletins of our own and their sender, the queries, the QRU server, the digipeater, the receive-only iGate and its connection to APRS-IS, the base map, Find my radio, the update check and Update now (the services are made here and nowhere else), the station preferences, the packet log, the message log, the bulletin log, the log of our own objects and bulletins, the weather log and the task set. The parts are made here and connected in neoaprs/wiring.py; the start and the stop are neoaprs/controller.py.

The radios are made from the settings (`Config.radios`): from the defaults here, and again by the controller once the stored radios are read. Each radio's driver makes its line and its modem (a test may
hand in a line of its own for a radio, by its id: `lines`). Every service that sends or answers takes the registry itself, and our frames are made by one maker (`beacon_frames`).
"""
import asyncio
import logging
import platform
import sys
from pathlib import Path
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from . import VERSION, ax25, stopfile
from .aprsis import AprsIs
from .bulletinlog import BulletinLog
from .claims import Claims
from .clock import Clock, utcnow
from .config import DEFAULTS, MESSAGE_RADIOS, Config
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
from .services.keyring import Keyring
from .services.mapauto import MapAuto
from .services.mapfetch import MapFetch
from .services.messaging import Messaging
from .services.ownbulletins import OwnBulletins
from .services.ownobjects import OwnObjects
from .services.prefbook import PrefBook
from .services.answers import AnswerBudget
from .services.qru import Qru
from .services.qruask import QruAsk
from .services.queries import Queries
from .services.radiofinder import RadioFinder, candidates
from .services.radioset import AirRadio
from .services.rigstatus import RigStatus
from .services.selfinstall import installer_for, release_key, release_source
from .services.selfupdate import SelfUpdate
from .services.sender import Sender
from .services.stationalerts import StationAlerts
from .services.frequencies import Frequencies
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

Radio = LiveRadio[Beacon]            # a radio of the station at run time, with the beacon this root gives it


class Frontend(Protocol):
    """What the controller needs of the page's server (neoaprs/web/server.py, which this layer does not import): it is started once the radio is, and stopped before it."""
    async def start(self) -> bool: ...
    async def stop(self) -> None: ...
    def settings_changed(self, config: Config) -> None: ...


@dataclass(frozen=True)
class PositionFrames:
    """Our position packet for the radio an answer goes on, as the queries ask for it (services/queries.py `Frames`)."""
    made: Callable[[AirRadio | None], ax25.Frame]

    def frame(self, radio: AirRadio | None = None) -> ax25.Frame:
        return self.made(radio)


class Services:
    check_sec: float = TNC_CHECK_SEC         # the keep-alive's quiet period in seconds (the controller is given the run's: the tests make it shorter, or 0 for none)
    radios_unread = False                    # the radios could not be read at the start (Controller._load_settings): none is added, nor the stations' choices of them stored, until the next start

    def __init__(self, data_dir: Path, clock: Clock = utcnow, store: Store | None = None, port: str = "", pattern: str = "", install: InstallInfo = PLAIN_INSTALL, auto_map: bool = False, encryption: bool = False,
                 hf_port: str = "", lines: Mapping[RadioId, Tnc] | None = None) -> None:
        self.data_dir = data_dir
        self.encryption = encryption                                    # the daemon was started with --encryption: encrypted messages may be sent (services/keyring.py)
        self.clock = clock
        self.config: Config = replace(DEFAULTS, radios=())              # the settings, with no radio (a new installation has none); the controller reads them from the database at its start
        self.config_lock = asyncio.Lock()                               # held while the settings are stored and put in force (Controller.save_config, change_config): a change is made of the settings as they are then
        self.port_override = port                                       # a serial port for this run only (--port): the FM radio's, used instead of serial/port, never stored
        self.hf_port_override = hf_port                                 # the HF radio's for this run only (--hf-port): a Mercury that something else runs (the benches), instead of the one the daemon starts
        self.pattern_override = pattern                                 # the globs the search listens to for this run only, instead of serial/pattern (the tests: a folder of their own)
        self.store = store if store is not None else Store(clock)       # the one database: everything is kept in it
        self.lines = dict(lines or {})                                  # a line a test hands in for the radio of that id (its driver gives it the settings when it is started); every other radio's driver makes its own
        claims = Claims()                                               # the station's one table of resources (the registry's): what each radio and the GPS receiver hold
        self.suggested_frequencies = [Frequency(band, dial) for band, dial in SUGGESTED]      # the dials the project suggests, the station's (neoaprs/wiring.py puts the project's list here and on every modem)
        interlock = Interlock(lambda: self.config)                     # the transmit interlock: nothing goes out under no call, or one that is not a call (config.can_transmit)
        self.stationbook = StationBook(clock, carries_path=lambda radio: carries_path(self.config.radios, radio))      # who was heard, where, and on which radio; the routes of the radios that may carry a path are the station's as a whole
        self.radio_packet: Signal[[Packet]] = Signal("radio.packet")    # every packet of every radio, in and out, stamped with its radio: what the parts take (neoaprs/wiring.py connects each radio's line to it)
        self.radio_changed: Signal[[RadioId]] = Signal("radio.changed")       # a radio's state, lines, counters or modem changed: its id
        kept = Remembered(self.store)                                    # (the operator's radio by station, in a state row: neoaprs/radioregistry.py)
        self.radios: RadioRegistry[Beacon] = RadioRegistry(claims, lambda spec: self._make_driver(spec, interlock), self._make_beacon, lambda: self.config, self.stationbook,
                                                           lambda text: None if self.radios_unread else kept.put({MESSAGE_RADIOS: text}), kept.flush,
                                                           clock=clock, run=lambda: self.run)       # the radios of the settings, any number: each with its driver, its line and its beacon, one lifecycle for all, and the choice between them (the main radio, by station, by packet)
        self._make_radio_parts(clock)
        self._make_logs(clock)
        self.aprsis = AprsIs(clock)                                      # the connection to an APRS-IS server: it writes the lines it is given and reads the packets of the internet, which wiring.py hands to `hear_internet`; configured and started by the iGate
        self.igate = Igate(self.aprsis, lambda: self.config, self.beacon_frames.position_info, lambda: self.stationbook.me_position, clock)       # the iGate (igate/enabled): what the radio hears is put on APRS-IS (with a passcode), the stations of the internet round us are read; nothing of APRS-IS goes to the radio, which this service does not have; started by the controller after the beacon; made before the queries, which answer ?IGATE? while it gates
        self._make_messaging(clock)
        self._make_map_and_update(data_dir, install, auto_map, clock)
        self.digipeater = Digipeater(self.radios, lambda: self.config, clock)     # the fill-in digipeater (digi/enabled): a packet that asks for WIDE1-1 or for our call is sent again on the radio that heard it, where that radio's type may repeat and its own digipeater is on (services/digipeater.py `digi_rows`); each radio's own duplicates, burst and counts; nothing to start
        self.internet_packet: Signal[[Packet]] = Signal("internet.packet")   # a packet received from APRS-IS (Packet.via `is`): the packet log, the station book and the weather log take it, the page's topics follow it, nothing else (neoaprs/wiring.py)
        self.igate.made_up = lambda: any(radio.line.is_dummy for radio in self.radios.enabled())       # (a Dummy radio that is on makes up its traffic: neither it nor our position goes to APRS-IS)
        self.config_changed: Signal[[Config]] = Signal("config_changed")   # every save of the settings, though nothing differs: the page's settings form waits for it
        self.web: Frontend | None = None                                # the page's server, made by the controller from the factory the process gave it, once the settings are read
        self.db: Db | None = None                                       # its thread, once the controller has opened it
        self.tasks = TaskSet(log)                                             # what the parts start on the loop; the controller's stop ends them
        self.running = False
        self.debug = False

    @property
    def run(self) -> RunOverrides:
        """What the process gave for this run only (neoaprs/radiodriver.py), as it is now: a test may change one between two starts of a radio."""
        return RunOverrides(self.port_override, self.pattern_override, self.hf_port_override, self.check_sec, modem_radio(self.config.radios))

    def _make_driver(self, spec: RadioSpec, interlock: Interlock) -> RadioDriver:
        """The driver of a radio's type, with the line a test handed in for the radio, else its own."""
        driver = make_driver(spec, self.radios.claims, self.clock, self.data_dir, self.lines.get(spec.id), search_lock=self.radios.search_lock)
        driver.line.where = lambda: self.config.station_position       # the Dummy radio's traffic is made round it
        driver.line.interlock = interlock
        return driver

    def _make_beacon(self, radio: Radio) -> Beacon:
        """A radio's own beacon: our position packet on it, on an interval, on SmartBeaconing for a moving station where the radio's kind allows it, and on request, by the rules of its type (the one beacon interval,
        raised to the radio's own floor, 30 minutes on an HF radio; on HF the random pause), while the radio's Send on is ticked (neoaprs/beaconrule.py); started by the controller while its radio is on. Its last send is kept in the radio's own row
        (services/beacon.py memory_key_of: `radio/<id>/beacon_last_sent_at`), and its frames are the station's one maker's."""
        return Beacon(radio, lambda: self.config, self.clock, memory=self.store, frames=self.beacon_frames)

    def moving_beacon(self) -> Beacon | None:
        """The beacon a moving station's SmartBeaconing is read from (the page's GPS topic, the support report): that of the first radio the beacon goes out on whose type has SmartBeaconing; None while there is none."""
        return next((radio.beacon for radio in self.radios.beaconing() if radio.allowed.smart_beacon), None)

    def position_frame(self, radio: AirRadio | None = None) -> ax25.Frame:
        """Our position packet for the radio an answer goes on (the main radio when the question names none): the station's one maker's. BeaconError when there is no radio, or the settings make no frame."""
        radio = radio or self.radios.main
        if radio is None:
            raise BeaconError("there is no radio that is on")
        return self.beacon_frames.position(radio)

    def _make_radio_parts(self, clock: Clock) -> None:
        """The radios with their beacons, and what the beacons need: the GPS and the status report."""
        self.gps_feed = GpsFeed(clock)                                  # the GPS receiver: a gpsd to ask or a serial port to read; configured and started by the gps service
        self.gps = Gps(self.gps_feed, lambda: self.config, clock, claims=self.radios.claims)       # the latest GPS fix and how fresh it is, for the moving station's beacon and the page; started by the controller before the beacon
        self.beacon_frames = BeaconFrames(lambda: self.config, self.gps, clock)      # the one maker of our frames: the position, the status report and the position field for any radio (services/beaconframe.py); each radio's beacon, the status report, the queries and the iGate take theirs from it
        self.radios.sync(self.config)                                   # (no radio until the settings are read: the controller syncs again then, and a radio the database gives an id later is made new)
        self.rigstatus = RigStatus(self.radios, lambda: self.config, self.beacon_frames, clock, memory=self.store)  # our status report, from the radio or the static text, at most every status/interval_min, on the main radio; started by the controller after the beacon
        self.alerts = Alerts(lambda: self.config, clock)                # the command run for a message to us; nothing to start

    def _make_logs(self, clock: Clock) -> None:
        """The parts that keep rows in the database, and the board and the preferences kept with them."""
        self.packetlog = PacketLog(clock=clock)                         # every packet and the station cache, in the database
        self.messagelog = MessageLog(clock=clock)                       # every message we sent and every one sent to us, in the database
        self.prefbook = PrefBook(self.messagelog, lambda: self.config, self._deliveries, clock, paths=self.messagelog)  # the path, the timeout and RF only of each station, kept with the messages; read by the controller before messaging starts
        self.keyring = Keyring(self.data_dir, self.messagelog, clock, allowed=self.encryption)      # the keys of encrypted messages: ours in the data folder, the stations' with the messages; read by the controller before messaging starts
        self.weatherlog = WeatherLog(clock=clock)                       # every observation of the weather stations, in the database
        self.bulletinlog = BulletinLog(clock=clock)                     # the message board in the database
        self.bulletins = Bulletins(self.bulletinlog, clock)             # bulletins, announcements and group messages, one for each sender and slot; they stay until deleted; started by the controller before the Tnc
        self.ownlog = OwnLog(clock=clock)                               # the objects, items and bulletins of our own, in the database
        self.stationalerts = StationAlerts(self.stationbook, self.prefbook, lambda: self.config, clock)       # the alerts set on stations, watched as the book changes; read by the controller after the preferences

    def _make_messaging(self, clock: Clock) -> None:
        """What sends by a schedule, the QRU parts, messaging and the answers to queries."""
        self.sender = Sender(self.radios, lambda: self.config, clock)   # our frames that go out by a schedule: one at a time, by the interlock and the state of the radio each goes on (the main radio for a bulletin)
        self.ownobjects = OwnObjects(self.sender, lambda: self.config, self.ownlog, self._is_station, clock)       # the objects and items of ours, on the decay schedule of the specification; started by the controller after the beacon
        self.ownbulletins = OwnBulletins(self.sender, lambda: self.config, self.ownlog, clock)       # the bulletins and announcements of ours, on their schedule; started by the controller after the beacon
        answer_budget = AnswerBudget(clock)                             # the frames of answers of the minute: one for the QRU server and the queries, so that it is the station's as a whole
        self.qru = Qru(self.radios, lambda: self.config, self.ownobjects, self.stationbook, self.prefbook.path_for, clock, budget=answer_budget)       # the QRU server: our objects of a group, sent to the station that asks QRU for the group; messaging hands it the messages to QRU
        self.qruask = QruAsk(self.radios, lambda: self.config, self.prefbook.path_for, clock)       # asking QRU for local info, and the servers that answered; the Tnc's packets go to it (neoaprs/wiring.py)
        self.generalask = GeneralAsk(self.radios, lambda: self.config, self.stationbook, clock)       # asking around (?APRS?, ?IGATE?, ?WX?) at the operator's request, and the stations heard after it; the Tnc's packets go to it (neoaprs/wiring.py)
        self.messaging = Messaging(self.radios, lambda: self.config, self.messagelog, self.prefbook.path_for, clock, board=self.bulletins.heard, alert=self.alerts.alert, qru=self.qru.heard, qru_answer=self.qruask.answers, keyring=self.keyring)       # messages with acks and retries, by each station's path; started by the controller after the beacon
        self.queries = Queries(self.radios, lambda: self.config, PositionFrames(self.position_frame), self.rigstatus.status_frame, self.stationbook, self.prefbook.path_for, clock, objects=self.ownobjects,
                               messages=self.messaging, heard=self.packetlog, igate=self.igate, budget=answer_budget)       # the answers to ?APRSP, ?APRSS, ?APRSD, ?APRST, ?PING?, ?APRSO, ?APRSM, ?APRSH, ?APRS? and (while the iGate gates) ?IGATE?, by the asker's path

    def _make_map_and_update(self, data_dir: Path, install: InstallInfo, auto_map: bool, clock: Clock) -> None:
        """The base map, the ALOHA circle, Find my radio and the update parts."""
        self.mapfetch = MapFetch(data_dir, lambda: self.config, clock)  # the base map: the detailed map round our position and the world map under it, made on request from the page; nothing to start
        self.mapauto = MapAuto(self.mapfetch, lambda: self.config, self.store, auto_map)    # the detailed map made once without a click, when a place is first set (only where the process asks for it: the daemon); started by the controller
        self.aloha = Aloha(self.stationbook, clock, main=lambda: self.radios.main)      # the ALOHA circle round our station, the main radio's (rule 3.8), worked out again every minute and when our position moves; started by the controller
        self.radiofinder = RadioFinder(self._radio_ports, self.hold_radio, self.release_radio, claims=self.radios.claims, search_lock=self.radios.search_lock)       # Find my radio: on the page's request only, for one radio (the one the page names, radio 1 when it names none); nothing to start
        self.install = install                                           # how this copy was installed, for the page (the steps of an update)
        self.updatecheck = UpdateCheck(lambda: self.config, VERSION, platform_name(sys.platform, platform.machine(), install.kind == "appimage"), fetch_update, memory=self.store, developer=install.kind == "source")   # once a day: which version is the latest (update/check); started by the controller
        self.frequencies = Frequencies(VERSION, platform_name(sys.platform, platform.machine(), install.kind == "appimage"), memory=self.store)       # the frequencies the project suggests: a small file asked a minute after the start and when a page shows the HF radio's box; started by the controller
        self.skeds = Skeds(VERSION, platform_name(sys.platform, platform.machine(), install.kind == "appimage"), lambda: self.config, lambda: self.suggested_frequencies, memory=self.store)       # the sked board: when people will be on the air, read from the project's server a minute after the start, every six hours and when a page shows the Skeds tab; started by the controller
        self.selfupdate = SelfUpdate(install, installer_for(install, data_dir, self.restart_into, encryption=self.encryption), self._announced, release_source(), end=self._end_for_restart, key=release_key)      # Update now: on the page's request only; nothing to start
        self.reexec: list[str] | None = None                            # the command line that is to run in the place of this process when it has ended (Update now of an AppImage)

    def hear_internet(self, packet: Packet) -> None:
        """The one way a packet received from APRS-IS enters the program (`aprsisline.parse_is_line` makes it): it is handed to `internet_packet`, a signal that no part which answers, acknowledges, repeats, sends or
        gates is connected to. Anything but an `is` packet is refused: a packet of the radio has its own signal, the Tnc's."""
        if packet.via != IS or packet.direction != "in":
            raise ValueError("only a packet received from the internet (Packet.via is) enters here")
        self.internet_packet.emit(packet)

    def forget_radio(self, id: RadioId) -> None:
        """A removed radio leaves what the parts keep of it in memory: the registry's sets, choices and paths, and the radios of every object (the removal's transaction took it out of their rows)."""
        self.radios.forget_radio(id)
        self.ownobjects.forget_radio(id)

    def _deliveries(self, call: str) -> Deliveries | None:
        """How the packets of the station reached us, for the path of a message to it (None for a station not in the book)."""
        found = self.stationbook.get(call)
        return None if found is None else found.deliveries

    async def _radio_ports(self) -> list[str]:
        """The ports Find my radio tries: those of the search for the radio, as the search has them now (what the other radios hold or are set to, the finder leaves out by the station's table)."""
        pattern = self.pattern_override or search_pattern(self.config.serial_pattern)
        return await asyncio.to_thread(candidates, pattern, self.config.serial_skip_paths)

    async def hold_radio(self, id: RadioId) -> None:
        """One radio lets go of what it holds, for a search that opens the ports (the controller also ends its start)."""
        radio = self.radios.get(id)
        if radio is not None:
            await radio.driver.stop()

    def release_radio(self, id: RadioId) -> None:
        """The radio takes what it holds again (the controller does)."""

    def repoint(self, radio: RadioId) -> None:
        """The radio's modem was started again on other ports: its line is pointed at them (the controller does)."""

    def _announced(self) -> str | None:
        latest = self.updatecheck.latest
        return latest.version if latest is not None else None

    def restart_into(self, argv: list[str]) -> None:
        """Has the process run `argv` in its place once the daemon has ended and everything is let go (neoaprs/daemon.py). Called from a thread of Update now, which ends the daemon after the page is told."""
        self.reexec = argv
        stopfile.mark_restart(self.data_dir)

    def _end_for_restart(self) -> None:
        """Ends the daemon the way `neoaprs stop` does, when Update now has a command line to run in its place."""
        if self.reexec is not None:
            stopfile.request(self.data_dir)

    def _is_station(self, name: str) -> bool:
        """Is the name that of a station of the book (a call that was heard, not an object)? An object of ours is never made under it."""
        found = self.stationbook.get(name)
        return found is not None and found.kind == "station"
