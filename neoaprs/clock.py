"""Time, always UTC and always aware. A clock is a function so that tests can set the time."""

import sys
import time as _time
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

Clock = Callable[[], datetime]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# a clock that moves this much more than the monotonic time between two looks was stepped
STEP_SEC = 5.0


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=UTC)


def from_unix(seconds: float) -> datetime:
    # Not fromtimestamp: on Windows it rejects times before 1970 and beyond year 3000.
    return _EPOCH + timedelta(seconds=seconds)


def to_unix(t: datetime) -> int:
    return int(t.timestamp())


def iso(t: datetime | None) -> str | None:
    """Return the time for the page as 2026-10-09T18:05:00Z, or None."""
    if t is None:
        return None
    # Fast path: isoformat is much quicker than strftime.
    if t.tzinfo is UTC and t.year >= 1000:
        return t.isoformat(timespec="seconds")[:-6] + "Z"
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def days(n: int) -> timedelta:
    return timedelta(days=n)


def since_boot() -> float:
    """Return monotonic seconds that count time asleep too, where the system has them (Linux)."""
    if sys.platform == "linux":
        return _time.clock_gettime(_time.CLOCK_BOOTTIME)
    else:
        return _time.monotonic()


def monotonic_of(clock: Clock) -> Callable[[], float]:
    """Return the monotonic seconds that go with `clock`: its own if it keeps them (a test's), else the system's."""
    own = getattr(clock, "monotonic", None)
    return own if callable(own) else since_boot


class StepWatch:
    """Tells how far the clock was stepped forward between two looks, beyond the monotonic time."""

    def __init__(self) -> None:
        self._last: tuple[datetime, float] | None = None

    def forward(self, clock: Clock) -> timedelta:
        """Return the step since the last look, or zero when it is under STEP_SEC (the first look too)."""
        # both read here, together: a time read before a wait would look like a step
        now, mono = clock(), monotonic_of(clock)()
        last, self._last = self._last, (now, mono)
        if last is None:
            return timedelta(0)
        step = now - last[0] - timedelta(seconds=mono - last[1])
        return step if step > timedelta(seconds=STEP_SEC) else timedelta(0)
