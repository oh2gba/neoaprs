"""Migration 14 (neoaprs/migrationsteps12to21.py): an empty `beacon/path` meant no digipeaters and
now means the recommended path, so the stored empty one becomes DIRECT and nobody starts to digipeat
on an upgrade.
"""
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.support.migrated31 import flat_row, station_rows, stored_config
from tests.test_migrations import GOLDEN, raw


def version_thirteen(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 13 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 14")
    step_back(db, 13)
    db.execute("PRAGMA user_version = 13")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


@contextmanager
def migrate(folder: Path, stored: dict[str, str]) -> Iterator[sqlite3.Connection]:
    """The database of a version 13 with these settings, brought up to date: every step from 14 on
    ran, each the frozen one."""
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_thirteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 14
    assert [(r[0], r[1], r[2]) for r in migrated.history()][13:] == [(number, f"_v{number}", GOLDEN[number]) for number in range(14, SCHEMA_VERSION + 1)]
    try:
        yield migrated.db
    finally:
        migrated.close()


def test_a_stored_empty_beacon_path_becomes_direct_only_and_nothing_else_is_touched(tmp_path: Path) -> None:
    with migrate(tmp_path, {"beacon/path": "", "station/call": "OH2GBA"}) as db:
        assert flat_row(db, "beacon/path") == ("DIRECT", 2), "cleared on purpose, so no digipeaters; the revision moves on"
        assert station_rows(db) == {"station/call": ("OH2GBA", 1)}
        assert stored_config(db).beacon_path == "DIRECT" and stored_config(db).beacon_path_calls == (), "and the settings in force send the beacon with no digipeaters"


def test_a_beacon_path_that_names_digipeaters_is_as_it_was(tmp_path: Path) -> None:
    with migrate(tmp_path / "a", {"beacon/path": "WIDE1-1"}) as db:
        assert flat_row(db, "beacon/path") == ("WIDE1-1", 1) and stored_config(db).beacon_path_calls == ("WIDE1-1",)


def test_a_custom_beacon_path_is_as_it_was(tmp_path: Path) -> None:
    with migrate(tmp_path / "b", {"beacon/path": "WIDE2-2"}) as db:
        assert flat_row(db, "beacon/path") == ("WIDE2-2", 1) and stored_config(db).beacon_path_calls == ("WIDE2-2",)


def test_a_database_with_no_beacon_path_stored_stays_so(tmp_path: Path) -> None:
    with migrate(tmp_path / "c", {"station/call": "OH2GBA"}) as db:
        assert flat_row(db, "beacon/path") is None and stored_config(db).beacon_path == "" and station_rows(db) == {"station/call": ("OH2GBA", 1)}
