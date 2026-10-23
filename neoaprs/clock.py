"""Time, always UTC and always aware. A clock is a function so that tests can set the time."""
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

Clock = Callable[[], datetime]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=UTC)


def from_unix(seconds: float) -> datetime:
    return _EPOCH + timedelta(seconds=seconds)             # (not fromtimestamp: on Windows that refuses a time before 1970 and one beyond year 3000)


def to_unix(t: datetime) -> int:
    return int(t.timestamp())


def iso(t: datetime | None) -> str | None:
    """For the page: 2026-10-09T18:05:00Z, or None."""
    if t is None:
        return None
    if t.tzinfo is UTC and t.year >= 1000:                  # already UTC (every time here is): no conversion, and isoformat is much quicker than strftime
        return t.isoformat(timespec="seconds")[:-6] + "Z"
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def days(n: int) -> timedelta:
    return timedelta(days=n)
