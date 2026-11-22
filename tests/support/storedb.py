"""The Store for tests, on the database thread as the daemon has it (one Db, one connection)."""
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from neoaprs.clock import Clock, utcnow
from neoaprs.db import Db
from neoaprs.dbfile import DEFAULT_BUSY_MS
from neoaprs.dbopen import open_connection
from neoaprs.store import DB_NAME, Store
from tests.support import env
from tests.support.clock import FixedClock

L = TypeVar("L")


async def store_at(path: str | Path = ":memory:", clock: Clock = utcnow, busy_ms: int = DEFAULT_BUSY_MS, opener: Callable[[], sqlite3.Connection] | None = None) -> Store:
    """`opener`: another way to make the connection (one that fails on demand,
    tests/support/safety.py); it is run in the database thread."""
    db = Db(opener or (lambda: open_connection(path, busy_ms, clock)))
    await db.start()
    env.remember(db)
    store = Store(clock)
    store.use(db, path)
    return store


async def log_at(tmp_path: Path, make: Callable[[Db, FixedClock], L], clock: FixedClock | None = None) -> tuple[L, Store, FixedClock]:
    """A log of the daemon (a class made from the Db and the clock: MessageLog, OwnLog, BulletinLog)
    on a new database file in the test's folder; with its Store and its clock."""
    clock = clock or FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    return make(store.db, clock), store, clock


async def sql(store: Store, statement: str, *args: object) -> list[tuple[Any, ...]]:
    """A statement of the test itself, on the connection of the database thread, as another version
    of the program or a tool would have run it; the rows it gives."""
    assert store.db is not None
    return await store.db.write(lambda conn: [tuple(r) for r in conn.execute(statement, args)])


async def keep_old_attempts(db: Db, call: str, attempts: int, path: str | None = None) -> None:
    """A row of `station_pref` as a version that let the operator choose the attempts wrote it: the
    station's own count, and a path when given."""
    def keep(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO station_pref (call, attempts, updated_at) VALUES (?, ?, '2026-10-01T00:00:00.000000Z')", (call, attempts))
        if path is not None:                    # (the path is the station's on radio 1 since migration 33)
            conn.execute("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES (?, 1, ?, '2026-10-01T00:00:00.000000Z')", (call, path))
    await db.write(keep)
