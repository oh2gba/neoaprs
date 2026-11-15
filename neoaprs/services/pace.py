"""The pause between our attempts to send, on each radio: after one attempt goes out on a radio, `spacing_sec` pass before the next on that radio, so that several messages written together never go out
in a burst, and one on another radio does not wait for that pause (plan rule 3.1: the pause between our scheduled frames is per radio)."""
from datetime import datetime

from neoaprs.clock import Clock
from neoaprs.radiotype import RadioId

SPACING_SEC = 10.0


class Pace:
    def __init__(self, clock: Clock, spacing_sec: float = SPACING_SEC) -> None:
        self._clock = clock
        self.spacing_sec = spacing_sec
        self._last: dict[RadioId, datetime] = {}                # by radio: when the latest attempt went out on it

    def too_soon(self, radio: RadioId) -> bool:
        """Whether the pause after the latest attempt on the radio is not over."""
        last = self._last.get(radio)
        return last is not None and (self._clock() - last).total_seconds() < self.spacing_sec

    def stamp(self, radio: RadioId) -> datetime:
        """An attempt has just gone out on the radio: the time it did, which starts the pause on it."""
        self._last[radio] = at = self._clock()
        return at
