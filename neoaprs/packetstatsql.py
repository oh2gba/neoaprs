"""The statements of the statistics card's counts, as functions of a connection that the database thread runs (packetstats.py is the part that asks for them and keeps what no longer changes).

Each counts the packets of a span of time [`start`, `end`) by the hour of the clock ("YYYY-MM-DDTHH", the first 13 characters of `heard_at`), through the index of the times (packet_heard_at): the span is all
they read. `end` None is open: the hour that is running. Nothing here begins or commits a transaction."""
import sqlite3

from .dberror import Row, rows
from .packetsql import NOT_INTERNET, heard

_SPAN = "heard_at >= ? AND heard_at < ?"
_OPEN = "￿"                                  # (after every time: the span of the running hour has no end)

# What a packet we sent was: a copy of another station's (the digipeater's), else ours by its kind; an ack and a reject are messages with `ack_id` or `rej_id` in the decoded packet.
_SENT_AS = ("CASE WHEN source != ? THEN 'repeated' "
            "WHEN kind IN ('position', 'status') THEN 'beacon' "
            "WHEN kind IN ('object', 'item') THEN 'object' "
            "WHEN kind = 'message' AND (json_extract(decoded, '$.ack_id') IS NOT NULL OR json_extract(decoded, '$.rej_id') IS NOT NULL) THEN 'ack' "
            "WHEN kind = 'message' THEN 'message' "
            "ELSE 'other' END")
SENT_KINDS = ("repeated", "beacon", "object", "ack", "message", "other")

# The information field of a frame kept from a radio: after the control and protocol bytes 03 F0 (an address byte is never 03 followed by F0: the bytes after an address's last are the control).
_INFO = "substr(raw, instr(raw, x'03f0') + 2)"


def heard_hours(db: sqlite3.Connection, start: str, end: str | None, internet: bool = True) -> list[Row]:
    """(hour, radio, count) of the packets heard (not sent by us; none from APRS-IS when `internet` is false) in the span, by the radio that heard them (its id; null for the internet)."""
    return rows(db.execute(f"SELECT substr(heard_at, 1, 13) AS hour, radio, count(*) FROM packet WHERE {heard(internet)} AND {_SPAN} GROUP BY hour, radio ORDER BY hour",
                           (start, end or _OPEN)))


def sent_hours(db: sqlite3.Connection, start: str, end: str | None, own: str) -> list[Row]:
    """(hour, radio, what, count) of the packets we sent in the span, by the radio they went out on and by what they were (SENT_KINDS): a copy the digipeater sent of a station not ours (`own`, our call),
    or ours, a beacon (a position or a status), an object or item, a message, an ack (or a reject), or other."""
    return rows(db.execute(f"SELECT substr(heard_at, 1, 13) AS hour, radio, {_SENT_AS} AS what, count(*) FROM packet WHERE direction = 'out' AND {_SPAN} GROUP BY hour, radio, what ORDER BY hour",
                           (own, start, end or _OPEN)))


def copy_hours(db: sqlite3.Connection, start: str, end: str | None) -> list[Row]:
    """(hour, packets, frames) of what the radios heard in the span (not the internet): the frames, and the packets they were, a packet being one source, destination and information field within one
    minute of the clock. A packet that came by several ways (direct and through a digipeater, through two digipeaters, on two radios) is one packet of several frames. Grouped in a temporary b-tree
    of the span's frames only."""
    return rows(db.execute(f"SELECT hour, count(*), sum(n) FROM (SELECT substr(heard_at, 1, 13) AS hour, count(*) AS n FROM packet WHERE direction = 'in' AND {NOT_INTERNET} AND {_SPAN} "
                           f"GROUP BY substr(heard_at, 1, 16), source, destination, {_INFO}) GROUP BY hour ORDER BY hour", (start, end or _OPEN)))


def repeated_since(db: sqlite3.Connection, stamp: str, own: str) -> int:
    """How many copies of other stations' packets (not of our call `own`) the digipeater sent at `stamp` or later."""
    return int(db.execute("SELECT count(*) FROM packet WHERE direction = 'out' AND source != ? AND heard_at >= ?", (own, stamp)).fetchone()[0])
