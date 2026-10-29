"""Migration 22 (neoaprs/migrationsteps22on.py): the alerts of a station (`alert_on_air`, `alert_within_km`, `alert_direct`) join the path and RF only in `station_pref`, a database of the version before keeps every
preference with no alert, the table refuses what the program cannot produce and takes a row that holds only an alert; and the old default of the alert command, which every save stored, gives way to the new one
while a command of the operator's own stays."""
import logging
import sqlite3
from pathlib import Path

import pytest

from neoaprs import migrationsteps22on
from neoaprs.alertcommand import LINUX_ALERT_COMMAND, WINDOWS_ALERT_COMMAND
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back, try_open
from tests.test_migrations import GOLDEN, STAMP, raw, shape

COLUMNS = "call, path, attempts, rf_only, updated_at"
PREFS = [("OH2RDG", "OH2RCH-2,WIDE2-1", None, 0, STAMP), ("OH2DIR", "", None, 1, STAMP), ("OH2RFO", None, None, 1, STAMP), ("EMAIL-2", None, 2, 0, STAMP)]


def version_twentyone(path: Path, clock: FixedClock, command: str | None) -> None:
    """A database as version 21 left it: preferences of every kind there was, and the alert command as `command` (None: no row)."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 22")
    step_back(db, 21)
    db.execute("PRAGMA user_version = 21")
    for row in PREFS:
        db.execute(f"INSERT INTO station_pref ({COLUMNS}) VALUES (?, ?, ?, ?, ?)", row)
    if command is not None:
        db.execute("INSERT INTO settings (key, value) VALUES ('messages/alert_command', ?)", (command,))
    db.close()


def migrate(folder: Path, command: str | None = None) -> sqlite3.Connection:
    clock = FixedClock()
    old = folder / "old" / DB_NAME
    old.parent.mkdir()
    version_twentyone(old, clock, command)
    migrated = opened(old, clock)
    fresh = opened(folder / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 22
    assert shape(migrated.db) == shape(fresh.db), "a migrated database has exactly the tables, indexes and checks of a new one"
    assert [(r[0], r[1], r[2]) for r in migrated.history()][21:] == [(22, "_v22", GOLDEN[22]), (23, "_v23", GOLDEN[23])]
    fresh.close()
    return migrated.db


def test_a_database_of_version_twentyone_keeps_every_preference_with_no_alert_and_takes_one_that_is_only_an_alert(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    assert db.execute(f"SELECT {COLUMNS} FROM station_pref ORDER BY call").fetchall() == sorted(PREFS)
    assert db.execute("SELECT COUNT(*) FROM station_pref WHERE alert_on_air = 0 AND alert_within_km IS NULL AND alert_direct = 0").fetchone() == (len(PREFS),)
    for call, on_air, within, direct in (("OH2AIR", 1, None, 0), ("OH2NEAR", 0, 10, 0), ("OH2DCT", 0, None, 1), ("OH2ALL", 1, 1000, 1)):
        db.execute("INSERT INTO station_pref (call, alert_on_air, alert_within_km, alert_direct, updated_at) VALUES (?, ?, ?, ?, ?)", (call, on_air, within, direct, STAMP))
    assert db.execute("SELECT COUNT(*) FROM station_pref").fetchone() == (len(PREFS) + 4,)
    db.close()


@pytest.mark.parametrize("row, name", [(("OH2X", 2, None, 0), "station_pref_alert_on_air"), (("OH2X", 0, 0, 0), "station_pref_alert_within_range"), (("OH2X", 0, 1001, 0), "station_pref_alert_within_range"),
                                       (("OH2X", 0, None, 2), "station_pref_alert_direct"), (("OH2X", 0, "near", 0), "cannot store"), (("OH2X", 0, None, 0), "station_pref_says_something")])
def test_the_table_refuses_an_alert_the_program_cannot_produce(tmp_path: Path, row: tuple[object, ...], name: str) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute("INSERT INTO station_pref (call, alert_on_air, alert_within_km, alert_direct, updated_at) VALUES (?, ?, ?, ?, ?)", (*row, STAMP))
    s.close()


@pytest.mark.parametrize("old", [migrationsteps22on._OLD_LINUX_ALERT, migrationsteps22on._OLD_WINDOWS_ALERT])
def test_the_old_default_alert_command_gives_way_to_the_new_one_with_a_line_in_the_log(tmp_path: Path, old: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    db = migrate(tmp_path, old)
    assert db.execute("SELECT value FROM settings WHERE key = 'messages/alert_command'").fetchall() == []
    assert any("messages/alert_command was the old default" in r.getMessage() for r in caplog.records)
    db.close()


def test_a_command_of_the_operators_own_stays_and_the_old_defaults_are_the_new_ones_with_the_title_of_the_alert(tmp_path: Path) -> None:
    db = migrate(tmp_path, 'curl -s -H "Title: APRS message from $NEOAPRS_FROM" -d "$NEOAPRS_TEXT" https://ntfy.sh/x')
    assert db.execute("SELECT value FROM settings WHERE key = 'messages/alert_command'").fetchone()[0].startswith("curl -s")
    db.close()
    assert migrationsteps22on._OLD_LINUX_ALERT.replace('"APRS message from $NEOAPRS_FROM"', '"$NEOAPRS_TITLE"') == LINUX_ALERT_COMMAND
    assert migrationsteps22on._OLD_WINDOWS_ALERT.replace("'APRS message from '+$env:NEOAPRS_FROM", "$env:NEOAPRS_TITLE") == WINDOWS_ALERT_COMMAND


@pytest.mark.expects_errors
def test_a_migration_22_that_doubts_changes_nothing_and_leaves_the_preferences_where_they_were(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_twentyone(old, clock, migrationsteps22on._OLD_LINUX_ALERT)
    db = raw(old)
    db.execute("CREATE TABLE station_pref_old (x TEXT)")                       # something is in the way
    db.close()
    ok, why = try_open(old, clock)
    assert not ok and "station_pref_old" in why
    db = raw(old)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 21 and db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0] == len(PREFS)
    assert "alert_on_air" not in {r[1] for r in db.execute("PRAGMA table_info(station_pref)")} and db.execute("SELECT COUNT(*) FROM settings WHERE key = 'messages/alert_command'").fetchone() == (1,)
    db.close()


def test_the_step_is_the_one_in_migrations() -> None:
    assert MIGRATIONS[21] is migrationsteps22on._v22
