"""Time, always UTC and always aware. A clock is a function so that tests can set the time."""
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

Clock = Callable[[], datetime]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_FIRST_UNIX, _LAST_UNIX = -62135596800 + 86400, 253402300799          # the second day of the year 1 and the last second of 9999, UTC: what a datetime can be made from


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=UTC)


def secs_between(earlier: datetime, later: datetime) -> float:
    """Seconds from `earlier` to `later`: positive when `later` is after `earlier`."""
    return (later - earlier).total_seconds()


def span_text(secs: float) -> str:
    """A duration in words: "25 min", "1 h 20 min", "2 d 3 h"."""
    s = max(0, int(secs))
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60

    if d > 0:
        return f"{d} d {h} h" if h > 0 else f"{d} d"
    if h > 0:
        return f"{h} h {m} min" if m > 0 else f"{h} h"

    return f"{m} min"


def from_unix(seconds: float) -> datetime:
    return _EPOCH + timedelta(seconds=seconds)             # (not fromtimestamp: on Windows that refuses a time before 1970 and one beyond year 3000)


def from_unix_or_none(seconds: float) -> datetime | None:
    """The time of a number from outside, None when it is none (NaN, infinity) or beyond the years a datetime has (year 10000 and over)."""
    try:
        return from_unix(int(seconds))
    except (OverflowError, OSError, ValueError):
        return None


def from_unix_clamped(seconds: int) -> datetime:
    """The time of a number a database holds, the nearest one a datetime has when it has none (a row somebody else wrote: 9e18, the year 10000): a read of the rows that are right
    must not fail for the one that is not. Anything inside a day of the ends of the calendar is the end."""
    return from_unix(min(max(int(seconds), _FIRST_UNIX), _LAST_UNIX))


def to_unix(t: datetime) -> int:
    return int(t.timestamp())


def iso(t: datetime | None) -> str | None:
    """For the page: 2026-10-09T18:05:00Z, or None."""
    if t is None:
        return None
    if t.tzinfo is UTC and t.year >= 1000:                  # already UTC (every time here is): no conversion, and isoformat is much quicker than strftime
        return t.isoformat(timespec="seconds")[:-6] + "Z"
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hhmm(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%H:%M")


def days(n: int) -> timedelta:
    return timedelta(days=n)
