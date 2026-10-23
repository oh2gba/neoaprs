"""The size of the write-ahead log of the database file.

In WAL mode a commit goes to the -wal file and a checkpoint moves the pages into the database file. Two settings of the connection bound the log: SQLite's own automatic checkpoint, which every
commit past `AUTOCHECKPOINT_PAGES` pages of log tries, and `journal_size_limit`, which cuts the file down to `WAL_LIMIT_BYTES` whenever the log is started again after a checkpoint. A checkpoint stops
at the oldest snapshot a reader holds, so another process that keeps a read transaction open (a forgotten sqlite3 shell, `neoaprs-db`, a long query) keeps the log from being moved and it grows with
every commit until that reader lets go."""
import sqlite3

WAL_LIMIT_BYTES = 64 * 1024 * 1024         # the file is cut to this when the log restarts
AUTOCHECKPOINT_PAGES = 1000                # SQLite's own default, written down: after this many pages a commit tries a checkpoint


def limit(db: sqlite3.Connection) -> None:
    db.execute(f"PRAGMA journal_size_limit={int(WAL_LIMIT_BYTES)}")
    db.execute(f"PRAGMA wal_autocheckpoint={AUTOCHECKPOINT_PAGES}")
