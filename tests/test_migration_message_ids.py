"""Migration 23 (neoaprs/migrationsteps22on.py): `message.id` is AUTOINCREMENT, so a database of the version before, in which the newest messages were deleted, never gives their ids again; every message is kept with its id,
the table is the one a new database has, and a step that doubts changes nothing."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs import migrationsteps22on
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, try_open
from tests.test_migrations import GOLDEN, STAMP, raw, shape

COLUMNS = "id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route"
MESSAGES = [(1, STAMP, "out", "OH2GBA", "OH2RDG", "one", "1", "acked", 1, STAMP, STAMP, 6, ""), (2, STAMP, "in", "OH2RDG", "OH2GBA", "two", "7", "received", 0, None, None, 6, ""),
            (5, STAMP, "out", "OH2GBA", "OH2XYZ", "five", None, "failed", 6, STAMP, None, 10, "WIDE1-1")]


def version_twentytwo(path: Path, clock: FixedClock, deleted: tuple[int, ...] = (), chain_of: int = 0) -> None:
    """A database as version 22 left it: `message` with a bare INTEGER PRIMARY KEY, the messages of MESSAGES, and those with the ids `deleted` deleted again; the delivery chain of the message
    `chain_of` (a message that is gone) is still there when it is not 0."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 23")
    sql = str(db.execute("SELECT sql FROM sqlite_master WHERE name = 'message'").fetchone()[0])
    assert "AUTOINCREMENT" in sql
    db.execute("DROP TABLE message")
    db.execute("DROP INDEX IF EXISTS message_calls")
    db.execute(sql.replace(" AUTOINCREMENT", ""))
    db.execute("CREATE INDEX message_calls ON message (to_call, from_call, at)")
    db.execute("PRAGMA user_version = 22")
    for row in MESSAGES:
        db.execute(f"INSERT INTO message ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
    for number in deleted:
        db.execute("DELETE FROM message WHERE id = ?", (number,))
    if chain_of:
        db.execute("INSERT INTO message_attempt (message_id, attempt, sent_at, path) VALUES (?, 1, ?, '')", (chain_of, STAMP))
    db.close()


def migrate(folder: Path, deleted: tuple[int, ...] = (), chain_of: int = 0) -> sqlite3.Connection:
    clock = FixedClock()
    old = folder / "old" / DB_NAME
    old.parent.mkdir()
    version_twentytwo(old, clock, deleted, chain_of)
    migrated = opened(old, clock)
    fresh = opened(folder / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 23
    assert shape(migrated.db) == shape(fresh.db), "a migrated database has exactly the tables, indexes and checks of a new one"
    assert [(r[0], r[1], r[2]) for r in migrated.history()][22:] == [(23, "_v23", GOLDEN[23])]
    fresh.close()
    return migrated.db


def next_id(db: sqlite3.Connection) -> int:
    db.execute("INSERT INTO message (at, direction, from_call, to_call, text, state) VALUES (?, 'out', 'OH2GBA', 'OH2NEW', 'next', 'sending')", (STAMP,))
    return int(db.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_a_database_of_version_twentytwo_keeps_every_message_with_its_id(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    assert db.execute(f"SELECT {COLUMNS} FROM message ORDER BY id").fetchall() == MESSAGES
    assert "AUTOINCREMENT" in str(db.execute("SELECT sql FROM sqlite_master WHERE name = 'message'").fetchone()[0])
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'message_calls'").fetchall() == [("message_calls",)]
    db.close()


@pytest.mark.parametrize("deleted, expected", [((), 6), ((1,), 6), ((2, 5), 2), ((1, 2, 5), 1)], ids=["none deleted", "the first deleted", "the newest deleted", "all deleted"])
def test_the_next_message_gets_an_id_above_the_highest_the_table_holds(tmp_path: Path, deleted: tuple[int, ...], expected: int) -> None:
    db = migrate(tmp_path, deleted)
    assert next_id(db) == expected, "the table's own highest id is all the daemon knows of the ids that were given"
    db.close()


def test_the_next_message_is_above_the_id_of_a_deleted_one_whose_delivery_chain_is_still_there(tmp_path: Path) -> None:
    db = migrate(tmp_path, deleted=(5,), chain_of=9)
    assert next_id(db) == 10, "the chain rows of message 9 must not be shown under a new message"
    db.close()


def test_an_empty_message_table_starts_at_one(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_twentytwo(old, clock, deleted=(1, 2, 5))
    migrated = opened(old, clock)
    assert next_id(migrated.db) == 1
    migrated.close()


def test_the_id_of_a_deleted_message_is_not_given_again_after_the_migration(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    db.execute("DELETE FROM message WHERE id = 5")
    assert next_id(db) == 6
    db.execute("DELETE FROM message")
    assert next_id(db) == 7
    db.close()


@pytest.mark.expects_errors
def test_a_migration_23_that_doubts_changes_nothing_and_leaves_the_messages_where_they_were(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_twentytwo(old, clock)
    db = raw(old)
    db.execute("CREATE TABLE message_old (x TEXT)")                              # something is in the way
    db.close()
    ok, why = try_open(old, clock)
    assert not ok and "message_old" in why
    db = raw(old)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 22 and db.execute("SELECT COUNT(*) FROM message").fetchone()[0] == len(MESSAGES)
    assert "AUTOINCREMENT" not in str(db.execute("SELECT sql FROM sqlite_master WHERE name = 'message'").fetchone()[0])
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'message_calls'").fetchall() == [("message_calls",)]
    db.close()


def test_the_step_is_the_one_in_migrations() -> None:
    assert MIGRATIONS[22] is migrationsteps22on._v23
    assert MIGRATION_LOG
