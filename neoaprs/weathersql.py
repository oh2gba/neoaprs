"""The statements of the weather table (every observation of every weather station), as functions of a connection that the database thread runs (weatherlog.py is the part that asks for them).

A row is a tuple in the order of WEATHER_COLUMNS; the codec between a row and an observation is weatherlog.py's. The last statement reads the packet table, for seeding the weather from the
packets already kept. Nothing here begins or commits a transaction."""
import sqlite3
from collections.abc import Sequence

from .dberror import Row, rows
from .packetsql import HEARD

WEATHER_COLUMNS = ("station", "at", "wind_dir", "wind_kmh", "gust_kmh", "temp_c", "humidity", "pressure_hpa", "rain_1h_mm", "rain_24h_mm", "rain_today_mm", "luminosity", "raw")
_LIST = ", ".join(WEATHER_COLUMNS)
_PLACES = ", ".join("?" * len(WEATHER_COLUMNS))
_NEWEST = ", ".join("MAX(at)" if c == "at" else c for c in WEATHER_COLUMNS)          # (a bare column beside the one MAX is the value of the row that has it)


def insert_weather(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO weather ({_LIST}) VALUES ({_PLACES})", tuple(row))


def insert_weather_many(db: sqlite3.Connection, observations: Sequence[Sequence[object]]) -> int:
    """Keeps all the observations; how many."""
    db.executemany(f"INSERT INTO weather ({_LIST}) VALUES ({_PLACES})", [tuple(r) for r in observations])
    return len(observations)


def weather_since(db: sqlite3.Connection, station: str, stamp: str) -> list[Row]:
    """The observations of the station at or after `stamp`, the oldest first."""
    return rows(db.execute(f"SELECT {_LIST} FROM weather WHERE station = ? AND at >= ? ORDER BY at, rowid", (station, stamp)))


def latest_weather(db: sqlite3.Connection, station: str) -> Row | None:
    """The newest observation of the station, None for a station with none."""
    row = db.execute(f"SELECT {_LIST} FROM weather WHERE station = ? ORDER BY at DESC, rowid DESC LIMIT 1", (station,)).fetchone()
    return None if row is None else tuple(row)


def latest_weather_all(db: sqlite3.Connection) -> list[Row]:
    """The newest observation of each station."""
    return rows(db.execute(f"SELECT {_NEWEST} FROM weather GROUP BY station"))


def count_weather(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM weather").fetchone()[0])


def prune_weather_before(db: sqlite3.Connection, stamp: str) -> int:
    """Deletes the observations made before `stamp`; how many."""
    return db.execute("DELETE FROM weather WHERE at < ?", (stamp,)).rowcount


def delete_weather(db: sqlite3.Connection) -> int:
    """Deletes every observation; how many."""
    return db.execute("DELETE FROM weather").rowcount


def weather_packets(db: sqlite3.Connection, stamp: str) -> list[Row]:
    """(source, destination, raw, heard_at, via) of the packets heard at or after `stamp` that may carry weather, the oldest first: a position whose symbol code is `_`, an object or item whose position's is, or
    a packet of the kind other that the parser read as weather (or called weather). The decoded JSON says it, not the summary. A few more than there are weather reports: the parser decides."""
    return rows(db.execute(
        f"SELECT source, destination, raw, heard_at, via FROM packet WHERE {HEARD} AND heard_at >= ? AND ("
        "(kind = 'position' AND json_extract(decoded, '$.symbol_code') = '_') OR "
        "(kind IN ('object', 'item') AND json_extract(decoded, '$.position.symbol_code') = '_') OR "
        "(kind = 'other' AND (json_extract(decoded, '$.weather') IS NOT NULL OR json_extract(decoded, '$.kind') = 'weather'))) ORDER BY id", (stamp,)))
