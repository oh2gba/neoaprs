"""What the logs on the database thread share (the packet log, packetlog.py, and the message log, messagelog.py): the `Db` they run on once the controller has opened it, and the ways they ask it,
each of which says no instead of raising when the database is not open or would not take the statement: a read with a default, a write with a default, an append nobody waits for (counted in
`dropped` when the thread would not take it), and the rows of a table read into values with the ones this program did not write left out."""
import logging
from collections.abc import Callable, Iterable

from .clock import Clock
from .db import Db
from .dberror import Connection, DbClosed, SqlError


class DbLog:
    def __init__(self, db: Db | None, clock: Clock, logger: logging.Logger, unreadable: str) -> None:
        self.db = db
        self.clock = clock
        self.dropped = 0                                 # appends the database thread would not take (its queue was full or it was closed)
        self._logger = logger
        self._unreadable = unreadable                    # what the log says when a read fails: "the packet log could not be read"

    def use(self, db: Db) -> None:
        """The log in the database the Db is the thread of (the file is migrated already)."""
        self.db = db

    def is_open(self) -> bool:
        return self.db is not None and self.db.is_open

    def _append(self, fn: Callable[[Connection], object]) -> bool:
        """An append that nobody waits for, in order with everything else the thread was asked; False (and counted) when it could not be queued."""
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
        """fn in a write transaction, awaited; `failed` when the database is not open or would not take it (logged as `what`)."""
        db = self.db
        if db is None or not db.is_open:
            return failed
        try:
            return await db.write(fn)
        except (SqlError, DbClosed) as e:
            self._logger.error("%s: %s", what, e)
            return failed

    async def _done(self, fn: Callable[[Connection], object], what: str) -> bool:
        """Whether the write was done."""
        def run(conn: Connection) -> bool:
            fn(conn)
            return True
        return await self._write(run, False, what)

    def _decoded[R, V](self, rows: Iterable[R], of: Callable[[R], V], table: str) -> list[V]:
        """The values of the rows; a row this program did not write (`of` raises) is left out and told."""
        found: list[V] = []
        for row in rows:
            try:
                found.append(of(row))
            except Exception as e:
                self._logger.warning("a row of the %s table could not be read (%s: %s); it is left out", table, type(e).__name__, e)
        return found

