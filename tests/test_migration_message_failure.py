"""Migration 28 (neoaprs/migrationsteps22on.py): a failed message says why it failed,
`message.failure`. Existing messages keep what they had and get no failure; the column takes the one
reason there is.
"""

import sqlite3
from pathlib import Path

import pytest

from neoaprs.messagelog import message_of
from neoaprs.messagesql import held_messages
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.support.migrated32 import newest
from tests.test_migrations import GOLDEN, STAMP, raw, shape

COLUMNS = "id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route, seal, wire, radio"
# The radio of a message of version 27, and what migration 32 makes of it
RADIOS = {"": None, "fm": 1}
MESSAGES = [
    (1, STAMP, "out", "OH2GBA", "OH2RDG", "one", "1", "acked", 1, STAMP, STAMP, 4, "", "", None, ""),
    (2, STAMP, "in", "OH2RDG", "OH2GBA", "two", "7", "received", 0, None, None, 4, "direct", "", None, "fm"),
    (3, STAMP, "out", "OH2GBA", "OH2XYZ", "three", "2", "failed", 4, STAMP, None, 4, "", "", None, ""),
    (4, STAMP, "out", "OH2GBA", "OH2XYZ", "four", "3", "failed", 0, None, None, 4, "", "", None, ""),
]


def version_twenty_seven(path: Path, clock: FixedClock) -> None:
    """A database as version 27 left it, with the messages of MESSAGES (two of them failed, one of
    those never sent)."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 28")
    step_back(db, 27)
    db.execute("PRAGMA user_version = 27")
    # A database with messages is a station's: migration 31 gives it radio 1
    db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    for row in MESSAGES:
        db.execute(f"INSERT INTO message ({COLUMNS}) VALUES ({', '.join('?' * len(row))})", row)
    db.close()


def migrate(folder: Path) -> sqlite3.Connection:
    clock = FixedClock()
    old = folder / "old" / DB_NAME
    old.parent.mkdir()
    version_twenty_seven(old, clock)
    migrated = newest(old, clock)
    fresh = newest(folder / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 28
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert [(r[0], r[1], r[2]) for r in migrated.history()][27:] == [
        (n, f"_v{n}", GOLDEN[n]) for n in range(28, SCHEMA_VERSION + 1)
    ]
    fresh.close()
    return migrated.db


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_every_message_is_kept_and_none_has_a_failure(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    assert db.execute(f"SELECT {COLUMNS} FROM message ORDER BY id").fetchall() == [
        (*row[:-1], RADIOS[row[-1]]) for row in MESSAGES
    ], "every column as it was, the radio by its id"
    assert db.execute("SELECT failure FROM message ORDER BY id").fetchall() == [(None,)] * len(MESSAGES)
    records = sorted((message_of(row) for row in held_messages(db, 10)), key=lambda r: r.id)
    assert [(r.id, r.state, r.failure) for r in records] == [
        (1, "acked", None),
        (2, "received", None),
        (3, "failed", None),
        (4, "failed", None),
    ], "an old failed message failed for want of an answer"
    assert [(r.id, r.radio_id) for r in records] == [(1, None), (2, 1), (3, None), (4, None)], (
        "the one that came in came on the FM radio, as it did"
    )
    db.close()


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_the_column_takes_the_reason_there_is_and_nothing_else(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    db.execute("UPDATE message SET failure = 'too_long_for_radio' WHERE id = 4")
    assert message_of(held_messages(db, 10)[0]).failure == "too_long_for_radio"
    for wrong in ("", "message.too_long_for_radio", "the message is too long"):
        with pytest.raises(sqlite3.IntegrityError, match="message_failure"):
            db.execute("UPDATE message SET failure = ? WHERE id = 3", (wrong,))
    db.close()
