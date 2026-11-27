"""Whether Mercury's receive side has stalled, and whether it is restarted or given up on.

Mercury says CAPTURE_FULL (mercury.py) while what it records is not taken by its demodulator: it
hears nothing then. A run of the warning longer than STALL_SEC is a stall.
"""

from collections import deque
from datetime import datetime
from typing import Literal

STALL_SEC = 30.0  # the warning comes this long with no gap: a short burst is no stall
GAP_SEC = 5.0  # a pause longer than this ends a run of the warning
RESTART_EVERY_SEC = 600.0
HOUR_SEC = 3600.0
RESTARTS_PER_HOUR = 3

Action = Literal["", "restart", "give_up"]


class StallWatch:
    """The runs of the capture warning of one modem, and its stalls and restarts (monotonic times)."""

    def __init__(self) -> None:
        self.stalls = self.restarts = 0
        self.last_stall_at: datetime | None = None
        self.last_restart_at: datetime | None = None
        self.stalled = False
        self.given_up = False
        self._run_from: float | None = None
        self._last_seen = 0.0
        self._restarted: deque[float] = deque(maxlen=RESTARTS_PER_HOUR)

    def seen(self, now: float, at: datetime) -> bool:
        """Note the warning at `now`; return True when it makes a new stall."""
        if self._run_from is None or now - self._last_seen > GAP_SEC:
            self._run_from, self.stalled = now, False
        self._last_seen = now
        if self.stalled or now - self._run_from < STALL_SEC:
            return False
        self.stalled = True
        self.stalls += 1
        self.last_stall_at = at
        return True

    def deaf(self, now: float) -> bool:
        """Return whether the modem hears nothing now: stalled, the warning still coming, and not given up."""
        return self.stalled and not self.given_up and now - self._last_seen <= GAP_SEC

    def pause(self) -> None:
        """The radio transmits: warnings meanwhile count for nothing, and a run starts afresh after."""
        self.stalled, self._run_from = False, None

    def action(self, now: float, busy: bool) -> Action:
        """Return what is to be done about a stall now: never while `busy` (keyed, a test on)."""
        if not self.stalled or self.given_up or busy:
            return ""
        recent = [t for t in self._restarted if now - t < HOUR_SEC]
        if len(recent) >= RESTARTS_PER_HOUR:
            self.given_up = True
            return "give_up"
        if recent and now - recent[-1] < RESTART_EVERY_SEC:
            return ""
        return "restart"

    def restarted(self, now: float, at: datetime) -> None:
        self._restarted.append(now)
        self.restarts += 1
        self.last_restart_at = at
        self.stalled, self._run_from = False, None
