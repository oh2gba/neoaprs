"""Base of the logs that run on the database thread (packetlog.py, messagelog.py, bulletinlog.py).

Holds the `Db` and the ways to ask it. Each returns a default or False instead of raising when the
database is not open or refuses the statement."""

import logging
from collections.abc import Callable, Iterable

from .clock import Clock
from .db import Db
from .dberror import Connection, DbClosed, SqlError


class DbLog:
    def __init__(self, db: Db | None, clock: Clock, logger: logging.Logger, unreadable: str) -> None:
        self.db = db
        self.clock = clock
        self.dropped = 0  # appends refused by a full or closed queue
        self._logger = logger
        self._unreadable = unreadable  # logged when a read fails

    def use(self, db: Db) -> None:
        """Use this Db, whose file is already migrated."""
        self.db = db

    def is_open(self) -> bool:
        return self.db is not None and self.db.is_open

    def _append(self, fn: Callable[[Connection], object]) -> bool:
        """Queue an append; return False, counting it in `dropped`, if it could not be queued."""
        db = self.db
        if db is None or not db.write_nowait(fn):
            self.dropped += 1
            return False
        return True

    async def _read[T](self, fn: Callable[[Connection], T], default: T) -> T:
        db = self.db
        if db is None or not db.is_open:
            return default
        try:
            return await db.read(fn)
        except (SqlError, DbClosed) as e:
            self._logger.warning("%s: %s", self._unreadable, e)
            return default

    async def _write[T](self, fn: Callable[[Connection], T], failed: T, what: str) -> T:
        """Run fn in a write transaction; return `failed` (logging `what`) if the database is
        closed or refuses it."""
        db = self.db
        if db is None or not db.is_open:
            return failed
        try:
            return await db.write(fn)
        except (SqlError, DbClosed) as e:
            self._logger.error("%s: %s", what, e)
            return failed

    async def _done(self, fn: Callable[[Connection], object], what: str) -> bool:
        """Return whether the write was done."""

        def run(conn: Connection) -> bool:
            fn(conn)
            return True

        return await self._write(run, False, what)

    def _decoded[R, V](self, rows: Iterable[R], of: Callable[[R], V], table: str) -> list[V]:
        """Return the values of the rows; a row that `of` cannot read is logged and left out."""
        found: list[V] = []
        for row in rows:
            try:
                found.append(of(row))
            except Exception as e:
                self._logger.warning(
                    "a row of the %s table could not be read (%s: %s); it is left out", table, type(e).__name__, e
                )
        return found
