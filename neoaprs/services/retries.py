"""The retry schedule of messages being sent.

Tracks when each message needs attention (message.due_at); a ticker runs the attempt that is due or
ends a message that used its last. Waits do not run while the radio is away.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Protocol

from neoaprs.clock import Clock
from neoaprs.config import can_transmit
from neoaprs.interlock import Interlock
from neoaprs.message import UNCONFIRMED_MAX, MessageRecord, State, due_at, retry_pause
from neoaprs.radiospec import told
from neoaprs.radiotype import RadioId
from neoaprs.services.answers import air_of, as_pick
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.radioset import AirRadio, RadioPick, first_sender
from neoaprs.tasks import every

log = logging.getLogger("neoaprs.messaging")


class Host(Protocol):
    """What the schedule asks of messaging."""

    def get(self, number: int) -> MessageRecord | None: ...
    def attempt(self, record: MessageRecord) -> MessageRecord: ...
    def put(self, record: MessageRecord) -> None: ...
    # None when the message has no radio now (email gateway, no email radio): the attempt waits
    def radio_of(self, record: MessageRecord) -> AirRadio | None: ...


class Retries:
    def __init__(
        self,
        host: Host,
        radios: RadioPick | Radio,
        config: ConfigSource,
        interlock: Interlock,
        clock: Clock,
        tick_sec: Callable[[], float],
        first: Callable[[], None] | None = None,
    ) -> None:
        self._host = host
        self._given = radios
        self._config = config
        self._interlock = interlock
        self._clock = clock
        self._tick_sec = tick_sec
        # runs before the attempts at a tick where a radio takes frames: the acks that waited for it
        self._first = first
        # messages being sent, and when each needs attention
        self._due: dict[int, datetime] = {}
        # by radio id: since when it has not taken frames, and the last tick that found it so
        self._down: dict[RadioId, tuple[datetime, datetime]] = {}
        # radios whose waiting attempts were logged, once per outage (None: a message with no radio)
        self._told_down: set[RadioId | None] = set()
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
        """Schedule the message's next attention; a message that is not being sent is dropped."""
        due = due_at(record)
        if due is None:
            self._due.pop(record.id, None)
        else:
            radio = self._host.radio_of(record)
            self._due[record.id] = due + retry_pause(record, radio.limits.retry_jitter_sec if radio is not None else 0)

    def forget(self, number: int) -> None:
        self._due.pop(number, None)

    def away(self, radio: AirRadio | Radio) -> bool:
        """Return whether the ticker counted the radio as away (taking no frames) last tick."""
        return air_of(radio, self._config).id in self._down  # pragma: no mutate

    def radio_up(self, record: MessageRecord | None = None) -> bool:
        """Return whether an attempt can be made now; log once per radio that attempts wait."""
        radio = first_sender(as_pick(self._given, self._config)) if record is None else self._host.radio_of(record)
        if radio is not None and radio.usable:
            return True
        key = radio.id if radio is not None else None
        if key not in self._told_down:
            self._told_down.add(key)
            if radio is None and record is not None:
                log.warning("message %d to %s waits: it has no radio to go on now", record.id, record.to_call)
            elif radio is not None:
                log.warning(
                    "a message is waiting and %s: its attempts wait for the radio (none is used up)",
                    radio.why_unusable(),
                )
        return False

    async def _run(self) -> None:
        await every(self._tick_sec, self.tick, "the messaging ticker")

    def tick(self) -> None:
        now = self._clock()
        # the interlock: receive only, or no call
        shut = can_transmit(self._config()) is not None
        radios = as_pick(self._given, self._config).senders()
        for radio in radios:
            self._watch(radio, now, shut)
        if shut or not any(radio.usable for radio in radios):
            if any(now >= due for due in self._due.values()):
                if shut:
                    self._interlock.refused("message")
                else:
                    self.radio_up()
            return
        if self._first is not None:
            self._first()
        for number, due in list(self._due.items()):
            record = self._host.get(number)
            if record is None or now < due or not self.radio_up(record):
                continue
            if record.attempts >= record.attempts_max:
                state: State = "unconfirmed" if record.attempts_max <= UNCONFIRMED_MAX else "failed"
                log.log(
                    logging.INFO if state == "unconfirmed" else logging.WARNING,
                    "message %d to %s is %s: no answer after %d attempts",
                    record.id,
                    record.to_call,
                    state,
                    record.attempts,
                )
                self._host.put(replace(record, state=state))
            else:
                self._host.attempt(record)

    def end_too_long(self, record: MessageRecord, why: Exception) -> MessageRecord:
        """Fail a message whose frame no longer fits its radio; no attempt is counted."""
        log.warning("message %d to %s fails: %s", record.id, record.to_call, why)
        record = replace(record, state="failed", failure="too_long_for_radio")
        self._host.put(record)
        return record

    def _watch(self, radio: AirRadio, now: datetime, shut: bool) -> None:
        """Track a radio's time away; when found back, move on its messages' waits by that span."""
        key = radio.id
        if shut or not radio.usable:
            since = self._down.get(key, (now, now))[0]
            self._down[key] = (since, now)
            return
        self._told_down.discard(key)
        span = self._down.pop(key, None)
        if span is not None and span[1] > span[0]:
            moved = self._move_on(span[1] - span[0], key)
            log.log(
                logging.INFO if moved else logging.DEBUG,
                "%s takes frames again after %d s: the waits of the messages on it are moved on by that time",
                told(radio.name, radio.id),
                (span[1] - span[0]).total_seconds(),
            )

    def _move_on(self, away: timedelta, key: RadioId) -> int:
        """Extend the waits of messages on the radio by the time it was away; return how many."""
        moved = 0
        for number, due in self._due.items():
            record = self._host.get(number)
            if record is None or record.attempts == 0:
                continue
            radio = self._host.radio_of(record)
            if radio is not None and radio.id == key:
                self._due[number] = due + away
                moved += 1  # pragma: no mutate
        return moved
