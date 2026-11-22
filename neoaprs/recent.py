"""The keys seen lately: tells a duplicate within a window from a new one.

A key is anything hashable. `lately` asks, `note` notes, `seen` does both; old keys are dropped
once the table passes `keep_max`. Pure code.
"""

from collections.abc import Hashable
from datetime import datetime, timedelta

# most keys kept before the old are dropped
KEEP_MAX = 2000


class Recent[K: Hashable]:
    def __init__(self, window_sec: float, keep_max: int = KEEP_MAX) -> None:
        self.window = timedelta(seconds=window_sec)
        self.keep_max = keep_max
        self._at: dict[K, datetime] = {}

    def _prune(self, now: datetime) -> None:
        if len(self._at) > self.keep_max:
            self._at = {k: t for k, t in self._at.items() if abs(now - t) < self.window}

    def lately(self, key: K, now: datetime) -> bool:
        """Return whether the key was noted less than the window before `now`."""
        self._prune(now)
        before = self._at.get(key)
        return before is not None and abs(now - before) < self.window

    def note(self, key: K, now: datetime) -> None:
        self._prune(now)
        self._at[key] = now

    def seen(self, key: K, now: datetime) -> bool:
        """Return whether the key was noted within the window, and note it now."""
        found = self.lately(key, now)
        self.note(key, now)
        return found

    def __len__(self) -> int:
        return len(self._at)
