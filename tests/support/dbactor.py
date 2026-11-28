"""Shared by the Db actor tests: a Db on a table of numbers, failing connections, a leak guard."""

import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, TypeVar

from neoaprs.db import Db
from neoaprs.dbfile import connect
from neoaprs.dbthread import DbThread, Tuning
from tests.support.safety import FaultyConnection, Injected as Injected, raw
from tests.support.patience import PATIENCE_SEC

T = TypeVar("T")
THREAD_PREFIX = "neoaprs-db"
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS t (n INTEGER PRIMARY KEY, v TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS pair (n INTEGER NOT NULL, side INTEGER NOT NULL, PRIMARY KEY (n, side))",
)
# Appends commit after 20 ms; a failed batch is retried after 10 ms.
QUICK = Tuning(tick=0.02, retry_sec=0.01)


def db_threads() -> list[DbThread]:
    return [t for t in threading.enumerate() if isinstance(t, DbThread) and t.name.startswith(THREAD_PREFIX)]


def wait_gone(timeout: float = PATIENCE_SEC) -> list[DbThread]:
    deadline = time.monotonic() + timeout
    while db_threads() and time.monotonic() < deadline:
        time.sleep(0.005)
    return db_threads()


def fast_connection(path: str | Path) -> sqlite3.Connection:
    """The daemon's connection without the disk sync, for tests that do thousands of commits."""
    conn = connect(path)
    conn.execute("PRAGMA synchronous=OFF")
    return conn


class Faulty(FaultyConnection):
    """FaultyConnection that lets every ROLLBACK through, armed from inside the database thread with
    `arm`."""

    def _tick(self, sql: str) -> None:
        if sql.lstrip().upper().startswith("ROLLBACK"):
            return
        super()._tick(sql)


def faulty_connection(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=5, factory=Faulty)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    return conn


def arm(conn: sqlite3.Connection, fail_at: int | None, sticky: bool = False) -> None:
    """From the next statement on, the `fail_at`th (1 is the next) raises what a full disk raises."""
    assert isinstance(conn, Faulty)
    conn.statements = 0
    conn.log = []
    conn.fail_at, conn.sticky = fail_at, sticky


def statements(conn: sqlite3.Connection) -> list[str]:
    assert isinstance(conn, Faulty)
    return list(conn.log)


def statement_of(sql: str) -> Callable[[sqlite3.Connection], object]:
    return lambda conn: conn.execute(sql)


async def started(
    path: Path, opener: Callable[[], sqlite3.Connection] | None = None, tuning: Tuning = QUICK, tables: bool = True
) -> Db:
    db = Db(opener or (lambda: connect(path)), tuning=tuning, name=THREAD_PREFIX + "-test")
    await db.start()
    if tables:
        for statement in SCHEMA:
            await db.write(statement_of(statement))
    return db


def committed(path: Path, sql: str = "SELECT n FROM t ORDER BY n") -> list[Any]:
    """What a reader that is not the Db sees: only what is committed."""
    conn = raw(path)
    try:
        return [r[0] if len(r) == 1 else tuple(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def eager(coro: Coroutine[Any, Any, T]) -> "asyncio.Task[T]":
    """A task that runs to its first await at once, so the order of asking is the order of the
    calls."""
    return asyncio.Task(coro, loop=asyncio.get_running_loop(), eager_start=True)
