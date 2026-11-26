"""The room a database file gives back (neoaprs/walcare.py): the one rewrite that makes the file shortenable,
and the slices that shorten it after deleting."""

import sqlite3
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import walcare
from neoaprs.dbfile import connect
from neoaprs.store import DB_NAME
from neoaprs.weatherlog import WeatherLog
from tests.support.clock import FixedClock
from tests.support.storedb import store_at


def filled(path: Path, rows: int = 6000) -> sqlite3.Connection:
    """A database with a table of `rows` rows of about a kilobyte, as `connect` sets it up."""
    db = connect(path)
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, body BLOB)")
    db.execute("BEGIN")
    db.executemany("INSERT INTO t (body) VALUES (?)", [(b"x" * 1000,)] * rows)
    db.execute("COMMIT")
    return db


def size_of(path: Path, db: sqlite3.Connection) -> int:
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path.stat().st_size


def mode(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA auto_vacuum").fetchone()[0])


def test_a_file_is_rewritten_once_so_that_it_gives_back_the_room_deleting_leaves(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = filled(path)
    db.execute("DELETE FROM t WHERE id % 4 != 0")
    full = size_of(path, db)
    assert mode(db) == 0
    walcare.make_returnable(db, path)
    assert mode(db) == walcare.INCREMENTAL
    assert db.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1500, "no row is lost"
    assert size_of(path, db) < full // 2, "the room the deleted rows left is given back at once"
    db.execute("BEGIN")
    db.execute("DELETE FROM t WHERE id % 2 = 0")
    db.execute("COMMIT")
    before = size_of(path, db)
    assert db.execute("PRAGMA freelist_count").fetchone()[0] > 0
    assert walcare.release(db) == 0
    assert size_of(path, db) < before, "and a later delete is given back by release"
    walcare.make_returnable(db, path)  # a file made so is not rewritten again
    db.close()


def test_release_takes_one_slice_of_the_free_pages_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "x.sqlite"
    db = filled(path, 3000)
    walcare.make_returnable(db, path)
    db.execute("DELETE FROM t")
    monkeypatch.setattr(walcare, "SLICE_PAGES", 100)
    left = walcare.release(db)
    assert left > 0, "a slice does not take all"
    while left:
        left = walcare.release(db)
    db.close()


def test_a_file_is_left_as_it_was_when_the_disk_has_too_little_room(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "x.sqlite"
    db = filled(path, 200)
    monkeypatch.setattr(walcare.shutil, "disk_usage", lambda folder: SimpleNamespace(free=1000))
    walcare.make_returnable(db, path)
    assert mode(db) == 0
    db.close()


def test_a_database_in_memory_is_not_rewritten() -> None:
    db = connect(":memory:")
    walcare.make_returnable(db, ":memory:")
    assert mode(db) == 0
    db.close()


async def test_pruning_the_log_gives_the_file_its_room_back(tmp_path: Path) -> None:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    log = WeatherLog(store.db, clock)
    old = (clock() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    await store.db.write(
        lambda conn: conn.executemany(
            "INSERT INTO weather (station, at, raw) VALUES (?, ?, ?)", [("OH2MUI", old, "x" * 900)] * 8000
        )
    )
    other = connect(tmp_path / DB_NAME)  # a second connection, to settle the log of the first and look at the file
    assert mode(other) == walcare.INCREMENTAL, "a file the daemon opens is made so"
    full = size_of(tmp_path / DB_NAME, other)
    assert await log.prune(7) == 8000
    assert size_of(tmp_path / DB_NAME, other) < full // 2
    other.close()
