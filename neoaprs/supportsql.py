"""The statements of the support bundle (neoaprs/cli/supportgather.py): functions of a connection that only read. The bundle opens the database file read-only, on the thread that makes it, beside the
daemon's own connection (the write-ahead log lets a reader and the writer go on together), and changes nothing: no migration, no pragma that writes, no checkpoint."""
import sqlite3
from pathlib import Path

from .dberror import Connection, Row, limit, rows
from .packetsql import PACKET_LIST

OPEN_WAIT_SEC = 3.0


def open_readonly(path: str | Path) -> Connection:
    """A connection to the existing database file that cannot write. A file that no daemon has open has no write-ahead log beside it (SQLite removes it when the last connection closes): it is opened as immutable, which reads the file
    as it is and creates nothing next to it (a plain read-only connection would make the -wal and -shm files). With a log beside it a daemon has the file open, and the reader goes through the log as any other. Raises sqlite3.Error
    when the file is not there or not a database."""
    base = Path(path).absolute()
    quiet = not base.with_name(base.name + "-wal").exists()
    return sqlite3.connect(f"{base.as_uri()}?mode=ro" + ("&immutable=1" if quiet else ""), uri=True, timeout=OPEN_WAIT_SEC)


def table_counts(db: Connection) -> list[tuple[str, int]]:
    """(table, rows) of every table of the file, by name."""
    names = [str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return [(name, int(db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0])) for name in names]


def file_facts(db: Connection) -> dict[str, str]:
    """What SQLite says of the file itself: the schema version, the page size and count and the free pages."""
    return {
        "user_version": str(db.execute("PRAGMA user_version").fetchone()[0]),
        "page_size": str(db.execute("PRAGMA page_size").fetchone()[0]),
        "page_count": str(db.execute("PRAGMA page_count").fetchone()[0]),
        "freelist_count": str(db.execute("PRAGMA freelist_count").fetchone()[0]),
    }


def quick_check(db: Connection) -> list[str]:
    """The lines `PRAGMA quick_check` answers: `ok` alone when the file is sound."""
    return [str(r[0]) for r in db.execute("PRAGMA quick_check")]




def latest_undecoded(db: Connection, count: int) -> list[Row]:
    """The latest `count` packets the parser could not read, the newest first."""
    return rows(db.execute(f"SELECT {PACKET_LIST} FROM packet WHERE kind = 'undecoded' ORDER BY id DESC LIMIT ?", (limit(count),)))
