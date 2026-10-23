"""The composition root: the parts of the program, made in one place. The data directory, the clock, the settings (`config`), the Store, the Tnc, the station book, the beacon, the status, the message alert, messaging, the message board,
the queries and the base map (the services are made here and nowhere else), the station preferences, the packet log, the message log, the bulletin log, the weather log and the task set. The parts are made here and connected in neoaprs/wiring.py; the start and the stop are neoaprs/controller.py.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Protocol

from .bulletinlog import BulletinLog
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .db import Db
from .interlock import Interlock
from .messagelog import MessageLog
from .packetlog import PacketLog
from .services.alerts import Alerts
from .services.beacon import Beacon
from .services.bulletins import Bulletins
from .services.mapfetch import MapFetch
from .services.messaging import Messaging
from .services.prefbook import PrefBook
from .services.queries import Queries
from .services.rigstatus import RigStatus
from .signal import Signal
from .stationbook import StationBook
from .store import Store
from .tasks import TaskSet
from .tnc import Tnc
from .weatherlog import WeatherLog

log = logging.getLogger("neoaprs.controller")


class Frontend(Protocol):
    """What the controller needs of the page's server (neoaprs/web/server.py, which this layer does not import): it is started once the radio is, and stopped before it."""
    async def start(self) -> bool: ...
    async def stop(self) -> None: ...
    def settings_changed(self, config: Config) -> None: ...


class Services:
    def __init__(self, data_dir: Path, clock: Clock = utcnow, store: Store | None = None, tnc: Tnc | None = None, port: str = "", pattern: str = "") -> None:
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
        self.prefbook = PrefBook(self.messagelog, lambda: self.config)  # the path, the timeout and the attempts of each station, kept with the messages; read by the controller before messaging starts
        self.weatherlog = WeatherLog(clock=clock)                       # every observation of the weather stations, in the database
        self.bulletinlog = BulletinLog(clock=clock)                     # the message board in the database
        self.bulletins = Bulletins(self.bulletinlog, clock)             # bulletins, announcements and group messages, one for each sender and slot; they stay until deleted; started by the controller before the Tnc
        self.messaging = Messaging(self.tnc, lambda: self.config, self.messagelog, self.prefbook.path_for, clock, board=self.bulletins.heard, alert=self.alerts.alert, attempts=self.prefbook.attempts_for)       # messages with acks and retries, by each station's path; started by the controller after the beacon
        self.queries = Queries(self.tnc, lambda: self.config, self.beacon, self.rigstatus.status_frame, self.stationbook, self.prefbook.path_for, clock)       # the answers to ?APRSP, ?APRSS, ?APRSD, ?APRST, ?PING? and ?APRS?, by the asker's path
        self.mapfetch = MapFetch(data_dir, lambda: self.config, clock)  # the base map: the detailed map round our position and the world map under it, made on request from the page; nothing to start
        self.config_changed: Signal[[Config]] = Signal("config_changed")   # every save of the settings, though nothing differs: the page's settings form waits for it
        self.web: Frontend | None = None                                # the page's server, made by the controller from the factory the process gave it, once the settings are read
        self.db: Db | None = None                                       # its thread, once the controller has opened it
        self.tasks = TaskSet(self._task_failed)                         # what the parts start on the loop; the controller's stop ends them
        self.running = False
        self.debug = False

    def _task_failed(self, task: "asyncio.Task[Any]") -> None:
        log.error("task %s failed: %r", task.get_name(), task.exception())
