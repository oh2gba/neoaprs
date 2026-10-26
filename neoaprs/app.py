"""The composition root: the parts of the program, made in one place. The data directory, the clock, the settings (`config`), the Store, the Tnc, the station book, the GPS and its service, the beacon, the status, the message alert, messaging, the message board,
the objects and the bulletins of our own and their sender, the queries, the QRU server, the digipeater, the receive-only iGate and its connection to APRS-IS, the base map, Find my radio, the update check and Update now (the services are made here and nowhere else), the station preferences, the packet log, the message log, the bulletin log, the log of our own objects and bulletins, the weather log and the task set. The parts are made here and connected in neoaprs/wiring.py; the start and the stop are neoaprs/controller.py.
"""
import asyncio
import logging
import platform
import sys
from pathlib import Path
from typing import Protocol

from . import VERSION, stopfile
from .aprsis import AprsIs
from .bulletinlog import BulletinLog
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .db import Db
from .gpsfeed import GpsFeed
from .interlock import Interlock
from .messagelog import MessageLog
from .ownlog import OwnLog
from .packet import IS, Packet
from .packetlog import PacketLog
from .route import Deliveries
from .serialprobe import search_pattern
from .services.alerts import Alerts
from .services.aloha import Aloha
from .services.beacon import Beacon
from .services.bulletins import Bulletins
from .services.digipeater import Digipeater
from .services.gps import Gps
from .services.igate import Igate
from .services.mapauto import MapAuto
from .services.mapfetch import MapFetch
from .services.messaging import Messaging
from .services.ownbulletins import OwnBulletins
from .services.ownobjects import OwnObjects
from .services.prefbook import PrefBook
from .services.qru import Qru
from .services.qruask import QruAsk
from .services.queries import Queries
from .services.radiofinder import RadioFinder, candidates
from .services.rigstatus import RigStatus
from .services.selfinstall import installer_for, release_source
from .services.selfupdate import SelfUpdate
from .services.sender import Sender
from .services.updatecheck import UpdateCheck
from .signal import Signal
from .stationbook import StationBook
from .store import Store
from .tasks import TaskSet
from .tnc import Tnc
from .updatefetch import fetch as fetch_update
from .versions import PLAIN_INSTALL, InstallInfo, platform_name
from .weatherlog import WeatherLog

log = logging.getLogger("neoaprs.controller")


class Frontend(Protocol):
    """What the controller needs of the page's server (neoaprs/web/server.py, which this layer does not import): it is started once the radio is, and stopped before it."""
    async def start(self) -> bool: ...
    async def stop(self) -> None: ...
    def settings_changed(self, config: Config) -> None: ...


class Services:
    def __init__(self, data_dir: Path, clock: Clock = utcnow, store: Store | None = None, tnc: Tnc | None = None, port: str = "", pattern: str = "", install: InstallInfo = PLAIN_INSTALL, auto_map: bool = False) -> None:
        self.data_dir = data_dir
        self.clock = clock
        self.config: Config = DEFAULTS                                  # the settings; the controller reads them from the database at its start
        self.config_lock = asyncio.Lock()                               # held while the settings are stored and put in force (Controller.save_config, change_config): a change is made of the settings as they are then
        self.port_override = port                                       # a serial port for this run only (--port): used instead of serial/port, never stored
        self.pattern_override = pattern                                 # the globs the search listens to for this run only, instead of serial/pattern (the tests: a folder of their own)
        self.store = store if store is not None else Store(clock)       # the one database: everything is kept in it
        self.tnc = tnc if tnc is not None else Tnc(clock=clock)         # the radio; its port and speed are set from the config when it is started
        self.tnc.where = lambda: self.config.station_position          # the Dummy radio's traffic is made round it
        self.tnc.interlock = Interlock(lambda: self.config)            # the transmit interlock: nothing goes out under no call, or one that is not a call (config.can_transmit)
        self._make_radio_parts(clock)
        self._make_logs(clock)
        self._make_messaging(clock)
        self._make_map_and_update(data_dir, install, auto_map, clock)
        self.digipeater = Digipeater(self.tnc, lambda: self.config, clock, self.tnc.stats)     # the fill-in digipeater (digi/enabled): a packet that asks for WIDE1-1 or for our call is sent again; nothing to start
        self.internet_packet: Signal[[Packet]] = Signal("internet.packet")   # a packet received from APRS-IS (Packet.via `is`): the packet log, the station book and the weather log take it, the page's topics follow it, nothing else (neoaprs/wiring.py)
        self.aprsis = AprsIs(clock)                                      # the connection to an APRS-IS server: it writes the lines it is given and reads the packets of the internet, which wiring.py hands to `hear_internet`; configured and started by the iGate
        self.igate = Igate(self.aprsis, lambda: self.config, self.beacon.position_info, lambda: self.stationbook.me_position, clock)       # the iGate (igate/enabled): what the radio hears is put on APRS-IS (with a passcode), the stations of the internet round us are read; nothing of APRS-IS goes to the radio, which this service does not have; started by the controller after the beacon
        self.igate.made_up = lambda: self.tnc.is_dummy                       # (a Dummy radio makes up its traffic: neither it nor our position goes to APRS-IS)
        self.config_changed: Signal[[Config]] = Signal("config_changed")   # every save of the settings, though nothing differs: the page's settings form waits for it
        self.web: Frontend | None = None                                # the page's server, made by the controller from the factory the process gave it, once the settings are read
        self.db: Db | None = None                                       # its thread, once the controller has opened it
        self.tasks = TaskSet(log)                                             # what the parts start on the loop; the controller's stop ends them
        self.running = False
        self.debug = False

    def _make_radio_parts(self, clock: Clock) -> None:
        """The beacon and what it needs: the book of stations, the GPS and the status report."""
        self.stationbook = StationBook(clock)                           # who was heard, where
        self.gps_feed = GpsFeed(clock)                                  # the GPS receiver: a gpsd to ask or a serial port to read; configured and started by the gps service
        self.gps = Gps(self.gps_feed, lambda: self.config, clock)       # the latest GPS fix and how fresh it is, for the moving station's beacon and the page; started by the controller before the beacon
        self.beacon = Beacon(self.tnc, lambda: self.config, clock, memory=self.store, gps=self.gps)       # our position packet, on an interval, on SmartBeaconing for a moving station, and on request; started by the controller after the Tnc
        self.rigstatus = RigStatus(self.tnc, lambda: self.config, self.beacon, clock, memory=self.store)  # our status report, from the radio or the static text, at most every status/interval_min; started by the controller after the beacon
        self.alerts = Alerts(lambda: self.config, clock)                # the command run for a message to us; nothing to start

    def _make_logs(self, clock: Clock) -> None:
        """The parts that keep rows in the database, and the board and the preferences kept with them."""
        self.packetlog = PacketLog(clock=clock)                         # every packet and the station cache, in the database
        self.messagelog = MessageLog(clock=clock)                       # every message we sent and every one sent to us, in the database
        self.prefbook = PrefBook(self.messagelog, lambda: self.config, self._deliveries, clock)  # the path, the timeout and RF only of each station, kept with the messages; read by the controller before messaging starts
        self.weatherlog = WeatherLog(clock=clock)                       # every observation of the weather stations, in the database
        self.bulletinlog = BulletinLog(clock=clock)                     # the message board in the database
        self.bulletins = Bulletins(self.bulletinlog, clock)             # bulletins, announcements and group messages, one for each sender and slot; they stay until deleted; started by the controller before the Tnc
        self.ownlog = OwnLog(clock=clock)                               # the objects, items and bulletins of our own, in the database

    def _make_messaging(self, clock: Clock) -> None:
        """What sends by a schedule, the QRU parts, messaging and the answers to queries."""
        self.sender = Sender(self.tnc, lambda: self.config, clock)      # our frames that go out by a schedule: one at a time, by the interlock and the state of the radio
        self.ownobjects = OwnObjects(self.sender, lambda: self.config, self.ownlog, self._is_station, clock)       # the objects and items of ours, on the decay schedule of the specification; started by the controller after the beacon
        self.ownbulletins = OwnBulletins(self.sender, lambda: self.config, self.ownlog, clock)       # the bulletins and announcements of ours, on their schedule; started by the controller after the beacon
        self.qru = Qru(self.tnc, lambda: self.config, self.ownobjects, self.stationbook, self.prefbook.path_for, clock)       # the QRU server: our objects of a group, sent to the station that asks QRU for the group; messaging hands it the messages to QRU
        self.qruask = QruAsk(self.tnc, lambda: self.config, self.prefbook.path_for, clock)       # asking QRU for local info, and the servers that answered; the Tnc's packets go to it (neoaprs/wiring.py)
        self.messaging = Messaging(self.tnc, lambda: self.config, self.messagelog, self.prefbook.path_for, clock, board=self.bulletins.heard, alert=self.alerts.alert, qru=self.qru.heard, qru_answer=self.qruask.answers)       # messages with acks and retries, by each station's path; started by the controller after the beacon
        self.queries = Queries(self.tnc, lambda: self.config, self.beacon, self.rigstatus.status_frame, self.stationbook, self.prefbook.path_for, clock, objects=self.ownobjects,
                               messages=self.messaging, heard=self.packetlog)       # the answers to ?APRSP, ?APRSS, ?APRSD, ?APRST, ?PING?, ?APRSO, ?APRSM, ?APRSH and ?APRS?, by the asker's path

    def _make_map_and_update(self, data_dir: Path, install: InstallInfo, auto_map: bool, clock: Clock) -> None:
        """The base map, the ALOHA circle, Find my radio and the update parts."""
        self.mapfetch = MapFetch(data_dir, lambda: self.config, clock)  # the base map: the detailed map round our position and the world map under it, made on request from the page; nothing to start
        self.mapauto = MapAuto(self.mapfetch, lambda: self.config, self.store, auto_map)    # the detailed map made once without a click, when a place is first set (only where the process asks for it: the daemon); started by the controller
        self.aloha = Aloha(self.stationbook, clock)                      # the ALOHA circle round our station, worked out again every minute and when our position moves; started by the controller
        self.radiofinder = RadioFinder(self._radio_ports, self.hold_tnc, self.release_tnc)       # Find my radio: on the page's request only; nothing to start
        self.install = install                                           # how this copy was installed, for the page (the steps of an update)
        self.updatecheck = UpdateCheck(lambda: self.config, VERSION, platform_name(sys.platform, platform.machine(), install.kind == "appimage"), fetch_update, memory=self.store)   # once a day: which version is the latest (update/check); started by the controller
        self.selfupdate = SelfUpdate(install, installer_for(install, data_dir, self.restart_into), self._announced, release_source(), end=self._end_for_restart)      # Update now: on the page's request only; nothing to start
        self.reexec: list[str] | None = None                            # the command line that is to run in the place of this process when it has ended (Update now of an AppImage)

    def hear_internet(self, packet: Packet) -> None:
        """The one way a packet received from APRS-IS enters the program (`aprsisline.parse_is_line` makes it): it is handed to `internet_packet`, a signal that no part which answers, acknowledges, repeats, sends or
        gates is connected to. Anything but an `is` packet is refused: a packet of the radio has its own signal, the Tnc's."""
        if packet.via != IS or packet.direction != "in":
            raise ValueError("only a packet received from the internet (Packet.via is) enters here")
        self.internet_packet.emit(packet)

    def _deliveries(self, call: str) -> Deliveries | None:
        """How the packets of the station reached us, for the path of a message to it (None for a station not in the book)."""
        found = self.stationbook.get(call)
        return None if found is None else found.deliveries

    async def _radio_ports(self) -> list[str]:
        """The ports Find my radio tries: those of the search for the radio, as the search has them now."""
        pattern = self.pattern_override or search_pattern(self.config.serial_pattern)
        return await asyncio.to_thread(candidates, pattern, self.config.serial_skip_paths)

    async def hold_tnc(self) -> None:
        """The radio lets go of its line, for a search that opens the ports."""
        await self.tnc.stop()

    def release_tnc(self) -> None:
        """The radio takes its line again (the controller does)."""

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
