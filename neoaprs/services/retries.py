"""The retry schedule of the messages being sent: when each one needs attention again (message.due_at), the ticker that looks at the clock once a `tick_sec` and makes the attempt that is due or ends a message
that has had its last, and the waits that do not run while the radio is away.

The radio is the radio of the message (`Host.radio_of`: the station's, neoaprs/radios.py), and each radio that is on is watched on its own: while a message's radio is not usable, or transmitting is switched off (the
interlock), an attempt that is due waits, it is not used up, and when that radio is back the waits of the messages on it are moved on by the time it was away; a message to a station heard on HF alone is attempted
while the FM radio is silent at night, and the acks that waited for a radio go when that radio takes frames (`first`, services/acks.py). The log says so once for each time a radio was away (`radio_up`).

The time a radio was away is measured by the ticks: from the tick that first found it away to the last tick that still did, not to the tick that finds it back. Between those two ticks the radio came back, at a moment
nobody saw; a clock that jumped in between (a test's, a suspend) jumped while the radio was back as far as anyone knows, and the attempt it made due goes at once instead of a jump later. The error is one tick."""
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
from neoaprs.services.common import ConfigSource, Radio, radios_on
from neoaprs.tasks import every

log = logging.getLogger("neoaprs.messaging")


class Host(Protocol):
    """What the schedule asks of messaging."""
    def get(self, number: int) -> MessageRecord | None: ...
    def attempt(self, record: MessageRecord) -> MessageRecord: ...
    def put(self, record: MessageRecord) -> None: ...
    def radio_of(self, record: MessageRecord) -> Radio | None: ...        # the radio the message goes out on; None when it has none now (the email gateway while the FM radio is off): the attempt waits


class Retries:
    def __init__(self, host: Host, tnc: Radio, config: ConfigSource, interlock: Interlock, clock: Clock, tick_sec: Callable[[], float], first: Callable[[], None] | None = None) -> None:
        self._host = host
        self._tnc = tnc
        self._config = config
        self._interlock = interlock
        self._clock = clock
        self._tick_sec = tick_sec                                # (what the owner says now: a test makes the ticker quick)
        self._first = first                                      # what goes before the attempts at a tick where a radio takes frames: the acks that waited for it (services/acks.py)
        self._due: dict[int, datetime] = {}                     # the messages being sent, and when each needs attention
        self._down: dict[str, tuple[datetime, datetime]] = {}  # by the kind of radio: since when it has not taken frames, and the last tick that found it so
        self._told_down: set[str] = set()                       # the kinds of radio whose waiting attempts the log has been told of, once per time away
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
            radio = self._host.radio_of(record)
            self._due[record.id] = due + retry_pause(record, radio.rules.retry_jitter_sec if radio is not None else 0)

    def forget(self, number: int) -> None:
        self._due.pop(number, None)

    def away(self, radio: Radio) -> bool:
        """Whether the ticker counts this radio as away (not taking frames) as of its last tick: what a test waits on before it moves the clock."""
        return radio.rules.kind in self._down

    def radio_up(self, record: MessageRecord | None = None) -> bool:
        """Whether an attempt of this message (of any, on the default radio, when none is named) can be made now; the log says once per radio that the attempts wait when it cannot."""
        radio = self._tnc if record is None else self._host.radio_of(record)
        if radio is not None and radio.usable:
            return True
        kind = radio.rules.kind if radio is not None else ""
        if kind not in self._told_down:
            self._told_down.add(kind)
            if radio is None and record is not None:
                log.warning("message %d to %s waits: it has no radio to go on now", record.id, record.to_call)
            elif radio is not None:
                log.warning("a message is waiting and %s: its attempts wait for the radio (none is used up)", radio.why_unusable())
        return False

    async def _run(self) -> None:
        await every(self._tick_sec, self.tick, "the messaging ticker")

    def tick(self) -> None:
        now = self._clock()
        shut = can_transmit(self._config()) is not None                       # (the interlock: receive only, no call)
        radios = radios_on(self._tnc)
        for radio in radios:
            self._watch(radio, now, shut)
        if shut or not any(radio.usable for radio in radios):
            if any(now >= due for due in self._due.values()):
                if shut:
                    self._interlock.refused("message")                           # (tells once)
                else:
                    self.radio_up()                                              # (tells once that the attempts wait for the radio)
            return
        if self._first is not None:
            self._first()
        for number, due in list(self._due.items()):
            record = self._host.get(number)
            if record is None or now < due or not self.radio_up(record):        # (its radio is away: the attempt waits, told once per radio)
                continue
            if record.attempts >= record.attempts_max:
                state: State = "unconfirmed" if record.attempts_max <= UNCONFIRMED_MAX else "failed"
                log.log(logging.INFO if state == "unconfirmed" else logging.WARNING, "message %d to %s is %s: no answer after %d attempts", record.id, record.to_call, state, record.attempts)
                self._host.put(replace(record, state=state))
            else:
                self._host.attempt(record)

    def end_too_long(self, record: MessageRecord, why: Exception) -> MessageRecord:
        """A message whose frame does not fit the radio it goes out on now (the radio changed, or its path is longer) cannot be sent by waiting: it has failed, and the log says why. Nothing was transmitted, so no attempt is counted; the record says why (`too_long_for_radio`), and so does the page."""
        log.warning("message %d to %s fails: %s", record.id, record.to_call, why)
        record = replace(record, state="failed", failure="too_long_for_radio")
        self._host.put(record)
        return record

    def _watch(self, radio: Radio, now: datetime, shut: bool) -> None:
        """One radio's time away, tick by tick: while it does not take frames (or the interlock is shut) the span grows to this tick; at the first tick that finds it back, the waits of the messages on it are
        moved on by the span up to the last tick that saw it away (the module docstring says why not up to this one)."""
        kind = radio.rules.kind
        if shut or not radio.usable:
            since = self._down.get(kind, (now, now))[0]
            self._down[kind] = (since, now)
            return
        self._told_down.discard(kind)
        span = self._down.pop(kind, None)
        if span is not None and span[1] > span[0]:
            log.info("the %s radio takes frames again after %d s: the waits of the messages on it are moved on by that time", kind, (span[1] - span[0]).total_seconds())
            self._move_on(span[1] - span[0], kind)

    def _move_on(self, away: timedelta, kind: str) -> None:
        """The radio of this kind was away for this long: the waits that were running on it did not run."""
        for number, due in self._due.items():
            record = self._host.get(number)
            if record is None or record.attempts == 0:
                continue
            radio = self._host.radio_of(record)
            if radio is not None and radio.rules.kind == kind:
                self._due[number] = due + away
