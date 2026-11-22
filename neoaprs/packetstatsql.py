"""SQL for the statistics card's counts.

Each function counts packets in the span [`start`, `end`) by hour ("YYYY-MM-DDTHH"); `end` None
means the running hour. Functions of a connection; none begins or commits a transaction."""

import sqlite3

from .dberror import Row, rows
from .packetsql import NOT_INTERNET, heard

_SPAN = "heard_at >= ? AND heard_at < ?"
_OPEN = "￿"  # sorts after every time: the running hour has no end

# Classify a sent packet: a digipeated copy of another station's, else ours by kind.
# An ack or reject is a message with `ack_id` or `rej_id` in the decoded packet.
_SENT_AS = (
    "CASE WHEN source != ? THEN 'repeated' "
    "WHEN kind IN ('position', 'status') THEN 'beacon' "
    "WHEN kind IN ('object', 'item') THEN 'object' "
    "WHEN kind = 'message' AND (json_extract(decoded, '$.ack_id') IS NOT NULL OR json_extract(decoded, '$.rej_id') IS NOT NULL) THEN 'ack' "
    "WHEN kind = 'message' THEN 'message' "
    "ELSE 'other' END"
)
SENT_KINDS = ("repeated", "beacon", "object", "ack", "message", "other")

# The information field of a radio frame: after the control and PID bytes 03 F0 (address bytes never
# contain that pair).
_INFO = "substr(raw, instr(raw, x'03f0') + 2)"


def heard_hours(db: sqlite3.Connection, start: str, end: str | None, internet: bool = True) -> list[Row]:
    """Return (hour, radio, count) of heard packets in the span, by radio id (null: internet).

    APRS-IS packets are excluded when `internet` is false."""
    return rows(
        db.execute(
            f"SELECT substr(heard_at, 1, 13) AS hour, radio, count(*) FROM packet WHERE {heard(internet)} AND {_SPAN} GROUP BY hour, radio ORDER BY hour",
            (start, end or _OPEN),
        )
    )


def sent_hours(db: sqlite3.Connection, start: str, end: str | None, own: str) -> list[Row]:
    """Return (hour, radio, what, count) of sent packets in the span, by radio and SENT_KINDS.

    A packet whose source is not `own` is a digipeated copy."""
    return rows(
        db.execute(
            f"SELECT substr(heard_at, 1, 13) AS hour, radio, {_SENT_AS} AS what, count(*) FROM packet WHERE direction = 'out' AND {_SPAN} GROUP BY hour, radio, what ORDER BY hour",
            (own, start, end or _OPEN),
        )
    )


def copy_hours(db: sqlite3.Connection, start: str, end: str | None) -> list[Row]:
    """Return (hour, packets, frames) of what the radios heard in the span, internet excluded.

    A packet is one source, destination and info field within a minute; copies are frames."""
    return rows(
        db.execute(
            f"SELECT hour, count(*), sum(n) FROM (SELECT substr(heard_at, 1, 13) AS hour, count(*) AS n FROM packet WHERE direction = 'in' AND {NOT_INTERNET} AND {_SPAN} "
            f"GROUP BY substr(heard_at, 1, 16), source, destination, {_INFO}) GROUP BY hour ORDER BY hour",
            (start, end or _OPEN),
        )
    )


def repeated_since(db: sqlite3.Connection, stamp: str, own: str) -> int:
    """Return how many digipeated copies of other stations' packets were sent since `stamp`."""
    return int(
        db.execute(
            "SELECT count(*) FROM packet WHERE direction = 'out' AND source != ? AND heard_at >= ?", (own, stamp)
        ).fetchone()[0]
    )
