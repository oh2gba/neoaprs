"""How a connection to the database is made for a `Db` (db.py): the opener runs in the database thread, which then owns the connection. The file is migrated by `open_database` (migrations.py);
a file that has been migrated is found at its version and nothing is migrated again, and ":memory:" is a database of its own, made (and migrated) in the thread."""
from pathlib import Path

from .clock import Clock, utcnow
from .dberror import Connection, StoreError
from .dbfile import DEFAULT_BUSY_MS
from .migrations import open_database


def open_connection(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, clock: Clock = utcnow) -> Connection:
    """A migrated connection to the database. Raises StoreError with the reason `open_database` gives."""
    db, why = open_database(path, busy_ms, clock)
    if db is None:
        raise StoreError(why)
    return db
