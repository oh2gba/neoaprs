"""Migration 18 (neoaprs/migrations2.py): the QRU group and the on-request flag of an object of ours; the objects already there keep everything and get no group and the schedule, and the table refuses a group
the program cannot produce."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migration_own import INSERT_OBJECT, OBJECT
from tests.test_migrations import GOLDEN, raw, shape

OLD_INSERT = INSERT_OBJECT


def version_seventeen(path: Path, clock: FixedClock) -> None:
    """A database as version 17 left it, with an object of ours in it."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 18")
    db.execute("PRAGMA user_version = 17")
    step_back(db, 17)
    db.execute(OLD_INSERT, OBJECT)
    db.close()


def test_every_object_there_is_keeps_its_values_and_gets_no_group_and_the_schedule(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_seventeen(old, clock)
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 18
    assert [(r[0], r[1], r[2]) for r in migrated.history()][17:] == [(18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19]), (20, "_v20", GOLDEN[20])]
    assert shape(migrated.db) == shape(fresh.db), "a migrated database has exactly the tables, indexes and checks of a new one"
    assert migrated.db.execute("SELECT name, comment, sent, qru_group, on_request FROM own_object").fetchall() == [("LEADER", "Rescue 1", 2, "", 0)]
    for opened_ in (migrated, fresh):
        opened_.close()


@pytest.mark.parametrize("group, flag, check", [("rp70", 0, "own_object_qru_group_form"), ("LIFEBOATS", 0, "own_object_qru_group_form"), ("R P", 0, "own_object_qru_group_form"), ("RP70", 2, "own_object_on_request")])
def test_the_table_refuses_a_group_that_is_not_one_and_a_flag_that_is_not_a_flag(tmp_path: Path, group: str, flag: int, check: str) -> None:
    db = opened(tmp_path / DB_NAME, FixedClock())
    db.db.execute(OLD_INSERT, OBJECT)
    with pytest.raises(sqlite3.IntegrityError, match=check):
        db.db.execute("UPDATE own_object SET qru_group = ?, on_request = ?", (group, flag))
    db.db.execute("UPDATE own_object SET qru_group = 'RP70', on_request = 1")
    db.close()
