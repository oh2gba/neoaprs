"""SQL for the weather table, as functions of a connection.

A row is a tuple in the order of WEATHER_COLUMNS. Nothing here begins or commits a transaction.
"""

import sqlite3
from collections.abc import Sequence

from .dberror import Row, rows
from .packetsql import HEARD

WEATHER_COLUMNS = (
    "station",
    "at",
    "wind_dir",
    "wind_kmh",
    "gust_kmh",
    "temp_c",
    "humidity",
    "pressure_hpa",
    "rain_1h_mm",
    "rain_24h_mm",
    "rain_today_mm",
    "luminosity",
    "raw",
)
_LIST = ", ".join(WEATHER_COLUMNS)
_PLACES = ", ".join("?" * len(WEATHER_COLUMNS))
# In SQLite a bare column beside a single MAX() takes the value of the row that has the maximum.
_NEWEST = ", ".join("MAX(at)" if c == "at" else c for c in WEATHER_COLUMNS)


def insert_weather(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO weather ({_LIST}) VALUES ({_PLACES})", tuple(row))


def insert_weather_many(db: sqlite3.Connection, observations: Sequence[Sequence[object]]) -> int:
    """Insert all the observations; return the count."""
    db.executemany(f"INSERT INTO weather ({_LIST}) VALUES ({_PLACES})", [tuple(r) for r in observations])
    return len(observations)


def weather_since(db: sqlite3.Connection, station: str, stamp: str) -> list[Row]:
    """Return the station's observations at or after `stamp`, oldest first."""
    return rows(
        db.execute(f"SELECT {_LIST} FROM weather WHERE station = ? AND at >= ? ORDER BY at, rowid", (station, stamp))
    )


def latest_weather(db: sqlite3.Connection, station: str) -> Row | None:
    """Return the station's newest observation, or None."""
    row = db.execute(
        f"SELECT {_LIST} FROM weather WHERE station = ? ORDER BY at DESC, rowid DESC LIMIT 1", (station,)
    ).fetchone()
    return None if row is None else tuple(row)


def latest_weather_all(db: sqlite3.Connection) -> list[Row]:
    """Return the newest observation of each station."""
    return rows(db.execute(f"SELECT {_NEWEST} FROM weather GROUP BY station"))


def count_weather(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM weather").fetchone()[0])


def prune_weather_before(db: sqlite3.Connection, stamp: str) -> int:
    """Delete observations before `stamp`; return the count."""
    return db.execute("DELETE FROM weather WHERE at < ?", (stamp,)).rowcount


def delete_weather(db: sqlite3.Connection) -> int:
    """Delete every observation; return the count."""
    return db.execute("DELETE FROM weather").rowcount


def weather_packets(db: sqlite3.Connection, stamp: str) -> list[Row]:
    """Return (source, destination, raw, heard_at, via) of packets since `stamp` that may be wx.

    The decoded JSON decides, not the summary; the parser makes the final decision.
    """
    return rows(
        db.execute(
            f"SELECT source, destination, raw, heard_at, via FROM packet WHERE {HEARD} AND heard_at >= ? AND ("
            "(kind = 'position' AND json_extract(decoded, '$.symbol_code') = '_') OR "
            "(kind IN ('object', 'item') AND json_extract(decoded, '$.position.symbol_code') = '_') OR "
            "(kind = 'other' AND (json_extract(decoded, '$.weather') IS NOT NULL OR json_extract(decoded, '$.kind') = 'weather'))) ORDER BY id",
            (stamp,),
        )
    )
