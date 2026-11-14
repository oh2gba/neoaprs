"""The one database file: everything NeoAPRS keeps (the settings and the radios here; the packets and the stations are packetlog.py's, the messages and the preferences of the stations messagelog.py's). The only
thing outside it is the log of the program itself, a rotating text file.

This is the part of it that the daemon uses through the database thread (db.py): the settings, the radios, the checkpoint of the write-ahead log and the copy of the file. The file is brought up to
date before the thread uses it, by the migrations (migrations.py).
"""
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, TypeVar

from .clock import Clock, utcnow
from .configradios import radios_from_rows
from .db import Db
from .dberror import Connection, DbClosed, Row, SqlError, StoreError as StoreError           # (kept here: the names the rest of the program imports them by)
from .packetcodec import stamp
from .radiospec import RadioId, RadioSpec
from .radiosql import insert_radio, put_radio_settings, radio_rows, radio_settings, remove_radio, seed_radios, update_radio
from .storesql import Settings, delete_setting, read_setting, read_settings, write_setting, write_settings

log = logging.getLogger("neoaprs.store")

DB_NAME = "neoaprs.sqlite"

T = TypeVar("T")


class RadioWrite(NamedTuple):
    """What a save of the settings writes of one radio (Store.put_config): a radio that is new with its id and its own settings, or a radio's changed columns (radiosql.CHANGEABLE) and own settings."""
    spec: RadioSpec
    new: bool = False
    columns: Mapping[str, object] = {}
    values: Mapping[str, str] = {}


class _Refused(Exception):
    """A radio of a save is not there or is removed: the save is rolled back whole."""


class Store:
    """The settings and the radios of the one database, on the database thread (db.py): every method is an operation of the thread, awaited by the caller, in the order it was asked. A store whose
    database is not open says no and does not raise: it has no settings, no radios and keeps nothing. The statements are those of storesql.py and radiosql.py."""

    def __init__(self, clock: Clock = utcnow) -> None:
        self.now = clock
        self.db: Db | None = None
        self.path = ""

    def use(self, db: Db, path: str | Path) -> None:
        """The store in the database the Db is the thread of (the file is migrated already, by open_connection())."""
        self.db = db
        self.path = str(path)

    def is_open(self) -> bool:
        return self.db is not None and self.db.is_open

    async def _read(self, fn: Callable[[Connection], T], default: T, what: str) -> T:
        """fn on the thread, in a read transaction; `default` when the database is not open, and also (told as a warning, as `what`) when it cannot be read."""
        db = self.db
        if db is None or not db.is_open:
            return default
        try:
            return await db.read(fn)
        except (SqlError, DbClosed) as e:
            log.warning("%s: %s", what, e)
            return default

    async def _quietly(self, fn: Callable[[Connection], object], what: str) -> bool:
        """fn on the thread, in a write transaction; whether it was done (an error of the database is not raised, it is told as a warning as `what`)."""
        db = self.db
        if db is None or not db.is_open:
            return False
        try:
            await db.write(fn)
        except (SqlError, DbClosed) as e:
            log.warning("%s: %s", what, e)
            return False
        return True

    async def checkpoint(self) -> None:
        """What is committed is on the disk, in the database file itself (not only in the -wal): before something that cannot be undone."""
        if self.is_open():
            assert self.db is not None
            try:
                await self.db.checkpoint()
            except (SqlError, DbClosed) as e:
                log.warning("the checkpoint failed: %s", e)

    # ---- the settings: a key ("station/call") and the raw text of the value
    async def settings(self) -> Settings:
        return await self._read(read_settings, {}, "the settings could not be read")

    async def setting(self, key: str) -> str | None:
        return await self._read(lambda db: read_setting(db, key), None, f"the setting {key} could not be read")

    async def put_setting(self, key: str, value: str) -> bool:
        """One setting, replaced in one statement."""
        db = self.db
        if db is None or not db.is_open:
            return False
        try:
            await db.write(lambda conn: write_setting(conn, key, value))
        except (SqlError, DbClosed) as e:
            log.error("the setting %s could not be stored: %s", key, e)
            return False
        return True

    async def put_settings(self, data: Settings) -> bool:
        """Every key of `data` in one transaction (all of it or none); the other settings stay."""
        db = self.db
        if db is None or not db.is_open:
            return False
        try:
            await db.write(lambda conn: write_settings(conn, data))
        except (SqlError, DbClosed) as e:
            log.error("the settings could not be stored: %s", e)
            return False
        return True

    async def delete_setting(self, key: str) -> None:
        await self._quietly(lambda db: delete_setting(db, key), f"the setting {key} could not be deleted")

    # ---- the radios: the rows of `radio` and each radio's own settings (radiosql.py)
    async def _stored(self, fn: Callable[[Connection], T], default: T, what: str) -> T:
        """fn on the thread, in a write transaction (all of it or none), and what it gives; `default` when the database is not open or would not take it (told as an error, as `what`)."""
        db = self.db
        if db is None or not db.is_open:
            return default
        try:
            return await db.write(fn)
        except (SqlError, DbClosed) as e:
            log.error("%s: %s", what, e)
            return default

    async def radios(self) -> tuple[RadioSpec, ...]:
        """Every radio as it is stored, removed ones too, by id (configradios.radios_from_rows); none when the database is not open or cannot be read (told as a warning, as `settings()` does:
        none can also mean that, so a caller that would write radios on none must not)."""
        none: tuple[list[Row], list[Row]] = ([], [])
        return radios_from_rows(*await self._read(lambda db: (radio_rows(db), radio_settings(db)), none, "the radios could not be read"))

    async def add_radio(self, kind: str, type: str, name: str, enabled: bool, position: int, *, id: RadioId | None = None, settings: Mapping[str, str] | None = None) -> RadioId | None:
        """A new radio with its own settings, in one transaction; its id, or None when it was not stored. `id`: the id it is to have (radiosql.insert_radio: radios 1 and 2 of today's flat keys)."""
        def add(db: Connection) -> RadioId:
            made = insert_radio(db, kind, type, name, enabled, position, id=id)
            put_radio_settings(db, made, settings or {})        # (the radio was inserted just now: it takes them)
            return made
        return await self._stored(add, None, f"the new {kind} radio could not be stored")

    async def change_radio(self, id: RadioId, /, **columns: object) -> bool:
        """Sets columns of a radio (radiosql.CHANGEABLE: type, name, enabled, position); False when there is no such radio, it is removed or it was not stored."""
        return bool(await self._stored(lambda db: update_radio(db, id, **columns), 0, f"radio {id} could not be changed"))

    async def put_radio_settings(self, id: RadioId, values: Mapping[str, str]) -> bool:
        """A radio's own settings (key to text) in one transaction (all of it or none); its other settings stay. False when there is no such radio, it is removed or they were not stored."""
        return await self._stored(lambda db: put_radio_settings(db, id, values), False, f"the settings of radio {id} could not be stored")

    async def remove_radio(self, id: RadioId) -> bool:
        """Removes a radio and takes back what chooses it, in one transaction (radiosql.remove_radio); False when there is no such radio, it is removed already or it was not stored."""
        at = stamp(self.now())
        return bool(await self._stored(lambda db: remove_radio(db, id, at), 0, f"radio {id} could not be removed"))

    async def put_config(self, data: Settings, radios: Iterable[RadioWrite]) -> bool:
        """The station's settings (key to text) and what changed of the radios, in one transaction (all of it or none): a save of the settings. False, and nothing stored, when a radio that is not new
        is not there or is removed (a removed radio takes no change), or the database would not take them."""
        writes = list(radios)

        def put(db: Connection) -> bool:
            write_settings(db, data)
            for spec, new, columns, values in writes:
                if new:
                    insert_radio(db, spec.kind, spec.type, spec.name, spec.enabled, spec.position, id=spec.id)
                elif columns and not update_radio(db, spec.id, **columns):
                    raise _Refused
                if values and not put_radio_settings(db, spec.id, values):
                    raise _Refused
            return True
        try:
            return await self._stored(put, False, "the settings could not be stored")
        except _Refused:
            log.error("the settings could not be stored: a radio they change is not there or is removed")
            return False

    async def seed_radios(self, decide: Callable[[Settings], Sequence[tuple[RadioId, str, str, bool, int]]]) -> Sequence[tuple[RadioId, str, str, bool, int]]:
        """The stand-in's radios (radiosql.seed_radios), written in one transaction only where there is no radio at all: `decide` gives them from the settings rows that same transaction reads, so that
        what is moved is what was decided on. The radios written; none when there is a radio already, or the database would not take them, or its rows disagree (told as an error)."""
        def seed(db: Connection) -> Sequence[tuple[RadioId, str, str, bool, int]]:
            radios = decide(read_settings(db))
            return radios if seed_radios(db, radios) else ()
        try:
            return await self._stored(seed, (), "the radios of the settings could not be stored")
        except StoreError as e:                     # (radiosql.seed_radios found rows that disagree, migration 31's own check: rolled back, the daemon runs without writing a radio)
            log.error("the radios of the settings were not stored: %s", e)
            return ()

    # ---- a consistent copy, whole, while the daemon runs
    async def backup(self, dest: Path) -> bool:
        """One file, written whole to a temporary name and renamed: a half copy is never taken for a good one."""
        db = self.db
        if db is None or not db.is_open or self.path == ":memory:":
            return False
        try:
            await db.backup(dest)
        except (SqlError, OSError, DbClosed) as e:
            log.error("the backup %s failed: %s", dest, e)
            return False
        return True
