"""The pause between our attempts to send: after one attempt goes out, `spacing_sec` pass before the next, so that several messages written together never go out in a burst."""
from datetime import datetime

from neoaprs.clock import Clock

SPACING_SEC = 10.0


class Pace:
    def __init__(self, clock: Clock, spacing_sec: float = SPACING_SEC) -> None:
        self._clock = clock
        self.spacing_sec = spacing_sec
        self._last: datetime | None = None                      # when the latest attempt went out

    def too_soon(self) -> bool:
        """Whether the pause after the latest attempt is not over."""
        return self._last is not None and (self._clock() - self._last).total_seconds() < self.spacing_sec

    def stamp(self) -> datetime:
        """An attempt has just gone out: the time it did, which starts the pause."""
        self._last = self._clock()
        return self._last
