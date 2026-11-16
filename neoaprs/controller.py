"""The program without a window: the database, the settings, the radio and the station book. The Controller is the composition root's object (docs/ARCHITECTURE.md): the parts are made in
neoaprs/app.py (`Services`) and connected in neoaprs/wiring.py, and this class brings them up and takes them down. The page and the tests call a part as `ctl.<part>.<method>`; the Controller has
the order of the start (the message board, the GPS and the beacons, our objects and bulletins, the status and messaging, then the radios, whose packets those take, and the page; the stop takes the page and the radios first, then the parts, one failing to stop not keeping the others from it), the restart of a radio when its settings change, and the care of the database: the daily prune, and the station rows written every half minute (packetlog.py says why) and at the stop.

The radios are the registry's (neoaprs/radioregistry.py), any number of them, each brought up and down by the one lifecycle of every type; this class starts each in a task of its own, so that one that is
still looking for its port keeps no other waiting, and restarts the one a save changed and no other. They are read from the database at the start (a new installation has none), and the operator adds,
changes and removes them here (`add_radio`, `change_radio`, `remove_radio`, `save_radio_settings`; the checks are neoaprs/radioedits.py's), each stored before it is put in force. A save of the settings
writes the station's rows to the settings and what it changes of a radio to that radio's rows.
"""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path

from . import nodevices, radioedits, wiring
from .app import Frontend, Services
from .backupfolder import FOLDER_NAME, LITTER_AGE_SEC, sweep
from .clock import Clock, days, utcnow
from .config import DEFAULTS, LAST_PORT, STATION_KEYS, Config
from .mercuryclaims import end_left_behind
from .message import MessagingError
from .policy import INTERNET_KEEP_DAYS, LOG_KEEP_DAYS, TNC_CHECK_SEC
from .dummyworlds import made_up_calls
from .db import Db
from .dbfile import DEFAULT_BUSY_MS
from .dbopen import open_connection
from .packetlog import STATION_FLUSH_SEC
from .radioregistry import is_dummy
from .radiospec import FM_ID, HF_ID, KIND_WORDS, RadioId, RadioSpec, enabled
from .store import DB_NAME, Store
from .tasks import cancel_all, every
from .tnc import Tnc
from .versions import PLAIN_INSTALL, InstallInfo

log = logging.getLogger("neoaprs.controller")

PRUNE_EVERY_SEC = 24 * 3600.0
BACKUP_SWEEP_FIRST_SEC = LITTER_AGE_SEC + 60.0    # backup/ swept again after the start: the temporary file of a copy a kill ended just before it (its note still fresh, so the open left it) is dead by then
RECOUNT_EVERY_SEC = 60.0                # the station book's hour of packets moves on a minute at a time
TASK_NAMES: dict[RadioId, str] = {FM_ID: "tnc", HF_ID: "hf"}       # the task of a radio's start as the log has named it for radios 1 and 2 (another is `radio-<id>`)
BEACON_NAMES: dict[RadioId, str] = {FM_ID: "the beacon", HF_ID: "the Mercury beacon"}       # a radio's beacon as the stop's log has named it for radios 1 and 2


def made_up_alone(was: RadioSpec, config: Config) -> frozenset[str]:
    """The calls a Dummy radio that leaves its world made up (its world by its id as the seed: dummyworlds.py) and no Dummy radio still on in `config` makes up too: the HF worlds share their cities, and
    what another radio still hears stays."""
    others = (made_up_calls(spec.rtype.profile, spec.id) for spec in enabled(config.radios) if is_dummy(spec) and spec.id != was.id)
    return made_up_calls(was.rtype.profile, was.id) - frozenset().union(*others)


WebFactory = Callable[["Controller", Config], Frontend]
"""How the process says what its page's server is: neoaprs.web.server.WebServer. The controller makes it from the settings and the process, which is the delivery layer, is the one that names it."""


class Controller(Services):
    def __init__(self, data_directory: str | Path, clock: Clock = utcnow, store: Store | None = None, busy_ms: int = DEFAULT_BUSY_MS, port: str = "", web: WebFactory | None = None, pattern: str = "", install: InstallInfo = PLAIN_INSTALL, check_sec: float = TNC_CHECK_SEC, auto_map: bool = False, encryption: bool = False,
                 hf_port: str = "", lines: Mapping[RadioId, Tnc] | None = None) -> None:
        super().__init__(Path(data_directory), clock, store, port, pattern, install, auto_map, encryption, hf_port, lines)
        self._web_factory = web
        self.check_sec = check_sec              # the keep-alive's quiet period in seconds (TNC_CHECK_SEC; the tests make it shorter, or 0 for none)
        self.busy_ms = busy_ms                  # how long the thread's connection waits for another writer: the daemon asks for a few seconds
        self._starts: dict[RadioId, asyncio.Task[None]] = {}    # the start of each radio (with its modem): each radio is restarted on its own
        self._held: set[RadioId] = set()        # the radios Find my radio holds while it tries the ports: none of them is started meanwhile
        self._implied: set[str] = set()         # the station's settings that a row of an older version implies (configlegacy.py), stored at the first save
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
        await self._load_settings()
        for level, note in radioedits.start_notes(self.config, self.run):
            log.log(level, "%s", note)
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
        await asyncio.to_thread(end_left_behind, self.data_dir)        # (a Mercury that a daemon which did not stop cleanly left running, a radio's that is off now among them)
        self.start_tnc()                                                # (last of the parts that take its packets: the source after its consumers)
        await self._start_web()
        await self.mapauto.start()
        for asks in (self.updatecheck, self.frequencies, self.skeds):       # (what asks the project's server: the update check, the suggested frequencies and the sked board)
            await asks.start()
        self.tasks.spawn(self._prune_daily(), "prune")
        self.tasks.spawn(self._sweep_backup(), "backup-sweep")
        self.tasks.spawn(self._recount_minutely(), "recount")
        self.tasks.spawn(self._flush_stations(), "station-flush")

    async def _load_settings(self) -> None:
        """The settings and the radios as they are stored (a new installation has no radio until the operator adds one). Where the radios cannot be read, none runs, and none is added nor a station's
        radio stored until the next start (`radios_unread`): the radios stored, and the stations' choices of them, stay as they are."""
        rows, radios = await self.store.settings(), await self.store.read_radios()
        self.radios_unread = radios is None
        if radios is None:
            log.warning("the radios could not be read (the log above says why): no radio runs, and no radio is added nor a station's radio stored until the next start")
        self.config = Config.from_data(rows, radios=radios or ())
        defaults = DEFAULTS.to_data()
        self._implied = {key for key, text in self.config.to_data().items() if key in STATION_KEYS and key not in rows and text != defaults[key]}

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
        return [("the page", self._stop_web), ("Find my radio", self.radiofinder.stop), ("the Tnc", self._stop_radios), ("the update check", self.updatecheck.stop), ("the suggested frequencies", self.frequencies.stop), ("the HF test board", self.skeds.stop), ("the ALOHA circle", self.aloha.stop),
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
        """(Re)starts one radio (its modem with it) with the settings as they are now, in a task: finding its port can take as long as 20 s a port, and nothing waits for it, another radio least. A start that is still
        looking for the port is ended first. A radio whose tickbox is off stays stopped. No other radio is touched. One that Find my radio holds is started when the search lets go of it (`release_radio`), with the settings as they are then."""
        if id in self._held:
            log.info("the %s radio is started once Find my radio lets go of it", self.radios.name_of(id))
            return
        self._starts[id] = self.tasks.spawn(self._restart(id, self._starts.get(id)), TASK_NAMES.get(id, f"radio-{id}"))

    async def _restart(self, id: RadioId, previous: "asyncio.Task[None] | None") -> None:
        if previous is not None:
            await cancel_all([previous])
        await self.radios.restart(id)
        if self.running:
            await self.radios.beacons_as_set()

    def _leave_dummy(self, was: RadioSpec) -> None:
        """A radio that was on as a Dummy radio is one no longer (it became a real radio, or was switched off): nothing it made up under calls of its own stays once a real radio is on. The messages still being
        sent to its made-up stations are cancelled (a real radio would send them on the air for ever, to calls that are nobody's, and hold the channel), and the stations it made up are forgotten with their place
        on the map, unless something real was heard of them too."""
        made_up, words = made_up_alone(was, self.config), f"the Dummy {KIND_WORDS[was.kind]} radio"
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

    async def hold_radio(self, id: RadioId) -> None:
        """One radio lets go of what it holds (its line, its modem), for a search that opens the ports; its start still looking for its port is ended first, and none is made until `release_radio`. No other radio is touched."""
        self._held.add(id)
        start = self._starts.pop(id, None)
        if start is not None:
            await cancel_all([start])
        radio = self.radios.get(id)
        if radio is not None:
            await radio.driver.stop()

    def release_radio(self, id: RadioId) -> None:
        """The radio takes what it holds again, while the daemon runs: one start, with the settings as they are now (a save meanwhile asked for none of its own)."""
        self._held.discard(id)
        if self.running:
            self.start_radio(id)

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
        """The station's rows that this save changes (a key written by `neoaprs db set` in the meantime stays), radio 1's last port in its own row, and what it changes of the radios in theirs, all in one
        transaction; then put in force."""
        stored, data = set(self.config.changed(config)) | self._implied, config.to_data()
        rows = {key: text for key, text in data.items() if key in stored and key in STATION_KEYS} | ({LAST_PORT: data["serial/last_port"]} if "serial/last_port" in stored else {})
        writes = radioedits.radio_writes(self.config.radios, config.radios)
        if (refused := radioedits.refusal(self.config.radios, config.radios)) is not None:
            log.error("the settings were not stored: %s", refused)
            return False
        if not await self.store.put_config(rows, writes):
            return False
        self._implied = set()
        self._in_force(config)
        return True

    def _in_force(self, config: Config) -> None:
        """The settings, stored, put in force: the radios follow them (the one a change is of is restarted, and no other), and every part that reads them is told."""
        restart = self.radios.sync(config)                              # (before they are put in force: what differs of a radio is read against the settings in force)
        previous, self.config = self.config, config
        now_dummy = {spec.id for spec in enabled(config.radios) if is_dummy(spec)}
        wiring.place_me(self)
        self.gps.settings_changed()
        for radio in self.radios.all():
            radio.beacon.settings_changed()
        self.igate.settings_changed()
        for id in restart:
            log.info("the %s radio is restarted because its settings changed: %s", self.radios.name_of(id), self.radios.why[id])
            self.start_radio(id)
        for was in enabled(previous.radios):
            if is_dummy(was) and was.id not in now_dummy:
                self._leave_dummy(was)
        self.config_changed.emit(config)
        self.mapauto.settings_changed(previous)
        if self.web is not None:
            self.web.settings_changed(config)

    # ---- the radios the operator adds, changes and removes (refusals: radiospec.RadioError, and radiotype.RadioTypeError for a type that is none; False: the database would not take it)
    async def add_radio(self, type: str, name: str = "", *, enabled: bool = True) -> RadioId | None:
        """A new radio of the type (`kiss`, `mercury`, ...), after the others, with the name typed ("" for none) and the defaults of its kind, stored and started while it is enabled; its id, which no
        radio had before, or None when it was not stored."""
        async with self.config_lock:
            spec = radioedits.new_radio(self.config, type, name, enabled)
            if self.radios_unread:
                log.warning("the radio is not added: the radios could not be read at the start, and none is added until the next start")
                return None
            id = await self.store.add_radio(spec.kind, spec.type, spec.name, spec.enabled, spec.position)
            if id is not None:
                log.info("radio %d is added: the type %s (%s)%s", id, spec.type, KIND_WORDS[spec.kind], f", named {spec.name}" if spec.name else "")
                self._in_force(radioedits.put(self.config, replace(spec, id=id)))
            return id

    async def change_radio(self, id: RadioId, **columns: object) -> bool:
        """The radio's name, type (one of its own kind), tickbox or place (`position`), stored and put in force: the radio is restarted when its driver or its tickbox says so."""
        async with self.config_lock:
            return await self._save(radioedits.put(self.config, radioedits.changed_radio(self.config, id, columns)))

    async def save_radio_settings(self, id: RadioId, values: Mapping[str, str]) -> bool:
        """The radio's own settings (`port`, `baud`, `sound_card`, `path`, ... as text), each checked, stored and put in force: that radio alone is restarted, when what restarts it changed."""
        async with self.config_lock:
            return await self._save(radioedits.put(self.config, radioedits.with_settings(self.config, id, values)))

    async def remove_radio(self, id: RadioId) -> bool:
        """Removes the radio, and in the same transaction its id from the objects' sets, the stations' paths on it and choices of it, and its own state rows (radiosql.remove_radio); it is stopped for good.
        Its row stays, so that what came by it still says so. The last enabled radio is not removed."""
        async with self.config_lock:
            spec = radioedits.removable(self.config, id)
            if not await self.store.remove_radio(id):
                return False
            log.info("the %s radio (radio %d) is removed", self.radios.name_of(id), id)
            self.forget_radio(id)
            self._in_force(radioedits.put(self.config, replace(spec, removed_at=self.clock())))
            await self.prefbook.load()                                  # (the stations' paths as the removal left them)
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

    async def _sweep_backup(self) -> None:
        await every(PRUNE_EVERY_SEC, lambda: asyncio.to_thread(sweep, self.data_dir / FOLDER_NAME, time.time()), "the sweep of the backup folder", first=BACKUP_SWEEP_FIRST_SEC)

    async def _recount_minutely(self) -> None:
        await every(RECOUNT_EVERY_SEC, self.stationbook.recount, "the recount of the station book")

    async def _flush_stations(self) -> None:
        await every(STATION_FLUSH_SEC, self.packetlog.flush_stations, "the writing of the station rows")
