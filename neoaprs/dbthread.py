"""The thread that owns the database connection and the FIFO queue that feeds it (see db.py).

Operations are READ, WRITE, APPEND (batched, each in a savepoint), MAINT and STOP."""

import asyncio
import logging
import queue
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .dberror import DbClosed, DbError, NestedUse
from .dbstats import DbStats

log = logging.getLogger("neoaprs.db")

# The marker comment keeps a user function from hitting these statements' cache entries.
BEGIN_WRITE = "BEGIN IMMEDIATE /*neoaprs-db*/"
BEGIN_READ = "BEGIN /*neoaprs-db*/"
COMMIT = "COMMIT /*neoaprs-db*/"
ROLLBACK = "ROLLBACK /*neoaprs-db*/"


class Kind(Enum):
    READ = "reads"
    WRITE = "writes"
    APPEND = "appends"
    MAINT = "maintenance"
    STOP = "stop"


@dataclass(frozen=True)
class Tuning:
    # Appends are collected this long (or until another operation or batch_max), one sync for all.
    tick: float = 1.0
    batch_max: int = 2000  # most appends in one transaction
    # Most appends waiting; beyond it `write_nowait` returns False.
    max_appends: int = 200_000
    # Attempts at a failing batch, retry_sec * n apart, then it is dropped.
    attempts: int = 3
    retry_sec: float = 0.5
    slow_sec: float = 0.5  # a longer operation is counted and sometimes logged


@dataclass(eq=False)
class Op:
    kind: Kind
    fn: Callable[[sqlite3.Connection], Any] | None
    queued: float
    future: "asyncio.Future[Any] | None" = None
    loop: asyncio.AbstractEventLoop | None = None
    # a maintenance function whose statements begin a transaction of their own (VACUUM)
    own: bool = False


# Result codes (low byte of `sqlite_errorcode`) that come from the environment, not the statement:
# locked, no memory, read-only, disk fault, full, cannot open, corrupt, not a database, WAL
# protocol.
PLACE_CODES = frozenset(
    {
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
        sqlite3.SQLITE_NOMEM,
        sqlite3.SQLITE_READONLY,
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_FULL,
        sqlite3.SQLITE_CANTOPEN,
        sqlite3.SQLITE_CORRUPT,
        sqlite3.SQLITE_NOTADB,
        sqlite3.SQLITE_PROTOCOL,
    }
)


def environmental(e: BaseException) -> bool:
    """Return whether the error is environmental (locked, full, damaged), so a retry may work.

    Statement errors recur. An error without a SQLite result code counts as environmental."""
    if not (isinstance(e, (sqlite3.OperationalError, sqlite3.InternalError)) or type(e) is sqlite3.DatabaseError):
        return False
    code = getattr(e, "sqlite_errorcode", None)
    return code is None or code & 0xFF in PLACE_CODES


def often(n: int) -> bool:
    """Return True for the first, the tenth and every hundredth call, to limit log volume."""
    return n in (1, 10) or n % 100 == 0


class DbThread(threading.Thread):
    def __init__(
        self,
        opener: Callable[[], sqlite3.Connection],
        tuning: Tuning,
        stats: DbStats,
        ready: Callable[[BaseException | None], None],
        exited: Callable[[], None],
        name: str,
    ) -> None:
        super().__init__(name=name, daemon=True)  # daemon: a program that never closes still ends
        self._opener, self.tuning, self.stats, self._ready, self._exited = opener, tuning, stats, ready, exited
        self._q: queue.SimpleQueue[Op] = queue.SimpleQueue()
        self._lock = threading.Lock()  # guards the closed flag and the append count
        self._closing = False
        self._appends = 0
        self._own = False  # set while running the thread's own transaction statement
        self._query_only = False

    # Any thread: put work on the queue.
    def submit(self, op: Op) -> bool:
        """Queue `op`; return False only for an append refused by a full queue."""
        if self.ident is not None and threading.get_ident() == self.ident:
            raise NestedUse(
                "the database thread was asked to do something from inside a function it is running: do it with the connection that function was given"
            )
        with self._lock:
            if self._closing:
                raise DbClosed
            full = op.kind is Kind.APPEND and self._appends >= self.tuning.max_appends
            if not full:
                self._appends += op.kind is Kind.APPEND
                self._q.put(op)
        if full:
            dropped = self.stats.count("dropped")
            if often(dropped):
                log.error(
                    "the database queue holds %d appends and is full: %d appends dropped so far",
                    self.tuning.max_appends,
                    dropped,
                )
            return False
        self.stats.depth(self._q.qsize())
        return True

    def finish(self) -> None:
        """Close the queue behind everything in it; the thread does all of that, then ends."""
        with self._lock:
            if not self._closing:
                self._closing = True
                self._q.put(Op(Kind.STOP, None, time.perf_counter()))

    def pending(self) -> int:
        return self._q.qsize()

    # The thread.
    def run(self) -> None:
        try:
            conn = self._open()
        except BaseException as e:
            self._ready(e)
            self._abandon()  # answer what was asked during the open
            self._exited()
            return
        self._ready(None)
        try:
            self._serve(conn)
        except BaseException:
            log.exception("the database thread failed; what is queued is answered with an error")
        finally:
            self._abandon()
            self._close(conn)
            self._exited()

    def _open(self) -> sqlite3.Connection:
        conn = self._opener()
        if conn.isolation_level is not None:
            conn.close()
            raise DbError(
                "the connection must be made with isolation_level=None: the transactions are the database thread's, not sqlite3's"
            )
        conn.set_authorizer(self._authorize)
        return conn

    def _authorize(
        self, action: int, arg1: str | None, arg2: str | None, dbname: str | None, source: str | None
    ) -> int:
        if action == sqlite3.SQLITE_TRANSACTION and not self._own:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def _close(self, conn: sqlite3.Connection) -> None:
        try:
            if conn.in_transaction:
                self._sql(conn, ROLLBACK)
            conn.close()
        except sqlite3.Error as e:
            log.error("the database could not be closed cleanly: %s", e)

    def _abandon(self) -> None:
        """Answer whatever is still queued when the thread ends."""
        with self._lock:
            self._closing = True
        while True:
            try:
                op = self._q.get_nowait()
            except queue.Empty:
                return
            self._reply(op, None, DbClosed("the database thread has stopped"))

    def _serve(self, conn: sqlite3.Connection) -> None:
        op: Op | None = None
        while True:
            op = op or self._q.get()
            if op.kind is Kind.STOP:
                return
            if op.kind is Kind.APPEND:
                op = self._batch(conn, op)
            else:
                self._run_one(conn, op)
                op = None

    # One awaited operation.
    def _run_one(self, conn: sqlite3.Connection, op: Op) -> None:
        if op.future is not None and op.future.cancelled():
            self.stats.count("withdrawn")  # cancelled before it began: it did not happen
            return
        started = time.perf_counter()
        result: Any = None
        error: BaseException | None = None
        try:
            result = self._execute(conn, op)
        except BaseException as e:
            error = e
        ran = time.perf_counter() - started
        self.stats.done(op.kind.value, started - op.queued, ran, error is not None)
        self._slow(op.kind, ran)
        self._reply(op, result, error)

    def _execute(self, conn: sqlite3.Connection, op: Op) -> Any:
        assert op.fn is not None
        if op.kind is Kind.MAINT:
            self._set_query_only(conn, False)
            self._own = op.own
            try:
                return op.fn(conn)
            finally:
                self._own = False
        reading = op.kind is Kind.READ
        self._set_query_only(conn, reading)
        return self._transaction(conn, op.fn, BEGIN_READ if reading else BEGIN_WRITE)

    def _begin(self, conn: sqlite3.Connection, begin: str) -> None:
        self._rollback(conn)  # a failed ROLLBACK must not leak into this operation
        self._sql(conn, begin)

    def _transaction(self, conn: sqlite3.Connection, fn: Callable[[sqlite3.Connection], Any], begin: str) -> Any:
        self._begin(conn, begin)
        try:
            result = fn(conn)
            if not conn.in_transaction:
                raise DbError("the function ended its transaction itself")
            self._sql(conn, COMMIT)
        except BaseException:
            self._rollback(conn)
            raise
        return result

    def _sql(self, conn: sqlite3.Connection, text: str) -> None:
        self._own = True
        try:
            conn.execute(text)
        finally:
            self._own = False

    def _rollback(self, conn: sqlite3.Connection) -> None:
        if conn.in_transaction:
            try:
                self._sql(conn, ROLLBACK)
            except sqlite3.Error as e:
                log.error("the transaction could not be rolled back: %s", e)

    def _set_query_only(self, conn: sqlite3.Connection, on: bool) -> None:
        if self._query_only != on:
            conn.execute("PRAGMA query_only=ON" if on else "PRAGMA query_only=OFF")
            self._query_only = on

    def _slow(self, kind: Kind, ran: float) -> None:
        if ran > self.tuning.slow_sec and often(self.stats.count("slow")):
            log.warning("a %s of the database ran for %.2f s: the others waited for it", kind.name.lower(), ran)

    def _reply(self, op: Op, result: Any, error: BaseException | None) -> None:
        if op.loop is None or op.future is None:
            return
        try:
            op.loop.call_soon_threadsafe(self._settle, op.future, result, error, time.perf_counter())
        except RuntimeError:
            pass  # the loop is closed

    def _settle(self, future: "asyncio.Future[Any]", result: Any, error: BaseException | None, posted: float) -> None:
        """Deliver the answer on the event loop and record the loop delay."""
        self.stats.delivered(time.perf_counter() - posted)
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    # Appends: one transaction for all that are waiting.
    def _batch(self, conn: sqlite3.Connection, first: Op) -> Op | None:
        """Commit the appends following `first` for a tick; return the operation ending the batch.

        An operation of another kind ends the batch at once."""
        batch = [first]
        stop_at = time.perf_counter() + self.tuning.tick
        ender: Op | None = None
        while len(batch) < self.tuning.batch_max:
            try:
                nxt = self._q.get(timeout=max(0.0, stop_at - time.perf_counter()))
            except queue.Empty:
                break
            if nxt.kind is not Kind.APPEND:
                ender = nxt
                break
            batch.append(nxt)
        try:
            self._commit_batch(conn, batch)
        except BaseException:
            if ender is not None:
                # Already off the queue, so the thread's end would miss it.
                self._reply(ender, None, DbClosed("the database thread has stopped"))
            raise
        with self._lock:
            self._appends -= len(batch)
        return ender

    def _commit_batch(self, conn: sqlite3.Connection, batch: list[Op]) -> None:
        started = time.perf_counter()
        for attempt in range(1, self.tuning.attempts + 1):
            try:
                self._attempt(conn, batch)
            except sqlite3.Error as e:
                if self._try_again(e, attempt, len(batch)):
                    continue
                break
            self.stats.done(
                Kind.APPEND.value, started - batch[0].queued, time.perf_counter() - started, False, len(batch)
            )
            self.stats.count("batches")
            return
        self.stats.count("lost", len(batch))

    def _try_again(self, e: sqlite3.Error, attempt: int, size: int) -> bool:
        """Return whether to retry a failed batch; not while closing (the stop must end in time)."""
        with self._lock:
            closing = self._closing
        if attempt >= self.tuning.attempts or closing:
            log.error(
                "the database could not commit %d appends (%s): they are lost%s",
                size,
                e,
                " (the database is closing: no second attempt)" if closing else "",
            )
            return False
        if often(self.stats.count("retried")):
            log.warning("the database could not commit %d appends (%s): they are tried again", size, e)
        time.sleep(self.tuning.retry_sec * attempt)
        return True

    def _attempt(self, conn: sqlite3.Connection, batch: list[Op]) -> None:
        self._set_query_only(conn, False)
        self._begin(conn, BEGIN_WRITE)
        try:
            for op in batch:
                self._append_one(conn, op)
            self._sql(conn, COMMIT)
        except BaseException:
            self._rollback(conn)
            raise

    def _append_one(self, conn: sqlite3.Connection, op: Op) -> None:
        """Run an append in a savepoint; a statement error undoes it alone, others raise."""
        assert op.fn is not None
        conn.execute("SAVEPOINT append")
        try:
            op.fn(conn)
        except Exception as e:
            conn.execute("ROLLBACK TO append")
            conn.execute("RELEASE append")
            if environmental(e):
                raise
            if often(self.stats.count("poisoned")):
                log.error("an append to the database failed and was dropped (%s: %s)", type(e).__name__, e)
            return
        conn.execute("RELEASE append")
