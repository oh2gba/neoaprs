"""Counts for the statistics card: packets heard per hour, sent per kind, and digipeated copies.

A finished hour never changes, so it is counted once and kept; only the running hour is read
again. The whole answer is cached for FRESH_SEC."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial

from .clock import Clock, utcnow
from .db import Db
from .dberror import Connection, Row
from .dblog import DbLog
from .packetcodec import parse_stamp, stamp
from .packetsql import oldest_packet
from .packetstatsql import SENT_KINDS, copy_hours, heard_hours, repeated_since, sent_hours
from .policy import LOG_KEEP_DAYS
from .radiospec import RadioId

log = logging.getLogger("neoaprs.packetstats")

WEEK_HOURS = LOG_KEEP_DAYS * 24  # hours of heard packets counted: all the log keeps
DAY_HOURS = 24  # hours of sent and multi-path packets counted
SLICE_HOURS = 12  # finished hours counted per read
FRESH_SEC = 60  # seconds a cached answer is reused
HOUR = timedelta(hours=1)

Channel = RadioId | None  # a radio id; None for the internet


@dataclass(frozen=True, slots=True)
class Counted:
    """The counts the card shows: `heard` per channel and hour from `start`, `sent` per kind."""
    start: datetime
    hours: int
    heard: dict[Channel, list[int]] = field(default_factory=dict)
    sent: dict[Channel, dict[str, int]] = field(default_factory=dict)
    packets: int = 0
    frames: int = 0
    repeated_hour: int = 0


Hours = tuple[list[Row], list[Row], list[Row]]  # (heard, sent, copies) rows, hour first


def hour_text(top: datetime) -> str:
    """Return the hour as the statements group it, e.g. "2026-11-18T10"."""
    return stamp(top)[:13]


def _counts(conn: Connection, *, start: str, end: str | None, own: str, internet: bool) -> Hours:
    return heard_hours(conn, start, end, internet), sent_hours(conn, start, end, own), copy_hours(conn, start, end)


class PacketCounts(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the packet statistics could not be read")
        self._key: tuple[str, bool] | None = None      # (our call, internet counted) of the kept hours
        self._over: dict[str, Hours] = {}              # finished hours by hour_text, each counted once
        self._until: datetime | None = None            # hours before this are in `_over` if they had packets
        self._answer: tuple[datetime, tuple[str, bool], Counted] | None = None

    def clear(self) -> None:
        """Drop the kept counts so the next ask counts anew."""
        self._over, self._until, self._answer = {}, None, None

    async def counted(self, own: str, internet: bool) -> Counted:
        """Return the current counts for call `own`; APRS-IS packets only if `internet` is true."""
        now = self.clock()
        key = (own, internet)
        if self._answer is not None and self._answer[1] == key and timedelta(0) <= now - self._answer[0] < timedelta(seconds=FRESH_SEC):
            return self._answer[2]
        if key != self._key:
            self._key, self._over, self._until = key, {}, None
        top = now.replace(minute=0, second=0, microsecond=0)
        first = top - (WEEK_HOURS - 1) * HOUR
        since = first if self._until is None or self._until < first else self._until
        # count finished hours SLICE_HOURS at a time, so other requests are served between reads
        while since < top:
            end = min(top, since + SLICE_HOURS * HOUR)
            done = await self._read(partial(_counts, start=stamp(since), end=stamp(end), own=own, internet=internet), None)
            if done is None:
                return Counted(top, 1)
            self._keep(done, since, end, first)
            since = end
        hour_ago = stamp(now - HOUR)

        def read(conn: Connection) -> tuple[str | None, Hours, int]:
            return oldest_packet(conn), _counts(conn, start=stamp(top), end=None, own=own, internet=internet), repeated_since(conn, hour_ago, own)

        found = await self._read(read, None)
        if found is None:
            return Counted(top, 1)
        oldest, running, repeated = found
        start = first if oldest is None else max(first, parse_stamp(oldest).replace(minute=0, second=0, microsecond=0))
        answer = _assemble(start, top, [*self._over.values(), running], repeated)
        self._answer = (now, key, answer)
        return answer

    def _keep(self, done: Hours, start: datetime, end: datetime, first: datetime) -> None:
        """Keep the rows of finished hours from `start` to `end`, replacing earlier ones.

        Replacing means a slice counted twice by concurrent asks is never added twice."""
        hours: dict[str, Hours] = {}
        for part, found in enumerate(done):
            for row in found:
                hours.setdefault(str(row[0]), ([], [], []))[part].append(row)
        self._over = {hour: rows for hour, rows in self._over.items() if hour >= hour_text(first) and not hour_text(start) <= hour < hour_text(end)} | hours
        self._until = end if self._until is None else max(self._until, end)


def _assemble(start: datetime, top: datetime, parts: list[Hours], repeated: int) -> Counted:
    hours = int((top - start) / HOUR) + 1
    day = hour_text(top - (DAY_HOURS - 1) * HOUR)
    heard_by: dict[Channel, list[int]] = {}
    sent_by: dict[Channel, dict[str, int]] = {}
    def at(hour: str) -> int:
        return int((parse_stamp(hour + ":00:00.000000Z") - start) / HOUR)

    packets = frames = 0
    for heard, sent, copies in parts:
        for hour, radio, n in heard:
            if 0 <= (i := at(str(hour))) < hours:
                heard_by.setdefault(_channel(radio), [0] * hours)[i] += int(n)
        for hour, radio, what, n in sent:
            if str(hour) >= day and str(what) in SENT_KINDS:
                kinds = sent_by.setdefault(_channel(radio), dict.fromkeys(SENT_KINDS, 0))
                kinds[str(what)] += int(n)
        for hour, distinct, n in copies:
            if str(hour) >= day:
                packets, frames = packets + int(distinct), frames + int(n)
    return Counted(start, hours, heard_by, sent_by, packets, frames, repeated)


def _channel(radio: object) -> Channel:
    return None if radio is None else int(str(radio))
