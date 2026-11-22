"""The ticker shared by own objects and bulletins.

Every `tick_sec` it sends the thing due longest when the sender is ready. A subclass defines
`_keys`, `_due` and `_transmit`. A thing on several radios goes out in rounds (`_round`).
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from neoaprs.clock import Clock, utcnow
from neoaprs.radiotype import RadioId
from neoaprs.services.radioset import AirRadio, SendError
from neoaprs.services.sender import Sender
from neoaprs.source import Source
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.sender")

TICK_SEC = 1.0
# how long a connected radio that takes no frame holds up a round, from the first radio taking it
ROUND_HOLD_SEC = 60


class Repeater[K](ABC):
    # what the log calls what it sends
    kind = "frame"

    def __init__(self, sender: Sender, clock: Clock = utcnow, tick_sec: float = TICK_SEC) -> None:
        self._sender = sender
        self.clock = clock
        self.tick_sec = tick_sec
        self._tasks = TaskSet(log)
        # things whose frame cannot be made, with the reason; logged once, not at every tick
        self._refused: dict[K, str] = {}
        # radios that have taken the current round of a thing
        self._taken: dict[K, set[RadioId]] = {}
        # when the first radio took the current round of a thing
        self._round_at: dict[K, datetime] = {}

    @abstractmethod
    def _keys(self) -> list[K]: ...

    @abstractmethod
    def _due(self, key: K) -> datetime | None: ...

    @abstractmethod
    def _transmit(self, key: K, now: datetime) -> bool: ...

    def _new_round(self, key: K) -> None:
        """Start the thing's next round afresh for every radio."""
        self._taken.pop(key, None)
        self._round_at.pop(key, None)

    def _round(
        self, key: K, radios: list[AirRadio], info: bytes, path: tuple[str, ...] | None, now: datetime
    ) -> tuple[bool, set[RadioId]]:
        """Run one tick of the round; return whether it is done and the ids that took it.

        A connected radio that takes no frame holds the round up for ROUND_HOLD_SEC at most."""
        taken = self._taken.setdefault(key, set())
        went = set()
        for radio in radios:
            if radio.id not in taken and self._sender.send(info, path, radio):
                taken.add(radio.id)
                went.add(radio.id)
        if not taken:
            return False, went
        began = self._round_at.setdefault(key, now)
        if any(
            radio.id not in taken and radio.state is Source.State.CONNECTED for radio in radios
        ) and now - began < timedelta(seconds=ROUND_HOLD_SEC):
            return False, went
        self._new_round(key)
        return True, went

    def start_ticker(self) -> None:
        if not self._tasks:
            self._tasks.spawn(self._run(), self.kind)

    async def stop_ticker(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await every(self.tick_sec, self.tick, f"the {self.kind} ticker")

    def tick(self) -> bool:
        """Send what is due, longest overdue first; return whether something went out."""
        now = self.clock()
        due = [(when, key) for key in self._keys() if (when := self._due(key)) is not None and when <= now]
        due.sort(key=lambda pair: pair[0])
        for _, key in due:
            if not self._sender.ready(self.kind):
                return False
            try:
                if self._transmit(key, now):
                    self._refused.pop(key, None)
                    return True
            except SendError as e:
                if self._refused.get(key) != str(e):
                    self._refused[key] = str(e)
                    log.warning("the %s %s cannot be sent: %s (it waits)", self.kind, key, e)
        return False
