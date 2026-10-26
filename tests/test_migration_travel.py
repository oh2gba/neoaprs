"""Migrations 19 and 20 (neoaprs/migrationsteps12to21.py): the rows of `beacon/mobile` and of the seven `smart/*` numbers are deleted once, with a line in the log for each; every other setting is as it was,
and `beacon/travel` has no row, so the car is in force. A row `beacon/moving_as`, which an earlier build stored for the setting that is now `beacon/travel`, is renamed once, with a line in the log."""
import logging
from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS, Config
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.smartbeacon import PRESETS
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw

GONE = {"beacon/mobile": "true", "smart/fast_kmh": "90", "smart/fast_sec": "45", "smart/slow_kmh": "5", "smart/slow_sec": "900", "smart/turn_min_deg": "25", "smart/turn_min_sec": "20", "smart/turn_slope": "200"}
KEPT = {"station/call": "OH2GBA", "gps/source": "gpsd", "gps/host": "10.0.0.7:2947", "gps/baud": "9600", "beacon/interval_min": "45", "beacon/path": "WIDE2-2", "beacon/last_sent_at": "2026-10-23T10:00:00Z"}


def version_eighteen(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 18 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 19")
    step_back(db, 18)
    db.execute("PRAGMA user_version = 18")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, tuple[str, int]]:
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_eighteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 20
    assert [(r[0], r[1], r[2]) for r in migrated.history()][18:] == [(19, "_v19", GOLDEN[19]), (20, "_v20", GOLDEN[20]), (21, "_v21", GOLDEN[21])]
    found = {str(k): (str(v), int(rev)) for k, v, rev in migrated.db.execute("SELECT key, value, rev FROM settings")}
    migrated.close()
    return found


def test_the_rows_of_the_removed_settings_are_deleted_and_every_other_is_as_it_was(tmp_path: Path) -> None:
    found = migrate(tmp_path, {**GONE, **KEPT})
    assert found == {key: (value, 1) for key, value in KEPT.items()}


def test_a_moving_station_of_the_old_settings_travels_by_car_when_the_gps_is_set(tmp_path: Path) -> None:
    found = migrate(tmp_path, {**GONE, **KEPT})
    config = Config.from_data({key: value for key, (value, _) in found.items()})
    assert config.mobile and config.beacon_travel == "car" and config.smart == PRESETS["car"]


def test_one_info_line_for_each_row_removed_with_its_old_value(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        migrate(tmp_path, {**GONE, **KEPT})
    lines = [r.getMessage() for r in caplog.records if " removed (was " in r.getMessage() and r.levelno == logging.INFO]
    assert [line.split(" removed")[0] for line in lines] == sorted(GONE)
    assert lines[0].startswith("beacon/mobile removed (was true)") and lines[3].startswith("smart/slow_kmh removed (was 5)")


def test_a_database_with_none_of_these_rows_is_as_it_was_and_says_nothing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        assert migrate(tmp_path, KEPT) == {key: (value, 1) for key, value in KEPT.items()}
    assert not [r for r in caplog.records if " removed (was " in r.getMessage()]


def test_a_removed_setting_that_is_stored_by_hand_is_ignored_and_cannot_be_set() -> None:
    assert Config.from_data(GONE) == DEFAULTS
    for key in GONE:
        with pytest.raises(ValueError, match=f"{key}: no such setting"):
            Config.check(key, "7")


def test_a_stored_moving_as_row_is_renamed_to_travel_with_its_value_and_its_revision_and_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {**KEPT, "beacon/moving_as": "boat"})
    assert found == {**{key: (value, 1) for key, value in KEPT.items()}, "beacon/travel": ("boat", 1)}
    assert [r.getMessage() for r in caplog.records if "beacon/moving_as" in r.getMessage()] == ["beacon/moving_as renamed to beacon/travel (value boat)"]
    assert Config.from_data({key: value for key, (value, _) in found.items()}).smart == PRESETS["boat"]


def test_a_database_with_both_rows_keeps_the_travel_row_and_loses_the_other(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {**KEPT, "beacon/moving_as": "foot", "beacon/travel": "bicycle"})
    assert found["beacon/travel"] == ("bicycle", 1) and "beacon/moving_as" not in found
    assert [r.getMessage() for r in caplog.records if "beacon/moving_as" in r.getMessage()] == ["beacon/moving_as removed (was foot): beacon/travel is set"]


def test_a_database_without_a_moving_as_row_gets_no_travel_row_and_no_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, KEPT)
    assert "beacon/travel" not in found and not [r for r in caplog.records if "beacon/moving_as" in r.getMessage()]
