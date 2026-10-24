"""How many packets a station sent in the last hour, kept as a count for each minute (at most 60 of them): the cost of a station does not grow with its packets, and the count is right to the minute.

A packet of the minute `m` counts until the minute `m + 60` begins. Packets are noted in the order they are heard (the log is read oldest first); one that is older than the newest noted is counted with it."""
from datetime import datetime

WINDOW_MIN = 60


class HourCount:
    def __init__(self) -> None:
        self._minutes: list[int] = []               # the minutes that had a packet, oldest first
        self._counts: list[int] = []                # and how many
        self.total = 0                              # their sum, as of the last note or expiry

    @staticmethod
    def _minute(at: datetime) -> int:
        return int(at.timestamp() // 60)

    def note(self, at: datetime, count: int = 1) -> None:
        """A packet heard at `at` (or `count` of them)."""
        minute = self._minute(at)
        if self._minutes and minute <= self._minutes[-1]:
            self._counts[-1] += count
        else:
            self._minutes.append(minute)
            self._counts.append(count)
        self.total += count

    def expire(self, now: datetime) -> bool:
        """Drops the minutes that are an hour old at `now`; whether the total changed."""
        edge = self._minute(now) - WINDOW_MIN
        gone = 0
        while gone < len(self._minutes) and self._minutes[gone] <= edge:
            self.total -= self._counts[gone]
            gone += 1
        del self._minutes[:gone], self._counts[:gone]
        return gone > 0

    def count(self, now: datetime) -> int:
        """The packets of the last hour at `now`."""
        self.expire(now)
        return self.total
