"""The statements of the packet log and the station cache, as functions of a connection that the database thread runs (packetlog.py is the part that asks for them).

A row is a tuple in the order of the column lists below; the codecs are packetcodec.py's (packets) and packetlog.py's (stations). Nothing here begins or commits a transaction."""
import sqlite3
from collections.abc import Sequence
from typing import Any

PACKET_COLUMNS = ("heard_at", "direction", "raw", "source", "destination", "path", "kind", "summary", "decoded", "error")
STATION_COLUMNS = ("call", "kind", "reported_by", "symbol_table", "symbol_code", "lat", "lon", "altitude_m", "course_deg", "speed_kmh", "first_heard", "last_heard",
                   "last_position_at", "last_status", "last_comment", "packets", "last_path")
_PACKET_LIST = ", ".join(PACKET_COLUMNS)
_STATION_LIST = ", ".join(STATION_COLUMNS)
_PLACES = {n: ", ".join("?" * n) for n in (len(PACKET_COLUMNS), len(STATION_COLUMNS))}
_STATION_UPDATE = ", ".join(f"{c} = excluded.{c}" for c in STATION_COLUMNS if c != "call")

Row = tuple[Any, ...]


def insert_packet(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO packet ({_PACKET_LIST}) VALUES ({_PLACES[len(PACKET_COLUMNS)]})", tuple(row))


def recent_packets(db: sqlite3.Connection, count: int) -> list[Row]:
    """The latest `count` packets, the newest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM packet ORDER BY id DESC LIMIT ?", (max(0, count),))]


def packets_since(db: sqlite3.Connection, stamp: str) -> list[Row]:
    """The packets heard at `stamp` or later, the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM packet WHERE heard_at >= ? ORDER BY id", (stamp,))]


def heard_routes(db: sqlite3.Connection, count: int) -> list[Row]:
    """(source, path, raw, heard_at) of the latest `count` packets that were heard, the oldest first."""
    return [tuple(r) for r in db.execute("SELECT source, path, raw, heard_at FROM (SELECT id, source, path, raw, heard_at FROM packet WHERE direction = 'in' ORDER BY id DESC LIMIT ?) ORDER BY id", (max(0, count),))]


def position_packets(db: sqlite3.Connection, stamp: str, count: int) -> list[Row]:
    """The latest `count` packets heard at or after `stamp` that carry a position (a position, an object or an item), the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM (SELECT id, {_PACKET_LIST} FROM packet WHERE direction = 'in' AND kind IN ('position', 'object', 'item') AND heard_at >= ? "
                                          "ORDER BY id DESC LIMIT ?) ORDER BY id", (stamp, max(0, count)))]


def count_packets(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM packet").fetchone()[0])


def prune_packets_before(db: sqlite3.Connection, stamp: str) -> int:
    """Deletes the packets heard before `stamp`; how many."""
    return db.execute("DELETE FROM packet WHERE heard_at < ?", (stamp,)).rowcount


def upsert_station(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO station ({_STATION_LIST}) VALUES ({_PLACES[len(STATION_COLUMNS)]}) ON CONFLICT(call) DO UPDATE SET {_STATION_UPDATE}", tuple(row))


def delete_station(db: sqlite3.Connection, call: str) -> None:
    db.execute("DELETE FROM station WHERE call = ?", (call,))


def all_stations(db: sqlite3.Connection) -> list[Row]:
    return [tuple(r) for r in db.execute(f"SELECT {_STATION_LIST} FROM station ORDER BY last_heard DESC, call DESC")]

