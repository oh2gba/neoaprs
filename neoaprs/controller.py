"""The program without a window: the database, the settings, the radio and the station book. The Controller is the composition root's object (docs/ARCHITECTURE.md): the parts are made in
neoaprs/app.py (`Services`) and connected in neoaprs/wiring.py, and this class brings them up and takes them down. The page and the tests call a part as `ctl.<part>.<method>`; the Controller has
the order of the start (the message board, the GPS and the beacon, our objects and bulletins, the status and messaging, then the Tnc, whose packets those take, and the page; the stop takes the page and the Tnc first, then the parts, one failing to stop not keeping the others from it), the Tnc's restart when its settings change, and the care of the database: the daily prune, and the station rows written every half minute (packetlog.py says why) and at the stop.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from . import wiring
from .app import Frontend, Services
from .clock import Clock, days, utcnow
from .config import DEFAULTS, Config
from .message import MessagingError
from .policy import INTERNET_KEEP_DAYS, LOG_KEEP_DAYS, TNC_CHECK_SEC
from .radios import hf_is_dummy, hf_is_mercury
from .dummyhfscene import STATIONS as DUMMY_HF_STATIONS
from .db import Db
from .dbfile import DEFAULT_BUSY_MS
from .dbopen import open_connection
from .packetlog import STATION_FLUSH_SEC
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
    def __init__(self, data_directory: str | Path, clock: Clock = utcnow, store: Store | None = None, busy_ms: int = DEFAULT_BUSY_MS, tnc: Tnc | None = None, port: str = "", web: WebFactory | None = None, pattern: str = "", install: InstallInfo = PLAIN_INSTALL, check_sec: float = TNC_CHECK_SEC, auto_map: bool = False, encryption: bool = False,
                 hf: Tnc | None = None, hf_port: str = "") -> None:
        super().__init__(Path(data_directory), clock, store, tnc, port, pattern, install, auto_map, encryption, hf, hf_port)
        self._web_factory = web
        self.check_sec = check_sec              # the keep-alive's quiet period in seconds (TNC_CHECK_SEC; the tests make it shorter, or 0 for none)
        self.busy_ms = busy_ms                  # how long the thread's connection waits for another writer: the daemon asks for a few seconds
        self._fm_task: asyncio.Task[None] | None = None         # the start of the FM radio, and of the HF radio with its modem: each radio is restarted on its own
        self._hf_task: asyncio.Task[None] | None = None
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
        await self._hf_beacon_as_set()
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
        await self.updatecheck.start()
        await self.frequencies.start()
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
        return [("the page", self._stop_web), ("Find my radio", self.radiofinder.stop), ("the Tnc", self._stop_tnc), ("the update check", self.updatecheck.stop), ("the suggested frequencies", self.frequencies.stop), ("the ALOHA circle", self.aloha.stop),
                ("Update now", self.selfupdate.stop), ("the automatic map", self.mapauto.stop), ("the map job", self.mapfetch.stop), ("the queries", self.queries.stop), ("the QRU server", self.qru.stop),
                ("asking QRU", self.qruask.stop), ("messaging", self.messaging.stop), ("the alerts", self.alerts.stop), ("the status", self.rigstatus.stop), ("the bulletins of ours", self.ownbulletins.stop),
                ("the objects of ours", self.ownobjects.stop), ("the iGate", self.igate.stop), ("the HF beacon", self.hf_beacon.stop), ("the beacon", self.beacon.stop), ("the GPS", self.gps.stop), ("the radio choices", self.radios.flush), ("the tasks", self.tasks.cancel_all)]

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
        """(Re)starts both radios with the settings as they are now, each in a task of its own (see start_fm and start_hf)."""
        self.start_fm()
        self.start_hf()

    def start_fm(self) -> None:
        """(Re)starts the FM radio with the settings as they are now, in a task: finding its port can take as long as 20 s a port, and nothing waits for it, the HF radio least. A start that is still looking for the port is
        ended first. A radio whose tickbox is off stays stopped. The HF radio and its modem are not touched."""
        self._fm_task = self.tasks.spawn(self._restart_fm(self._fm_task), "tnc")

    def start_hf(self) -> None:
        """(Re)starts the HF radio and the modem it connects to with the settings as they are now, in a task. The FM radio is not touched."""
        self._hf_task = self.tasks.spawn(self._restart_hf_radio(self._hf_task), "hf")

    async def _restart_fm(self, previous: "asyncio.Task[None] | None") -> None:
        if previous is not None:
            await cancel_all([previous])
        await self.tnc.stop()
        self._configure_fm()
        if self.config.fm_enabled:
            log.info("the FM radio is started: %s", wiring.radio_words(wiring.tnc_settings(self.config, self.port_override, self.pattern_override)))
            await self.tnc.start()
        else:
            log.info("the FM radio is off in the settings")

    async def _restart_hf_radio(self, previous: "asyncio.Task[None] | None") -> None:
        if previous is not None:
            await cancel_all([previous])
        await self.hf.stop()
        await self.mercury.stop()
        if not self.config.hf_enabled:
            log.info("the HF radio is off in the settings")
        else:
            log.info("the HF radio is started: %s", wiring.hf_words(self.config, self.hf_port_override))
            try:
                await self.mercury.start(self.config, self.hf_port_override, speaker=not hf_is_mercury(self.config))       # (the modem first: it chooses the ports the HF Tnc then connects to; a port given for this run is a Mercury something else runs; for the Dummy HF radio the program is the speaker)
            except Exception:
                log.exception("the Mercury modem could not be started")        # (the HF radio is started all the same: it keeps trying its port)
        self._configure_hf()
        if self.config.hf_enabled:
            await self.hf.start()
        if self.running:
            await self._hf_beacon_as_set()

    async def _hf_beacon_as_set(self) -> None:
        """The HF beacon runs while the HF radio is on and not otherwise (a beacon service of a radio that is off would only say, at every tick, why nothing goes)."""
        if self.config.hf_enabled:
            await self.hf_beacon.start()
        else:
            await self.hf_beacon.stop()

    def _configure_tnc(self) -> None:
        """The radios, which are stopped, take the settings as they are now."""
        self._configure_fm()
        self._configure_hf()

    def _configure_fm(self) -> None:
        """The FM radio, which is stopped, takes the settings as they are now (the HF radio, which may be running, is left alone)."""
        wiring.apply_tnc_settings(self.tnc, wiring.tnc_settings(self.config, self.port_override, self.pattern_override))
        self.tnc.set_check(self.check_sec)

    def _configure_hf(self) -> None:
        """The HF radio, which is stopped, takes the settings as they are now (the FM radio, which may be running, is left alone)."""
        wiring.apply_tnc_settings(self.hf, wiring.hf_settings(self.config, self.hf_port_override, self.mercury.broadcast_port))
        self.hf.set_check(self.check_sec)

    def _fm_settings(self, config: Config) -> tuple[object, ...]:
        """What a change of restarts the FM radio: its settings, or its tickbox, and nothing of the HF radio's."""
        return (wiring.tnc_settings(config, self.port_override, self.pattern_override), config.fm_enabled)

    def _hf_settings(self, config: Config) -> tuple[object, ...]:
        """What a change of restarts the HF radio and its modem: its settings (its type, the sound card and the keying), or its tickbox, and nothing of the FM radio's."""
        return (wiring.hf_settings(config, self.hf_port_override, self.mercury.broadcast_port), config.hf_enabled, None if self.mercury.live_gain else config.mercury_tx_gain_db)

    def _leave_dummy_hf(self) -> None:
        """The HF radio is no longer the Dummy HF radio (it became the Mercury modem, or was switched off): nothing it made up stays once a real radio is on. The messages still being sent to its made-up stations are cancelled
        (a real radio would send them on the air for ever, to calls that are nobody's, and hold the channel), and the stations it made up are forgotten with their place on the map, unless something real was heard of them too."""
        made_up = {station.call for station in DUMMY_HF_STATIONS}
        for record in self.messaging.records():
            if record.state == "sending" and record.to_call in made_up:
                self.messaging.cancel(record.id)
                log.info("message %d to %s cancelled: the Dummy HF radio that makes %s up is left", record.id, record.to_call, record.to_call)
        gone = [s.call for s in self.stationbook.stations() if s.call in made_up and s.heard_dummy > 0 and s.heard_rf == s.heard_rf_gated == s.heard_is == 0 and self.stationbook.forget(s.call)]
        if gone:
            log.info("forgot the made-up stations of the Dummy HF radio: %s", ", ".join(gone))

    def _made_explicit(self, before: Config, after: Config) -> Config:
        """`before`, with the sound card and the keying that the running modem has chosen for itself (the settings were empty) taken as set where `after` sets exactly those: the page stores the daemon's proposal as the setting, which
        changes nothing the modem does, so it is no reason to restart it."""
        modem = self.mercury
        if modem.state not in ("starting", "running"):
            return before
        card, keying = before.mercury_sound_card, before.mercury_keying
        if card == "" and after.mercury_sound_card == modem.sound_card:
            card = after.mercury_sound_card
        if keying == "" and after.mercury_keying == modem.keying.text:
            keying = after.mercury_keying
        return replace(before, mercury_sound_card=card, mercury_keying=keying)

    def repoint_hf(self) -> None:
        """The modem was started again on other ports (the pair it had was taken while it was down): the HF Tnc is pointed at them, in a task, so that it does not wait on the old ones for ever."""
        if self.running and self.config.hf_enabled:
            self.tasks.spawn(self._repoint_hf(), "hf-tnc")

    async def _repoint_hf(self) -> None:
        await self.hf.stop()
        self._configure_hf()
        await self.hf.start()

    async def hold_tnc(self) -> None:
        await self._stop_tnc()

    def release_tnc(self) -> None:
        if self.running:
            self.start_tnc()

    async def _stop_tnc(self) -> None:
        tasks = [task for task in (self._fm_task, self._hf_task) if task is not None]
        self._fm_task = self._hf_task = None
        await cancel_all(tasks)
        await self.tnc.stop()
        await self.hf.stop()
        await self.mercury.stop()

    # ---- the settings
    async def save_config(self, config: Config) -> bool:
        """Stores the settings that differ from the ones in force, puts them all in force, and restarts the radio whose port, speed, type, sound card, keying or tickbox changed (and only that one). False when the
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
        fm_before, hf_before = self._fm_settings(self.config), self._hf_settings(self._made_explicit(self.config, config))
        previous, self.config = self.config, config
        left_dummy_hf = hf_is_dummy(previous) and not hf_is_dummy(config)
        wiring.place_me(self)
        self.gps.settings_changed()
        self.beacon.settings_changed()
        self.hf_beacon.settings_changed()
        self.igate.settings_changed()
        fm_after, hf_after = self._fm_settings(config), self._hf_settings(config)
        if fm_after != fm_before:
            log.info("the FM radio is restarted because its settings changed: %s", wiring.changed_words(fm_before, fm_after))
            self.start_fm()
        if hf_after != hf_before:
            log.info("the HF radio is restarted because its settings changed: %s", wiring.changed_words(hf_before, hf_after))
            self.start_hf()
        if left_dummy_hf:
            self._leave_dummy_hf()
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
