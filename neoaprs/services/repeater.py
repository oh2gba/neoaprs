"""The ticker the objects and the bulletins of our own share: once a `tick_sec` it looks at the clock, and the thing that has been due longest goes out when the sender (services/sender.py) is ready.

A subclass keeps its things by key and says when each is next due (`_due`: None for one that is not sent again) and how one is transmitted (`_transmit`: True when it went out, False when the radio would
not take it, SendError when the values make no frame). A thing whose frame cannot be made is told in the log once and waits, the rest are not held up by it.

A thing on several radios (an object, a bulletin) goes out in one round on all of them (`_round`): each radio that has not taken it yet and takes a frame now is given it; the round is done when every radio
that is there has taken it (one that is away does not hold it up, one that is connected but takes no frame for ROUND_HOLD_SEC after the first radio took it no longer does). The radios that have taken the
round are kept in memory (a restart sends on all of them, which is one packet more), told apart by their ids."""
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
ROUND_HOLD_SEC = 60                                         # how long a connected radio that takes no frame holds up the round of a thing, from when the first of its radios took it


class Repeater[K](ABC):
    kind = "frame"                                          # what the log calls what it sends

    def __init__(self, sender: Sender, clock: Clock = utcnow, tick_sec: float = TICK_SEC) -> None:
        self._sender = sender
        self.clock = clock
        self.tick_sec = tick_sec
        self._tasks = TaskSet(log)
        self._refused: dict[K, str] = {}                    # the things whose frame cannot be made, with why: told once, not at every tick
        self._taken: dict[K, set[RadioId]] = {}             # by thing: the ids of the radios that have taken the round of it that is being sent
        self._round_at: dict[K, datetime] = {}              # by thing: when the first of its radios took the round that is being sent

    @abstractmethod
    def _keys(self) -> list[K]: ...

    @abstractmethod
    def _due(self, key: K) -> datetime | None: ...

    @abstractmethod
    def _transmit(self, key: K, now: datetime) -> bool: ...

    def _new_round(self, key: K) -> None:
        """The thing is new, changed or gone: its next round is a fresh one for every radio."""
        self._taken.pop(key, None)
        self._round_at.pop(key, None)

    def _round(self, key: K, radios: list[AirRadio], info: bytes, path: tuple[str, ...] | None, now: datetime) -> tuple[bool, set[RadioId]]:
        """One tick of the round of the thing on its radios: whether the round is done, and the ids of the radios that took it in this tick. False until one has taken it (the next tick tries the radios
        that are still owed it, and no other sends it again)."""
        taken = self._taken.setdefault(key, set())
        went = set()
        for radio in radios:
            if radio.id not in taken and self._sender.send(info, path, radio):
                taken.add(radio.id)
                went.add(radio.id)
        if not taken:
            return False, went
        began = self._round_at.setdefault(key, now)
        if any(radio.id not in taken and radio.state is Source.State.CONNECTED for radio in radios) and now - began < timedelta(seconds=ROUND_HOLD_SEC):
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
        """Sends what is due, the one due longest first; whether something went out."""
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
