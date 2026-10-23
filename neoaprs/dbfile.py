"""The database file as a file: how a connection to it is set up, and how a whole copy of it is made.

They live here so that the connection of the `Db` actor (db.py) is set up exactly as the Store's is (WAL, `synchronous=FULL`, the busy time, the bound of the
write-ahead log, the file private to its owner), and a copy is made one way: written under a temporary name, checked, synced to the disk, renamed, the folder synced.
"""
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from .durable import fsync_dir, fsync_file
from .walcare import WalWatch

DEFAULT_BUSY_MS = 30000

T = TypeVar("T")


def private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def configure(db: sqlite3.Connection, path: str | Path, busy_ms: int) -> None:
    """The pragmas every connection of the program's database gets, in this order. The caller has made the connection with `isolation_level=None` (the transactions are its own)."""
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")             # in WAL mode NORMAL does not sync a commit: a setting the page was told of could be lost to a power cut
    db.execute(f"PRAGMA busy_timeout={int(busy_ms)}")
    WalWatch.limit(db)                                # the log is cut to a limit when it restarts
    if str(path) != ":memory:":
        private(Path(path))                           # the operator's position and messages are in it: for this user only (the -wal and -shm follow the file)


def connect(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS) -> sqlite3.Connection:
    """A connection to the database file, set up. It belongs to the thread that calls this (sqlite3 refuses another one). No migration: that is the Store's."""
    db = sqlite3.connect(str(path), isolation_level=None, timeout=busy_ms / 1000.0)
    try:
        configure(db, path, busy_ms)
    except BaseException:
        db.close()
        raise
    return db


def transaction(db: sqlite3.Connection, fn: Callable[[sqlite3.Connection], T]) -> T:
    """fn(db) in BEGIN IMMEDIATE ... COMMIT, ROLLBACK when it raises: for the tools that own a connection of their own (in autocommit, isolation_level=None). The daemon never calls this:
    its statements are operations of the database thread (db.py), which makes the transactions."""
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
    """The open database as one file at `dest`, private from the first byte, written under a temporary name, checked, synced to the disk, renamed into place, and the
    folder synced (a power cut then leaves the old copy or the new one, never a name without its data). Raises sqlite3.Error or OSError; whatever was started is removed then."""
    tmp = dest.with_name(dest.name + ".tmp")
    journal = tmp.with_name(tmp.name + "-journal")                  # SQLite's, while the copy is written: it stays behind when the copy fails
    try:
        new_folder = not dest.parent.exists()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)          # private from the first byte
        os.close(fd)
        out = sqlite3.connect(str(tmp))
        try:
            src.backup(out)
            out.execute("PRAGMA journal_mode=DELETE")          # one self-contained file, no -wal or -shm beside it
        finally:
            out.close()
        private(tmp)                                           # a copy holds the position and messages too
        check = sqlite3.connect(f"{tmp.absolute().as_uri()}?mode=ro", uri=True)       # read-only: a file that is not there is an error, not a new empty database that passes
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("the copy is damaged")      # never published, never allowed to push out the good ones
        finally:
            check.close()
        fsync_file(tmp)                                       # on the disk before it has its name: after a power cut the name is never there without the data
        tmp.replace(dest)
        fsync_dir(dest.parent)                                # and the name itself is on the disk
        if new_folder:
            fsync_dir(dest.parent.parent)                     # (a folder made for this copy: its own entry too)
    except BaseException:
        for leftover in (tmp, journal):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
        raise
