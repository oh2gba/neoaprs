"""The room a database file gives back (neoaprs/walcare.py): the one rewrite that makes the file shortenable,
and the slices that shorten it after deleting."""

import logging
import os
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import walcare
from neoaprs.dbfile import connect
from neoaprs.dbopen import open_connection
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
    assert mode(other) == 0, "the opener does not rewrite the file"
    assert store.db is not None
    assert await store.db.maintain_own(lambda conn: walcare.make_returnable(conn, tmp_path / DB_NAME))
    other.close()
    other = connect(tmp_path / DB_NAME)
    assert mode(other) == walcare.INCREMENTAL
    full = size_of(tmp_path / DB_NAME, other)
    assert await log.prune(7) == 8000
    assert size_of(tmp_path / DB_NAME, other) < full // 2
    other.close()


def temp_files(folders: list[Path]) -> set[Path]:
    """The folders that hold a SQLite temporary file now (a file unlinked while open shows under /proc on Linux)."""
    found: set[Path] = set()
    for folder in folders:
        found |= {folder for name in os.listdir(folder) if "etilqs" in name}
    if sys.platform.startswith("linux"):
        for fd in os.listdir("/proc/self/fd"):
            try:
                target = Path(os.readlink(f"/proc/self/fd/{fd}").removesuffix(" (deleted)"))
            except OSError:
                continue
            if "etilqs" in target.name:
                found.add(target.parent)
    return found


def test_the_copy_is_built_beside_the_file_wherever_the_system_keeps_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, elsewhere = tmp_path / "data", tmp_path / "elsewhere"
    data.mkdir()
    elsewhere.mkdir()
    monkeypatch.setenv("TMPDIR", str(elsewhere))
    monkeypatch.setenv("TMP", str(elsewhere))
    monkeypatch.setenv("TEMP", str(elsewhere))
    monkeypatch.setenv("SQLITE_TMPDIR", str(elsewhere))
    path = data / "x.sqlite"
    db = filled(path, 3000)
    seen: set[Path] = set()

    def look() -> int:
        seen.update(temp_files([data, elsewhere]))
        return 0

    db.set_progress_handler(look, 1)
    assert walcare.make_returnable(db, path)
    db.set_progress_handler(None, 1)
    assert seen == {data}, "the temporary file is in the folder of the database and nowhere else"
    assert not db.execute("PRAGMA temp_store_directory").fetchall(), "the setting is put back"
    db.close()


def test_the_opener_returns_before_any_rewrite_and_the_rewrite_keeps_every_row(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = open_connection(path)
    db.execute("BEGIN")
    db.executemany(
        "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded)"
        " VALUES (?, 'in', ?, 'A', 'B', '', 'other', '', '{}')",
        [("2026-01-01T00:00:00.000000Z", b"x" * 500)] * 50,
    )
    db.execute("COMMIT")
    assert mode(db) == 0, "opening does not rewrite"
    ids = db.execute("SELECT id FROM packet ORDER BY id").fetchall()
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    counts = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    assert walcare.make_returnable(db, path)
    assert mode(db) == walcare.INCREMENTAL
    assert db.execute("SELECT id FROM packet ORDER BY id").fetchall() == ids
    assert {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables} == counts
    db.close()


def test_a_short_disk_skips_the_rewrite_with_one_line_and_a_later_start_does_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "x.sqlite"
    db = filled(path, 200)
    with monkeypatch.context() as short:
        short.setattr(walcare.shutil, "disk_usage", lambda folder: SimpleNamespace(free=1000))
        with caplog.at_level(logging.INFO, logger="neoaprs.db"):
            assert not walcare.make_returnable(db, path)
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert mode(db) == 0
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="neoaprs.db"):
        assert walcare.make_returnable(db, path)
    assert [r.levelno for r in caplog.records] == [logging.INFO, logging.INFO], "one line at the start, one at the end"
    db.close()
