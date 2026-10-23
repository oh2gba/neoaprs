"""The one database file: everything NeoAPRS keeps (the settings here; the packets and the stations are packetlog.py's, the messages and the preferences of the stations messagelog.py's). The only
thing outside it is the log of the program itself, a rotating text file.

This is the part of it that the daemon uses through the database thread (db.py): the settings, the checkpoint of the write-ahead log and the copy of the file. The file is brought up to
date before the thread uses it, by the migrations (migrations.py).
"""
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from .clock import Clock, utcnow
from .db import Db
from .dberror import Connection, DbClosed, SqlError, StoreError as StoreError           # (kept here: the names the rest of the program imports them by)
from .storesql import Settings, delete_setting, read_setting, read_settings, write_setting, write_settings

log = logging.getLogger("neoaprs.store")

DB_NAME = "neoaprs.sqlite"

T = TypeVar("T")


class Store:
    """The settings of the one database, on the database thread (db.py): every method is an operation of the thread, awaited by the caller, in the order it was asked. A store whose
    database is not open says no and does not raise: it has no settings and keeps nothing. The statements are those of storesql.py."""

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

    async def _read(self, fn: Callable[[Connection], T], default: T) -> T:
        """fn on the thread, in a read transaction; `default` when the database is not open or cannot be read."""
        db = self.db
        if db is None or not db.is_open:
            return default
        try:
            return await db.read(fn)
        except (SqlError, DbClosed):
            return default

    async def _quietly(self, fn: Callable[[Connection], object]) -> bool:
        """fn on the thread, in a write transaction; whether it was done (an error of the database is not raised)."""
        db = self.db
        if db is None or not db.is_open:
            return False
        try:
            await db.write(fn)
        except (SqlError, DbClosed):
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
        return await self._read(read_settings, {})

    async def setting(self, key: str) -> str | None:
        return await self._read(lambda db: read_setting(db, key), None)

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
        await self._quietly(lambda db: delete_setting(db, key))

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
