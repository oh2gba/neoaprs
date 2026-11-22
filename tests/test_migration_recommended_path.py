"""Migration 15 (neoaprs/migrationsteps12to21.py): the recommended path follows the station's type.
The old default `WIDE1-1,WIDE2-1` of `beacon/path` becomes empty; any other stored path is kept.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from neoaprs.config import Config
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.support.migrated31 import flat_row, station_rows, stored_config
from tests.test_migrations import GOLDEN, raw


def version_fourteen(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 14 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 15")
    step_back(db, 14)
    db.execute("PRAGMA user_version = 14")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


@contextmanager
def migrate(folder: Path, stored: dict[str, str]) -> Iterator[sqlite3.Connection]:
    """The database of a version 14 with these settings, brought up to date: every step from 15 on
    ran, each the frozen one."""
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_fourteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 15
    assert [(r[0], r[1], r[2]) for r in migrated.history()][14:] == [
        (number, f"_v{number}", GOLDEN[number]) for number in range(15, SCHEMA_VERSION + 1)
    ]
    try:
        yield migrated.db
    finally:
        migrated.close()


def test_the_old_default_path_becomes_the_recommended_one_and_nothing_else_is_touched(tmp_path: Path) -> None:
    with migrate(
        tmp_path, {"beacon/path": "WIDE1-1,WIDE2-1", "station/call": "OH2GBA", "station/symbol_code": "-"}
    ) as db:
        assert flat_row(db, "beacon/path") == ("", 2), (
            "the default that every save stored is the recommended path of the station's type; the revision moves on"
        )
        assert station_rows(db) == {"station/call": ("OH2GBA", 1), "station/symbol_code": ("-", 1)}
        assert stored_config(db).beacon_path == "" and stored_config(db).beacon_path_calls == ("WIDE2-2",), (
            "and the settings in force send the beacon on the path of a house"
        )


def test_a_custom_path_and_direct_only_are_as_they_were(tmp_path: Path) -> None:
    for folder, path, calls in (
        ("a", "WIDE2-2", ("WIDE2-2",)),
        ("b", "DIRECT", ()),
        ("c", "WIDE2-1", ("WIDE2-1",)),
        ("d", "WIDE1-1,WIDE2-2", ("WIDE1-1", "WIDE2-2")),
        ("e", "", ("WIDE2-2",)),
    ):
        with migrate(tmp_path / folder, {"beacon/path": path}) as db:
            assert flat_row(db, "beacon/path") == (path, 1), (
                "the owner's own path, DIRECT and the empty one keep their value and their revision"
            )
            assert stored_config(db).beacon_path == path and stored_config(db).beacon_path_calls == calls


def test_a_database_with_no_beacon_path_stored_stays_so(tmp_path: Path) -> None:
    with migrate(tmp_path / "f", {"station/call": "OH2GBA"}) as db:
        assert flat_row(db, "beacon/path") is None and stored_config(db).beacon_path == ""


def test_after_the_migration_the_path_follows_the_symbol_and_the_custom_path_stays() -> None:
    house = Config.from_data({"beacon/path": "", "station/symbol_table": "/", "station/symbol_code": "-"})
    car = Config.from_data({"beacon/path": "", "station/symbol_table": "/", "station/symbol_code": ">"})
    owner = Config.from_data({"beacon/path": "WIDE2-1", "station/symbol_table": "/", "station/symbol_code": ">"})
    assert (
        house.beacon_path_calls == ("WIDE2-2",)
        and car.beacon_path_calls == ("WIDE1-1", "WIDE2-1")
        and owner.beacon_path_calls == ("WIDE2-1",)
    )
