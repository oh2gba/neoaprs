"""The pause between send attempts, per radio.

After an attempt on a radio, `spacing_sec` pass before the next on that radio, so messages written
together do not go out in a burst; other radios do not wait (plan rule 3.1)."""

from datetime import datetime

from neoaprs.clock import Clock
from neoaprs.radiotype import RadioId

SPACING_SEC = 10.0


def within(last: datetime, now: datetime, seconds: float) -> bool:
    """Return whether `now` is less than `seconds` after `last`.

    A `last` after `now` (clock set back) counts as not within, so it never holds a send."""
    return 0.0 <= (now - last).total_seconds() < seconds


class Pace:
    def __init__(self, clock: Clock, spacing_sec: float = SPACING_SEC) -> None:
        self._clock = clock
        self.spacing_sec = spacing_sec
        self._last: dict[RadioId, datetime] = {}

    def too_soon(self, radio: RadioId) -> bool:
        """Return whether the pause after the latest attempt on the radio is still running."""
        last = self._last.get(radio)
        return last is not None and within(last, self._clock(), self.spacing_sec)

    def stamp(self, radio: RadioId) -> datetime:
        """Record an attempt on the radio now, starting its pause, and return the time."""
        self._last[radio] = at = self._clock()
        return at
