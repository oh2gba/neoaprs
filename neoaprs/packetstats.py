"""What the statistics card counts from the packet log beyond the station book (`packet_stats`, neoaprs/web/historyhandlers.py): the packets heard by the hour over the week the log keeps, by the radio that
heard them; what went out on each radio over the last day, ours by kind and the digipeater's copies; how many of the packets the radios heard came by several ways; and the copies sent in the last hour.

The card asks each minute, on a Raspberry Pi too, and a week of a busy station is a million packets: an hour that is over never changes, so each is counted once (packetstatsql.py, by the index of the
times) and kept, and what is read again is the hour that is running and the last hour of copies. The whole answer is kept for FRESH_SEC, so that several pages that look are one count. Forgetting the
heard packets, another call or the internet switched on or off counts anew."""
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

WEEK_HOURS = LOG_KEEP_DAYS * 24                  # the hours the packets heard are counted over: all the log keeps
DAY_HOURS = 24                                   # the hours what went out and the packets that came by several ways are counted over
SLICE_HOURS = 12                                 # the hours that are over counted in one read: half a day, some 70 000 packets of a station that keeps a million a week
FRESH_SEC = 60                                   # how long an answer is given again before it is counted anew
HOUR = timedelta(hours=1)

Channel = RadioId | None                         # a radio by its id; None for the internet


@dataclass(frozen=True, slots=True)
class Counted:
    """The counts the card shows. `heard` has a list for each channel that heard anything, a count for each hour from `start` (the top of the first), `hours` of them, the running one last: the week the
    log keeps, or less when its oldest packet is younger. `sent` is the last DAY_HOURS of each radio's packets that went out, by what they were (SENT_KINDS); `packets` and `frames` the same day of
    what the radios heard; `repeated_hour` the digipeater's copies in the last 60 minutes."""
    start: datetime
    hours: int
    heard: dict[Channel, list[int]] = field(default_factory=dict)
    sent: dict[Channel, dict[str, int]] = field(default_factory=dict)
    packets: int = 0
    frames: int = 0
    repeated_hour: int = 0


Hours = tuple[list[Row], list[Row], list[Row]]   # (heard, sent, copies) rows of packetstatsql.py, each beginning with its hour


def hour_text(top: datetime) -> str:
    """The hour as the statements group by it: "2026-11-18T10"."""
    return stamp(top)[:13]


def _counts(conn: Connection, *, start: str, end: str | None, own: str, internet: bool) -> Hours:
    return heard_hours(conn, start, end, internet), sent_hours(conn, start, end, own), copy_hours(conn, start, end)


class PacketCounts(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the packet statistics could not be read")
        self._key: tuple[str, bool] | None = None      # (our call, the internet counted) the kept hours were counted for
        self._over: dict[str, Hours] = {}              # the hours that are over, by hour_text, each counted once
        self._until: datetime | None = None            # the hours before this one are in `_over`, where they had packets
        self._answer: tuple[datetime, tuple[str, bool], Counted] | None = None

    def clear(self) -> None:
        """Counts everything anew at the next ask (the heard packets were forgotten)."""
        self._over, self._until, self._answer = {}, None, None

    async def counted(self, own: str, internet: bool) -> Counted:
        """The counts as they are now, for our call `own`, with the packets from APRS-IS or (`internet` false) without them."""
        now = self.clock()
        key = (own, internet)
        if self._answer is not None and self._answer[1] == key and timedelta(0) <= now - self._answer[0] < timedelta(seconds=FRESH_SEC):
            return self._answer[2]
        if key != self._key:
            self._key, self._over, self._until = key, {}, None
        top = now.replace(minute=0, second=0, microsecond=0)
        first = top - (WEEK_HOURS - 1) * HOUR
        since = first if self._until is None or self._until < first else self._until
        while since < top:                              # the hours that are over and not yet counted, SLICE_HOURS a read, so that what else waits for the database is served between
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
        """The rows of the hours from `start` to `end`, which are over, kept by their hour in place of what was kept for them (two pages that asked at once count a slice twice, never add it twice);
        those before `first` are no longer asked for."""
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
