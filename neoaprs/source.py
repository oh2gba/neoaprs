"""What every feed of packets looks like from the outside: it is started and stopped, it has a state and a problem, it counts what it did, and it keeps the latest lines of what it saw
and did. The page shows the one feed there is (the TNC, tnc.py) from this. `Backoff` is when to try again after a connection dropped.
"""
import asyncio
import logging
import os
import time as _time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .clock import Clock, utcnow
from .signal import Signal
from .tasks import TaskSet

log = logging.getLogger("neoaprs.source")


class Backoff:
    """When to try again after a connection dropped: 5, 10, 20, 30 seconds, and the series starts over only once a connection stayed up for a minute. A line that drops every few seconds
    must not be hammered."""

    def __init__(self, delays_sec: list[float] | None = None, stable_after_sec: float = 60.0) -> None:
        self.delays_sec = delays_sec or [5.0, 10.0, 20.0, 30.0]
        self.stable_after_sec = stable_after_sec
        self.index = 0
        self._connected_at: float | None = None

    def connected(self) -> None:
        self._connected_at = _time.monotonic()

    def next_delay_sec(self) -> float:
        if self._connected_at is not None and _time.monotonic() - self._connected_at >= self.stable_after_sec:
            self.index = 0
        self._connected_at = None
        delay = self.delays_sec[min(self.index, len(self.delays_sec) - 1)]
        if self.index < len(self.delays_sec) - 1:
            self.index += 1
        return delay

    def reset(self) -> None:
        self.index = 0
        self._connected_at = None


def minutes_between(earlier: datetime, later: datetime) -> str:
    """The whole minutes from one time to the other: "17 min"."""
    return f"{int((later - earlier).total_seconds() // 60)} min"


def os_error_text(e: BaseException) -> str:
    """The system's words for the error: "No such file or directory", not the Python wording."""
    if isinstance(e, OSError):
        if e.errno:
            return os.strerror(e.errno)
        if e.strerror:
            return str(e.strerror)
    return str(e) or type(e).__name__


@dataclass
class Stats:
    opens: int = 0             # times the line was opened
    bytes_in: int = 0
    bytes_out: int = 0
    frames_in: int = 0         # frames received
    packets: int = 0           # packets handed on
    rejected: int = 0          # frames that could not be read as a packet
    last_packet: datetime | None = None


class Source:
    class State(Enum):
        STOPPED = "stopped"
        CONNECTING = "connecting"
        CONNECTED = "connected"
        WAITING = "waiting"
        SILENT = "silent"              # the line is open but the radio does not answer (the TNC sets it; any byte ends it)

    MAX_LINES = 1500

    def __init__(self, name: str, clock: Clock = utcnow) -> None:
        self.name = name
        self.clock: Clock = clock
        self.state = Source.State.STOPPED
        self.last_error = ""
        self.problem = ""                  # why it is not connected
        self.stats = Stats()
        self.lines: deque[str] = deque(maxlen=self.MAX_LINES)
        self.last_byte_at: datetime | None = None          # when the latest byte came (the open, if none has since); kept across a reopen of the line
        self.state_changed: Signal[[Source.State]] = Signal(f"{name}.state_changed")
        self.changed: Signal[[]] = Signal(f"{name}.changed")          # lines or counters moved
        self._generation = 0                                           # changes at stop(), so that an attempt that was under way knows it is over
        self._tasks = TaskSet(self._task_failed)

    # ---- what a feed implements
    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def send(self, data: bytes) -> bool:
        return False

    def describe(self) -> str:                     # one line for the page
        return ""

    @property
    def is_dummy(self) -> bool:
        """Whether what this feed delivers is made up (the Dummy radio, dummyline.py): nothing of it is on the air. Whatever hands packets on to the internet (an iGate) must look at this and gate nothing of such a feed."""
        return False

    @property
    def usable(self) -> bool:
        """Whether a frame can be sent now: the line is open and the radio answers. CONNECTED, and a feed that settles after switching the radio to KISS says no meanwhile."""
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        """Why a frame cannot be sent now, as a clause (`unusable_because`, and a feed that knows more says it)."""
        return unusable_because(self.state)

    @property
    def silent_since(self) -> datetime | None:
        """The time of the latest byte while the radio is silent; None otherwise."""
        return self.last_byte_at if self.state is Source.State.SILENT else None

    def _hear(self, then: str = "") -> None:
        """A byte came: the time of it is kept, and a silent radio has answered (`then` is what the feed does about that, for the log: "; entering KISS")."""
        before, self.last_byte_at = self.last_byte_at, self.now()
        if self.state is Source.State.SILENT:
            text = f"the radio answers again after {minutes_between(before or self.last_byte_at, self.last_byte_at)}{then}"
            log.info("%s: %s", self.name, text)
            self._note(text)
            self._set_state(Source.State.CONNECTED)

    def went_silent(self, then: str = "") -> None:
        """The line is open and the radio does not answer (the Tnc's keep-alive got no byte at all in return for its check); `then` is what the feed does about that, for the log."""
        if self.state is Source.State.CONNECTED:
            self._set_state(Source.State.SILENT)
            text = f"the radio is silent: nothing heard since {self.last_byte_at or self.now():%H:%M} UTC, no answer to a check{then}"
            log.warning("%s: %s", self.name, text)
            self._note(text)

    # ---- helpers for the feeds
    def now(self) -> datetime:
        return self.clock()

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> "asyncio.Task[None]":
        """A task of this source: cancelled by _cancel_tasks(), its exceptions logged, never lost."""
        return self._tasks.spawn(coro)

    def _task_failed(self, task: "asyncio.Task[Any]") -> None:
        log.error("source %s: task failed: %r", self.name, task.exception())

    async def _cancel_tasks(self) -> None:
        await self._tasks.cancel_all()

    def _set_state(self, state: "Source.State", problem: str = "") -> None:
        if state == Source.State.CONNECTING:
            self.problem = ""
        elif state == Source.State.WAITING:
            self.last_error = problem
            if not self.problem:
                self.problem = problem
        if state != self.state:
            self.state = state
            self.state_changed.emit(state)
        self.changed.emit()

    def _waiting(self, problem: str, delay: float, retry: Callable[[], Coroutine[Any, Any, None]] | None = None) -> None:
        """The line is down: the state is WAITING and the problem is why it is down now, not what was wrong with an earlier line; `retry`, when given, is run after `delay` seconds unless the feed was stopped meanwhile."""
        logging.getLogger(f"neoaprs.{self.name}").warning("%s: %s; trying again in %g s", self.name, problem, delay)
        self.problem = ""
        self._set_state(Source.State.WAITING, problem)
        self._note(f"{problem}; trying again in {delay:g} s")
        if retry is not None:
            self._spawn(self._retry_after(delay, self._generation, retry))

    async def _retry_after(self, delay: float, generation: int, retry: Callable[[], Coroutine[Any, Any, None]]) -> None:
        await asyncio.sleep(delay)
        if generation == self._generation:
            await retry()

    def _set_problem(self, text: str) -> None:
        self.problem = text
        self.changed.emit()

    def _add_line(self, text: str) -> None:
        self.lines.append(self.clock().strftime("%H:%M:%S") + "  " + text)
        self.changed.emit()

    def _note(self, text: str) -> None:            # what the source did: "NeoAPRS: ..." in the list
        self._add_line("NeoAPRS: " + text)

    def _saw(self, text: str) -> None:             # what the line said
        self.stats.frames_in += 1
        self._add_line(text[:300])

    def _reject(self) -> None:
        self.stats.rejected += 1


CHECKING = "the TNC is checking that the radio is there"


def unusable_because(state: Source.State) -> str:
    """Why a frame cannot be sent in this state, as a clause: "the radio is silent", "the TNC is restarting into KISS mode" (connected, but not usable: the feed is settling), else "the TNC is not connected"."""
    if state is Source.State.SILENT:
        return "the radio is silent"
    return "the TNC is restarting into KISS mode" if state is Source.State.CONNECTED else "the TNC is not connected"
