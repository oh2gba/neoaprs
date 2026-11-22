"""SQL for messages, delivery chains, station keys and station preferences.

Functions of a connection on the database thread; none begins or commits a transaction."""
import sqlite3
from collections.abc import Sequence

from . import stationsql
from .dberror import Row as Row, limit, rows

MESSAGE_COLUMNS = ("id", "at", "direction", "from_call", "to_call", "text", "msg_id", "state", "attempts", "last_attempt_at", "acked_at", "attempts_max", "route", "seal", "wire", "radio", "failure", "snr", "rssi")
_LIST = ", ".join(MESSAGE_COLUMNS)
_NEW_LIST = ", ".join(MESSAGE_COLUMNS[1:])
_NEW_PLACES = ", ".join("?" * (len(MESSAGE_COLUMNS) - 1))


def insert_message(db: sqlite3.Connection, row: Sequence[object]) -> int:
    cursor = db.execute(f"INSERT INTO message ({_NEW_LIST}) VALUES ({_NEW_PLACES})", tuple(row))
    return int(cursor.lastrowid or 0)


def update_message(db: sqlite3.Connection, number: int, state: str, attempts: int, last_attempt_at: str | None, acked_at: str | None, failure: str | None, reading: tuple[float | None, float | None] = (None, None)) -> int:
    """Update the sending state and the signal of the settling answer; return the row count."""
    return db.execute("UPDATE message SET state = ?, attempts = ?, last_attempt_at = ?, acked_at = ?, failure = ?, snr = ?, rssi = ? WHERE id = ?", (state, attempts, last_attempt_at, acked_at, failure, *reading, number)).rowcount


def delete_message(db: sqlite3.Connection, number: int) -> int:
    """Delete a message and its delivery chain; return the message row count."""
    clear_chain(db, number)
    return db.execute("DELETE FROM message WHERE id = ?", (number,)).rowcount


def delete_conversation(db: sqlite3.Connection, call: str) -> int:
    """Delete messages to or from `call` and their chains, not overheard ones; return the count."""
    ours = "state <> 'overheard' AND ((direction = 'out' AND to_call = ?1) OR (direction = 'in' AND from_call = ?1))"
    for table in ("message_hop", "message_attempt"):
        db.execute(f"DELETE FROM {table} WHERE message_id IN (SELECT id FROM message WHERE {ours})", (call,))
    return db.execute(f"DELETE FROM message WHERE {ours}", (call,)).rowcount


def delete_overheard(db: sqlite3.Connection, from_call: str, to_call: str) -> int:
    """Delete the overheard messages between the two; return the count."""
    return db.execute("DELETE FROM message WHERE state = 'overheard' AND from_call = ? AND to_call = ?", (from_call, to_call)).rowcount


def recent_messages(db: sqlite3.Connection, count: int, overheard: bool) -> list[Row]:
    """Return the latest `count` messages, newest first; with `overheard`, those of others."""
    return rows(db.execute(f"SELECT {_LIST} FROM message WHERE (state = 'overheard') = ? ORDER BY id DESC LIMIT ?", (overheard, limit(count))))


def held_messages(db: sqlite3.Connection, count: int) -> list[Row]:
    return rows(db.execute(f"SELECT {_LIST} FROM message ORDER BY id DESC LIMIT ?", (limit(count),)))


def sending_messages(db: sqlite3.Connection) -> list[Row]:
    return rows(db.execute(f"SELECT {_LIST} FROM message WHERE state = 'sending' ORDER BY id"))


# ---- the public keys the stations announced (table station_key)
def all_keys(db: sqlite3.Connection) -> list[Row]:
    return rows(db.execute("SELECT call, pubkey, heard_at FROM station_key ORDER BY call"))


def save_key(db: sqlite3.Connection, call: str, pubkey: str, heard_at: str) -> None:
    db.execute("INSERT INTO station_key (call, pubkey, heard_at) VALUES (?1, ?2, ?3) ON CONFLICT(call) DO UPDATE SET pubkey = ?2, heard_at = ?3", (call, pubkey, heard_at))


def delete_key(db: sqlite3.Connection, call: str) -> int:
    return db.execute("DELETE FROM station_key WHERE call = ?", (call,)).rowcount


# a station_pref row that sets something
_SAYS = "rf_only = 1 OR alert_on_air = 1 OR alert_within_km IS NOT NULL OR alert_direct = 1"


def all_prefs(db: sqlite3.Connection, *, radio_id: int = 1) -> list[Row]:
    """Return (call, path, rf_only, on_air, within_km, direct) for each station with a setting.

    The path is the one on `radio_id`; a station with only a path there is included."""
    return rows(db.execute(f"SELECT call, (SELECT path FROM station_path WHERE call = station_pref.call AND radio_id = ?1), rf_only, alert_on_air, alert_within_km, alert_direct FROM station_pref WHERE {_SAYS} "
                           f"UNION ALL SELECT call, path, 0, 0, NULL, 0 FROM station_path WHERE radio_id = ?1 AND call NOT IN (SELECT call FROM station_pref WHERE {_SAYS}) ORDER BY call", (radio_id,)))


def save_pref(db: sqlite3.Connection, call: str, path: str | None, rf_only: bool, alert: tuple[bool, int | None, bool], stamp: str, *, radio_id: int = 1) -> None:
    """Store a station's path on `radio_id` (None removes it), RF-only and the alert parts.

    The table refuses a row that sets nothing; use `delete_pref` to forget a station."""
    on_air, within_km, direct = alert
    if rf_only or on_air or within_km is not None or direct or path is None:
        db.execute("INSERT INTO station_pref (call, rf_only, alert_on_air, alert_within_km, alert_direct, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6) "
                   "ON CONFLICT(call) DO UPDATE SET rf_only = ?2, alert_on_air = ?3, alert_within_km = ?4, alert_direct = ?5, updated_at = ?6", (call, int(rf_only), int(on_air), within_km, int(direct), stamp))
    else:                                       # only a path: drop the row unless legacy columns hold data
        db.execute("DELETE FROM station_pref WHERE call = ? AND hide_after_min IS NULL AND attempts IS NULL", (call,))
        db.execute("UPDATE station_pref SET rf_only = 0, alert_on_air = 0, alert_within_km = NULL, alert_direct = 0, updated_at = ? WHERE call = ?", (stamp, call))
    if path is None:
        stationsql.clear_station_path(db, call, radio_id)
    else:
        stationsql.put_station_path(db, call, radio_id, path, stamp)


def delete_pref(db: sqlite3.Connection, call: str) -> int:
    """Delete RF-only, the alert and the path on radio 1; return the rows removed."""
    gone = db.execute("DELETE FROM station_pref WHERE call = ?", (call,)).rowcount
    return gone + stationsql.clear_station_path(db, call, 1)


# ---- the delivery chain of a sent message (tables message_attempt and message_hop)
def insert_attempt(db: sqlite3.Connection, number: int, attempt: int, sent_at: str, path: str, radio: int | None = None) -> None:
    db.execute("INSERT OR REPLACE INTO message_attempt (message_id, attempt, sent_at, path, radio) VALUES (?, ?, ?, ?, ?)", (number, attempt, sent_at, path, radio))


def insert_hop(db: sqlite3.Connection, number: int, attempt: int, position: int, call: str, heard_at: str, via_internet: bool) -> int:
    """Store a heard hop, keeping the first hearing; return the rows added (0 if known)."""
    return db.execute("INSERT OR IGNORE INTO message_hop (message_id, attempt, position, call, heard_at, via_internet) VALUES (?, ?, ?, ?, ?, ?)", (number, attempt, position, call, heard_at, via_internet)).rowcount


def clear_chain(db: sqlite3.Connection, number: int) -> None:
    """Delete the attempts and hops of a message."""
    db.execute("DELETE FROM message_hop WHERE message_id = ?", (number,))
    db.execute("DELETE FROM message_attempt WHERE message_id = ?", (number,))


def all_attempts(db: sqlite3.Connection) -> list[Row]:
    return rows(db.execute("SELECT message_id, attempt, sent_at, path, radio FROM message_attempt ORDER BY message_id, attempt"))


def all_hops(db: sqlite3.Connection) -> list[Row]:
    return rows(db.execute("SELECT message_id, attempt, position, call, heard_at, via_internet FROM message_hop ORDER BY message_id, attempt, position, via_internet"))
