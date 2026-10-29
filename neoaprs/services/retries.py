"""The retry schedule of the messages being sent: when each one needs attention again (message.due_at), the ticker that looks at the clock once a `tick_sec` and makes the attempt that is due or ends a message
that has had its last, and the waits that do not run while the radio is away.

While the Tnc is not usable, or transmitting is switched off (the interlock), an attempt that is due waits: it is not used up, and when the radio is back the waits that were running are moved on by the time it
was away. The log says so once for each time the radio was away (`radio_up`)."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Protocol

from neoaprs.clock import Clock
from neoaprs.config import can_transmit
from neoaprs.interlock import Interlock
from neoaprs.message import UNCONFIRMED_MAX, MessageRecord, State, due_at
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.tasks import every

log = logging.getLogger("neoaprs.messaging")


class Host(Protocol):
    """What the schedule asks of messaging."""
    def get(self, number: int) -> MessageRecord | None: ...
    def attempt(self, record: MessageRecord) -> MessageRecord: ...
    def put(self, record: MessageRecord) -> None: ...


class Retries:
    def __init__(self, host: Host, tnc: Radio, config: ConfigSource, interlock: Interlock, clock: Clock, tick_sec: Callable[[], float]) -> None:
        self._host = host
        self._tnc = tnc
        self._config = config
        self._interlock = interlock
        self._clock = clock
        self._tick_sec = tick_sec                                # (what the owner says now: a test makes the ticker quick)
        self._due: dict[int, datetime] = {}                     # the messages being sent, and when each needs attention
        self._down_since: datetime | None = None
        self._told_down = False
        self._ticker: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._ticker is not None

    def start(self) -> None:
        self._ticker = asyncio.get_running_loop().create_task(self._run(), name="messaging")

    async def stop(self) -> None:
        ticker, self._ticker = self._ticker, None
        if ticker is not None:
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)

    def plan(self, record: MessageRecord) -> None:
        """When the message needs attention next; none for a message that is not being sent."""
        due = due_at(record)
        if due is None:
            self._due.pop(record.id, None)
        else:
            self._due[record.id] = due

    def forget(self, number: int) -> None:
        self._due.pop(number, None)

    def radio_up(self) -> bool:
        """Whether an attempt can be made now; the log says once that the attempts wait when it cannot."""
        if self._tnc.usable:
            return True
        if not self._told_down:
            self._told_down = True
            log.warning("a message is waiting and %s: its attempts wait for the radio (none is used up)", self._tnc.why_unusable())
        return False

    async def _run(self) -> None:
        await every(self._tick_sec, self.tick, "the messaging ticker")

    def tick(self) -> None:
        now = self._clock()
        if not self._tnc.usable or can_transmit(self._config()) is not None:      # (the radio is away, or the interlock is shut: receive only, no call)
            self._down_since = self._down_since or now
            if any(now >= due for due in self._due.values()) and self.radio_up():
                self._interlock.refused("message")                   # (tells once)
            return
        self._told_down = False
        if self._down_since is not None:
            self._move_on(now - self._down_since)
            self._down_since = None
        for number, due in list(self._due.items()):
            record = self._host.get(number)
            if record is None or now < due:
                continue
            if record.attempts >= record.attempts_max:
                state: State = "unconfirmed" if record.attempts_max <= UNCONFIRMED_MAX else "failed"
                log.log(logging.INFO if state == "unconfirmed" else logging.WARNING, "message %d to %s is %s: no answer after %d attempts", record.id, record.to_call, state, record.attempts)
                self._host.put(replace(record, state=state))
            else:
                self._host.attempt(record)

    def _move_on(self, away: timedelta) -> None:
        """The radio was away for this long: the waits that were running did not run."""
        for number, due in self._due.items():
            record = self._host.get(number)
            if record is not None and record.attempts > 0:
                self._due[number] = due + away
