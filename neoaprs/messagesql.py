"""The statements of the message table, as functions of a connection that the database thread runs (messagelog.py is the part that asks for them).

A row is a tuple in the order of MESSAGE_COLUMNS; the codec between a row and a `MessageRecord` is messagelog.py's. Nothing here begins or commits a transaction."""
import sqlite3
from collections.abc import Sequence
from typing import Any

MESSAGE_COLUMNS = ("id", "at", "direction", "from_call", "to_call", "text", "msg_id", "state", "attempts", "last_attempt_at", "acked_at", "attempts_max", "route")
_LIST = ", ".join(MESSAGE_COLUMNS)
_NEW_LIST = ", ".join(MESSAGE_COLUMNS[1:])
_NEW_PLACES = ", ".join("?" * (len(MESSAGE_COLUMNS) - 1))

Row = tuple[Any, ...]


def insert_message(db: sqlite3.Connection, row: Sequence[object]) -> int:
    """Adds a message (the row without its id); the id the database gave it."""
    cursor = db.execute(f"INSERT INTO message ({_NEW_LIST}) VALUES ({_NEW_PLACES})", tuple(row))
    return int(cursor.lastrowid or 0)


def update_message(db: sqlite3.Connection, number: int, state: str, attempts: int, last_attempt_at: str | None, acked_at: str | None) -> int:
    """Sets what changes in a message as it is sent; how many rows it found (0 or 1)."""
    return db.execute("UPDATE message SET state = ?, attempts = ?, last_attempt_at = ?, acked_at = ? WHERE id = ?", (state, attempts, last_attempt_at, acked_at, number)).rowcount


def delete_message(db: sqlite3.Connection, number: int) -> int:
    """Removes a message and its delivery chain; how many message rows it found (0 or 1)."""
    clear_chain(db, number)
    return db.execute("DELETE FROM message WHERE id = ?", (number,)).rowcount


def delete_conversation(db: sqlite3.Connection, call: str) -> int:
    """Removes every message of the conversation with the call, with the delivery chains of those we sent: those we sent to it and those it sent to us (not those it was overheard sending to somebody else); how many."""
    ours = "state <> 'overheard' AND ((direction = 'out' AND to_call = ?1) OR (direction = 'in' AND from_call = ?1))"
    for table in ("message_hop", "message_attempt"):
        db.execute(f"DELETE FROM {table} WHERE message_id IN (SELECT id FROM message WHERE {ours})", (call,))
    return db.execute(f"DELETE FROM message WHERE {ours}", (call,)).rowcount


def delete_overheard(db: sqlite3.Connection, from_call: str, to_call: str) -> int:
    """Removes every message we only overheard `from_call` sending to `to_call`; how many."""
    return db.execute("DELETE FROM message WHERE state = 'overheard' AND from_call = ? AND to_call = ?", (from_call, to_call)).rowcount


def recent_messages(db: sqlite3.Connection, count: int, overheard: bool) -> list[Row]:
    """The latest `count` messages, the newest first: those we sent or were sent, or (`overheard`) those we only overheard."""
    return [tuple(r) for r in db.execute(f"SELECT {_LIST} FROM message WHERE (state = 'overheard') = ? ORDER BY id DESC LIMIT ?", (overheard, max(0, count)))]


def held_messages(db: sqlite3.Connection, count: int) -> list[Row]:
    """The latest `count` messages of any kind (overheard ones too), the newest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_LIST} FROM message ORDER BY id DESC LIMIT ?", (max(0, count),))]


def sending_messages(db: sqlite3.Connection) -> list[Row]:
    """The messages that are still being sent, the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_LIST} FROM message WHERE state = 'sending' ORDER BY id")]


def all_prefs(db: sqlite3.Connection) -> list[Row]:
    """(call, path, rf_only) of every station the operator has said something about; path is null where nothing was said, rf_only is 0 or 1. The columns `attempts` and `hide_after_min` are not read: a value kept by an older version is ignored (migration 17 cleared the timeouts), and a row that holds only that says nothing."""
    return [tuple(r) for r in db.execute("SELECT call, path, rf_only FROM station_pref WHERE path IS NOT NULL OR rf_only = 1 ORDER BY call")]


def save_pref(db: sqlite3.Connection, call: str, path: str | None, rf_only: bool, stamp: str) -> None:
    db.execute("INSERT INTO station_pref (call, path, rf_only, updated_at) VALUES (?1, ?2, ?3, ?4) "
               "ON CONFLICT(call) DO UPDATE SET path = ?2, rf_only = ?3, updated_at = ?4", (call, path, int(rf_only), stamp))


def delete_pref(db: sqlite3.Connection, call: str) -> int:
    return db.execute("DELETE FROM station_pref WHERE call = ?", (call,)).rowcount


# ---- the delivery chain of a message we sent (the tables message_attempt and message_hop)
def insert_attempt(db: sqlite3.Connection, number: int, attempt: int, sent_at: str, path: str) -> None:
    db.execute("INSERT OR REPLACE INTO message_attempt (message_id, attempt, sent_at, path) VALUES (?, ?, ?, ?)", (number, attempt, sent_at, path))


def insert_hop(db: sqlite3.Connection, number: int, attempt: int, position: int, call: str, heard_at: str, via_internet: bool) -> int:
    """Keeps a hop that was heard; the first time it was heard stays. How many rows it added (0 when it was known)."""
    return db.execute("INSERT OR IGNORE INTO message_hop (message_id, attempt, position, call, heard_at, via_internet) VALUES (?, ?, ?, ?, ?, ?)", (number, attempt, position, call, heard_at, via_internet)).rowcount


def clear_chain(db: sqlite3.Connection, number: int) -> None:
    """Removes the attempts and hops of a message."""
    db.execute("DELETE FROM message_hop WHERE message_id = ?", (number,))
    db.execute("DELETE FROM message_attempt WHERE message_id = ?", (number,))


def all_attempts(db: sqlite3.Connection) -> list[Row]:
    """(message_id, attempt, sent_at, path) of every attempt, in order."""
    return [tuple(r) for r in db.execute("SELECT message_id, attempt, sent_at, path FROM message_attempt ORDER BY message_id, attempt")]


def all_hops(db: sqlite3.Connection) -> list[Row]:
    """(message_id, attempt, position, call, heard_at, via_internet) of every hop heard, in order."""
    return [tuple(r) for r in db.execute("SELECT message_id, attempt, position, call, heard_at, via_internet FROM message_hop ORDER BY message_id, attempt, position, via_internet")]
