"""A database file as the migrations leave it, for the tests of the migrations: `Opened(path)` runs `open_database` (the copy before, the steps, the history) and holds the connection it
gives, on this thread, as a test reads it back.

    s = opened(path)                 # asserts that it opened; s.db is the connection, s.version() and s.history() what the file says
    ok, error = try_open(path)       # the answer of a file that is refused, the connection closed
    step_back(db, 17)                # a database made by every migration, put back to the schema of version 17, for a test that runs the later migrations on it
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from neoaprs.clock import Clock, utcnow
from neoaprs.migrations import history, open_database, schema_version


class Opened:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def version(self) -> int:
        return schema_version(self.db)

    def history(self) -> list[tuple[int, str, str, datetime, str]]:
        return history(self.db)

    def tables(self) -> set[str]:
        return {str(r[0]) for r in self.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def close(self) -> None:
        self.db.close()


def opened(path: str | Path, clock: Clock = utcnow) -> Opened:
    db, error = open_database(path, clock=clock)
    assert db is not None, error
    return Opened(db)


def try_open(path: str | Path, clock: Clock = utcnow) -> tuple[bool, str]:
    db, error = open_database(path, clock=clock)
    if db is not None:
        db.close()
    return db is not None, error


def step_back(db: sqlite3.Connection, version: int) -> None:
    """Takes out of a fully migrated database what the migrations after `version` added to the schema, so that they can run again on it (the history and `user_version` are the test's to set)."""
    if version < 18:
        db.execute("ALTER TABLE own_object DROP COLUMN qru_group")
        db.execute("ALTER TABLE own_object DROP COLUMN on_request")
    if version < 21:
        db.execute("ALTER TABLE packet DROP COLUMN via")
        for column in ("heard_rf", "heard_rf_gated", "heard_is", "heard_dummy", "last_rf_at", "last_rf_gated_at", "last_is_at", "last_dummy_at", "position_via"):
            db.execute(f"ALTER TABLE station DROP COLUMN {column}")
