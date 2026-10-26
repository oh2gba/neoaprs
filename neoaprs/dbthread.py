"""The thread that owns the connection, and the queue that feeds it (see db.py for what the program sees).

One connection, made in this thread, used in this thread only. Everything that touches the database is an *operation* on one FIFO queue, so the order in which the
program asked is the order in which the database did it (no flush, no lock, no "write behind"):

    READ      fn(conn) inside a read transaction on a connection that cannot write (`query_only`): one snapshot for all the statements of the function
    WRITE     BEGIN IMMEDIATE, fn(conn), COMMIT: all of it or none; ROLLBACK when fn raises, and the error goes to whoever waits
    APPEND    a hot write nobody waits for (a heard packet): the appends that follow each other are one transaction, each one in a savepoint of its own, so
              that an append which cannot be made costs that append and not the others
    MAINT     fn(conn) outside a transaction: a backup, a checkpoint
    STOP      everything before it has been done: the connection is closed and the thread ends

A function that is run may not begin, commit or roll back a transaction (the authorizer refuses it, and the statements of this file are spelled so that a function cannot reach
their entries in the statement cache by chance): the transaction is the thread's. Whoever waits is answered on the event loop with `call_soon_threadsafe`.
"""
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
    tick: float = 1.0               # appends are collected this long (or until something else is asked, or batch_max) before they are committed: one sync to the disk for all of them
    batch_max: int = 2000           # appends in one transaction, at most
    max_appends: int = 200_000      # appends waiting at most; beyond it `write_nowait` says no
    attempts: int = 3               # a batch that cannot be committed (the file is locked, the disk is full) is tried this many times, retry_sec * n apart, and then dropped; once only while the queue closes
    retry_sec: float = 0.5
    slow_sec: float = 0.5           # an operation that runs longer is counted and (the first, the tenth, every hundredth) told in the log


@dataclass(eq=False)
class Op:
    kind: Kind
    fn: Callable[[sqlite3.Connection], Any] | None
    queued: float
    future: "asyncio.Future[Any] | None" = None
    loop: asyncio.AbstractEventLoop | None = None


def environmental(e: BaseException) -> bool:
    """An error of the place (the file is locked, the disk is full, the file is damaged) and not of the statement: trying again later may work. IntegrityError, DataError and
    the like are the statement's: they will happen again."""
    return isinstance(e, (sqlite3.OperationalError, sqlite3.InternalError)) or type(e) is sqlite3.DatabaseError


def often(n: int) -> bool:
    """The first, the tenth and every hundredth time: said, but not every second for ever."""
    return n in (1, 10) or n % 100 == 0


class DbThread(threading.Thread):
    def __init__(self, opener: Callable[[], sqlite3.Connection], tuning: Tuning, stats: DbStats, ready: Callable[[BaseException | None], None], exited: Callable[[], None], name: str) -> None:
        super().__init__(name=name, daemon=True)           # daemon: a program that forgot close() still ends; what was acknowledged is on the disk already
        self._opener, self.tuning, self.stats, self._ready, self._exited = opener, tuning, stats, ready, exited
        self._q: queue.SimpleQueue[Op] = queue.SimpleQueue()
        self._lock = threading.Lock()                       # the queue is closed and the appends are counted under it
        self._closing = False
        self._appends = 0
        self._own = False                                   # the thread is running one of its own transaction statements (the authorizer lets those through)
        self._query_only = False

    # ---- any thread: putting work on the queue
    def submit(self, op: Op) -> bool:
        """False only for an append that the full queue refuses. Raises DbClosed once the queue is closed, NestedUse when the database thread itself asks."""
        if self.ident is not None and threading.get_ident() == self.ident:
            raise NestedUse("the database thread was asked to do something from inside a function it is running: do it with the connection that function was given")
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
                log.error("the database queue holds %d appends and is full: %d appends dropped so far", self.tuning.max_appends, dropped)
            return False
        self.stats.depth(self._q.qsize())
        return True

    def finish(self) -> None:
        """Closes the queue behind everything that is in it: the thread does all of that, then ends."""
        with self._lock:
            if not self._closing:
                self._closing = True
                self._q.put(Op(Kind.STOP, None, time.perf_counter()))

    def pending(self) -> int:
        return self._q.qsize()

    # ---- the thread
    def run(self) -> None:
        try:
            conn = self._open()
        except BaseException as e:
            self._ready(e)
            self._abandon()                                 # what was asked while the file was being opened gets its answer too
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
            raise DbError("the connection must be made with isolation_level=None: the transactions are the database thread's, not sqlite3's")
        conn.set_authorizer(self._authorize)
        return conn

    def _authorize(self, action: int, arg1: str | None, arg2: str | None, dbname: str | None, source: str | None) -> int:
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
        """Whatever is still queued when the thread ends (it failed) is answered, not left to wait for ever."""
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

    # ---- one awaited operation
    def _run_one(self, conn: sqlite3.Connection, op: Op) -> None:
        if op.future is not None and op.future.cancelled():
            self.stats.count("withdrawn")                   # the caller gave up before it began: it did not happen
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
            return op.fn(conn)
        reading = op.kind is Kind.READ
        self._set_query_only(conn, reading)
        return self._transaction(conn, op.fn, BEGIN_READ if reading else BEGIN_WRITE)

    def _begin(self, conn: sqlite3.Connection, begin: str) -> None:
        self._rollback(conn)                                # nothing is open between operations; if a failed ROLLBACK left something open, it is closed now and not carried into this one
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
            pass                                            # the loop is closed: nobody waits for the answer

    def _settle(self, future: "asyncio.Future[Any]", result: Any, error: BaseException | None, posted: float) -> None:
        """On the event loop: the answer reaches the one who waits. How long it took the loop to get here is the stall the loop had."""
        self.stats.delivered(time.perf_counter() - posted)
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    # ---- appends: one transaction for all that are waiting
    def _batch(self, conn: sqlite3.Connection, first: Op) -> Op | None:
        """Collects the appends that follow `first` for a tick (the queue is read in order: the first operation of another kind ends the batch at once, so that nothing that
        was asked after an append can be done before it), commits them, and returns the operation that ended the batch."""
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
                self._reply(ender, None, DbClosed("the database thread has stopped"))          # (taken off the queue already: the thread's end would not find it there)
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
            self.stats.done(Kind.APPEND.value, started - batch[0].queued, time.perf_counter() - started, False, len(batch))
            self.stats.count("batches")
            return
        self.stats.count("lost", len(batch))

    def _try_again(self, e: sqlite3.Error, attempt: int, size: int) -> bool:
        """After a failed attempt at a batch: whether there is another, after a wait that grows. Not while the queue is closing: the STOP stands behind the batch, the lock is another
        process's that no wait of ours hurries, and the unit kills a stop that takes longer than TimeoutStopSec (10 s), where three attempts with the busy time of 3 s took 10.5 s."""
        with self._lock:
            closing = self._closing
        if attempt >= self.tuning.attempts or closing:
            log.error("the database could not commit %d appends (%s): they are lost%s", size, e, " (the database is closing: no second attempt)" if closing else "")
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
        """In a savepoint: an append that fails for its own reasons is undone alone and counted; one that fails for the place's reasons ends the attempt."""
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
