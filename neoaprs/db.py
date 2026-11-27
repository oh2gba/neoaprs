"""The Db actor: one connection owned by one thread, fed by a FIFO queue.

Use `read`, `write` (one transaction), `write_nowait` (a batched append) and `close`."""

import asyncio
import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .dberror import DbClosed, DbError, NestedUse as NestedUse, StoreError as StoreError
from .dbfile import DEFAULT_BUSY_MS, connect, copy_database
from .dbstats import DbStats
from .dbthread import DbThread, Kind, Op, Tuning

log = logging.getLogger("neoaprs.db")

T = TypeVar("T")
Fn = Callable[[sqlite3.Connection], T]

NEW, OPEN, CLOSED = "new", "open", "closed"
# Poll interval of close(): the thread's notice may fail to wake the loop.
END_LOOK_SEC = 0.1
CHECKPOINTS = {
    "PASSIVE": "PRAGMA wal_checkpoint(PASSIVE)",
    "FULL": "PRAGMA wal_checkpoint(FULL)",
    "RESTART": "PRAGMA wal_checkpoint(RESTART)",
    "TRUNCATE": "PRAGMA wal_checkpoint(TRUNCATE)",
}


READ_WAIT_MS = 3000  # how long a read-only command waits for a write


class Db:
    def __init__(
        self, opener: Callable[[], sqlite3.Connection], *, name: str = "neoaprs-db", tuning: Tuning | None = None
    ) -> None:
        self._opener = opener
        self._name = name
        self._tuning = tuning or Tuning()
        self._stats = DbStats()
        self._state = NEW
        self._thread: DbThread | None = None
        self._exited: "asyncio.Future[None] | None" = None

    @classmethod
    def at(
        cls, path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, *, name: str = "neoaprs-db", tuning: Tuning | None = None
    ) -> "Db":
        """Return a Db on the database file; no migrations."""
        return cls(lambda: connect(path, busy_ms), name=name, tuning=tuning)

    async def start(self) -> None:
        """Start the thread and wait until the connection is open; an opener failure is raised."""
        if self._state != NEW:
            raise DbError("the database was started already")
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()
        exited: asyncio.Future[None] = loop.create_future()
        self._exited = exited
        self._thread = thread = DbThread(
            self._opener,
            self._tuning,
            self._stats,
            lambda e: _post(loop, ready, e),
            lambda: _post(loop, exited, None),
            self._name,
        )
        self._state = OPEN
        thread.start()
        try:
            await ready
        except BaseException as e:
            self._state = CLOSED
            thread.finish()
            # A failed opener ends the thread; on cancel it ends by itself.
            if not isinstance(e, asyncio.CancelledError):
                await _ended(thread, exited)
            raise

    async def close(self) -> None:
        """Finish everything asked, close the connection and end the thread; safe to repeat."""
        thread, exited = self._thread, self._exited
        if thread is None or exited is None:
            self._state = CLOSED
            return
        self._state = CLOSED
        thread.finish()
        await _ended(thread, exited)

    @property
    def is_open(self) -> bool:
        return self._state == OPEN

    async def read(self, fn: Fn[T]) -> T:
        """Run fn(conn) in a read transaction; return plain data, not a cursor."""
        return await self._ask(Kind.READ, fn)

    async def write(self, fn: Fn[T]) -> T:
        """Run fn(conn) in BEGIN IMMEDIATE ... COMMIT; return its result (ROLLBACK on error)."""
        return await self._ask(Kind.WRITE, fn)

    async def maintain(self, fn: Fn[T]) -> T:
        """Run fn(conn) outside a transaction (backup, checkpoint)."""
        return await self._ask(Kind.MAINT, fn)

    async def maintain_own(self, fn: Fn[T]) -> T:
        """`maintain` for a function whose statements begin a transaction of their own (VACUUM)."""
        return await self._ask(Kind.MAINT, fn, own=True)

    def write_nowait(self, fn: Fn[Any]) -> bool:
        """Queue an append and return True; False if dropped (queue full or Db closed)."""
        thread = self._thread
        if thread is None or self._state != OPEN:
            self._stats.count("dropped")
            return False
        try:
            return thread.submit(Op(Kind.APPEND, fn, time.perf_counter()))
        except DbClosed:
            self._stats.count("dropped")
            return False

    async def _ask(self, kind: Kind, fn: Fn[T], own: bool = False) -> T:
        thread = self._thread
        if thread is None or self._state != OPEN:
            raise DbClosed
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        thread.submit(Op(kind, fn, time.perf_counter(), future, loop, own))
        if kind is not Kind.WRITE:
            return await future
        try:
            return await asyncio.shield(future)  # a cancelled asker must not cancel a queued write
        except asyncio.CancelledError:
            future.add_done_callback(self._cut_off)
            raise

    def _cut_off(self, future: "asyncio.Future[Any]") -> None:
        """Log the outcome of a write whose asker was cancelled; the write happened anyway."""
        self._stats.count("cut")
        error = future.exception()
        if error is None:
            log.warning("a write of the database whose asker was cancelled before the answer came is committed")
        else:
            log.error("a write of the database whose asker was cancelled before the answer came has failed: %s", error)

    async def backup(self, dest: Path) -> None:
        """Write a checked copy of the database to `dest`; raise sqlite3.Error or OSError."""
        await self.maintain(lambda conn: copy_database(conn, dest))

    async def checkpoint(self, mode: str = "TRUNCATE") -> tuple[int, int, int]:
        """Run PRAGMA wal_checkpoint(mode); return (busy, frames in the log, frames moved)."""
        statement = CHECKPOINTS.get(mode)
        if statement is None:
            raise ValueError(mode)
        return await self.maintain(lambda conn: tuple(conn.execute(statement).fetchone()))

    async def barrier(self) -> None:
        """Return when everything asked before is done."""
        await self.maintain(lambda conn: None)

    def stats(self) -> dict[str, object]:
        thread = self._thread
        return {**self._stats.snapshot(), "queued": thread.pending() if thread is not None else 0, "state": self._state}


async def _ended(thread: DbThread, exited: "asyncio.Future[None]") -> None:
    """Return when the thread has ended; it polls, as a cross-thread notice can be missed."""
    while not exited.done() and thread.is_alive():
        await asyncio.wait((exited,), timeout=END_LOOK_SEC)
    thread.join()


def _post(loop: asyncio.AbstractEventLoop, future: "asyncio.Future[None]", error: BaseException | None) -> None:
    """Settle a loop future from the database thread."""

    def settle() -> None:
        if not future.done():
            future.set_result(None) if error is None else future.set_exception(error)

    try:
        loop.call_soon_threadsafe(settle)
    except RuntimeError:
        pass  # the loop is closed
