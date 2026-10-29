"""The statements of the packet log and the station cache, as functions of a connection that the database thread runs (packetlog.py is the part that asks for them).

A row is a tuple in the order of the column lists below; the codecs are packetcodec.py's (packets) and packetlog.py's (stations). Nothing here begins or commits a transaction."""
import sqlite3
from collections.abc import Sequence
from typing import Any

PACKET_COLUMNS = ("heard_at", "direction", "raw", "source", "destination", "path", "kind", "summary", "decoded", "error", "via")
STATION_COLUMNS = ("call", "kind", "reported_by", "symbol_table", "symbol_code", "lat", "lon", "altitude_m", "course_deg", "speed_kmh", "first_heard", "last_heard",
                   "last_position_at", "last_status", "last_comment", "packets", "last_path", "heard_rf", "heard_rf_gated", "heard_is", "last_rf_at", "last_rf_gated_at", "last_is_at", "position_via", "heard_dummy", "last_dummy_at")
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


def window_packets(db: sqlite3.Connection, count: int) -> list[Row]:
    """The latest `count` packets and the latest `count` that were not from the internet, together, the newest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM packet WHERE id IN (SELECT id FROM packet ORDER BY id DESC LIMIT ?) "
                                          "OR id IN (SELECT id FROM packet WHERE via != 'is' ORDER BY id DESC LIMIT ?) ORDER BY id DESC", (max(0, count), max(0, count)))]


def packets_since(db: sqlite3.Connection, stamp: str) -> list[Row]:
    """The packets heard at `stamp` or later, the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM packet WHERE heard_at >= ? ORDER BY id", (stamp,))]


def heard_times(db: sqlite3.Connection, source: str, stamp: str) -> list[str]:
    """When the packets of the source were heard on the radio (not sent by us, not from the internet) at `stamp` or later, the oldest first."""
    return [str(r[0]) for r in db.execute("SELECT heard_at FROM packet WHERE source = ? AND direction = 'in' AND via != 'is' AND heard_at >= ? ORDER BY heard_at", (source, stamp))]


def _heard(internet: bool) -> str:
    """The packets heard (not sent by us); without those that came from APRS-IS when `internet` is false (Internet stations off: a packet heard on the radio stays, an iGate's third-party one too)."""
    return "direction = 'in'" if internet else "direction = 'in' AND via != 'is'"


def heard_by_hour(db: sqlite3.Connection, stamp: str, source: str | None = None, internet: bool = True) -> list[tuple[str, int]]:
    """How many packets were heard (not sent by us; none from APRS-IS when `internet` is false) in each hour of the clock at `stamp` or later, all of them or those whose source is `source`: (the hour as
    "YYYY-MM-DDTHH", the count), the oldest first, hours with none left out. One station's goes by the index of the source (packet_source), a few days of its packets at most: the table is pruned."""
    if source is None:
        return [(str(r[0]), int(r[1])) for r in db.execute(f"SELECT substr(heard_at, 1, 13) AS hour, count(*) FROM packet WHERE {_heard(internet)} AND heard_at >= ? GROUP BY hour ORDER BY hour", (stamp,))]
    return [(str(r[0]), int(r[1])) for r in db.execute(f"SELECT substr(heard_at, 1, 13) AS hour, count(*) FROM packet WHERE source = ? AND {_heard(internet)} AND heard_at >= ? GROUP BY hour ORDER BY hour",
                                                        (source, stamp))]


def station_positions(db: sqlite3.Connection, source: str, stamp: str, internet: bool = True) -> list[Row]:
    """The position packets heard from `source` at or after `stamp` (none from APRS-IS when `internet` is false), the oldest first: the speeds of a moving station are read from them (by the index of the
    source: a few days of one station's packets at most)."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM packet WHERE source = ? AND {_heard(internet)} AND kind = 'position' AND heard_at >= ? ORDER BY id", (source, stamp))]


def heard_routes(db: sqlite3.Connection, count: int) -> list[Row]:
    """(source, path, raw, heard_at) of the latest `count` packets that were heard on the radio (not those from the internet: they came by no route), the oldest first."""
    return [tuple(r) for r in db.execute("SELECT source, path, raw, heard_at FROM (SELECT id, source, path, raw, heard_at FROM packet WHERE direction = 'in' AND via != 'is' ORDER BY id DESC LIMIT ?) ORDER BY id", (max(0, count),))]


def position_packets(db: sqlite3.Connection, stamp: str, count: int) -> list[Row]:
    """The latest `count` packets heard at or after `stamp` that carry a position (a position, an object or an item), the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM (SELECT id, {_PACKET_LIST} FROM packet WHERE direction = 'in' AND kind IN ('position', 'object', 'item') AND heard_at >= ? "
                                          "ORDER BY id DESC LIMIT ?) ORDER BY id", (stamp, max(0, count)))]


def radio_position_packets(db: sqlite3.Connection, stamp: str, count: int) -> list[Row]:
    """The latest `count` packets heard at or after `stamp` that carry a position (a position, an object or an item) and were not from the internet, the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM (SELECT id, {_PACKET_LIST} FROM packet WHERE direction = 'in' AND via != 'is' AND kind IN ('position', 'object', 'item') AND heard_at >= ? "
                                          "ORDER BY id DESC LIMIT ?) ORDER BY id", (stamp, max(0, count)))]


_LOCATED = "(direction = 'in' OR source = ?) AND kind IN ('position', 'object', 'item') AND heard_at >= ?"


def _located(internet: bool) -> str:
    """The packets that carry a position, heard or sent under our call; without those that came from APRS-IS when `internet` is false (a packet heard on the radio stays, a third-party one an iGate put on
    the air too: it was on the air near us)."""
    return _LOCATED if internet else f"{_LOCATED} AND via != 'is'"


def located_from(db: sqlite3.Connection, stamp: str, own: str, count: int, internet: bool = True) -> str | None:
    """Where the latest `count` packets at or after `stamp` that carry a position (heard, or sent under our call `own`; none from APRS-IS when `internet` is false) begin: the time of the packet just before
    them, null when there are no more than `count`. By the index of the times, newest first, so that a short span does not read the week the log keeps."""
    row = db.execute(f"SELECT heard_at FROM packet WHERE {_located(internet)} ORDER BY heard_at DESC LIMIT 1 OFFSET ?", (own, stamp, max(0, count))).fetchone()
    return None if row is None else str(row[0])


def located_since(db: sqlite3.Connection, stamp: str, own: str, after: str | None = None, internet: bool = True) -> sqlite3.Cursor:
    """(heard_at, source, name, lat, lon, raw, via) of the packets at or after `stamp` (and after `after`, when given) that carry a position, the oldest first, as a cursor to go through row by row: those heard
    (none from APRS-IS when `internet` is false), and those sent under our call `own` (our beacons and our objects; not the copies of other stations' packets the digipeater sent). An object or item that was
    killed is left out. `name` is the object's or item's (null for a position); the place is read from the JSON of the decoded packet here, so that a week of positions is not decoded in Python one by one.
    `raw` is only given for a packet that may be a third-party one (its information field begins with `}`: the frame has it after the control and protocol bytes 03 F0, a line of APRS-IS after a colon), whose
    sender is the station inside it; for any other it is null and the sender is the source."""
    return db.execute(
        "SELECT heard_at, source, "
        "CASE kind WHEN 'position' THEN NULL ELSE json_extract(decoded, '$.name') END AS name, "
        "CASE kind WHEN 'position' THEN json_extract(decoded, '$.lat') ELSE json_extract(decoded, '$.position.lat') END AS lat, "
        "CASE kind WHEN 'position' THEN json_extract(decoded, '$.lon') ELSE json_extract(decoded, '$.position.lon') END AS lon, "
        "CASE WHEN instr(raw, x'03f07d') > 0 OR instr(raw, x'3a7d') > 0 THEN raw END AS raw, via "
        f"FROM packet WHERE {_located(internet)} AND heard_at > ? AND coalesce(json_extract(decoded, '$.alive'), 1) = 1 ORDER BY heard_at", (own, stamp, after or ""))


def oldest_packet(db: sqlite3.Connection) -> str | None:
    """The time of the oldest packet the log keeps, null when it keeps none."""
    row = db.execute("SELECT min(heard_at) FROM packet").fetchone()
    return None if row is None or row[0] is None else str(row[0])


def message_packets(db: sqlite3.Connection, count: int) -> list[Row]:
    """The latest `count` packets that were heard and are messages (or acks), the oldest first."""
    return [tuple(r) for r in db.execute(f"SELECT {_PACKET_LIST} FROM (SELECT id, {_PACKET_LIST} FROM packet WHERE direction = 'in' AND kind = 'message' ORDER BY id DESC LIMIT ?) ORDER BY id", (max(0, count),))]


def count_packets(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM packet").fetchone()[0])


def prune_packets_before(db: sqlite3.Connection, stamp: str) -> int:
    """Deletes the packets heard before `stamp`; how many."""
    return db.execute("DELETE FROM packet WHERE heard_at < ?", (stamp,)).rowcount


def delete_heard(db: sqlite3.Connection, keep_call: str) -> int:
    """Deletes the packets that were heard and the cached stations but `keep_call`; how many packets."""
    gone = db.execute("DELETE FROM packet WHERE direction = 'in'").rowcount
    db.execute("DELETE FROM station WHERE call != ?", (keep_call,))
    return gone


def upsert_station(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO station ({_STATION_LIST}) VALUES ({_PLACES[len(STATION_COLUMNS)]}) ON CONFLICT(call) DO UPDATE SET {_STATION_UPDATE}", tuple(row))


def delete_station(db: sqlite3.Connection, call: str) -> None:
    db.execute("DELETE FROM station WHERE call = ?", (call,))


def all_stations(db: sqlite3.Connection) -> list[Row]:
    return [tuple(r) for r in db.execute(f"SELECT {_STATION_LIST} FROM station ORDER BY last_heard DESC, call DESC")]

