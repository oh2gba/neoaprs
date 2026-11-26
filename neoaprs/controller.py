"""The program without a window: the database, the settings, the radios and the station book.

The Controller starts and stops the parts, restarts a radio when its settings change and prunes
the database daily. The radios start last, each in its own task, and stop first."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path

from . import nodevices, pairsetting, radioedits, wiring
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
from .radioregistry import NEW, REMOVED, is_dummy
from .radioflows import RadioFlows
from .radiospec import FM_ID, HF_ID, KIND_WORDS, RadioId, RadioSpec, enabled
from .sendonrule import Kept
from .store import DB_NAME, Store
from .tasks import every
from .tnc import Tnc
from .versions import PLAIN_INSTALL, InstallInfo

log = logging.getLogger("neoaprs.controller")

PRUNE_EVERY_SEC = 24 * 3600.0
# Sweep backup/ again after the start: a copy killed just before leaves a temporary file.
BACKUP_SWEEP_FIRST_SEC = LITTER_AGE_SEC + 60.0
RECOUNT_EVERY_SEC = 60.0  # the station book's hour of packets advances by minutes
# Start task names in the log for radios 1 and 2 (others are `radio-<id>`).
TASK_NAMES: dict[RadioId, str] = {FM_ID: "tnc", HF_ID: "hf"}
# Beacon names in the stop's log for radios 1 and 2.
BEACON_NAMES: dict[RadioId, str] = {FM_ID: "the beacon", HF_ID: "the Mercury beacon"}


def made_up_alone(was: RadioSpec, config: Config) -> frozenset[str]:
    """Return the calls a leaving Dummy radio made up that no other Dummy radio makes up too."""
    others = (
        made_up_calls(spec.rtype.profile, spec.id)
        for spec in enabled(config.radios)
        if is_dummy(spec) and spec.id != was.id
    )
    return made_up_calls(was.rtype.profile, was.id) - frozenset().union(*others)


WebFactory = Callable[["Controller", Config], Frontend]
"""How the process says what its page's server is: neoaprs.web.server.WebServer. The controller makes it from the settings and the process, which is the delivery layer, is the one that names it."""


class Controller(Services):
    def __init__(
        self,
        data_directory: str | Path,
        clock: Clock = utcnow,
        store: Store | None = None,
        busy_ms: int = DEFAULT_BUSY_MS,
        port: str = "",
        web: WebFactory | None = None,
        pattern: str = "",
        install: InstallInfo = PLAIN_INSTALL,
        check_sec: float = TNC_CHECK_SEC,
        auto_map: bool = False,
        encryption: bool = False,
        hf_port: str = "",
        lines: Mapping[RadioId, Tnc] | None = None,
    ) -> None:
        super().__init__(
            Path(data_directory), clock, store, port, pattern, install, auto_map, encryption, hf_port, lines
        )
        self._web_factory = web
        self.check_sec = check_sec
        self.busy_ms = busy_ms
        self.flows = RadioFlows(self.tasks.spawn)
        self._implied: set[str] = set()  # settings implied by an older row, stored at the first save
        wiring.wire(self)

    async def open_database(self) -> None:
        """Open the database on its thread; raise StoreError if the file cannot be used."""
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
        nodevices.announce()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self.open_database()
        await self._load_settings()
        for level, note in radioedits.start_notes(self.config, self.run):
            log.log(level, "%s", note)
        await wiring.seed_station_book(self)
        self.radios.sync(self.config)
        self.radios.configure()
        self.running = True
        await self.bulletins.start()
        await self.gps.start()
        await self.radios.beacons_as_set()
        await self.igate.start()
        await self.ownobjects.start()
        await self.ownbulletins.start()
        await self.rigstatus.start()
        await self.prefbook.load()
        await self._load_keys()  # before messaging opens what comes in
        self.stationalerts.load()
        for start in (self.aloha.start, self.messaging.start, self.digipeater.start):
            await start()
        await asyncio.to_thread(end_left_behind, self.data_dir)  # end a Mercury left by an unclean stop
        self.start_tnc()  # last: the source starts after its consumers
        await self._start_web()
        await self.mapauto.start()
        for asks in (self.updatecheck, self.frequencies, self.skeds, self.layers):
            await asks.start()
        self.tasks.spawn(self._prune_daily(), "prune")
        self.tasks.spawn(self._sweep_backup(), "backup-sweep")
        self.tasks.spawn(self._recount_minutely(), "recount")
        self.tasks.spawn(self._flush_stations(), "station-flush")

    async def _load_settings(self) -> None:
        """Load the settings and radios as stored (`radios_unread` if the radios cannot be read)."""
        rows, radios = await self.store.settings(), await self.store.read_radios()
        self.radios_unread = radios is None
        if radios is None:
            log.warning(
                "the radios could not be read (the log above says why): no radio runs, and no radio is added nor a station's radio stored until the next start"
            )
        self.config = Config.from_data(rows, radios=radios or ())
        defaults = DEFAULTS.to_data()
        self._implied = {
            key
            for key, text in self.config.to_data().items()
            if key in STATION_KEYS and key not in rows and text != defaults[key]
        }

    async def _load_keys(self) -> None:
        """Load the keyring; a key file that cannot be made is logged and the daemon goes on."""
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
                    log.exception("%s could not be stopped", name)
        finally:
            self.packetlog.flush_stations()
            if self.db is not None:
                await self.db.close()

    def _stops(self) -> list[tuple[str, Callable[[], Awaitable[None]]]]:
        """Return what the stop ends, in order: the page, Find my radio and the Tnc first."""
        return [
            ("the page", self._stop_web),
            ("the map's layers", self.layers.stop),
            ("Find my radio", self.radiofinder.stop),
            ("the Tnc", self._stop_radios),
            ("the update check", self.updatecheck.stop),
            ("the suggested frequencies", self.frequencies.stop),
            ("the HF test board", self.skeds.stop),
            ("the ALOHA circle", self.aloha.stop),
            ("Update now", self.selfupdate.stop),
            ("the automatic map", self.mapauto.stop),
            ("the map job", self.mapfetch.stop),
            ("the queries", self.queries.stop),
            ("the QRU server", self.qru.stop),
            ("asking QRU", self.qruask.stop),
            ("the digipeater", self.digipeater.stop),
            ("messaging", self.messaging.stop),
            ("the alerts", self.alerts.stop),
            ("the status", self.rigstatus.stop),
            ("the bulletins of ours", self.ownbulletins.stop),
            ("the objects of ours", self.ownobjects.stop),
            ("the iGate", self.igate.stop),
            *(
                (BEACON_NAMES.get(radio.id) or f"the {radio.name} beacon", radio.beacon.stop)
                for radio in reversed(self.radios.all())
            ),
            ("the GPS", self.gps.stop),
            ("the radio choices", self.radios.flush),
            ("the tasks", self.tasks.cancel_all),
        ]

    # ---- the page
    async def _start_web(self) -> None:
        """Start the page's server if the process has one; if it cannot listen, go on without."""
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
        """(Re)start every radio, each in its own task."""
        for radio in self.radios.all():
            self.start_radio(radio.id)

    def start_radio(self, id: RadioId) -> None:
        """(Re)start one radio and its modem in a task: finding a port can take 20 s per port."""
        if id in self.flows.held:
            log.info("%s is started once Find my radio lets go of it", self.radios.told_of(id))
            return
        self.flows.begin(id, "restart", lambda: self._restart(id), TASK_NAMES.get(id, f"radio-{id}"))

    async def _restart(self, id: RadioId) -> None:
        await self.radios.restart(id)
        if self.flows.take_owed(id):
            await self.radios.repoint(id, unless_connected=True)
        if self.running:
            await self.radios.beacons_as_set()

    def _leave_dummy(self, was: RadioSpec) -> None:
        """Forget what a radio that stopped being a Dummy radio made up."""
        made_up, words = made_up_alone(was, self.config), f"the Dummy {KIND_WORDS[was.kind]} radio"
        if not made_up:
            return
        for record in self.messaging.records():
            if record.state == "sending" and record.to_call in made_up:
                self.messaging.cancel(record.id)
                log.info(
                    "message %d to %s cancelled: %s that makes %s up is left",
                    record.id,
                    record.to_call,
                    words,
                    record.to_call,
                )
        gone = [
            s.call
            for s in self.stationbook.stations()
            if s.call in made_up
            and s.heard_dummy > 0
            and s.heard_rf == s.heard_rf_gated == s.heard_is == 0
            and self.stationbook.forget(s.call)
        ]
        if gone:
            log.info("forgot the made-up stations of %s: %s", words, ", ".join(gone))

    def repoint(self, radio: RadioId) -> None:
        """Point the radio's line at the ports its modem was restarted on, in a task."""
        found = self.radios.get(radio)
        if not self.running or found is None or not found.spec.enabled or radio in self.flows.held:
            return
        if not self.flows.owe_repoint(radio):
            name = "hf-tnc" if radio == HF_ID else f"repoint-{radio}"
            self.flows.begin(radio, "repoint", lambda: self.radios.repoint(radio), name)

    async def hold_radio(self, id: RadioId) -> None:
        """Stop one radio so a search can open the ports; it stays stopped until `release_radio`."""
        await self.flows.hold(id, lambda: self._stop_one(id), f"hold-{id}")

    async def _stop_one(self, id: RadioId) -> None:
        radio = self.radios.get(id)
        if radio is not None:
            await radio.driver.stop()

    def release_radio(self, id: RadioId) -> None:
        """Restart the radio, if the daemon runs, with the settings as they are now."""
        self.flows.release(id)
        if self.running:
            self.start_radio(id)

    async def _stop_radios(self) -> None:
        await self.flows.end_all()
        await self.radios.stop_all()

    # ---- the settings
    async def save_config(self, config: Config) -> bool:
        """Store the changed settings and put them in force; False if the database refused."""
        async with self.config_lock:
            return await self._save(config)

    async def change_config(self, change: Callable[[Config], Config]) -> bool:
        """Store what `change` makes of the settings in force (read under the lock)."""
        async with self.config_lock:
            return await self._save(change(self.config))

    async def _save(self, config: Config) -> bool:
        """Store the changed rows in one transaction, then put the settings in force."""
        config, kept = self.kept_change(self.config, config)
        stored, data = set(self.config.changed(config)) | self._implied, config.to_data()
        rows = (
            {key: text for key, text in data.items() if key in stored and key in STATION_KEYS}
            | ({LAST_PORT: data["serial/last_port"]} if "serial/last_port" in stored else {})
            | pairsetting.changed_rows(self.config.pairs, config.pairs)
        )
        writes = radioedits.radio_writes(self.config.radios, config.radios)
        if (refused := radioedits.refusal(self.config.radios, config.radios)) is not None:
            log.error("the settings were not stored: %s", refused)
            return False
        if not await self.store.put_config(rows, writes, Kept(objects=kept.objects, bulletins=kept.bulletins)):
            return False
        self._implied = set()
        self._in_force(config)
        self.keep(kept)
        return True

    def _in_force(self, config: Config) -> None:
        """Put stored settings in force: restart the changed radios, tell the parts."""
        names = {radio.id: radio.told for radio in self.radios.all()}
        restart = self.radios.sync(config)
        previous, self.config = self.config, config
        now_dummy = {spec.id for spec in enabled(config.radios) if is_dummy(spec)}
        wiring.place_me(self)
        self.gps.settings_changed()
        for radio in self.radios.all():
            radio.beacon.settings_changed()
        self.igate.settings_changed()
        for id in restart:
            self._tell_restart(names.get(id) or self.radios.told_of(id), self.radios.why[id])
            self.start_radio(id)
        for was in enabled(previous.radios):
            if is_dummy(was) and was.id not in now_dummy:
                self._leave_dummy(was)
        self.config_changed.emit(config)
        self.mapauto.settings_changed(previous)
        if self.web is not None:
            self.web.settings_changed(config)

    @staticmethod
    def _tell_restart(told: str, why: str) -> None:
        """Log why the radio is started again: removed, new (its start says it) or its settings."""
        if why == REMOVED:
            log.info("%s is removed", told)
        elif why != NEW:
            log.info("%s is restarted because its settings changed: %s", told, why)

    # ---- the radios the operator adds, changes and removes
    async def add_radio(self, type: str, name: str = "", *, enabled: bool = True) -> RadioId | None:
        """Add a radio of `type` after the others, store it and start it; return its id or None."""
        async with self.config_lock:
            spec = radioedits.new_radio(self.config, type, name, enabled)
            if self.radios_unread:
                log.warning(
                    "the radio is not added: the radios could not be read at the start, and none is added until the next start"
                )
                return None
            _, kept = self.kept_change(
                self.config,
                radioedits.put(self.config, replace(spec, id=max((s.id for s in self.config.radios), default=0) + 1)),
            )
            id = await self.store.add_radio(spec.kind, spec.type, spec.name, spec.enabled, spec.position, kept=kept)
            if id is not None:
                log.info(
                    "radio %d is added: the type %s (%s)%s",
                    id,
                    spec.type,
                    KIND_WORDS[spec.kind],
                    f", named {spec.name}" if spec.name else "",
                )
                self._in_force(radioedits.put(radioedits.with_kept(self.config, kept), replace(spec, id=id)))
                self.keep(kept)
            return id

    async def change_radio(self, id: RadioId, **columns: object) -> bool:
        """Store and put in force a radio's name, type, tickbox or `position`."""
        async with self.config_lock:
            return await self._save(radioedits.put(self.config, radioedits.changed_radio(self.config, id, columns)))

    async def save_radio_settings(self, id: RadioId, values: Mapping[str, str]) -> bool:
        """Store and put in force a radio's own settings (as text); restart it if needed."""
        async with self.config_lock:
            return await self._save(radioedits.put(self.config, radioedits.with_settings(self.config, id, values)))

    async def remove_radio(self, id: RadioId) -> bool:
        """Remove the radio and every reference to it in one transaction; its row stays."""
        async with self.config_lock:
            spec = radioedits.removable(self.config, id)
            if not await self.store.remove_radio(id):
                return False
            self.forget_radio(id)
            self._in_force(radioedits.removed(self.config, spec, self.clock()))
            await self.prefbook.load()
            return True

    # ---- the care of the database
    async def prune(self) -> tuple[int, list[str]]:
        """Remove old packets, stations and weather; return the packets and stations removed."""
        keep = LOG_KEEP_DAYS
        packets = await self.packetlog.prune(keep, INTERNET_KEEP_DAYS)
        self.messaging.forget_heard(keep)
        await self.weatherlog.prune(keep)
        stations = self.stationbook.prune(self.clock() - days(keep))
        if packets or stations:
            log.info("pruned %d packets and %d stations older than %d days", packets, len(stations), keep)
        return packets, stations

    async def forget_stations(self) -> int:
        """Forget every station but ours with its packets and weather; return the count."""
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
        await every(
            PRUNE_EVERY_SEC,
            lambda: asyncio.to_thread(sweep, self.data_dir / FOLDER_NAME, time.time()),
            "the sweep of the backup folder",
            first=BACKUP_SWEEP_FIRST_SEC,
        )

    async def _recount_minutely(self) -> None:
        await every(RECOUNT_EVERY_SEC, self.stationbook.recount, "the recount of the station book")

    async def _flush_stations(self) -> None:
        await every(STATION_FLUSH_SEC, self.packetlog.flush_stations, "the writing of the station rows")
