"""Migration 35 (neoaprs/migrationsteps35.py): the map radius is at most 300 km. A larger stored
radius becomes 300 and its revision goes up; other values and a missing row are left alone.
"""

import sqlite3
from pathlib import Path

import pytest

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationsteps35 import _v35
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened
from tests.test_migrations import GOLDEN, raw

KEY = "map/radius_km"


def version_34(path: Path, radius: str | None) -> None:
    """A database at version 34 with this radius stored or none."""
    opened(path, FixedClock()).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 35")
    db.execute("PRAGMA user_version = 34")
    db.execute("DELETE FROM settings WHERE key = ?", (KEY,))
    if radius is not None:
        db.execute("INSERT INTO settings (key, value, rev) VALUES (?, ?, 1)", (KEY, radius))
    db.close()


def stored(path: Path) -> tuple[str, int] | None:
    db = sqlite3.connect(path)
    try:
        row = db.execute("SELECT value, rev FROM settings WHERE key = ?", (KEY,)).fetchone()
        return None if row is None else (str(row[0]), int(row[1]))
    finally:
        db.close()


@pytest.mark.parametrize(
    ("was", "now"),
    [
        ("1000", ("300", 2)),
        ("301", ("300", 2)),
        (" 450 ", ("300", 2)),
        ("300", ("300", 1)),
        ("150", ("150", 1)),
        ("10", ("10", 1)),
        ("far", ("far", 1)),
        ("1.5", ("1.5", 1)),
    ],
)
def test_a_radius_above_300_km_is_brought_to_300_and_the_others_are_left(
    tmp_path: Path, was: str, now: tuple[str, int]
) -> None:
    path = tmp_path / DB_NAME
    version_34(path, was)
    s = opened(path, FixedClock())
    assert s.version() == SCHEMA_VERSION and [(r[0], r[1], r[2]) for r in s.history()][-1] == (35, "_v35", GOLDEN[35])
    s.close()
    assert stored(path) == now


def test_a_file_with_no_radius_row_gets_none_and_a_second_start_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    version_34(path, None)
    opened(path, FixedClock()).close()
    assert stored(path) is None
    version_34(path, "800")
    opened(path, FixedClock()).close()
    opened(path, FixedClock()).close()
    assert stored(path) == ("300", 2)


def test_the_step_writes_one_line_in_the_log_for_a_radius_it_changes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, rev INTEGER NOT NULL)")
    db.execute("INSERT INTO settings VALUES (?, '600', 1)", (KEY,))
    with caplog.at_level("INFO"):
        _v35(db)
    assert db.execute("SELECT value FROM settings").fetchone() == ("300",) and "600 km" in caplog.text
