"""The write-ahead log of the database file: its size is bounded, and a reader that holds it back is told.

In WAL mode a commit goes to the -wal file and a checkpoint moves the pages into the database file. A checkpoint stops at the oldest snapshot a reader holds, so another process that
keeps a read transaction open (a forgotten sqlite3 shell, `neoaprs-db`, a long query) keeps the whole WAL from being moved: it grows with every commit (every heard packet is one), and once the reader has gone the file stays as big as it got (SQLite reuses it from the start but never makes it smaller unless it is told to). No data is at risk, the
disk is. Two things bound it: `journal_size_limit` cuts the file down to the limit whenever the log is started again, and the minute's PASSIVE checkpoint (which never waits for a reader
or a writer) moves what can be moved, sees what cannot, and says so once.
"""
import logging
import sqlite3

log = logging.getLogger("neoaprs.store")

WAL_LIMIT_BYTES = 64 * 1024 * 1024         # the file is cut to this when the log restarts, and a log this far behind a reader is worth a line in the log
AUTOCHECKPOINT_PAGES = 1000                # SQLite's own default, written down: after this many pages a commit tries a checkpoint


class WalWatch:
    def __init__(self) -> None:
        self.told = False                  # a reader holding the log back has been mentioned, and not let go yet

    @staticmethod
    def limit(db: sqlite3.Connection) -> None:
        db.execute(f"PRAGMA journal_size_limit={int(WAL_LIMIT_BYTES)}")
        db.execute(f"PRAGMA wal_autocheckpoint={AUTOCHECKPOINT_PAGES}")

    def tick(self, db: sqlite3.Connection) -> None:
        """The minute's checkpoint: what can be moved into the database file is moved, without waiting for anybody. When a reader holds back more than the limit, one line in the log."""
        try:
            _, frames, moved = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            page = int(db.execute("PRAGMA page_size").fetchone()[0])
        except sqlite3.Error as e:
            log.warning("the checkpoint of the write-ahead log failed: %s", e)
            return
        held = max(frames - moved, 0) * page if frames >= 0 else 0           # frames is -1 when the database has no log (in memory)
        if held > WAL_LIMIT_BYTES and not self.told:
            self.told = True
            log.warning("the write-ahead log holds %d MB that cannot be moved into the database: another program has it open in a read transaction (a sqlite3 shell, neoaprs-db, "
                        "a long query); the file grows until that program lets go", held // (1024 * 1024))
        elif held == 0:
            self.told = False
