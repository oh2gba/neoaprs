"""The Db actor: ONE connection owned by ONE thread, and every statement of the program an operation on that thread's queue.

    db = Db.at(path)                     # or Db(opener): opener() makes the connection (migrations and all) in the database thread
    await db.start()
    n = await db.read(lambda conn: conn.execute("SELECT COUNT(*) FROM packet").fetchone()[0])
    await db.write(lambda conn: conn.execute("INSERT INTO ..."))        # BEGIN IMMEDIATE, the function, COMMIT; the answer comes after the commit has reached the disk
    db.write_nowait(lambda conn: conn.execute("INSERT INTO ..."))       # nobody waits: the packet log's hot appends
    await db.backup(dest)                # a whole checked copy, in the same thread
    await db.close()                     # everything asked before is done, then the connection is closed

What it gives, by construction and not by discipline:

* **Order.** The queue is FIFO and there is one thread, so a read sees every write asked before it, an append asked before a write is on the disk before the write is, and nobody
  flushes anything or holds a lock. (The functions run in the thread, between other operations: they must not wait for the event loop or for each other.)
* **Transactions.** A write is `BEGIN IMMEDIATE` ... `COMMIT`; when the function raises, `ROLLBACK`, and the error reaches the one who awaits it exactly as it was raised
  (`sqlite3.IntegrityError` stays an IntegrityError; callers' `except` clauses keep working). A function may not begin, commit or roll back a transaction itself, and may not ask the
  Db for anything (NestedUse): it has the connection it was given. A read runs in a read transaction of a connection that cannot write.
* **Durable.** What `await db.write(...)` returned has been committed with `synchronous=FULL` (dbfile.configure), as a message acknowledged to the operator must be.
* **Appends** (`write_nowait`): returns at once; the appends that follow each other are collected for `tuning.tick` seconds and committed as one transaction (one sync to the disk), each in its
  own savepoint. They are in the order they were made and before anything made after them. They are *not* durable until committed: a crash loses up to a tick of them. The queue of appends is bounded (`tuning.max_appends`); beyond it `write_nowait` returns False and the append is dropped and counted: the
  newest is dropped, not the oldest, so that a producer is never slowed and the queue never grows without end. A batch that cannot be committed (locked file, full disk) is
  rolled back whole and tried again `tuning.attempts` times, then dropped, counted and told in the log (once the queue is closing it is tried once: the stop must end inside the unit's
  TimeoutStopSec, and a lock another process holds is not hurried by waiting); an append that fails for its own reasons (a constraint) is undone alone.
  Awaited operations are never refused or dropped: the caller waits.
* **Shutdown.** `close()` stops taking work, does what was queued (the last batch of appends included), closes the connection and ends the thread; asking after that is DbClosed
  (a StoreError, "the database is not open"). A program that never calls close() still ends (the thread is a daemon), and loses only appends of the last tick.
* **Cancelling** an `await` before the thread has begun the operation withdraws a read or a maintenance operation (it did not happen). A write is never withdrawn: once it is on the queue
  it happens, at the latest in the drain of `close()`; the one who asked is cancelled all the same and never sees the answer, so what the write ended with is told in the log and
  counted (`cut`). After the thread has begun an operation it completes and the answer is dropped.
* **Measured.** `stats()`: how long operations waited in the queue, how long they ran, how long the event loop took to take the answers (the stall of the loop), the counts.
"""
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
CHECKPOINTS = {"PASSIVE": "PRAGMA wal_checkpoint(PASSIVE)", "FULL": "PRAGMA wal_checkpoint(FULL)", "RESTART": "PRAGMA wal_checkpoint(RESTART)", "TRUNCATE": "PRAGMA wal_checkpoint(TRUNCATE)"}


class Db:
    def __init__(self, opener: Callable[[], sqlite3.Connection], *, name: str = "neoaprs-db", tuning: Tuning | None = None) -> None:
        self._opener = opener
        self._name = name
        self._tuning = tuning or Tuning()
        self._stats = DbStats()
        self._state = NEW
        self._thread: DbThread | None = None
        self._exited: "asyncio.Future[None] | None" = None

    @classmethod
    def at(cls, path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, *, name: str = "neoaprs-db", tuning: Tuning | None = None) -> "Db":
        """A Db on the database file as dbfile.connect sets it up (WAL, synchronous=FULL ...); no migrations: those are the Store's."""
        return cls(lambda: connect(path, busy_ms), name=name, tuning=tuning)

    # ---- life
    async def start(self) -> None:
        """Starts the thread and waits until the connection is open. What the opener raises (a StoreError, an sqlite3.Error) is raised here and the Db stays closed."""
        if self._state != NEW:
            raise DbError("the database was started already")
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()
        exited: asyncio.Future[None] = loop.create_future()
        self._exited = exited
        self._thread = thread = DbThread(self._opener, self._tuning, self._stats, lambda e: _post(loop, ready, e), lambda: _post(loop, exited, None), self._name)
        self._state = OPEN
        thread.start()
        try:
            await ready
        except BaseException as e:
            self._state = CLOSED
            thread.finish()
            if not isinstance(e, asyncio.CancelledError):           # the opener failed: the thread is ending (cancelled: it ends by itself when the connection is open)
                await exited
                thread.join()
            raise

    async def close(self) -> None:
        """Does everything that was asked, closes the connection and ends the thread. Can be called again; the second call waits for the first."""
        thread, exited = self._thread, self._exited
        if thread is None or exited is None:
            self._state = CLOSED
            return
        self._state = CLOSED
        thread.finish()
        await exited
        thread.join()

    @property
    def is_open(self) -> bool:
        return self._state == OPEN

    # ---- asking
    async def read(self, fn: Fn[T]) -> T:
        """fn(conn) in the database thread, in a read transaction of a connection that cannot write. Return plain data, not a cursor."""
        return await self._ask(Kind.READ, fn)

    async def write(self, fn: Fn[T]) -> T:
        """fn(conn) in the database thread inside BEGIN IMMEDIATE ... COMMIT; the result when the commit is on the disk, the error of fn (after ROLLBACK) or of the commit."""
        return await self._ask(Kind.WRITE, fn)

    async def maintain(self, fn: Fn[T]) -> T:
        """fn(conn) outside a transaction, in the database thread: what cannot run inside one (a backup, a checkpoint)."""
        return await self._ask(Kind.MAINT, fn)

    def write_nowait(self, fn: Fn[Any]) -> bool:
        """Queues an append that nobody waits for (see the module's notes). True: queued. False: dropped (the queue is full, or the Db is closed). Raises NestedUse from inside a function."""
        thread = self._thread
        if thread is None or self._state != OPEN:
            self._stats.count("dropped")
            return False
        try:
            return thread.submit(Op(Kind.APPEND, fn, time.perf_counter()))
        except DbClosed:
            self._stats.count("dropped")
            return False

    async def _ask(self, kind: Kind, fn: Fn[T]) -> T:
        thread = self._thread
        if thread is None or self._state != OPEN:
            raise DbClosed
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        thread.submit(Op(kind, fn, time.perf_counter(), future, loop))
        if kind is not Kind.WRITE:
            return await future
        try:
            return await asyncio.shield(future)              # a cancel of the asker does not reach the write: once on the queue it happens (the drain of close() included)
        except asyncio.CancelledError:
            future.add_done_callback(self._cut_off)
            raise

    def _cut_off(self, future: "asyncio.Future[Any]") -> None:
        """A write whose asker was cancelled before it saw the answer (the daemon's stop cancels the tasks that carry the page's commands): it happened all the same,
        and what it ended with is said here, since nobody else sees it."""
        self._stats.count("cut")
        error = future.exception()
        if error is None:
            log.warning("a write of the database whose asker was cancelled before the answer came is committed")
        else:
            log.error("a write of the database whose asker was cancelled before the answer came has failed: %s", error)

    # ---- the file
    async def backup(self, dest: Path) -> None:
        """A whole checked copy of the database at `dest`, written, synced and renamed by the database thread (dbfile.copy_database). Raises sqlite3.Error or OSError."""
        await self.maintain(lambda conn: copy_database(conn, dest))

    async def checkpoint(self, mode: str = "TRUNCATE") -> tuple[int, int, int]:
        """PRAGMA wal_checkpoint(mode): (busy, frames in the log, frames moved). TRUNCATE: what is committed is in the database file itself."""
        statement = CHECKPOINTS.get(mode)
        if statement is None:
            raise ValueError(mode)
        return await self.maintain(lambda conn: tuple(conn.execute(statement).fetchone()))

    async def barrier(self) -> None:
        """Returns when everything asked before is done (the appends committed). For tests and for a program that must know; nothing needs it for order."""
        await self.maintain(lambda conn: None)

    # ---- looking
    def stats(self) -> dict[str, object]:
        thread = self._thread
        return {**self._stats.snapshot(), "queued": thread.pending() if thread is not None else 0, "state": self._state}


def _post(loop: asyncio.AbstractEventLoop, future: "asyncio.Future[None]", error: BaseException | None) -> None:
    """From the database thread: settles a future of the loop."""
    def settle() -> None:
        if not future.done():
            future.set_result(None) if error is None else future.set_exception(error)
    try:
        loop.call_soon_threadsafe(settle)
    except RuntimeError:
        pass                                                # the loop is closed
