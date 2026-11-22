"""The ticker shared by own objects and bulletins.

Every `tick_sec` it sends the thing due longest when the sender is ready. A subclass defines
`_keys`, `_due` and `_transmit`. A thing on several radios goes out in rounds (`_round`); a repeat
waits a random pause within its slot (`_paused`), and the next slot counts from the slot.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from neoaprs import pause
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
        self.jitter: pause.Draw = pause.draw
        # the drawn pause of a thing's current wait, as a share of the most
        self._shares: dict[K, float] = {}
        # the current wait's slot (unpaused time) and how late in it the send may go, in seconds
        self._slots: dict[K, tuple[datetime, float]] = {}
        # the slot the latest send of a thing in this run belongs to; the next wait counts from it
        self._anchors: dict[K, datetime] = {}
        # things made or sent in this run; the others were loaded at the start
        self._fresh: set[K] = set()
        self._started: datetime | None = None

    @abstractmethod
    def _keys(self) -> list[K]: ...

    @abstractmethod
    def _due(self, key: K) -> datetime | None: ...

    @abstractmethod
    def _transmit(self, key: K, now: datetime) -> bool: ...

    def _new_round(self, key: K) -> None:
        """Start the thing's next round afresh for every radio, with a new pause."""
        self._taken.pop(key, None)
        self._round_at.pop(key, None)
        self._shares.pop(key, None)
        self._slots.pop(key, None)
        self._anchors.pop(key, None)
        self._fresh.add(key)

    def _last(self, key: K, sent_at: datetime) -> datetime:
        """Return what the next wait counts from: the latest send's slot, else its time."""
        return self._anchors.get(key, sent_at)

    def _paused(
        self, key: K, planned: datetime, radios: list[AirRadio], sent: int, wait: float | None, end: datetime | None
    ) -> datetime:
        """Return when the send planned for `planned` goes: after a random pause within its slot.

        The first packet of a thing made in this run goes at once. A thing loaded at the start waits
        from the start. The pause is drawn once per send and never longer than `wait` or past `end`."""
        most = max((radio.limits.beacon_jitter_sec for radio in radios), default=0)
        loaded = key not in self._fresh
        if most <= 0 or (sent == 0 and not loaded):
            return planned
        now = self.clock()
        if self._started is None or now < self._started:  # a clock set back starts the wait anew
            self._started = now
        base = max(planned, self._started) if loaded else planned
        if key not in self._shares:
            self._shares[key] = pause.share(self.jitter, most)
        rooms = (pause.latest(base, end),) if wait is None else (wait, pause.latest(base, end))
        delay = pause.capped(self._shares[key], most, *rooms)
        self._slots[key] = (base, 0.0 if wait is None else min(most, wait))
        return base + delay

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
        slot = self._slots.get(key)
        self._new_round(key)
        self._anchors[key] = pause.anchor(slot, now)
        return True, went

    def start_ticker(self) -> None:
        if self._started is None:
            self._started = self.clock()
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
