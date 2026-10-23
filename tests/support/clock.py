"""Time in tests: a clock the test holds."""
from datetime import datetime, timedelta

from neoaprs.clock import utc


class FixedClock:
    """A clock the test moves by hand."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or utc(2026, 10, 21, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)

    def set(self, t: datetime) -> None:
        self.now = t
