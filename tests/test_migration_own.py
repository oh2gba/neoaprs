"""Migration 13 (neoaprs/migrations2.py): the tables `own_object` and `own_bulletin`, where the objects, items and bulletins of our own are kept; a database of the version before keeps everything and gets
the two tables empty, a step that doubts changes nothing, and the tables refuse what the program cannot produce."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs import migrations as migrations_module, migrations2
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, try_open
from tests.test_migration_rf_only import version_eleven
from tests.test_migrations import GOLDEN, STAMP, raw, shape

OBJECT = ("LEADER", "object", 60.17, 24.94, "/", ">", "Rescue 1", 88, 40.0, "WIDE1-1,WIDE2-1", 1, STAMP, STAMP, 2, STAMP)
INSERT_OBJECT = "INSERT INTO own_object (name, kind, lat, lon, symbol_table, symbol_code, comment, course_deg, speed_kmh, path, alive, created_at, updated_at, sent, last_sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
BULLETIN = ("BLN3HAMS", "HAMS", "Net tonight 20:00", STAMP, 2, STAMP, "2026-10-21T12:02:00.000000Z")
INSERT_BULLETIN = "INSERT INTO own_bulletin (slot, group_name, text, created_at, sent, first_sent_at, last_sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)"


def version_twelve(path: Path, clock: FixedClock) -> None:
    """A database at schema version 12: preferences, messages and a bulletin heard, user_version 12."""
    version_eleven(path, clock)
    db = raw(path)
    migrations_module._v12(db)
    db.execute("PRAGMA user_version = 12")
    db.execute("INSERT INTO schema_history (version, name, sha256, applied) VALUES (12, '_v12', ?, ?)", (GOLDEN[12], int(clock().timestamp())))
    db.execute("INSERT INTO bulletin (sender, slot, group_name, text, first_heard, last_heard, times_heard) VALUES ('OH2XYZ', 'BLN3HAMS', 'HAMS', 'Net tonight', ?, ?, 2)", (STAMP, STAMP))
    db.close()


def test_a_database_of_version_twelve_gets_the_two_empty_tables_and_keeps_everything_it_had(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_twelve(old, clock)
    before = raw(old)
    messages = before.execute("SELECT id, text, state FROM message ORDER BY id").fetchall()
    prefs = before.execute("SELECT call, path, rf_only FROM station_pref WHERE path IS NOT NULL OR attempts IS NOT NULL OR rf_only = 1 ORDER BY call").fetchall()      # (a row that held only a timeout is deleted by migration 17)
    board = before.execute("SELECT sender, slot, text, times_heard FROM bulletin").fetchall()
    assert {"own_object", "own_bulletin"} & {r[0] for r in before.execute("SELECT name FROM sqlite_master")} == set() and messages and prefs and board
    before.close()
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 13
    assert shape(migrated.db) == shape(fresh.db), "a migrated database has exactly the tables, indexes and checks of a new one"
    assert {"own_object", "own_bulletin"} <= migrated.tables()
    assert [migrated.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("own_object", "own_bulletin")] == [0, 0]
    assert migrated.db.execute("SELECT id, text, state FROM message ORDER BY id").fetchall() == messages
    assert migrated.db.execute("SELECT call, path, rf_only FROM station_pref ORDER BY call").fetchall() == prefs
    assert migrated.db.execute("SELECT sender, slot, text, times_heard FROM bulletin").fetchall() == board
    assert [(r[0], r[1], r[2]) for r in migrated.history()][12:] == [(13, "_v13", GOLDEN[13]), (14, "_v14", GOLDEN[14]), (15, "_v15", GOLDEN[15]), (16, "_v16", GOLDEN[16]), (17, "_v17", GOLDEN[17]), (18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19])]
    migrated.db.execute(INSERT_OBJECT, OBJECT)
    migrated.db.execute(INSERT_BULLETIN, BULLETIN)
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v12-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 12 and "own_object" not in {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
    copy.close()


def test_the_object_table_takes_an_object_and_an_item_with_and_without_a_path_and_has_each_name_once(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(INSERT_OBJECT, OBJECT)
    s.db.execute(INSERT_OBJECT, ("AID", "item", -33.9, 151.2, "\\", "+", "", None, None, None, 0, STAMP, STAMP, 0, None))
    s.db.execute(INSERT_OBJECT, ("A", "object", 0, 0, "5", "k", "x" * 43, 0, 0, None, 1, STAMP, STAMP, 0, None))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        s.db.execute(INSERT_OBJECT, OBJECT)
    assert s.db.execute("SELECT name, kind, path, alive FROM own_object ORDER BY name").fetchall() == [("A", "object", None, 1), ("AID", "item", None, 0), ("LEADER", "object", "WIDE1-1,WIDE2-1", 1)]
    s.close()


@pytest.mark.parametrize("change, name", [
    ({0: ""}, "own_object_name_length"), ({0: "TENCHARSXX"}, "own_object_name_length"), ({1: "marker"}, "own_object_kind"), ({2: 91.0}, "own_object_lat_range"), ({2: -90.5}, "own_object_lat_range"),
    ({3: 180.5}, "own_object_lon_range"), ({4: ""}, "own_object_table_one"), ({4: "//"}, "own_object_table_one"), ({5: ""}, "own_object_code_one"), ({6: "x" * 44}, "own_object_comment_length"),
    ({7: 360}, "own_object_course_range"), ({7: -1}, "own_object_course_range"), ({8: 1851.0}, "own_object_speed_range"), ({8: -1.0}, "own_object_speed_range"),
    ({9: "wide1-1"}, "own_object_path_form"), ({9: ""}, "own_object_path_form"), ({9: ",WIDE1-1"}, "own_object_path_form"), ({9: "WIDE1-1,"}, "own_object_path_form"), ({9: "A,,B"}, "own_object_path_form"),
    ({10: 2}, "own_object_alive"), ({10: None}, "NOT NULL"), ({11: "noon"}, "own_object_created_form"), ({12: "2026-10-21"}, "own_object_updated_form"), ({13: -1}, "own_object_sent_count"),
    ({13: 1, 14: None}, "own_object_sent_has_time"), ({14: "yesterday"}, "own_object_last_sent_form"), ({1: "item", 0: "AB"}, "own_object_item_name"), ({2: "north"}, "cannot store"), ({0: None}, "NOT NULL")])
def test_the_object_table_refuses_what_the_program_cannot_produce(tmp_path: Path, change: dict[int, object], name: str) -> None:
    s = opened(tmp_path / DB_NAME)
    row = list(OBJECT)
    for index, value in change.items():
        row[index] = value
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute(INSERT_OBJECT, row)
    s.close()


def test_the_bulletin_table_takes_a_bulletin_an_announcement_and_a_group_bulletin_and_has_each_slot_once(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(INSERT_BULLETIN, BULLETIN)
    s.db.execute(INSERT_BULLETIN, ("BLN1", "", "Road closed", STAMP, 0, None, None))
    s.db.execute(INSERT_BULLETIN, ("BLNA", "", "x" * 67, STAMP, 1, STAMP, STAMP))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        s.db.execute(INSERT_BULLETIN, BULLETIN)
    assert [r[0] for r in s.db.execute("SELECT slot FROM own_bulletin ORDER BY slot")] == ["BLN1", "BLN3HAMS", "BLNA"]
    s.close()


@pytest.mark.parametrize("change, name", [
    ({0: "BLN"}, "own_bulletin_slot_form"), ({0: "ALL"}, "own_bulletin_slot_form"), ({0: "bln1"}, "own_bulletin_slot_form"), ({0: "BLN3HAMSXX"}, "own_bulletin_slot_form"), ({0: "BLN1 X"}, "own_bulletin_slot_form"),
    ({2: ""}, "own_bulletin_text_length"), ({2: "x" * 68}, "own_bulletin_text_length"), ({3: "noon"}, "own_bulletin_created_form"), ({4: -1}, "own_bulletin_sent_count"),
    ({5: None}, "own_bulletin_sent_has_times"), ({6: None}, "own_bulletin_sent_has_times"), ({5: "2026-10-21T12:03:00.000000Z"}, "own_bulletin_sent_in_order"), ({6: "yesterday"}, "own_bulletin_last_sent_form"),
    ({1: None}, "NOT NULL"), ({2: None}, "NOT NULL")])
def test_the_bulletin_table_refuses_what_the_program_cannot_produce(tmp_path: Path, change: dict[int, object], name: str) -> None:
    s = opened(tmp_path / DB_NAME)
    row = list(BULLETIN)
    for index, value in change.items():
        row[index] = value
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute(INSERT_BULLETIN, row)
    s.close()


@pytest.mark.expects_errors
def test_a_migration_13_that_doubts_changes_nothing(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_twelve(old, clock)
    db = raw(old)
    db.execute("CREATE TABLE own_bulletin (x TEXT)")                           # something is in the way of the second table
    db.close()
    ok, why = try_open(old, clock)
    assert not ok and "own_bulletin" in why
    db = raw(old)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 12 and "own_object" not in {r[0] for r in db.execute("SELECT name FROM sqlite_master")}, "the step is one transaction: the first table is not left behind"
    db.close()


def test_the_step_is_the_one_in_migrations2() -> None:
    assert MIGRATIONS[12] is migrations2._v13
