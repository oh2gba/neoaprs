"""Bound the size of the database's write-ahead log, and let the file give back the room that deleting leaves.

The automatic checkpoint and `journal_size_limit` bound the log. A checkpoint stops at the oldest
snapshot a reader holds, so a long read transaction lets the log grow.
"""

import logging
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

log = logging.getLogger("neoaprs.db")

# the file is truncated to this when the log restarts
WAL_LIMIT_BYTES = 64 * 1024 * 1024
# SQLite's default, set explicitly: a commit past this many pages tries a checkpoint
AUTOCHECKPOINT_PAGES = 1000


def limit(db: sqlite3.Connection) -> None:
    db.execute(f"PRAGMA journal_size_limit={int(WAL_LIMIT_BYTES)}")
    db.execute(f"PRAGMA wal_autocheckpoint={AUTOCHECKPOINT_PAGES}")


INCREMENTAL = 2  # PRAGMA auto_vacuum: the file is cut by `release`, not on its own
SLICE_PAGES = 5000  # pages one `release` takes off the file (20 MB), each in a transaction of its own
SPARE_BYTES = 32 * 1024 * 1024  # disk to be left over after the rewrite


def _quoted(folder: str | Path) -> str:
    return "'" + str(folder).replace("'", "''") + "'"


def _temp_setting(db: sqlite3.Connection) -> str:
    row = db.execute("PRAGMA temp_store_directory").fetchone()
    return str(row[0]) if row else ""


def _temp_folder(db: sqlite3.Connection, folder: Path) -> Path:
    """Point SQLite's temporary files at `folder` and return where they will go.

    The pragma is the one way that works on every platform (SQLITE_TMPDIR is ignored on Windows); it is
    process wide, so the caller restores it. If SQLite does not take it, they go to the system's own place.
    """
    db.execute("PRAGMA temp_store=FILE")
    try:
        db.execute(f"PRAGMA temp_store_directory={_quoted(folder)}")
        if _temp_setting(db):
            return folder
    except sqlite3.Error:
        pass
    return Path(tempfile.gettempdir())


def _room_for(size: int, folder: Path, temp: Path) -> bool:
    """Whether the copy (in `temp`) and its way into the file (in `folder`) both fit, with SPARE_BYTES left."""
    if temp == folder:
        return shutil.disk_usage(folder).free >= size * 2 + SPARE_BYTES
    return shutil.disk_usage(folder).free >= size + SPARE_BYTES and shutil.disk_usage(temp).free >= size + SPARE_BYTES


def make_returnable(db: sqlite3.Connection, path: str | Path) -> bool:
    """Rewrite the file once so that `release` can shorten it; a file already made so is left alone.

    Return whether it was rewritten. It runs in the database thread, after the page is up. Needs room for
    a second copy where SQLite builds it (beside the file); without it, or when another program holds the
    file, nothing is done and the next start tries again. A stop at any moment leaves the file as it was:
    the copy is built in a temporary file and enters the database as one transaction of the log.
    """
    if str(path) == ":memory:" or db.execute("PRAGMA auto_vacuum").fetchone()[0] == INCREMENTAL:
        return False
    folder = Path(path).absolute().parent
    size = os.path.getsize(path)
    began = time.monotonic()
    before = _temp_setting(db)
    try:
        if not _room_for(size, folder, _temp_folder(db, folder)):
            log.warning("the database is not rewritten to give room back: the disk has too little left")
            return False
        log.info("the database (%d MB) is rewritten once so that it can give room back; this takes a while", size >> 20)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute(f"PRAGMA auto_vacuum={INCREMENTAL}")
        db.execute("VACUUM")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except (sqlite3.Error, OSError) as e:
        log.warning("the database could not be rewritten to give room back (it is as it was): %s", e)
        return False
    finally:
        try:
            db.execute(f"PRAGMA temp_store_directory={_quoted(before)}")
        except sqlite3.Error:
            pass
    log.info(
        "the database is rewritten: %d s, %d MB given back",
        round(time.monotonic() - began),
        max(0, size - os.path.getsize(path)) >> 20,
    )
    return True


def release(db: sqlite3.Connection) -> int:
    """Take up to SLICE_PAGES free pages off the end of the file; return how many free pages are left."""
    db.execute(f"PRAGMA incremental_vacuum({SLICE_PAGES})").fetchall()  # one page for each row fetched
    return int(db.execute("PRAGMA freelist_count").fetchone()[0])
