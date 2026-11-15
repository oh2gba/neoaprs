"""The statements of the message table, as functions of a connection that the database thread runs (messagelog.py is the part that asks for them).

A row is a tuple in the order of MESSAGE_COLUMNS; the codec between a row and a `MessageRecord` is messagelog.py's. Nothing here begins or commits a transaction.

A message and an attempt name their radio by its id in the table `radio` (null for none: migration 32). What the operator said of a station is in two tables (migration 33): RF only and the alerts in
`station_pref`, by station, and its path in `station_path`, by station and radio (stationsql.py)."""
import sqlite3
from collections.abc import Sequence

from . import stationsql
from .dberror import Row as Row, limit, rows

MESSAGE_COLUMNS = ("id", "at", "direction", "from_call", "to_call", "text", "msg_id", "state", "attempts", "last_attempt_at", "acked_at", "attempts_max", "route", "seal", "wire", "radio", "failure", "snr", "rssi")
_LIST = ", ".join(MESSAGE_COLUMNS)
_NEW_LIST = ", ".join(MESSAGE_COLUMNS[1:])
_NEW_PLACES = ", ".join("?" * (len(MESSAGE_COLUMNS) - 1))


def insert_message(db: sqlite3.Connection, row: Sequence[object]) -> int:
    """Adds a message (the row without its id); the id the database gave it."""
    cursor = db.execute(f"INSERT INTO message ({_NEW_LIST}) VALUES ({_NEW_PLACES})", tuple(row))
    return int(cursor.lastrowid or 0)


def update_message(db: sqlite3.Connection, number: int, state: str, attempts: int, last_attempt_at: str | None, acked_at: str | None, failure: str | None, reading: tuple[float | None, float | None] = (None, None)) -> int:
    """Sets what changes in a message as it is sent, and the reading (snr, rssi) of the answer that settled it; how many rows it found (0 or 1)."""
    return db.execute("UPDATE message SET state = ?, attempts = ?, last_attempt_at = ?, acked_at = ?, failure = ?, snr = ?, rssi = ? WHERE id = ?", (state, attempts, last_attempt_at, acked_at, failure, *reading, number)).rowcount


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
    return rows(db.execute(f"SELECT {_LIST} FROM message WHERE (state = 'overheard') = ? ORDER BY id DESC LIMIT ?", (overheard, limit(count))))


def held_messages(db: sqlite3.Connection, count: int) -> list[Row]:
    """The latest `count` messages of any kind (overheard ones too), the newest first."""
    return rows(db.execute(f"SELECT {_LIST} FROM message ORDER BY id DESC LIMIT ?", (limit(count),)))


def sending_messages(db: sqlite3.Connection) -> list[Row]:
    """The messages that are still being sent, the oldest first."""
    return rows(db.execute(f"SELECT {_LIST} FROM message WHERE state = 'sending' ORDER BY id"))


# ---- the public keys the stations announced (the table station_key)
def all_keys(db: sqlite3.Connection) -> list[Row]:
    """(call, pubkey, heard_at) of every station whose key is kept."""
    return rows(db.execute("SELECT call, pubkey, heard_at FROM station_key ORDER BY call"))


def save_key(db: sqlite3.Connection, call: str, pubkey: str, heard_at: str) -> None:
    """The key of a station, replacing the one it had."""
    db.execute("INSERT INTO station_key (call, pubkey, heard_at) VALUES (?1, ?2, ?3) ON CONFLICT(call) DO UPDATE SET pubkey = ?2, heard_at = ?3", (call, pubkey, heard_at))


def delete_key(db: sqlite3.Connection, call: str) -> int:
    return db.execute("DELETE FROM station_key WHERE call = ?", (call,)).rowcount


_SAYS = "rf_only = 1 OR alert_on_air = 1 OR alert_within_km IS NOT NULL OR alert_direct = 1"       # a row of station_pref that says something this program reads


def all_prefs(db: sqlite3.Connection, *, radio_id: int = 1) -> list[Row]:
    """(call, path, rf_only, alert_on_air, alert_within_km, alert_direct) of every station the operator has said something about; path and alert_within_km are null where nothing was said, the flags 0 or 1. The
    path is the station's on the radio `radio_id` (the FM radio of today when not given: every path there was is on it); a station with a path there and nothing else is a row too. The columns `attempts`
    and `hide_after_min` are not read: a value kept by an older version is ignored (migration 17 cleared the timeouts), and a row that holds only that says nothing."""
    return rows(db.execute(f"SELECT call, (SELECT path FROM station_path WHERE call = station_pref.call AND radio_id = ?1), rf_only, alert_on_air, alert_within_km, alert_direct FROM station_pref WHERE {_SAYS} "
                           f"UNION ALL SELECT call, path, 0, 0, NULL, 0 FROM station_path WHERE radio_id = ?1 AND call NOT IN (SELECT call FROM station_pref WHERE {_SAYS}) ORDER BY call", (radio_id,)))


def save_pref(db: sqlite3.Connection, call: str, path: str | None, rf_only: bool, alert: tuple[bool, int | None, bool], stamp: str, *, radio_id: int = 1) -> None:
    """What is said of a station as a whole: its path on the radio `radio_id` (none takes it away there), RF only and the three parts of its alert (on the air, within how many km, heard direct). The row
    of `station_pref` is there while RF only or an alert is set, the row of `station_path` while the path is; its paths on other radios stay. Nothing at all said is refused by the table, as it was
    (station_pref_says_something): a station of which nothing is said is forgotten with `delete_pref`."""
    on_air, within_km, direct = alert
    if rf_only or on_air or within_km is not None or direct or path is None:
        db.execute("INSERT INTO station_pref (call, rf_only, alert_on_air, alert_within_km, alert_direct, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6) "
                   "ON CONFLICT(call) DO UPDATE SET rf_only = ?2, alert_on_air = ?3, alert_within_km = ?4, alert_direct = ?5, updated_at = ?6", (call, int(rf_only), int(on_air), within_km, int(direct), stamp))
    else:                                       # (only a path is said: no row here, but for what an older version kept in it, which stays)
        db.execute("DELETE FROM station_pref WHERE call = ? AND hide_after_min IS NULL AND attempts IS NULL", (call,))
        db.execute("UPDATE station_pref SET rf_only = 0, alert_on_air = 0, alert_within_km = NULL, alert_direct = 0, updated_at = ? WHERE call = ?", (stamp, call))
    if path is None:
        stationsql.clear_station_path(db, call, radio_id)
    else:
        stationsql.put_station_path(db, call, radio_id, path, stamp)


def delete_pref(db: sqlite3.Connection, call: str) -> int:
    """Removes what `save_pref` keeps of a station without naming a radio: RF only, the alert and its path on the FM radio of today (radio 1); its paths on other radios stay (`clear_station_path`
    takes one away). How many rows of the two tables."""
    gone = db.execute("DELETE FROM station_pref WHERE call = ?", (call,)).rowcount
    return gone + stationsql.clear_station_path(db, call, 1)


# ---- the delivery chain of a message we sent (the tables message_attempt and message_hop)
def insert_attempt(db: sqlite3.Connection, number: int, attempt: int, sent_at: str, path: str, radio: int | None = None) -> None:
    """Keeps an attempt, with the id of the radio it went out on (none: null)."""
    db.execute("INSERT OR REPLACE INTO message_attempt (message_id, attempt, sent_at, path, radio) VALUES (?, ?, ?, ?, ?)", (number, attempt, sent_at, path, radio))


def insert_hop(db: sqlite3.Connection, number: int, attempt: int, position: int, call: str, heard_at: str, via_internet: bool) -> int:
    """Keeps a hop that was heard; the first time it was heard stays. How many rows it added (0 when it was known)."""
    return db.execute("INSERT OR IGNORE INTO message_hop (message_id, attempt, position, call, heard_at, via_internet) VALUES (?, ?, ?, ?, ?, ?)", (number, attempt, position, call, heard_at, via_internet)).rowcount


def clear_chain(db: sqlite3.Connection, number: int) -> None:
    """Removes the attempts and hops of a message."""
    db.execute("DELETE FROM message_hop WHERE message_id = ?", (number,))
    db.execute("DELETE FROM message_attempt WHERE message_id = ?", (number,))


def all_attempts(db: sqlite3.Connection) -> list[Row]:
    """(message_id, attempt, sent_at, path, radio) of every attempt, in order."""
    return rows(db.execute("SELECT message_id, attempt, sent_at, path, radio FROM message_attempt ORDER BY message_id, attempt"))


def all_hops(db: sqlite3.Connection) -> list[Row]:
    """(message_id, attempt, position, call, heard_at, via_internet) of every hop heard, in order."""
    return rows(db.execute("SELECT message_id, attempt, position, call, heard_at, via_internet FROM message_hop ORDER BY message_id, attempt, position, via_internet"))
