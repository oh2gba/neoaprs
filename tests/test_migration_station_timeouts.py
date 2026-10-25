"""Migration 17 (neoaprs/migrations2.py): the own timeouts of the stations (`station_pref.hide_after_min`) are cleared once, with a line in the log for each; a row that said nothing else is deleted, and the path and RF only
of a station are as they were."""
import logging
from pathlib import Path

import pytest

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrations2 import MIGRATION_LOG
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, STAMP, raw

#           call       path              hide_after_min  attempts  rf_only
ROWS = [("OH2PATH", "WIDE2-1", None, None, 0), ("OH2BOTH", "OH2RCH-2", 45, None, 0), ("OH2TIME", None, 90, None, 0), ("OH2NEVR", None, 0, None, 0), ("OH2RFTM", None, 30, None, 1),
        ("OH2DIRT", "", 10080, None, 0), ("OH2ATTM", None, 5, 2, 0), ("OH2ATT", None, None, 3, 0), ("OH2RFON", None, None, None, 1)]


def version_sixteen(path: Path, clock: FixedClock) -> None:
    """A database as version 16 left it, with these station preferences."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 17")
    step_back(db, 16)
    db.execute("PRAGMA user_version = 16")
    for call, pref_path, minutes, attempts, rf_only in ROWS:
        db.execute("INSERT INTO station_pref (call, path, hide_after_min, attempts, rf_only, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (call, pref_path, minutes, attempts, rf_only, STAMP))
    db.close()


def migrate(folder: Path):  # type: ignore[no-untyped-def]
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_sixteen(old, clock)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 17
    assert [(r[0], r[1], r[2]) for r in migrated.history()][16:] == [(17, "_v17", GOLDEN[17]), (18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19])]
    return migrated


def test_every_own_timeout_is_cleared_and_a_row_that_held_only_that_is_gone(tmp_path: Path) -> None:
    migrated = migrate(tmp_path)
    rows = migrated.db.execute("SELECT call, path, hide_after_min, attempts, rf_only, updated_at FROM station_pref ORDER BY call").fetchall()
    assert rows == [("OH2ATT", None, None, 3, 0, STAMP), ("OH2ATTM", None, None, 2, 0, STAMP), ("OH2BOTH", "OH2RCH-2", None, None, 0, STAMP), ("OH2DIRT", "", None, None, 0, STAMP),
                    ("OH2PATH", "WIDE2-1", None, None, 0, STAMP), ("OH2RFON", None, None, None, 1, STAMP), ("OH2RFTM", None, None, None, 1, STAMP)]
    migrated.close()


def test_a_cleared_timeout_is_not_read_and_the_preferences_that_say_something_are_the_path_and_rf_only(tmp_path: Path) -> None:
    from neoaprs.messagesql import all_prefs
    migrated = migrate(tmp_path)
    assert all_prefs(migrated.db) == [("OH2BOTH", "OH2RCH-2", 0), ("OH2DIRT", "", 0), ("OH2PATH", "WIDE2-1", 0), ("OH2RFON", None, 1), ("OH2RFTM", None, 1)]
    migrated.close()


def test_one_info_line_for_each_station_that_had_a_timeout(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        migrate(tmp_path).close()
    lines = [r.getMessage() for r in caplog.records if "own timeout" in r.getMessage() and r.levelno == logging.INFO]
    assert lines == ["OH2ATTM: the own timeout of 5 minutes removed, the time on the map of the Stations tab counts", "OH2BOTH: the own timeout of 45 minutes removed, the time on the map of the Stations tab counts",
                     "OH2DIRT: the own timeout of 10080 minutes removed, the time on the map of the Stations tab counts", "OH2NEVR: the own timeout of never removed, the time on the map of the Stations tab counts",
                     "OH2RFTM: the own timeout of 30 minutes removed, the time on the map of the Stations tab counts", "OH2TIME: the own timeout of 90 minutes removed, the time on the map of the Stations tab counts"]


def test_a_database_without_timeouts_is_as_it_was_and_a_new_one_has_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    fresh = opened(tmp_path / DB_NAME)
    assert fresh.db.execute("SELECT COUNT(*) FROM station_pref").fetchone() == (0,)
    fresh.close()
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        again = opened(tmp_path / DB_NAME)
    assert again.version() == SCHEMA_VERSION and not [r for r in caplog.records if "own timeout" in r.getMessage()]
    again.close()
