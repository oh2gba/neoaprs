"""Bound the size of the database's write-ahead log.

The automatic checkpoint and `journal_size_limit` bound the log. A checkpoint stops at the oldest
snapshot a reader holds, so a long read transaction lets the log grow.
"""

import sqlite3

# the file is truncated to this when the log restarts
WAL_LIMIT_BYTES = 64 * 1024 * 1024
# SQLite's default, set explicitly: a commit past this many pages tries a checkpoint
AUTOCHECKPOINT_PAGES = 1000


def limit(db: sqlite3.Connection) -> None:
    db.execute(f"PRAGMA journal_size_limit={int(WAL_LIMIT_BYTES)}")
    db.execute(f"PRAGMA wal_autocheckpoint={AUTOCHECKPOINT_PAGES}")
