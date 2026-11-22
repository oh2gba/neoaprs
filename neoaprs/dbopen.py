"""The opener of a `Db` (db.py): runs in the database thread, which then owns the connection.

The file is migrated by `open_database` (migrations.py); ":memory:" is a separate database made
there."""
from pathlib import Path

from .clock import Clock, utcnow
from .dberror import Connection, StoreError
from .dbfile import DEFAULT_BUSY_MS
from .migrations import open_database


def open_connection(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, clock: Clock = utcnow) -> Connection:
    """Return a migrated connection. Raise StoreError with the reason from `open_database`."""
    db, why = open_database(path, busy_ms, clock)
    if db is None:
        raise StoreError(why)
    return db
