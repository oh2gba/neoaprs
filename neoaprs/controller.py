"""The program without a window: the database, the settings, the radio and the station book. The Controller is the composition root's object (docs/ARCHITECTURE.md): the parts are made in
neoaprs/app.py (`Services`) and connected in neoaprs/wiring.py, and this class brings them up and takes them down. The page and the tests call a part as `ctl.<part>.<method>`; the Controller has
the order of the start (the message board before the Tnc, the beacon, our objects and bulletins, the status and messaging after it, before the page; the stop the other way round), the Tnc's restart when its settings change, and the daily care of the database.
"""
import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from . import wiring
from .app import Frontend, Services
from .clock import Clock, days, utcnow
from .config import Config
from .policy import LOG_KEEP_DAYS, TNC_CHECK_SEC
from .db import Db
from .dbfile import DEFAULT_BUSY_MS
from .dbopen import open_connection
from .store import DB_NAME, Store
from .tasks import cancel_all
from .tnc import Tnc
from .versions import PLAIN_INSTALL, InstallInfo

log = logging.getLogger("neoaprs.controller")

PRUNE_EVERY_SEC = 24 * 3600.0

WebFactory = Callable[["Controller", Config], Frontend]
"""How the process says what its page's server is: neoaprs.web.server.WebServer. The controller makes it from the settings and the process, which is the delivery layer, is the one that names it."""


class Controller(Services):
    def __init__(self, data_directory: str | Path, clock: Clock = utcnow, store: Store | None = None, busy_ms: int = DEFAULT_BUSY_MS, tnc: Tnc | None = None, port: str = "", web: WebFactory | None = None, pattern: str = "", install: InstallInfo = PLAIN_INSTALL, check_sec: float = TNC_CHECK_SEC) -> None:
        super().__init__(Path(data_directory), clock, store, tnc, port, pattern, install)
        self._web_factory = web
        self.check_sec = check_sec              # the keep-alive's quiet period in seconds (TNC_CHECK_SEC; the tests make it shorter, or 0 for none)
        self.busy_ms = busy_ms                  # how long the thread's connection waits for another writer: the daemon asks for a few seconds
        self._tnc_task: asyncio.Task[None] | None = None
        wiring.wire(self)

    async def open_database(self) -> None:
        """The one database in the data directory, migrated and open on its thread; the Store and the packet log run on it. Raises StoreError (or an sqlite3 error) when the file cannot be
        used: a file of a newer version, a folder that cannot be written, a file that is not a database."""
        if self.db is not None:
            return
        path = self.data_dir / DB_NAME
        db = Db(lambda: open_connection(path, self.busy_ms, self.clock))
        await db.start()
        self.db = db
        self.store.use(db, path)
        self.packetlog.use(db)
        self.messagelog.use(db)
        self.bulletinlog.use(db)
        self.ownlog.use(db)
        self.weatherlog.use(db)
        log.debug("the database %s is open (busy time %d ms)", path, self.busy_ms)

    async def start(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self.open_database()
        self.config = Config.from_data(await self.store.settings())
        await wiring.seed_station_book(self)
        self.running = True
        await self.bulletins.start()
        self.start_tnc()
        await self.beacon.start()
        await self.ownobjects.start()
        await self.ownbulletins.start()
        await self.rigstatus.start()
        await self.prefbook.load()
        await self.aloha.start()
        await self.messaging.start()
        await self._start_web()
        await self.updatecheck.start()
        self.tasks.spawn(self._prune_daily(), "prune")

    async def stop(self) -> None:
        self.running = False
        try:
            await self._stop_web()
            await self.updatecheck.stop()
            await self.aloha.stop()
            await self.selfupdate.stop()
            await self.mapfetch.stop()
            await self.queries.stop()
            await self.messaging.stop()
            await self.alerts.stop()
            await self.rigstatus.stop()
            await self.ownbulletins.stop()
            await self.ownobjects.stop()
            await self.beacon.stop()
            await self._stop_tnc()
            await self.tasks.cancel_all()
        finally:
            if self.db is not None:
                await self.db.close()                           # what was asked of the database thread is done, then its connection is closed

    # ---- the page
    async def _start_web(self) -> None:
        """The page's server, when the process has one. One that cannot listen (the port is in use) says so in the log and the daemon goes on without the page."""
        if self._web_factory is None or self.web is not None:
            return
        web = self._web_factory(self, self.config)
        if await web.start():
            self.web = web

    async def _stop_web(self) -> None:
        web, self.web = self.web, None
        if web is not None:
            await web.stop()

    # ---- the radio
    def start_tnc(self) -> None:
        """(Re)starts the Tnc with the settings as they are now, in a task: finding the port can take as long as 20 s a port, and nothing waits for it. A start that is still looking for the
        port is ended first."""
        self._tnc_task = self.tasks.spawn(self._restart_tnc(self._tnc_task), "tnc")

    async def _restart_tnc(self, previous: "asyncio.Task[None] | None") -> None:
        if previous is not None:
            await cancel_all([previous])
        await self.tnc.stop()
        wiring.apply_tnc_settings(self.tnc, wiring.tnc_settings(self.config, self.port_override, self.pattern_override))
        self.tnc.set_check(self.check_sec)
        await self.tnc.start()

    async def _stop_tnc(self) -> None:
        task, self._tnc_task = self._tnc_task, None
        if task is not None:
            await cancel_all([task])
        await self.tnc.stop()

    # ---- the settings
    async def save_config(self, config: Config) -> bool:
        """Stores every setting, puts them in force, and restarts the Tnc when the port, the speed or entering KISS changed. False when the
        database would not take them (nothing changed)."""
        if not await self.store.put_settings(config.to_data()):
            return False
        before = wiring.tnc_settings(self.config, self.port_override, self.pattern_override)
        self.config = config
        wiring.place_me(self)
        self.beacon.settings_changed()
        if wiring.tnc_settings(config, self.port_override, self.pattern_override) != before:
            self.start_tnc()
        self.config_changed.emit(config)
        if self.web is not None:
            self.web.settings_changed(config)
        return True

    # ---- the care of the database
    async def prune(self) -> tuple[int, list[str]]:
        """Removes the packets and the stations not heard for 7 days (and the weather observations that old); how many packets, and which stations. The messages and the bulletins stay: the operator deletes those. A station the operator gave a timeout of 0 (never) is kept in
        the station book however long ago it was heard; its packets are pruned like the others."""
        keep = LOG_KEEP_DAYS
        packets = await self.packetlog.prune(keep)
        self.messaging.forget_heard(keep)
        await self.weatherlog.prune(keep)
        stations = self.stationbook.prune(self.clock() - days(keep), self.prefbook.never_hidden())
        if packets or stations:
            log.info("pruned %d packets and %d stations older than %d days", packets, len(stations), keep)
        return packets, stations

    async def _prune_daily(self) -> None:
        while True:
            await self.prune()
            await asyncio.sleep(PRUNE_EVERY_SEC)
