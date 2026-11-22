"""SQL for what each radio heard of a station (`station_radio`) and station paths (`station_path`).

Nothing here begins or commits a transaction. Foreign keys are not enforced: whoever deletes a
station deletes its rows here too.
"""
import sqlite3
from collections.abc import Sequence

from .dberror import Row, rows


# ---- what each radio heard of a station
def station_radio_rows(db: sqlite3.Connection) -> list[Row]:
    """Return (call, radio_id, heard, last_at, last_path) for every station and radio."""
    return rows(db.execute("SELECT call, radio_id, heard, last_at, last_path FROM station_radio ORDER BY call, radio_id"))


def upsert_station_radio(db: sqlite3.Connection, call: str, radio_id: int, heard: int, last_at: str | None, last_path: str) -> None:
    """Store what the radio heard of the station, replacing the old row."""
    db.execute("INSERT INTO station_radio (call, radio_id, heard, last_at, last_path) VALUES (?1, ?2, ?3, ?4, ?5) "
               "ON CONFLICT(call, radio_id) DO UPDATE SET heard = ?3, last_at = ?4, last_path = ?5", (call, radio_id, heard, last_at, last_path))


def put_station_radios(db: sqlite3.Connection, call: str, heard: Sequence[Sequence[object]]) -> None:
    """Replace the rows of one station with `heard`; rows of other radios are deleted."""
    radios = [row[1] for row in heard]
    db.execute(f"DELETE FROM station_radio WHERE call = ? AND radio_id NOT IN ({', '.join('?' * len(radios))})", (call, *radios))
    for _, radio_id, count, last_at, last_path in heard:
        upsert_station_radio(db, call, int(str(radio_id)), int(str(count)), None if last_at is None else str(last_at), str(last_path))


def delete_station_radios(db: sqlite3.Connection, call: str) -> int:
    """Delete what every radio heard of the station; return the rows deleted."""
    return db.execute("DELETE FROM station_radio WHERE call = ?", (call,)).rowcount


def delete_station_radios_but(db: sqlite3.Connection, keep_call: str) -> int:
    """Delete what every radio heard of every station but `keep_call`; return the rows deleted."""
    return db.execute("DELETE FROM station_radio WHERE call != ?", (keep_call,)).rowcount


# ---- the path of a station on a radio
def station_paths(db: sqlite3.Connection) -> list[Row]:
    """Return (call, radio_id, path) of every operator-given path (comma-separated calls)."""
    return rows(db.execute("SELECT call, radio_id, path FROM station_path ORDER BY call, radio_id"))


def put_station_path(db: sqlite3.Connection, call: str, radio_id: int, path: str, at: str) -> None:
    """Store the station's path on the radio, replacing the old one."""
    db.execute("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES (?1, ?2, ?3, ?4) ON CONFLICT(call, radio_id) DO UPDATE SET path = ?3, updated_at = ?4", (call, radio_id, path, at))


def clear_station_path(db: sqlite3.Connection, call: str, radio_id: int) -> int:
    """Delete the station's path on the radio; return the rows deleted (0 or 1)."""
    return db.execute("DELETE FROM station_path WHERE call = ? AND radio_id = ?", (call, radio_id)).rowcount
