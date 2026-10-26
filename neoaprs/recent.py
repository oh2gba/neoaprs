"""The keys seen lately: what tells a duplicate within a window from a new one (the digipeater's and the iGate's duplicate checks, the answer given once to a station that asks the same again).

A key is anything hashable (the source, destination and information field of a packet; a station and what it asked). `lately` says whether the key was noted less than the window before `now`, `note` notes it, and
`seen` does both: whether it was, and now it is. What is older than the window is dropped once the table has grown past `keep_max` entries, so that a busy channel costs a bounded amount of memory and a quiet
one costs no pruning. Pure code, like the rest of the foundation."""
from collections.abc import Hashable
from datetime import datetime, timedelta

KEEP_MAX = 2000                       # the most keys kept before the old ones are dropped: a channel does not carry more than this in the windows of the program (30 seconds)


class Recent[K: Hashable]:
    def __init__(self, window_sec: float, keep_max: int = KEEP_MAX) -> None:
        self.window = timedelta(seconds=window_sec)
        self.keep_max = keep_max
        self._at: dict[K, datetime] = {}

    def lately(self, key: K, now: datetime) -> bool:
        """Whether the key was noted less than the window before `now`."""
        if len(self._at) > self.keep_max:
            self._at = {k: t for k, t in self._at.items() if now - t < self.window}
        before = self._at.get(key)
        return before is not None and now - before < self.window

    def note(self, key: K, now: datetime) -> None:
        self._at[key] = now

    def seen(self, key: K, now: datetime) -> bool:
        """Whether the key was noted within the window; and it is noted now, so that a run of copies keeps the window open."""
        found = self.lately(key, now)
        self.note(key, now)
        return found

    def __len__(self) -> int:
        return len(self._at)
