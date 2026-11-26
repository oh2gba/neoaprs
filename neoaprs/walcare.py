"""Bound the size of the database's write-ahead log, and let the file give back the room that deleting leaves.

The automatic checkpoint and `journal_size_limit` bound the log. A checkpoint stops at the oldest
snapshot a reader holds, so a long read transaction lets the log grow.
"""

import logging
import os
import shutil
import sqlite3
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


def make_returnable(db: sqlite3.Connection, path: str | Path) -> None:
    """Rewrite the file once so that `release` can shorten it; a file already made so is left alone.

    Needs the size of the file free on its disk; without it, or when another program holds the file,
    nothing is done and the next start tries again.
    """
    if str(path) == ":memory:" or db.execute("PRAGMA auto_vacuum").fetchone()[0] == INCREMENTAL:
        return
    folder = Path(path).absolute().parent
    size = os.path.getsize(path)
    try:
        if shutil.disk_usage(folder).free < size * 2 + SPARE_BYTES:
            log.warning("the database is not rewritten to give room back: the disk has too little left")
            return
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute(f"PRAGMA auto_vacuum={INCREMENTAL}")
        # SQLite builds the new file in its temporary folder, which may be a RAM disk: keep it beside the file
        kept = os.environ.get("SQLITE_TMPDIR")
        os.environ["SQLITE_TMPDIR"] = str(folder)
        try:
            db.execute("VACUUM")
        finally:
            if kept is None:
                os.environ.pop("SQLITE_TMPDIR", None)
            else:
                os.environ["SQLITE_TMPDIR"] = kept
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except (sqlite3.Error, OSError) as e:
        log.warning("the database could not be rewritten to give room back (it is as it was): %s", e)
        return
    log.info(
        "the database was rewritten so that it can give room back: %d MB to %d MB",
        size >> 20,
        os.path.getsize(path) >> 20,
    )


def release(db: sqlite3.Connection) -> int:
    """Take up to SLICE_PAGES free pages off the end of the file; return how many free pages are left."""
    db.execute(f"PRAGMA incremental_vacuum({SLICE_PAGES})").fetchall()  # one page for each row fetched
    return int(db.execute("PRAGMA freelist_count").fetchone()[0])
