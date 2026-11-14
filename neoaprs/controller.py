"""The program without a window: the database, the settings, the radio and the station book. The Controller is the composition root's object (docs/ARCHITECTURE.md): the parts are made in
neoaprs/app.py (`Services`) and connected in neoaprs/wiring.py, and this class brings them up and takes them down. The page and the tests call a part as `ctl.<part>.<method>`; the Controller has
the order of the start (the message board, the GPS and the beacons, our objects and bulletins, the status and messaging, then the radios, whose packets those take, and the page; the stop takes the page and the radios first, then the parts, one failing to stop not keeping the others from it), the restart of a radio when its settings change, and the care of the database: the daily prune, and the station rows written every half minute (packetlog.py says why) and at the stop.

The radios are the registry's (neoaprs/radioregistry.py), any number of them, each brought up and down by the one lifecycle of every type; this class starts each in a task of its own, so that one that is
still looking for its port keeps no other waiting, and restarts the one a save changed and no other.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from . import nodevices, wiring
from .app import Frontend, Services
from .clock import Clock, days, utcnow
from .config import DEFAULTS, Config
from .message import MessagingError
from .policy import INTERNET_KEEP_DAYS, LOG_KEEP_DAYS, TNC_CHECK_SEC
from .dummyhfscene import STATIONS as DUMMY_HF_STATIONS
from .db import Db
from .dbfile import DEFAULT_BUSY_MS
from .dbopen import open_connection
from .packetlog import STATION_FLUSH_SEC
from .radiospec import FM_ID, HF_ID, KIND_WORDS, RadioId, RadioSpec, enabled
from .radiotype import Kind
from .store import DB_NAME, Store
from .tasks import cancel_all, every
from .tnc import Tnc
from .versions import PLAIN_INSTALL, InstallInfo

log = logging.getLogger("neoaprs.controller")

PRUNE_EVERY_SEC = 24 * 3600.0
RECOUNT_EVERY_SEC = 60.0                # the station book's hour of packets moves on a minute at a time
TASK_NAMES: dict[RadioId, str] = {FM_ID: "tnc", HF_ID: "hf"}       # the task of a radio's start as the log has named it for radios 1 and 2 (another is `radio-<id>`)
BEACON_NAMES: dict[RadioId, str] = {FM_ID: "the beacon", HF_ID: "the HF beacon"}       # a radio's beacon as the stop's log has named it for radios 1 and 2
MADE_UP: dict[Kind, frozenset[str]] = {"hf": frozenset(station.call for station in DUMMY_HF_STATIONS)}       # the stations a kind's Dummy radio makes up under calls of its own (the FM Dummy's are made round the station and go with the daily prune)

WebFactory = Callable[["Controller", Config], Frontend]
"""How the process says what its page's server is: neoaprs.web.server.WebServer. The controller makes it from the settings and the process, which is the delivery layer, is the one that names it."""


class Controller(Services):
    def __init__(self, data_directory: str | Path, clock: Clock = utcnow, store: Store | None = None, busy_ms: int = DEFAULT_BUSY_MS, tnc: Tnc | None = None, port: str = "", web: WebFactory | None = None, pattern: str = "", install: InstallInfo = PLAIN_INSTALL, check_sec: float = TNC_CHECK_SEC, auto_map: bool = False, encryption: bool = False,
                 hf: Tnc | None = None, hf_port: str = "") -> None:
        super().__init__(Path(data_directory), clock, store, tnc, port, pattern, install, auto_map, encryption, hf, hf_port)
        self._web_factory = web
        self.check_sec = check_sec              # the keep-alive's quiet period in seconds (TNC_CHECK_SEC; the tests make it shorter, or 0 for none)
        self.busy_ms = busy_ms                  # how long the thread's connection waits for another writer: the daemon asks for a few seconds
        self._starts: dict[RadioId, asyncio.Task[None]] = {}    # the start of each radio (with its modem): each radio is restarted on its own
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
        nodevices.announce()                                            # (a daemon under the no-devices switch says so in its log before any part is started)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self.open_database()
        rows = await self.store.settings()
        self.config = Config.from_data(rows)
        defaults = DEFAULTS.to_data()
        self._implied = {key for key, text in self.config.to_data().items() if key not in rows and text != defaults[key]}
        await wiring.seed_station_book(self)
        self.radios.sync(self.config)                                   # (the radios of the settings that were read)
        self.radios.configure()                                         # (what the parts ask of a radio, such as whether it is a Dummy radio, is true before they start; the radios themselves are started last)
        self.running = True
        await self.bulletins.start()
        await self.gps.start()
        await self.radios.beacons_as_set()
        await self.igate.start()
        await self.ownobjects.start()
        await self.ownbulletins.start()
        await self.rigstatus.start()
        await self.prefbook.load()
        await self._load_keys()                                         # (the stations' keys, and our own when encrypted messages are allowed: before messaging opens what comes in)
        self.stationalerts.load()                                       # (after the preferences and the station book: the stations as they are now are where the alerts start)
        await self.aloha.start()
        await self.messaging.start()
        self.start_tnc()                                                # (last of the parts that take its packets: the source after its consumers)
        await self._start_web()
        await self.mapauto.start()
        for asks in (self.updatecheck, self.frequencies, self.skeds):       # (what asks the project's server: the update check, the suggested frequencies and the sked board)
            await asks.start()
        self.tasks.spawn(self._prune_daily(), "prune")
        self.tasks.spawn(self._recount_minutely(), "recount")
        self.tasks.spawn(self._flush_stations(), "station-flush")

    async def _load_keys(self) -> None:
        """The keyring's keys; a key file that cannot be made (a data folder that cannot be written) is told in the log and the daemon goes on without our key, the page showing encrypted messages off."""
        try:
            await self.keyring.load()
        except MessagingError as e:
            log.error("encrypted messages are off: %s", e)

    async def stop(self) -> None:
        self.running = False
        try:
            for name, stop in self._stops():
                try:
                    await stop()
                except Exception:
                    log.exception("%s could not be stopped", name)        # (the parts after it are stopped all the same)
        finally:
            self.packetlog.flush_stations()                     # (the station rows that changed since the last flush, before the thread closes)
            if self.db is not None:
                await self.db.close()                           # what was asked of the database thread is done, then its connection is closed

    def _stops(self) -> list[tuple[str, Callable[[], Awaitable[None]]]]:
        """What the stop ends and in which order: the page, Find my radio and the Tnc first (the source of the packets, so that no packet comes to a part that is stopped), then the parts that take its packets, the
        others, and last the Controller's own tasks."""
        return [("the page", self._stop_web), ("Find my radio", self.radiofinder.stop), ("the Tnc", self._stop_radios), ("the update check", self.updatecheck.stop), ("the suggested frequencies", self.frequencies.stop), ("the sked board", self.skeds.stop), ("the ALOHA circle", self.aloha.stop),
                ("Update now", self.selfupdate.stop), ("the automatic map", self.mapauto.stop), ("the map job", self.mapfetch.stop), ("the queries", self.queries.stop), ("the QRU server", self.qru.stop),
                ("asking QRU", self.qruask.stop), ("messaging", self.messaging.stop), ("the alerts", self.alerts.stop), ("the status", self.rigstatus.stop), ("the bulletins of ours", self.ownbulletins.stop),
                ("the objects of ours", self.ownobjects.stop), ("the iGate", self.igate.stop), *((BEACON_NAMES.get(radio.id) or f"the {radio.name} beacon", radio.beacon.stop) for radio in reversed(self.radios.all())), ("the GPS", self.gps.stop), ("the radio choices", self.radios.flush), ("the tasks", self.tasks.cancel_all)]

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

    # ---- the radios
    def start_tnc(self) -> None:
        """(Re)starts every radio with the settings as they are now, each in a task of its own (see start_radio)."""
        for radio in self.radios.all():
            self.start_radio(radio.id)

    def start_radio(self, id: RadioId) -> None:
        """(Re)starts one radio (its modem with it) with the settings as they are now, in a task: finding its port can take as long as 20 s a port, and nothing waits for it, another radio least. A start that
        is still looking for the port is ended first. A radio whose tickbox is off stays stopped. No other radio is touched."""
        self._starts[id] = self.tasks.spawn(self._restart(id, self._starts.get(id)), TASK_NAMES.get(id, f"radio-{id}"))

    async def _restart(self, id: RadioId, previous: "asyncio.Task[None] | None") -> None:
        if previous is not None:
            await cancel_all([previous])
        await self.radios.restart(id)
        if self.running:
            await self.radios.beacons_as_set()

    def _hf_settings(self, config: Config) -> tuple[object, ...]:
        """What a change of restarts radio 2 (tests/test_hf_scope_page.py asks under this name)."""
        return self.radios.restart_key(HF_ID, config)

    def _leave_dummy(self, was: RadioSpec) -> None:
        """A radio that was on as a Dummy radio is one no longer (it became a real radio, or was switched off): nothing it made up under calls of its own stays once a real radio is on. The messages still being
        sent to its made-up stations are cancelled (a real radio would send them on the air for ever, to calls that are nobody's, and hold the channel), and the stations it made up are forgotten with their place
        on the map, unless something real was heard of them too."""
        made_up, words = MADE_UP.get(was.kind, frozenset()), f"the Dummy {KIND_WORDS[was.kind]} radio"
        if not made_up:
            return
        for record in self.messaging.records():
            if record.state == "sending" and record.to_call in made_up:
                self.messaging.cancel(record.id)
                log.info("message %d to %s cancelled: %s that makes %s up is left", record.id, record.to_call, words, record.to_call)
        gone = [s.call for s in self.stationbook.stations() if s.call in made_up and s.heard_dummy > 0 and s.heard_rf == s.heard_rf_gated == s.heard_is == 0 and self.stationbook.forget(s.call)]
        if gone:
            log.info("forgot the made-up stations of %s: %s", words, ", ".join(gone))

    def repoint(self, radio: RadioId) -> None:
        """The radio's modem was started again on other ports (the pair it had was taken while it was down): its line is pointed at them, in a task, so that it does not wait on the old ones for ever."""
        found = self.radios.get(radio)
        if self.running and found is not None and found.spec.enabled:
            self.tasks.spawn(self.radios.repoint(radio), "hf-tnc" if radio == HF_ID else f"repoint-{radio}")

    async def hold_tnc(self) -> None:
        await self._stop_radios()

    async def hold_radio(self, id: RadioId) -> None:
        """One radio lets go of what it holds (its line, its modem), for a search that opens the ports; its start that is still looking for its port is ended first. No other radio is touched."""
        start = self._starts.pop(id, None)
        if start is not None:
            await cancel_all([start])
        radio = self.radios.get(id)
        if radio is not None:
            await radio.driver.stop()

    def release_radio(self, id: RadioId) -> None:
        """The radio takes what it holds again, while the daemon runs."""
        if self.running:
            self.start_radio(id)

    def release_tnc(self) -> None:
        if self.running:
            self.start_tnc()

    async def _stop_radios(self) -> None:
        tasks, self._starts = list(self._starts.values()), {}
        await cancel_all(tasks)
        await self.radios.stop_all()

    # ---- the settings
    async def save_config(self, config: Config) -> bool:
        """Stores the settings that differ from the ones in force, puts them all in force, and restarts the radio whose own settings or tickbox changed (its port, speed, type, sound card, keying), and only that one. False when the
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
        restart = self.radios.sync(config)                              # (before they are put in force: what differs of a radio is read against the settings in force)
        previous, self.config = self.config, config
        now_dummy = {spec.id for spec in enabled(config.radios) if spec.rtype.dummy}
        wiring.place_me(self)
        self.gps.settings_changed()
        for radio in self.radios.all():
            radio.beacon.settings_changed()
        self.igate.settings_changed()
        for id in restart:
            log.info("the %s radio is restarted because its settings changed: %s", self.radios.name_of(id), self.radios.why[id])
            self.start_radio(id)
        for was in enabled(previous.radios):
            if was.rtype.dummy and was.id not in now_dummy:
                self._leave_dummy(was)
        self.config_changed.emit(config)
        self.mapauto.settings_changed(previous)
        if self.web is not None:
            self.web.settings_changed(config)
        return True

    # ---- the care of the database
    async def prune(self) -> tuple[int, list[str]]:
        """Removes the packets and the stations not heard for 7 days (and the weather observations that old), and the packets from the internet older than INTERNET_KEEP_DAYS; how many packets, and which stations.
        The messages and the bulletins stay: the operator deletes those."""
        keep = LOG_KEEP_DAYS
        packets = await self.packetlog.prune(keep, INTERNET_KEEP_DAYS)
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

    async def _flush_stations(self) -> None:
        await every(STATION_FLUSH_SEC, self.packetlog.flush_stations, "the writing of the station rows")
