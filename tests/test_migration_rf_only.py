"""Migration 12 (neoaprs/migrations2.py): `rf_only` joins the path, the timeout and the attempts in `station_pref`; a database of the version before keeps every preference, and the table refuses what the program cannot produce."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs import migrations2
from neoaprs.store import DB_NAME
from neoaprs.migrations import SCHEMA_VERSION
from tests.support.clock import FixedClock
from tests.support.migrated import opened, try_open
from tests.test_migrations import GOLDEN, STAMP, raw, shape, version_ten

COLUMNS = "call, path, hide_after_min, attempts, updated_at"


def version_eleven(path: Path, clock: FixedClock) -> None:
    """A database at schema version 11: preferences of every kind (a path, an empty path, a timeout, attempts, all of them), user_version 11."""
    version_ten(path, clock)
    from neoaprs import migrations as migrations_module
    db = raw(path)
    migrations_module._v11(db)
    db.execute("PRAGMA user_version = 11")
    db.execute("INSERT INTO schema_history (version, name, sha256, applied) VALUES (11, '_v11', ?, ?)", (GOLDEN[11], int(clock().timestamp())))
    for row in [("OH2RDG", "OH2RCH-2,WIDE2-1", None, None), ("OH2DIR", "", None, None), ("OH2PU-9", None, 90, None), ("OH2ATT", None, None, 2), ("OH2ALL", "WIDE2-2", 0, 4)]:
        db.execute(f"INSERT OR REPLACE INTO station_pref ({COLUMNS}) VALUES (?, ?, ?, ?, ?)", (*row, STAMP))
    db.close()


def test_a_database_of_version_eleven_gets_rf_only_off_for_every_preference_and_keeps_the_rest(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_eleven(old, clock)
    before = raw(old)
    prefs = before.execute(f"SELECT {COLUMNS} FROM station_pref ORDER BY call").fetchall()
    messages = before.execute("SELECT id, text, state FROM message ORDER BY id").fetchall()
    assert "rf_only" not in {r[1] for r in before.execute("PRAGMA table_info(station_pref)")} and len(prefs) >= 5 and {r[0] for r in prefs} >= {'EMAIL-2', 'OH2RDG', 'OH2ATT'}
    before.close()
    prefs = [(call, path, None, attempts, stamp) for call, path, hide, attempts, stamp in prefs if not (path is None and attempts is None)]       # (migration 17 clears the timeouts and deletes a row that said only that)
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 12
    assert shape(migrated.db) == shape(fresh.db), "a migrated database has exactly the tables, indexes and checks of a new one"
    assert migrated.db.execute(f"SELECT {COLUMNS} FROM station_pref ORDER BY call").fetchall() == prefs
    assert migrated.db.execute("SELECT COUNT(*) FROM station_pref WHERE rf_only = 0").fetchone() == (len(prefs),)
    assert migrated.db.execute("SELECT id, text, state FROM message ORDER BY id").fetchall() == messages
    assert [(r[0], r[1], r[2]) for r in migrated.history()][11:] == [(12, "_v12", GOLDEN[12]), (13, "_v13", GOLDEN[13]), (14, "_v14", GOLDEN[14]), (15, "_v15", GOLDEN[15]), (16, "_v16", GOLDEN[16]), (17, "_v17", GOLDEN[17]), (18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19]), (20, "_v20", GOLDEN[20]), (21, "_v21", GOLDEN[21])]
    migrated.db.execute("UPDATE station_pref SET rf_only = 1 WHERE call = 'OH2RDG'")          # and the new column takes it
    migrated.db.execute("INSERT INTO station_pref (call, rf_only, updated_at) VALUES ('OH2NEWX', 1, ?)", (STAMP,))
    assert migrated.db.execute("SELECT call FROM station_pref WHERE rf_only = 1 ORDER BY call").fetchall() == [("OH2NEWX",), ("OH2RDG",)]
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v11-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 11 and "rf_only" not in {r[1] for r in copy.execute("PRAGMA table_info(station_pref)")}
    copy.close()


@pytest.mark.parametrize("row, name", [(("OH2RDG", None, None, None, 2, STAMP), "station_pref_rf_only"), (("OH2RDG", None, None, None, -1, STAMP), "station_pref_rf_only"),
                                       (("OH2RDG", None, None, None, "yes", STAMP), "cannot store"), (("OH2RDG", None, None, None, None, STAMP), "NOT NULL"),
                                       (("OH2RDG", None, None, None, 0, STAMP), "station_pref_says_something")])
def test_the_station_pref_table_refuses_an_rf_only_the_program_cannot_produce(tmp_path: Path, row: tuple[object, ...], name: str) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute("INSERT INTO station_pref (call, path, hide_after_min, attempts, rf_only, updated_at) VALUES (?, ?, ?, ?, ?, ?)", row)
    s.db.execute("INSERT INTO station_pref (call, rf_only, updated_at) VALUES ('OH2RDG', 1, ?)", (STAMP,))               # (RF only alone says something)
    assert s.db.execute("SELECT rf_only FROM station_pref").fetchall() == [(1,)]
    s.close()


@pytest.mark.expects_errors
def test_a_migration_12_that_doubts_changes_nothing_and_leaves_the_preferences_where_they_were(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_eleven(old, clock)
    db = raw(old)
    db.execute("CREATE TABLE station_pref_old (x TEXT)")                       # something is in the way
    db.close()
    ok, why = try_open(old, clock)
    assert not ok and "station_pref_old" in why
    db = raw(old)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11 and db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0] >= 5
    assert "rf_only" not in {r[1] for r in db.execute("PRAGMA table_info(station_pref)")}
    db.close()


def test_the_step_is_the_one_in_migrations2() -> None:
    from neoaprs.migrations import MIGRATIONS
    assert MIGRATIONS[11] is migrations2._v12
