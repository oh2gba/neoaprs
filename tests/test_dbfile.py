"""How a connection to the database file is set up (neoaprs/dbfile.py), the transaction helper of the tools, the whole checked copy, and the limits of the write-ahead log (neoaprs/walcare.py)."""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from neoaprs import walcare
from neoaprs.dbfile import DEFAULT_BUSY_MS, connect, copy_database, private, transaction

PROC = Path("/proc/self/fd").is_dir()               # where a descriptor can be turned into the path it names


def test_a_connection_is_wal_synchronous_full_with_the_busy_time_and_a_private_file(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = connect(path, busy_ms=1234)
    values = [db.execute(f"PRAGMA {p}").fetchone()[0] for p in ("journal_mode", "synchronous", "busy_timeout", "journal_size_limit", "wal_autocheckpoint")]
    assert values == ["wal", 2, 1234, walcare.WAL_LIMIT_BYTES, walcare.AUTOCHECKPOINT_PAGES]
    assert DEFAULT_BUSY_MS == 30000
    if sys.platform != "win32":
        assert (path.stat().st_mode & 0o777) == 0o600       # (Windows has no mode bits: the folder of the user is the privacy)
    db.close()


def test_a_connection_that_cannot_be_set_up_is_closed_and_the_error_is_raised(tmp_path: Path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        connect(tmp_path / "no-such-folder" / "x.sqlite")


def test_a_database_in_memory_is_not_chmodded() -> None:
    connect(":memory:").close()


def test_private_ignores_a_file_that_is_not_there(tmp_path: Path) -> None:
    private(tmp_path / "nothing")


def test_a_transaction_commits_all_of_it_or_rolls_all_of_it_back(tmp_path: Path) -> None:
    db = connect(tmp_path / "x.sqlite")
    db.execute("CREATE TABLE t (n INTEGER PRIMARY KEY)")

    def two(conn: sqlite3.Connection) -> str:
        conn.execute("INSERT INTO t VALUES (1)")
        conn.execute("INSERT INTO t VALUES (2)")
        return "done"

    def broken(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (3)")
        conn.execute("INSERT INTO t VALUES (1)")

    assert transaction(db, two) == "done"
    with pytest.raises(sqlite3.IntegrityError):
        transaction(db, broken)
    assert [r[0] for r in db.execute("SELECT n FROM t ORDER BY n")] == [1, 2] and not db.in_transaction
    db.close()


def test_a_copy_is_whole_checked_private_synced_and_leaves_nothing_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = connect(tmp_path / "x.sqlite")
    db.execute("CREATE TABLE t (n INTEGER PRIMARY KEY, v TEXT)")
    db.executemany("INSERT INTO t VALUES (?, ?)", [(n, "x" * 100) for n in range(200)])
    dest = tmp_path / "new folder" / "copy.sqlite"
    synced: list[str] = []
    real = os.fsync

    def fsync(fd: int) -> None:
        synced.append(os.readlink(f"/proc/self/fd/{fd}") if PROC else "descriptor")
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    copy_database(db, dest)
    monkeypatch.undo()
    assert [p.name for p in dest.parent.iterdir()] == ["copy.sqlite"]
    if sys.platform != "win32":
        assert (dest.stat().st_mode & 0o777) == 0o600
    assert synced, "the copy is synced"
    if PROC:
        assert any(p.endswith(".tmp") for p in synced) and str(dest.parent) in synced and str(dest.parent.parent) in synced, "the file, the folder, and the folder that holds a new folder"
    copy = sqlite3.connect(dest)
    assert copy.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 200 and copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete", "one self-contained file"
    copy.close()
    db.close()


def test_a_copy_that_fails_removes_what_it_started(tmp_path: Path) -> None:
    db = connect(tmp_path / "x.sqlite")
    (tmp_path / "blocked").write_text("a file where the folder should be")
    with pytest.raises(OSError):
        copy_database(db, tmp_path / "blocked" / "copy.sqlite")
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(("copy", "blocked"))) == ["blocked"]
    db.close()
