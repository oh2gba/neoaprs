"""The database file: how a connection is set up and how a whole copy is made.

Shared so the `Db` actor and the Store configure connections and make copies the same way."""

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from .durable import fsync_dir, fsync_file
from .walcare import limit as limit_wal

DEFAULT_BUSY_MS = 30000

T = TypeVar("T")


def private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def configure(db: sqlite3.Connection, path: str | Path, busy_ms: int) -> None:
    """Apply the pragmas every connection gets. The connection must use `isolation_level=None`."""
    db.execute("PRAGMA journal_mode=WAL")
    # In WAL mode NORMAL does not sync each commit, so a power cut could lose it.
    db.execute("PRAGMA synchronous=FULL")
    db.execute(f"PRAGMA busy_timeout={int(busy_ms)}")
    limit_wal(db)
    if str(path) != ":memory:":
        # Holds position and messages: owner only (-wal and -shm follow).
        private(Path(path))


def connect(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS) -> sqlite3.Connection:
    """Return a configured connection; it belongs to the calling thread. No migration."""
    db = sqlite3.connect(str(path), isolation_level=None, timeout=busy_ms / 1000.0)
    try:
        configure(db, path, busy_ms)
    except BaseException:
        db.close()
        raise
    return db


def transaction(db: sqlite3.Connection, fn: Callable[[sqlite3.Connection], T]) -> T:
    """Run fn(db) in BEGIN IMMEDIATE ... COMMIT, ROLLBACK on error (for tools, not the daemon)."""
    db.execute("BEGIN IMMEDIATE")
    try:
        result = fn(db)
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    return result


def copy_database(src: sqlite3.Connection, dest: Path) -> None:
    """Copy the open database to `dest` as one private file, checked and synced.

    A power cut leaves the old copy or the new one. Raise sqlite3.Error or OSError."""
    tmp = dest.with_name(dest.name + ".tmp")
    journal = tmp.with_name(tmp.name + "-journal")
    try:
        new_folder = not dest.parent.exists()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # private from the first byte
        os.close(fd)
        out = sqlite3.connect(str(tmp))
        try:
            src.backup(out)
            out.execute("PRAGMA journal_mode=DELETE")  # one self-contained file
        finally:
            out.close()
        private(tmp)
        # Read-only: a missing file is an error, not a new empty database.
        check = sqlite3.connect(f"{tmp.absolute().as_uri()}?mode=ro", uri=True)
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("the copy is damaged")
        finally:
            check.close()
        fsync_file(tmp)  # on disk before it gets its name
        tmp.replace(dest)
        fsync_dir(dest.parent)
        if new_folder:
            fsync_dir(dest.parent.parent)
    except BaseException:
        for leftover in (tmp, journal):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
        raise
