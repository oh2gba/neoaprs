"""A database file as the migrations leave it, for the migration tests: `Opened(path)` runs
`open_database` and holds the connection it gives, on this thread.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from neoaprs.clock import Clock, utcnow
from neoaprs.migrations import history, open_database, schema_version
from neoaprs.migrationsteps1to11 import _v10
from neoaprs.migrationsteps12to21 import _v12
from tests.support.migrated31 import undo_31
from tests.support.migrated32 import undo_32, undo_33


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


def undo_34(db: sqlite3.Connection) -> None:
    """Take back what migration 34 did: `own_bulletin.radios` and the rows no version 33 file has.

    `station/main_radio` is the test's to put back.
    """
    db.execute("ALTER TABLE own_bulletin DROP COLUMN radios")
    db.execute("DELETE FROM settings WHERE key IN ('email/radio', 'objects/send_on', 'bulletins/send_on')")


def step_back(db: sqlite3.Connection, version: int) -> None:
    """Takes out of a fully migrated database what the migrations after `version` added to the
    schema, so that they can run again on it (the history and `user_version` are the test's to set).
    """
    if version < 34:
        undo_34(db)
    if version < 33:
        undo_33(db)
    if version < 32:
        undo_32(db)
    if version < 31:
        # After undo_33 and undo_32: the latest step is taken out first
        undo_31(db)
    if version < 30:
        for table in ("packet", "message", "station"):
            db.execute(f"ALTER TABLE {table} DROP COLUMN snr")
            db.execute(f"ALTER TABLE {table} DROP COLUMN rssi")
        db.execute("ALTER TABLE station DROP COLUMN signal_at")
    if version < 28:
        db.execute("ALTER TABLE message DROP COLUMN failure")
    if version < 18:
        db.execute("ALTER TABLE own_object DROP COLUMN qru_group")
        db.execute("ALTER TABLE own_object DROP COLUMN on_request")
    if version < 21:
        db.execute("ALTER TABLE packet DROP COLUMN via")
        for column in ("heard_rf", "heard_rf_gated", "heard_is", "heard_dummy", "last_rf_at", "last_rf_gated_at", "last_is_at", "last_dummy_at", "position_via"):
            db.execute(f"ALTER TABLE station DROP COLUMN {column}")
    if version < 22:
        # `station_pref` made again as migration 12 made it, without the columns of the alerts: a
        # column that a CHECK names cannot be dropped; the table of a test is empty here
        _v12(db)
    if version < 25:
        db.execute("ALTER TABLE packet DROP COLUMN radio")
        db.execute("ALTER TABLE message DROP COLUMN radio")
        db.execute("ALTER TABLE message_attempt DROP COLUMN radio")
        db.execute("ALTER TABLE own_object DROP COLUMN radio")
        for column in ("heard_fm", "heard_hf", "last_fm_at", "last_hf_at"):
            db.execute(f"ALTER TABLE station DROP COLUMN {column}")
    if version < 24:
        db.execute("DROP TABLE station_key")
        db.execute("ALTER TABLE message DROP COLUMN seal")
        db.execute("ALTER TABLE message DROP COLUMN wire")
    if version < 23:
        # `message` made again as migration 10 made it, without AUTOINCREMENT, so that migration 23
        # finds the table it expects; the rows are kept
        _v10(db)
