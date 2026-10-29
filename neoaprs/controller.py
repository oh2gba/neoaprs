"""The program without a window: the database, the settings, the radio and the station book. The Controller is the composition root's object (docs/ARCHITECTURE.md): the parts are made in
neoaprs/app.py (`Services`) and connected in neoaprs/wiring.py, and this class brings them up and takes them down. The page and the tests call a part as `ctl.<part>.<method>`; the Controller has
the order of the start (the message board, the GPS and the beacon, our objects and bulletins, the status and messaging, then the Tnc, whose packets those take, and the page; the stop takes the page and the Tnc first, then the parts, one failing to stop not keeping the others from it), the Tnc's restart when its settings change, and the daily care of the database.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from . import wiring
from .app import Frontend, Services
from .clock import Clock, days, utcnow
from .config import DEFAULTS, Config
from .policy import LOG_KEEP_DAYS, TNC_CHECK_SEC
from .db import Db
from .dbfile import DEFAULT_BUSY_MS
from .dbopen import open_connection
from .store import DB_NAME, Store
from .tasks import cancel_all, every
from .tnc import Tnc
from .versions import PLAIN_INSTALL, InstallInfo

log = logging.getLogger("neoaprs.controller")

PRUNE_EVERY_SEC = 24 * 3600.0
RECOUNT_EVERY_SEC = 60.0                # the station book's hour of packets moves on a minute at a time

WebFactory = Callable[["Controller", Config], Frontend]
"""How the process says what its page's server is: neoaprs.web.server.WebServer. The controller makes it from the settings and the process, which is the delivery layer, is the one that names it."""


class Controller(Services):
    def __init__(self, data_directory: str | Path, clock: Clock = utcnow, store: Store | None = None, busy_ms: int = DEFAULT_BUSY_MS, tnc: Tnc | None = None, port: str = "", web: WebFactory | None = None, pattern: str = "", install: InstallInfo = PLAIN_INSTALL, check_sec: float = TNC_CHECK_SEC, auto_map: bool = False) -> None:
        super().__init__(Path(data_directory), clock, store, tnc, port, pattern, install, auto_map)
        self._web_factory = web
        self.check_sec = check_sec              # the keep-alive's quiet period in seconds (TNC_CHECK_SEC; the tests make it shorter, or 0 for none)
        self.busy_ms = busy_ms                  # how long the thread's connection waits for another writer: the daemon asks for a few seconds
        self._tnc_task: asyncio.Task[None] | None = None
        self._implied: set[str] = set()         # the settings that a row of an older version implies (configlegacy.py), stored at the first save
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
        rows = await self.store.settings()
        self.config = Config.from_data(rows)
        defaults = DEFAULTS.to_data()
        self._implied = {key for key, text in self.config.to_data().items() if key not in rows and text != defaults[key]}
        await wiring.seed_station_book(self)
        self._configure_tnc()                                           # (what the parts ask of the Tnc, such as whether it is the Dummy radio, is true before they start; the radio itself is started last)
        self.running = True
        await self.bulletins.start()
        await self.gps.start()
        await self.beacon.start()
        await self.igate.start()
        await self.ownobjects.start()
        await self.ownbulletins.start()
        await self.rigstatus.start()
        await self.prefbook.load()
        self.stationalerts.load()                                       # (after the preferences and the station book: the stations as they are now are where the alerts start)
        await self.aloha.start()
        await self.messaging.start()
        self.start_tnc()                                                # (last of the parts that take its packets: the source after its consumers)
        await self._start_web()
        await self.mapauto.start()
        await self.updatecheck.start()
        self.tasks.spawn(self._prune_daily(), "prune")
        self.tasks.spawn(self._recount_minutely(), "recount")

    async def stop(self) -> None:
        self.running = False
        try:
            for name, stop in self._stops():
                try:
                    await stop()
                except Exception:
                    log.exception("%s could not be stopped", name)        # (the parts after it are stopped all the same)
        finally:
            if self.db is not None:
                await self.db.close()                           # what was asked of the database thread is done, then its connection is closed

    def _stops(self) -> list[tuple[str, Callable[[], Awaitable[None]]]]:
        """What the stop ends and in which order: the page, Find my radio and the Tnc first (the source of the packets, so that no packet comes to a part that is stopped), then the parts that take its packets, the
        others, and last the Controller's own tasks."""
        return [("the page", self._stop_web), ("Find my radio", self.radiofinder.stop), ("the Tnc", self._stop_tnc), ("the update check", self.updatecheck.stop), ("the ALOHA circle", self.aloha.stop),
                ("Update now", self.selfupdate.stop), ("the automatic map", self.mapauto.stop), ("the map job", self.mapfetch.stop), ("the queries", self.queries.stop), ("the QRU server", self.qru.stop),
                ("asking QRU", self.qruask.stop), ("messaging", self.messaging.stop), ("the alerts", self.alerts.stop), ("the status", self.rigstatus.stop), ("the bulletins of ours", self.ownbulletins.stop),
                ("the objects of ours", self.ownobjects.stop), ("the iGate", self.igate.stop), ("the beacon", self.beacon.stop), ("the GPS", self.gps.stop), ("the tasks", self.tasks.cancel_all)]

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
        self._configure_tnc()
        await self.tnc.start()

    def _configure_tnc(self) -> None:
        """The Tnc, which is stopped, takes the settings as they are now."""
        wiring.apply_tnc_settings(self.tnc, wiring.tnc_settings(self.config, self.port_override, self.pattern_override))
        self.tnc.set_check(self.check_sec)

    async def hold_tnc(self) -> None:
        await self._stop_tnc()

    def release_tnc(self) -> None:
        if self.running:
            self.start_tnc()

    async def _stop_tnc(self) -> None:
        task, self._tnc_task = self._tnc_task, None
        if task is not None:
            await cancel_all([task])
        await self.tnc.stop()

    # ---- the settings
    async def save_config(self, config: Config) -> bool:
        """Stores the settings that differ from the ones in force, puts them all in force, and restarts the Tnc when the port, the speed or entering KISS changed. False when the
        database would not take them (nothing changed). The settings are a whole: a change made of the settings in force goes through `change_config`, so that two that overlap keep each other's keys."""
        async with self.config_lock:
            return await self._save(config)

    async def change_config(self, change: Callable[[Config], Config]) -> bool:
        """Stores the settings that `change` makes of the ones in force, read under the lock, and puts them in force as save_config does; what `change` raises (a SettingError) is raised, and nothing is stored."""
        async with self.config_lock:
            return await self._save(change(self.config))

    async def _save(self, config: Config) -> bool:
        stored = set(self.config.changed(config)) | self._implied
        if not await self.store.put_settings({key: text for key, text in config.to_data().items() if key in stored}):        # (only what this save changes: a key written by `neoaprs db set` in the meantime stays)
            return False
        self._implied = set()
        before = wiring.tnc_settings(self.config, self.port_override, self.pattern_override)
        previous, self.config = self.config, config
        wiring.place_me(self)
        self.gps.settings_changed()
        self.beacon.settings_changed()
        self.igate.settings_changed()
        if wiring.tnc_settings(config, self.port_override, self.pattern_override) != before:
            self.start_tnc()
        self.config_changed.emit(config)
        self.mapauto.settings_changed(previous)
        if self.web is not None:
            self.web.settings_changed(config)
        return True

    # ---- the care of the database
    async def prune(self) -> tuple[int, list[str]]:
        """Removes the packets and the stations not heard for 7 days (and the weather observations that old); how many packets, and which stations. The messages and the bulletins stay: the operator deletes those."""
        keep = LOG_KEEP_DAYS
        packets = await self.packetlog.prune(keep)
        self.messaging.forget_heard(keep)
        await self.weatherlog.prune(keep)
        stations = self.stationbook.prune(self.clock() - days(keep))
        if packets or stations:
            log.info("pruned %d packets and %d stations older than %d days", packets, len(stations), keep)
        return packets, stations

    async def forget_stations(self) -> int:
        """A fresh start for what was heard: every station but ours is forgotten with its packets, its weather and its telemetry definitions; how many stations. The station we are, the objects and bulletins we send,
        the messages, the preferences of the stations and the settings stay (so does every packet we sent). The book is cleared and the database asked in one step, so that a packet heard meanwhile is kept with its station."""
        me = self.stationbook.me
        count = self.stationbook.forget_all()
        await self.packetlog.forget_heard("" if me is None else me.call)
        await self.weatherlog.forget_all()
        self.aloha.refresh()
        log.info("forgot %d stations with the packets heard", count)
        return count

    async def _prune_daily(self) -> None:
        await every(PRUNE_EVERY_SEC, self.prune, "the daily care of the database", at_start=True)

    async def _recount_minutely(self) -> None:
        await every(RECOUNT_EVERY_SEC, self.stationbook.recount, "the recount of the station book")
