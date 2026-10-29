"""The ticker the objects and the bulletins of our own share: once a `tick_sec` it looks at the clock, and the thing that has been due longest goes out when the sender (services/sender.py) is ready.

A subclass keeps its things by key and says when each is next due (`_due`: None for one that is not sent again) and how one is transmitted (`_transmit`: True when it went out, False when the radio would
not take it, SendError when the values make no frame). A thing whose frame cannot be made is told in the log once and waits, the rest are not held up by it."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from neoaprs.clock import Clock, utcnow
from neoaprs.services.sender import SendError, Sender
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.sender")

TICK_SEC = 1.0


class Repeater[K](ABC):
    kind = "frame"                                          # what the log calls what it sends

    def __init__(self, sender: Sender, clock: Clock = utcnow, tick_sec: float = TICK_SEC) -> None:
        self._sender = sender
        self.clock = clock
        self.tick_sec = tick_sec
        self._tasks = TaskSet(log)
        self._refused: dict[K, str] = {}                    # the things whose frame cannot be made, with why: told once, not at every tick

    @abstractmethod
    def _keys(self) -> list[K]: ...

    @abstractmethod
    def _due(self, key: K) -> datetime | None: ...

    @abstractmethod
    def _transmit(self, key: K, now: datetime) -> bool: ...

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
