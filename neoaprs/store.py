"""The settings and radios of the one database file, used through the database thread.

Also the write-ahead log checkpoint and the copy of the file. The file is migrated before the
thread uses it.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import NamedTuple, TypeVar

from .clock import Clock, utcnow
from .configradios import radios_from_rows
from .db import Db

# StoreError is re-exported: the rest of the program imports it from here.
from .dberror import Connection, DbClosed, Row, SqlError, StoreError as StoreError
from .packetcodec import stamp
from .radiospec import RadioId, RadioSpec
from .sendonrule import Kept
from .radiosql import (
    insert_radio,
    kept_by_rows,
    of_removed_radio,
    put_kept,
    put_radio_settings,
    radio_rows,
    radio_settings,
    remove_radio,
    update_radio,
)
from .storesql import Settings, delete_setting, read_setting, read_settings, write_setting, write_settings

log = logging.getLogger("neoaprs.store")

DB_NAME = "neoaprs.sqlite"

T = TypeVar("T")


class RadioWrite(NamedTuple):
    """What a save of the settings writes of one radio: changed columns and own settings."""

    spec: RadioSpec
    columns: Mapping[str, object] = {}
    values: Mapping[str, str] = {}


class _Refused(Exception):
    """A radio of a save is missing or removed; the save is rolled back."""


def _unless_removed(db: Connection, keys: Iterable[str], write: Callable[[], None]) -> bool:
    """Call `write` unless a key belongs to a removed radio; return whether it was called."""
    if of_removed_radio(db, keys):
        return False
    write()
    return True


class Store:
    """The settings and radios, as database-thread operations; a closed store raises nothing."""

    def __init__(self, clock: Clock = utcnow) -> None:
        self.now = clock
        self.db: Db | None = None
        self.path = ""

    def use(self, db: Db, path: str | Path) -> None:
        """Use the database of `db`; the file is already migrated."""
        self.db = db
        self.path = str(path)

    def is_open(self) -> bool:
        return self.db is not None and self.db.is_open

    async def _read(self, fn: Callable[[Connection], T], default: T, what: str) -> T:
        """Run `fn` in a read transaction; return `default` if closed or unreadable (logs `what`)"""
        db = self.db
        if db is None or not db.is_open:
            return default
        try:
            return await db.read(fn)
        except (SqlError, DbClosed) as e:
            log.warning("%s: %s", what, e)
            return default

    async def _quietly(self, fn: Callable[[Connection], object], what: str) -> bool:
        """Run `fn` in a write transaction; return whether it succeeded (an error logs `what`)."""
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
        if self.is_open():
            assert self.db is not None
            try:
                await self.db.checkpoint()
            except (SqlError, DbClosed) as e:
                log.warning("the checkpoint failed: %s", e)

    async def settings(self) -> Settings:
        return await self._read(read_settings, {}, "the settings could not be read")

    async def setting(self, key: str) -> str | None:
        return await self._read(lambda db: read_setting(db, key), None, f"the setting {key} could not be read")

    async def put_setting(self, key: str, value: str) -> bool:
        """Replace one setting; False stores nothing (a removed radio's row)."""
        db = self.db
        if db is None or not db.is_open:
            return False
        try:
            written = await db.write(lambda conn: _unless_removed(conn, [key], lambda: write_setting(conn, key, value)))
        except (SqlError, DbClosed) as e:
            log.error("the setting %s could not be stored: %s", key, e)
            return False
        if not written:
            log.info("%s was not stored: its radio has been removed", key)
        return written

    async def put_settings(self, data: Settings) -> bool:
        """Write every key of `data` in one transaction; False stores nothing (a removed radio)."""
        db = self.db
        if db is None or not db.is_open:
            return False
        try:
            written = await db.write(lambda conn: _unless_removed(conn, data, lambda: write_settings(conn, data)))
        except (SqlError, DbClosed) as e:
            log.error("the settings could not be stored: %s", e)
            return False
        if not written:
            log.info("%s were not stored: a radio of theirs has been removed", ", ".join(data))
        return written

    async def delete_setting(self, key: str) -> None:
        await self._quietly(lambda db: delete_setting(db, key), f"the setting {key} could not be deleted")

    async def _stored(self, fn: Callable[[Connection], T], default: T, what: str) -> T:
        """Run `fn` in a write transaction; return `default` if closed or rejected (logs `what`)."""
        db = self.db
        if db is None or not db.is_open:
            return default
        try:
            return await db.write(fn)
        except (SqlError, DbClosed) as e:
            log.error("%s: %s", what, e)
            return default

    async def radios(self) -> tuple[RadioSpec, ...]:
        """Return every radio, removed ones too, by id; empty if unreadable."""
        return await self.read_radios() or ()

    async def read_radios(self) -> tuple[RadioSpec, ...] | None:
        """Return every radio by id; None (not empty) if unreadable, unlike a new install."""
        unread: tuple[list[Row], list[Row]] | None = None
        read = await self._read(lambda db: (radio_rows(db), radio_settings(db)), unread, "the radios could not be read")
        return None if read is None else radios_from_rows(*read)

    async def add_radio(
        self,
        kind: str,
        type: str,
        name: str,
        enabled: bool,
        position: int,
        *,
        settings: Mapping[str, str] | None = None,
        kept: Kept | None = None,
        by_rows: bool = False,
    ) -> RadioId | None:
        """Add a radio with its settings and kept state, in one transaction; return its id or None.

        With `by_rows` the kept state is worked out from the rows (a tool run without a daemon).
        """

        def add(db: Connection) -> RadioId:
            before = radios_from_rows(radio_rows(db), radio_settings(db)) if by_rows else ()
            made = insert_radio(db, kind, type, name, enabled, position)
            put_radio_settings(db, made, settings or {})
            if found := kept_by_rows(db, before) if by_rows else kept:
                put_kept(db, found)
            return made

        return await self._stored(add, None, f"the new {kind} radio could not be stored")

    async def change_radio(self, id: RadioId, /, **columns: object) -> bool:
        """Set CHANGEABLE columns of a radio; False if missing, removed or not stored."""
        return bool(
            await self._stored(lambda db: update_radio(db, id, **columns), 0, f"radio {id} could not be changed")
        )

    async def put_radio_settings(self, id: RadioId, values: Mapping[str, str]) -> bool:
        return await self._stored(
            lambda db: put_radio_settings(db, id, values), False, f"the settings of radio {id} could not be stored"
        )

    async def remove_radio(self, id: RadioId) -> bool:
        """Remove a radio and everything that selects it; False if missing or not stored."""
        at = stamp(self.now())
        return bool(await self._stored(lambda db: remove_radio(db, id, at), 0, f"radio {id} could not be removed"))

    async def put_config(self, data: Settings, radios: Iterable[RadioWrite], kept: Kept | None = None) -> bool:
        """Save settings, radio changes and kept sets in one transaction; False stores nothing.

        False if a changed radio is missing or removed, or the database rejects it.
        """
        writes = list(radios)

        def put(db: Connection) -> bool:
            write_settings(db, data)
            for spec, columns, values in writes:
                if columns and not update_radio(db, spec.id, **columns):
                    raise _Refused
                if values and not put_radio_settings(db, spec.id, values):
                    raise _Refused
            if kept:
                put_kept(db, kept)
            return True

        try:
            return await self._stored(put, False, "the settings could not be stored")
        except _Refused:
            log.error("the settings could not be stored: a radio they change is not there or is removed")
            return False

    async def backup(self, dest: Path) -> bool:
        """Copy the database to `dest` via a temporary name so a partial copy never looks whole."""
        db = self.db
        if db is None or not db.is_open or self.path == ":memory:":
            return False
        try:
            await db.backup(dest)
        except (SqlError, OSError, DbClosed) as e:
            log.error("the backup %s failed: %s", dest, e)
            return False
        return True
