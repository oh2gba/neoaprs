"""Read-only SQL for the support bundle.

The bundle opens the database read-only beside the daemon's connection and changes nothing.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from .dberror import Connection, Row, limit, rows

OPEN_WAIT_SEC = 3.0
# a packet row (packetcodec.PacketRow) of the columns an unmigrated file has too
SHOWN_LIST = "heard_at, direction, raw, source, destination, path, kind, summary, NULL, error, '', ''"


def open_readonly(path: str | Path) -> Connection:
    """Open the existing database file read-only; raise sqlite3.Error if missing or invalid.

    Without a -wal file no daemon has it open, so it is opened immutable and creates no -wal or -shm.
    """
    base = Path(path).absolute()
    quiet = not base.with_name(base.name + "-wal").exists()
    return sqlite3.connect(
        f"{base.as_uri()}?mode=ro" + ("&immutable=1" if quiet else ""), uri=True, timeout=OPEN_WAIT_SEC
    )


def live_version(path: str | Path) -> int | None:
    """Return the schema version as SQLite reads it through the write-ahead log, or None."""
    try:
        with closing(open_readonly(path)) as db:
            return int(db.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error:
        return None


def table_counts(db: Connection) -> list[tuple[str, int]]:
    """Return (table, row count) for every table, by name."""
    names = [
        str(r[0])
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return [
        (name, int(db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]))
        for name in names
    ]


def file_facts(db: Connection) -> dict[str, str]:
    """Return the schema version, page size, page count and free pages."""
    return {
        "user_version": str(db.execute("PRAGMA user_version").fetchone()[0]),
        "page_size": str(db.execute("PRAGMA page_size").fetchone()[0]),
        "page_count": str(db.execute("PRAGMA page_count").fetchone()[0]),
        "freelist_count": str(db.execute("PRAGMA freelist_count").fetchone()[0]),
    }


def quick_check(db: Connection) -> list[str]:
    """Return the lines of `PRAGMA quick_check`: `ok` alone if the file is sound."""
    return [str(r[0]) for r in db.execute("PRAGMA quick_check")]


def latest_undecoded(db: Connection, count: int) -> list[Row]:
    """Return the latest `count` undecodable packets, newest first."""
    return rows(
        db.execute(
            f"SELECT {SHOWN_LIST} FROM packet WHERE kind = 'undecoded' ORDER BY id DESC LIMIT ?", (limit(count),)
        )
    )


def latest_packets(db: Connection, count: int) -> list[Row]:
    """Return the latest `count` packets heard and sent, newest first."""
    return rows(db.execute(f"SELECT {SHOWN_LIST} FROM packet ORDER BY id DESC LIMIT ?", (limit(count),)))
