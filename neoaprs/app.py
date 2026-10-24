"""The composition root: the parts of the program, made in one place. The data directory, the clock, the settings (`config`), the Store, the Tnc, the station book, the beacon, the status, the message alert, messaging, the message board,
the objects and the bulletins of our own and their sender, the queries, the digipeater, the base map, the update check and Update now (the services are made here and nowhere else), the station preferences, the packet log, the message log, the bulletin log, the log of our own objects and bulletins, the weather log and the task set. The parts are made here and connected in neoaprs/wiring.py; the start and the stop are neoaprs/controller.py.
"""
import logging
import platform
import sys
from pathlib import Path
from typing import Protocol

from . import VERSION, stopfile
from .bulletinlog import BulletinLog
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .db import Db
from .interlock import Interlock
from .messagelog import MessageLog
from .ownlog import OwnLog
from .packetlog import PacketLog
from .services.alerts import Alerts
from .services.beacon import Beacon
from .services.bulletins import Bulletins
from .services.digipeater import Digipeater
from .services.mapfetch import MapFetch
from .services.messaging import Messaging
from .services.ownbulletins import OwnBulletins
from .services.ownobjects import OwnObjects
from .services.prefbook import PrefBook
from .services.queries import Queries
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
    def __init__(self, data_dir: Path, clock: Clock = utcnow, store: Store | None = None, tnc: Tnc | None = None, port: str = "", pattern: str = "", install: InstallInfo = PLAIN_INSTALL) -> None:
        self.data_dir = data_dir
        self.clock = clock
        self.config: Config = DEFAULTS                                  # the settings; the controller reads them from the database at its start
        self.port_override = port                                       # a serial port for this run only (--port): used instead of serial/port, never stored
        self.pattern_override = pattern                                 # the globs the search listens to for this run only, instead of serial/pattern (the tests: a folder of their own)
        self.store = store if store is not None else Store(clock)       # the one database: everything is kept in it
        self.tnc = tnc if tnc is not None else Tnc(clock=clock)         # the radio; its port and speed are set from the config when it is started
        self.tnc.interlock = Interlock(lambda: self.config)            # the transmit interlock: nothing goes out under no call, or one that is not a call (config.can_transmit)
        self.stationbook = StationBook(clock)                           # who was heard, where
        self.beacon = Beacon(self.tnc, lambda: self.config, clock, memory=self.store)       # our position packet, on an interval and on request; started by the controller after the Tnc
        self.rigstatus = RigStatus(self.tnc, lambda: self.config, self.beacon, clock, memory=self.store)  # our status report, from the radio or the static text, at most every status/interval_min; started by the controller after the beacon
        self.alerts = Alerts(lambda: self.config, clock)                # the command run for a message to us; nothing to start
        self.packetlog = PacketLog(clock=clock)                         # every packet and the station cache, in the database
        self.messagelog = MessageLog(clock=clock)                       # every message we sent and every one sent to us, in the database
        self.prefbook = PrefBook(self.messagelog, lambda: self.config)  # the path, the timeout and RF only of each station, kept with the messages; read by the controller before messaging starts
        self.weatherlog = WeatherLog(clock=clock)                       # every observation of the weather stations, in the database
        self.bulletinlog = BulletinLog(clock=clock)                     # the message board in the database
        self.bulletins = Bulletins(self.bulletinlog, clock)             # bulletins, announcements and group messages, one for each sender and slot; they stay until deleted; started by the controller before the Tnc
        self.ownlog = OwnLog(clock=clock)                               # the objects, items and bulletins of our own, in the database
        self.sender = Sender(self.tnc, lambda: self.config, clock)      # our frames that go out by a schedule: one at a time, by the interlock and the state of the radio
        self.ownobjects = OwnObjects(self.sender, lambda: self.config, self.ownlog, self._is_station, clock)       # the objects and items of ours, on the decay schedule of the specification; started by the controller after the beacon
        self.ownbulletins = OwnBulletins(self.sender, lambda: self.config, self.ownlog, clock)       # the bulletins and announcements of ours, on their schedule; started by the controller after the beacon
        self.messaging = Messaging(self.tnc, lambda: self.config, self.messagelog, self.prefbook.path_for, clock, board=self.bulletins.heard, alert=self.alerts.alert)       # messages with acks and retries, by each station's path; started by the controller after the beacon
        self.queries = Queries(self.tnc, lambda: self.config, self.beacon, self.rigstatus.status_frame, self.stationbook, self.prefbook.path_for, clock)       # the answers to ?APRSP, ?APRSS, ?APRSD, ?APRST, ?PING? and ?APRS?, by the asker's path
        self.mapfetch = MapFetch(data_dir, lambda: self.config, clock)  # the base map: the detailed map round our position and the world map under it, made on request from the page; nothing to start
        self.install = install                                           # how this copy was installed, for the page (the steps of an update)
        self.updatecheck = UpdateCheck(lambda: self.config, VERSION, platform_name(sys.platform, platform.machine(), install.kind == "appimage"), fetch_update)   # once a day: which version is the latest (update/check); started by the controller
        self.selfupdate = SelfUpdate(install, installer_for(install, data_dir, self.restart_into), self._announced, release_source())      # Update now: on the page's request only; nothing to start
        self.reexec: list[str] | None = None                            # the command line that is to run in the place of this process when it has ended (Update now of an AppImage)
        self.digipeater = Digipeater(self.tnc, lambda: self.config, clock, self.tnc.stats)     # the fill-in digipeater (digi/enabled): a packet that asks for WIDE1-1 or for our call is sent again; nothing to start
        self.config_changed: Signal[[Config]] = Signal("config_changed")   # every save of the settings, though nothing differs: the page's settings form waits for it
        self.web: Frontend | None = None                                # the page's server, made by the controller from the factory the process gave it, once the settings are read
        self.db: Db | None = None                                       # its thread, once the controller has opened it
        self.tasks = TaskSet(log)                                             # what the parts start on the loop; the controller's stop ends them
        self.running = False
        self.debug = False

    def _announced(self) -> str | None:
        latest = self.updatecheck.latest
        return latest.version if latest is not None else None

    def restart_into(self, argv: list[str]) -> None:
        """Ends the daemon the way `neoaprs stop` does, and has the process run `argv` in its place once everything is let go (neoaprs/daemon.py). Called from a thread of Update now."""
        self.reexec = argv
        stopfile.mark_restart(self.data_dir)
        stopfile.request(self.data_dir)

    def _is_station(self, name: str) -> bool:
        """Is the name that of a station of the book (a call that was heard, not an object)? An object of ours is never made under it."""
        found = self.stationbook.get(name)
        return found is not None and found.kind == "station"
