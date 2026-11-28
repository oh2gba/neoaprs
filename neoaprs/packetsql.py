"""SQL for the packet log and the station cache.

Functions of a connection on the database thread; none begins or commits a transaction."""

import sqlite3
from collections.abc import Sequence

from . import stationsql
from .dberror import Row, limit, rows

PACKET_COLUMNS = (
    "heard_at",
    "direction",
    "raw",
    "source",
    "destination",
    "path",
    "kind",
    "summary",
    "decoded",
    "error",
    "via",
    "radio",
    "snr",
    "rssi",
)
STATION_COLUMNS = (
    "call",
    "kind",
    "reported_by",
    "symbol_table",
    "symbol_code",
    "lat",
    "lon",
    "altitude_m",
    "course_deg",
    "speed_kmh",
    "first_heard",
    "last_heard",
    "last_position_at",
    "last_status",
    "last_comment",
    "packets",
    "heard_rf",
    "heard_rf_gated",
    "heard_is",
    "last_rf_at",
    "last_rf_gated_at",
    "last_is_at",
    "position_via",
    "heard_dummy",
    "last_dummy_at",
    "snr",
    "rssi",
    "signal_at",
)
PACKET_LIST = ", ".join(PACKET_COLUMNS)
_PACKET_PLACES = ", ".join("?" * len(PACKET_COLUMNS))


def station_columns() -> tuple[str, ...]:
    return STATION_COLUMNS


HEARD = "direction = 'in'"  # heard, not sent by us
NOT_INTERNET = "via != 'is'"  # not from APRS-IS; iGate third-party packets stay
NOT_GATED = "via != 'rf-gated'"  # not put on the air from the internet by an iGate
# not gated, or a message or ack, which may be to us (neoaprs/shown.py decides)
NOT_GATED_BUT_MESSAGES = f"({NOT_GATED} OR kind = 'message')"


def heard(internet: bool = True, gated: bool = True) -> str:
    return HEARD + ("" if internet else f" AND {NOT_INTERNET}") + ("" if gated else f" AND {NOT_GATED}")


def insert_packet(db: sqlite3.Connection, row: Sequence[object]) -> None:
    db.execute(f"INSERT INTO packet ({PACKET_LIST}) VALUES ({_PACKET_PLACES})", tuple(row))


def recent_packets(db: sqlite3.Connection, count: int) -> list[Row]:
    return rows(db.execute(f"SELECT {PACKET_LIST} FROM packet ORDER BY id DESC LIMIT ?", (limit(count),)))


def window_packets(db: sqlite3.Connection, count: int) -> list[Row]:
    """Return the latest `count` packets of each view of the window (neoaprs/web/packetwindow.py), newest first."""
    views = ("1", NOT_INTERNET, NOT_GATED_BUT_MESSAGES, f"{NOT_INTERNET} AND {NOT_GATED_BUT_MESSAGES}")
    chosen = " OR ".join(f"id IN (SELECT id FROM packet WHERE {view} ORDER BY id DESC LIMIT ?)" for view in views)
    return rows(
        db.execute(f"SELECT {PACKET_LIST} FROM packet WHERE {chosen} ORDER BY id DESC", (limit(count),) * len(views))
    )


def packets_since(db: sqlite3.Connection, stamp: str) -> list[Row]:
    """Return packets heard at or after `stamp`, oldest first."""
    return rows(db.execute(f"SELECT {PACKET_LIST} FROM packet WHERE heard_at >= ? ORDER BY heard_at, id", (stamp,)))


def heard_times(db: sqlite3.Connection, source: str, stamp: str) -> list[str]:
    """Return when `source`'s packets were heard on the radio at or after `stamp`."""
    return [
        str(r[0])
        for r in db.execute(
            f"SELECT heard_at FROM packet WHERE source = ? AND {heard(False)} AND heard_at >= ? ORDER BY heard_at",
            (source, stamp),
        )
    ]


def heard_by_hour(
    db: sqlite3.Connection, stamp: str, source: str | None = None, internet: bool = True, gated: bool = True
) -> list[tuple[str, int]]:
    """Return (hour as "YYYY-MM-DDTHH", count) of heard packets since `stamp`, oldest first.

    Hours with none are left out."""
    if source is None:
        return [
            (str(r[0]), int(r[1]))
            for r in db.execute(
                f"SELECT substr(heard_at, 1, 13) AS hour, count(*) FROM packet WHERE {heard(internet, gated)} AND heard_at >= ? GROUP BY hour ORDER BY hour",
                (stamp,),
            )
        ]
    return [
        (str(r[0]), int(r[1]))
        for r in db.execute(
            f"SELECT substr(heard_at, 1, 13) AS hour, count(*) FROM packet WHERE source = ? AND {heard(internet, gated)} AND heard_at >= ? GROUP BY hour ORDER BY hour",
            (source, stamp),
        )
    ]


def station_positions(
    db: sqlite3.Connection, source: str, stamp: str, internet: bool = True, gated: bool = True
) -> list[Row]:
    """Return the position packets heard from `source` since `stamp`, oldest first."""
    return rows(
        db.execute(
            f"SELECT {PACKET_LIST} FROM packet WHERE source = ? AND {heard(internet, gated)} AND kind = 'position' AND heard_at >= ? ORDER BY id",
            (source, stamp),
        )
    )


def station_readings(db: sqlite3.Connection, source: str, stamp: str, count: int) -> list[Row]:
    """Return (heard_at, path, snr, rssi) of the latest `count` packets from `source` with a signal.

    Third-party packets are excluded: their frame's signal is the iGate's."""
    return rows(
        db.execute(
            f"SELECT heard_at, path, snr, rssi FROM (SELECT id, heard_at, path, snr, rssi FROM packet WHERE source = ? AND {HEARD} AND via != 'rf-gated' AND (snr IS NOT NULL OR rssi IS NOT NULL) "
            "AND heard_at >= ? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (source, stamp, limit(count)),
        )
    )


def station_traffic(
    db: sqlite3.Connection, call: str, own: str, count: int, span: int, internet: bool = True, gated: bool = True
) -> list[Row]:
    """Return (id, packet columns) of the latest `count` packets of station `call`, newest first.

    Includes messages from `own` to it and third-party packets among the latest `span`; without
    `gated`, of the third-party packets only messages and acks."""
    net = ("" if internet else f" AND {NOT_INTERNET}") + ("" if gated else f" AND {NOT_GATED_BUT_MESSAGES}")
    inner = "" if gated else " AND kind = 'message'"
    needle = b"}" + call.encode() + b">"
    return rows(
        db.execute(
            f"SELECT id, {PACKET_LIST} FROM packet WHERE id IN ("
            f"SELECT id FROM (SELECT id FROM packet WHERE source = ?{net} ORDER BY id DESC LIMIT ?) "
            "UNION SELECT id FROM (SELECT id FROM packet WHERE source = ? AND direction = 'out' AND kind = 'message' AND json_extract(decoded, '$.addressee') = ? ORDER BY id DESC LIMIT ?) "
            f"UNION SELECT id FROM (SELECT id FROM packet WHERE id > (SELECT coalesce(max(id), 0) FROM packet) - ? AND via = 'rf-gated'{inner} AND instr(raw, ?) > 0 ORDER BY id DESC LIMIT ?)"
            ") ORDER BY id DESC LIMIT ?",
            (call, limit(count), own, call, limit(count), limit(span), needle, limit(count), limit(count)),
        )
    )


def radio_routes(db: sqlite3.Connection, count: int) -> list[Row]:
    """Return (source, path, raw, heard_at, radio) of the latest `count` radio-heard packets."""
    return rows(
        db.execute(
            f"SELECT source, path, raw, heard_at, radio FROM (SELECT id, source, path, raw, heard_at, radio FROM packet WHERE {heard(False)} ORDER BY id DESC LIMIT ?) ORDER BY id",
            (limit(count),),
        )
    )


def position_packets(db: sqlite3.Connection, stamp: str, count: int) -> list[Row]:
    return rows(
        db.execute(
            f"SELECT {PACKET_LIST} FROM (SELECT id, {PACKET_LIST} FROM packet WHERE {HEARD} AND kind IN ('position', 'object', 'item') AND heard_at >= ? "
            "ORDER BY id DESC LIMIT ?) ORDER BY id",
            (stamp, limit(count)),
        )
    )


def radio_position_packets(db: sqlite3.Connection, stamp: str, count: int) -> list[Row]:
    return rows(
        db.execute(
            f"SELECT {PACKET_LIST} FROM (SELECT id, {PACKET_LIST} FROM packet WHERE {heard(False)} AND kind IN ('position', 'object', 'item') AND heard_at >= ? "
            "ORDER BY id DESC LIMIT ?) ORDER BY id",
            (stamp, limit(count)),
        )
    )


_LOCATED = f"({HEARD} OR source = ?) AND kind IN ('position', 'object', 'item') AND heard_at >= ?"


def _located(internet: bool, gated: bool) -> str:
    """Return the condition for position packets heard or sent under our call."""
    return _LOCATED + ("" if internet else f" AND {NOT_INTERNET}") + ("" if gated else f" AND {NOT_GATED}")


def located_from(
    db: sqlite3.Connection, stamp: str, own: str, count: int, internet: bool = True, gated: bool = True
) -> str | None:
    """Return the time of the position packet just before the latest `count` since `stamp`, or None.

    Reads the time index newest first, so a short span does not scan the whole log."""
    row = db.execute(
        f"SELECT heard_at FROM packet WHERE {_located(internet, gated)} ORDER BY heard_at DESC LIMIT 1 OFFSET ?",
        (own, stamp, limit(count)),
    ).fetchone()
    return None if row is None else str(row[0])


def located_since(
    db: sqlite3.Connection,
    stamp: str,
    own: str,
    after: str | None = None,
    internet: bool = True,
    gated: bool = True,
) -> sqlite3.Cursor:
    """Return a cursor of (heard_at, source, name, lat, lon, raw, via) of positions since `stamp`.

    Killed objects are skipped; `raw` is set only for a possible third-party packet."""
    return db.execute(
        "SELECT heard_at, source, "
        "CASE kind WHEN 'position' THEN NULL ELSE json_extract(decoded, '$.name') END AS name, "
        "CASE kind WHEN 'position' THEN json_extract(decoded, '$.lat') ELSE json_extract(decoded, '$.position.lat') END AS lat, "
        "CASE kind WHEN 'position' THEN json_extract(decoded, '$.lon') ELSE json_extract(decoded, '$.position.lon') END AS lon, "
        "CASE WHEN instr(raw, x'03f07d') > 0 OR instr(raw, x'3a7d') > 0 THEN raw END AS raw, via "
        f"FROM packet WHERE {_located(internet, gated)} AND heard_at > ? AND coalesce(json_extract(decoded, '$.alive'), 1) = 1 ORDER BY heard_at",
        (own, stamp, after or ""),
    )


def oldest_packet(db: sqlite3.Connection) -> str | None:
    row = db.execute("SELECT min(heard_at) FROM packet").fetchone()
    return None if row is None or row[0] is None else str(row[0])


def message_packets(db: sqlite3.Connection, count: int) -> list[Row]:
    return rows(
        db.execute(
            f"SELECT {PACKET_LIST} FROM (SELECT id, {PACKET_LIST} FROM packet WHERE {HEARD} AND kind = 'message' ORDER BY id DESC LIMIT ?) ORDER BY id",
            (limit(count),),
        )
    )


def count_packets(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM packet").fetchone()[0])


def prune_packets_slice(db: sqlite3.Connection, stamp: str, rows: int, internet_only: bool = False) -> int:
    """Delete up to `rows` of the oldest packets before `stamp` (APRS-IS only if `internet_only`).

    Return the count."""
    where = "heard_at < ? AND via = 'is'" if internet_only else "heard_at < ?"
    return db.execute(
        f"DELETE FROM packet WHERE id IN (SELECT id FROM packet WHERE {where} ORDER BY heard_at LIMIT ?)", (stamp, rows)
    ).rowcount


def delete_heard(db: sqlite3.Connection, keep_call: str) -> int:
    gone = db.execute(f"DELETE FROM packet WHERE {HEARD}").rowcount
    db.execute("DELETE FROM station WHERE call != ?", (keep_call,))
    stationsql.delete_station_radios_but(db, keep_call)
    return gone


def upsert_station(
    db: sqlite3.Connection, row: Sequence[object], *, heard: Sequence[Sequence[object]] | None = None
) -> None:
    """Store a station row (in `station_columns()` order), replacing any earlier one.

    `heard` replaces the per-radio rows (an unlisted radio loses its row); None leaves them."""
    columns = station_columns()
    update = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "call")
    db.execute(
        f"INSERT INTO station ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) ON CONFLICT(call) DO UPDATE SET {update}",
        tuple(row),
    )
    if heard is not None:
        stationsql.put_station_radios(db, str(row[0]), heard)


def delete_station(db: sqlite3.Connection, call: str) -> None:
    """Delete a cached station and its per-radio rows."""
    db.execute("DELETE FROM station WHERE call = ?", (call,))
    stationsql.delete_station_radios(db, call)


def all_stations(db: sqlite3.Connection) -> list[Row]:
    return rows(db.execute(f"SELECT {', '.join(station_columns())} FROM station ORDER BY last_heard DESC, call DESC"))


def heard_by_radio(db: sqlite3.Connection) -> list[Row]:
    """Return (call, radio_id, heard, last_at, last_path) for each station and radio hearing it."""
    return stationsql.station_radio_rows(db)
