"""Packets a station sent in the last hour, kept as a count per minute (at most 60).

A packet of minute `m` counts until minute `m + 60` begins. Packets are noted in the order heard;
one older than the newest noted is counted with it.
"""
from datetime import datetime

WINDOW_MIN = 60


class HourCount:
    def __init__(self) -> None:
        self._minutes: list[int] = []  # minutes that had a packet, oldest first
        self._counts: list[int] = []  # and how many
        self.total = 0  # their sum, as of the last note or expiry

    @staticmethod
    def _minute(at: datetime) -> int:
        return int(at.timestamp() // 60)

    def note(self, at: datetime, count: int = 1) -> None:
        """Note a packet heard at `at` (or `count` of them)."""
        minute = self._minute(at)
        if self._minutes and minute <= self._minutes[-1]:
            self._counts[-1] += count
        else:
            self._minutes.append(minute)
            self._counts.append(count)
        self.total += count

    def expire(self, now: datetime) -> bool:
        """Drop the minutes an hour old at `now`; return whether the total changed."""
        edge = self._minute(now) - WINDOW_MIN
        gone = 0
        while gone < len(self._minutes) and self._minutes[gone] <= edge:
            self.total -= self._counts[gone]
            gone += 1
        del self._minutes[:gone], self._counts[:gone]
        return gone > 0

    def count(self, now: datetime) -> int:
        """Return the packets of the last hour at `now`."""
        self.expire(now)
        return self.total

    def without(self, other: "HourCount") -> "HourCount":
        """Return this count less the other's, which is among them (one channel's packets)."""
        less = dict(zip(other._minutes, other._counts, strict=True))
        left = HourCount()
        for minute, count in zip(self._minutes, self._counts, strict=True):
            if count > less.get(minute, 0):
                left._minutes.append(minute)
                left._counts.append(count - less.get(minute, 0))
                left.total += count - less.get(minute, 0)
        return left
