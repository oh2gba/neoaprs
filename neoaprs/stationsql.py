"""The statements of what each radio heard of a station (the table `station_radio`) and of the path the operator gave a station on a radio (`station_path`), as functions of a connection that the database
thread runs: the tables migration 33 makes (migrationsteps32.py). packetsql.py asks for the first with a station's row, messagesql.py for the second with what is said of a station.

A row is a tuple in the order each function names. Nothing here begins or commits a transaction. The database has no foreign keys in force (no connection turns them on), so nothing deletes these rows
by itself: who deletes a station deletes its rows here in the same function (packetsql.delete_station, delete_heard; messagesql.delete_pref).

These tables are there once migration 33 has run: the stores ask for them only with `packetcodec.BY_RADIO` on."""
import sqlite3
from collections.abc import Sequence

from .dberror import Row, rows


# ---- what each radio heard of a station
def station_radio_rows(db: sqlite3.Connection) -> list[Row]:
    """(call, radio_id, heard, last_at, last_path) of every station and radio that heard it, by station and radio."""
    return rows(db.execute("SELECT call, radio_id, heard, last_at, last_path FROM station_radio ORDER BY call, radio_id"))


def upsert_station_radio(db: sqlite3.Connection, call: str, radio_id: int, heard: int, last_at: str | None, last_path: str) -> None:
    """What the radio heard of the station, replacing what was kept."""
    db.execute("INSERT INTO station_radio (call, radio_id, heard, last_at, last_path) VALUES (?1, ?2, ?3, ?4, ?5) "
               "ON CONFLICT(call, radio_id) DO UPDATE SET heard = ?3, last_at = ?4, last_path = ?5", (call, radio_id, heard, last_at, last_path))


def put_station_radios(db: sqlite3.Connection, call: str, heard: Sequence[Sequence[object]]) -> None:
    """The rows of one station as they are now, each (call, radio_id, heard, last_at, last_path): those given are kept, the row of a radio that is not among them goes."""
    radios = [row[1] for row in heard]
    db.execute(f"DELETE FROM station_radio WHERE call = ? AND radio_id NOT IN ({', '.join('?' * len(radios))})", (call, *radios))
    for _, radio_id, count, last_at, last_path in heard:
        upsert_station_radio(db, call, int(str(radio_id)), int(str(count)), None if last_at is None else str(last_at), str(last_path))


def delete_station_radios(db: sqlite3.Connection, call: str) -> int:
    """Removes what every radio heard of the station; how many rows."""
    return db.execute("DELETE FROM station_radio WHERE call = ?", (call,)).rowcount


def delete_station_radios_but(db: sqlite3.Connection, keep_call: str) -> int:
    """Removes what every radio heard of every station but `keep_call`; how many rows."""
    return db.execute("DELETE FROM station_radio WHERE call != ?", (keep_call,)).rowcount


# ---- the path of a station on a radio
def station_paths(db: sqlite3.Connection) -> list[Row]:
    """(call, radio_id, path) of every path the operator gave a station on a radio, by station and radio; the path is digipeater calls separated by commas, empty for direct."""
    return rows(db.execute("SELECT call, radio_id, path FROM station_path ORDER BY call, radio_id"))


def put_station_path(db: sqlite3.Connection, call: str, radio_id: int, path: str, at: str) -> None:
    """The path of the station on the radio, replacing the one it had there."""
    db.execute("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES (?1, ?2, ?3, ?4) ON CONFLICT(call, radio_id) DO UPDATE SET path = ?3, updated_at = ?4", (call, radio_id, path, at))


def clear_station_path(db: sqlite3.Connection, call: str, radio_id: int) -> int:
    """Removes the path of the station on the radio; how many rows it found (0 or 1)."""
    return db.execute("DELETE FROM station_path WHERE call = ? AND radio_id = ?", (call, radio_id)).rowcount


def clear_station_paths(db: sqlite3.Connection, call: str) -> int:
    """Removes the paths of the station on every radio; how many rows."""
    return db.execute("DELETE FROM station_path WHERE call = ?", (call,)).rowcount
