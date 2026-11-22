"""Time in tests: a clock the test holds."""

from datetime import datetime, timedelta

from neoaprs.clock import utc


class FixedClock:
    """A clock the test moves by hand; its monotonic time follows every move but a `step`."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or utc(2026, 10, 21, 12, 0, 0)
        self._origin = self.now

    def __call__(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return (self.now - self._origin).total_seconds()

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)

    def set(self, t: datetime) -> None:
        self.now = t

    def step(self, seconds: float) -> None:
        """Step the clock as the network time does, while the monotonic time stands."""
        self.now = self.now + timedelta(seconds=seconds)
        self._origin = self._origin + timedelta(seconds=seconds)
