"""The statements of the weather table (every observation of every weather station), as functions of a connection that the database thread runs (weatherlog.py is the part that asks for them).

A row is a tuple in the order of WEATHER_COLUMNS; the codec between a row and an observation is weatherlog.py's. The last statement reads the packet table, for seeding the weather from the
packets already kept. Nothing here begins or commits a transaction."""
import sqlite3
from collections.abc import Sequence
from typing import Any

WEATHER_COLUMNS = ("station", "at", "wind_dir", "wind_kmh", "gust_kmh", "temp_c", "humidity", "pressure_hpa", "rain_1h_mm", "rain_24h_mm", "rain_today_mm", "luminosity", "raw")
_LIST = ", ".join(WEATHER_COLUMNS)
_PLACES = ", ".join("?" * len(WEATHER_COLUMNS))
_NEWEST = ", ".join("MAX(at)" if c == "at" else c for c in WEATHER_COLUMNS)          # (a bare column beside the one MAX is the value of the row that has it)

Row = tuple[Any, ...]


def insert_weather(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO weather ({_LIST}) VALUES ({_PLACES})", tuple(row))


def insert_weather_many(db: sqlite3.Connection, rows: Sequence[Sequence[object]]) -> int:
    """Keeps all the observations; how many."""
    db.executemany(f"INSERT INTO weather ({_LIST}) VALUES ({_PLACES})", [tuple(r) for r in rows])
    return len(rows)


def weather_since(db: sqlite3.Connection, station: str, stamp: str) -> list[Row]:
    """The observations of the station at or after `stamp`, the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_LIST} FROM weather WHERE station = ? AND at >= ? ORDER BY at, rowid", (station, stamp))]


def latest_weather(db: sqlite3.Connection, station: str) -> Row | None:
    """The newest observation of the station, None for a station with none."""
    row = db.execute(f"SELECT {_LIST} FROM weather WHERE station = ? ORDER BY at DESC, rowid DESC LIMIT 1", (station,)).fetchone()
    return None if row is None else tuple(row)


def latest_weather_all(db: sqlite3.Connection) -> list[Row]:
    """The newest observation of each station."""
    return [tuple(r) for r in db.execute(f"SELECT {_NEWEST} FROM weather GROUP BY station")]


def count_weather(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM weather").fetchone()[0])


def prune_weather_before(db: sqlite3.Connection, stamp: str) -> int:
    """Deletes the observations made before `stamp`; how many."""
    return db.execute("DELETE FROM weather WHERE at < ?", (stamp,)).rowcount


def weather_packets(db: sqlite3.Connection, stamp: str) -> list[Row]:
    """(source, destination, raw, heard_at) of the packets heard at or after `stamp` that may carry weather, the oldest first: a position, object or item whose symbol code is `_` (the summary has the symbol
    after the position: "... 24.4300 /_ ..."), or a packet of the kind weather. A few more than there are weather reports: the parser decides."""
    return [tuple(r) for r in db.execute(
        "SELECT source, destination, raw, heard_at FROM packet WHERE direction = 'in' AND heard_at >= ? AND "
        "((kind IN ('position', 'object', 'item') AND (summary GLOB '*[0-9] ?_' OR summary GLOB '*[0-9] ?_ *')) OR (kind = 'other' AND summary GLOB 'weather: *')) ORDER BY id", (stamp,))]
