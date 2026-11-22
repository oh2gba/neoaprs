"""Base class of every packet feed: start, stop, state, problem, counters and recent lines.

`Backoff` gives the delay before reconnecting after a connection dropped.
"""

import asyncio
import logging
import os
import socket
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
from .coded import Reason

log = logging.getLogger("neoaprs.source")


class Backoff:
    """Delays before a retry: 5, 10, 20, 30 seconds, restarting only after a minute of uptime."""

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
    """Return the whole minutes between two times, such as "17 min"."""
    return f"{int((later - earlier).total_seconds() // 60)} min"


NO_LOOKUP = "the server's name cannot be looked up; is there a connection?"


def os_error_text(e: BaseException) -> str:
    """Return the system's wording of the error; a failed name lookup gives NO_LOOKUP."""
    if isinstance(e, socket.gaierror):
        return NO_LOOKUP
    if isinstance(e, OSError):
        words = os.strerror(e.errno) if e.errno else ""
        # a library's own error number has no text in the system's table
        if words and not words.startswith("Unknown error"):
            return words
        if e.strerror:
            return str(e.strerror)
    return str(e) or type(e).__name__


@dataclass
class Stats:
    opens: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    frames_in: int = 0
    packets: int = 0
    rejected: int = 0
    last_packet: datetime | None = None


class Source:
    class State(Enum):
        STOPPED = "stopped"
        CONNECTING = "connecting"
        CONNECTED = "connected"
        WAITING = "waiting"
        # the line is open but the radio does not answer; any byte ends it
        SILENT = "silent"

    MAX_LINES = 1500

    def __init__(self, name: str, clock: Clock = utcnow) -> None:
        self.name = name
        self.clock: Clock = clock
        self.state = Source.State.STOPPED
        self.last_error = ""
        self.problem = ""
        self.stats = Stats()
        self.lines: deque[str] = deque(maxlen=self.MAX_LINES)
        self.last_byte_at: datetime | None = None
        self.state_changed: Signal[[Source.State]] = Signal(f"{name}.state_changed")
        self.changed: Signal[[]] = Signal(f"{name}.changed")
        # changes at stop(), so that an attempt under way knows it is over
        self._generation = 0
        self._tasks = TaskSet(self._task_failed)

    @property
    def label(self) -> str:
        """The prefix of this feed's log lines."""
        return self.name

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def send(self, data: bytes) -> bool:
        return False

    def describe(self) -> str:
        """Return one line describing the feed for the page."""
        return ""

    @property
    def is_dummy(self) -> bool:
        """True if the feed's traffic is made up (Dummy radio); an iGate passes nothing from it."""
        return False

    @property
    def usable(self) -> bool:
        """True if a frame can be sent now: CONNECTED and not still settling into KISS."""
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        """Return why a frame cannot be sent now."""
        return unusable_because(self.state)

    @property
    def silent_since(self) -> datetime | None:
        """Return the time of the latest byte while the radio is silent, else None."""
        return self.last_byte_at if self.state is Source.State.SILENT else None

    def _hear(self, then: str = "") -> None:
        """Record that a byte came; a silent radio has answered. `then` goes in the log."""
        before, self.last_byte_at = self.last_byte_at, self.now()
        if self.state is Source.State.SILENT:
            text = (
                f"the radio answers again after {minutes_between(before or self.last_byte_at, self.last_byte_at)}{then}"
            )
            log.info("%s: %s", self.label, text)
            self._note(text)
            self._set_state(Source.State.CONNECTED)

    def went_silent(self, then: str = "") -> None:
        """Mark the radio silent: the line is open but the keep-alive check got no byte."""
        if self.state is Source.State.CONNECTED:
            self._set_state(Source.State.SILENT)
            text = f"the radio is silent: nothing heard since {self.last_byte_at or self.now():%H:%M} UTC, no answer to a check{then}"
            log.warning("%s: %s", self.label, text)
            self._note(text)

    def now(self) -> datetime:
        return self.clock()

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> "asyncio.Task[None]":
        """Start a task of this source, cancelled by _cancel_tasks(); its exceptions are logged."""
        return self._tasks.spawn(coro)

    def _task_failed(self, task: "asyncio.Task[Any]") -> None:
        log.error("source %s: task failed: %r", self.label, task.exception(), exc_info=task.exception())

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

    def _waiting(
        self,
        problem: str,
        delay: float,
        retry: Callable[[], Coroutine[Any, Any, None]] | None = None,
        *,
        expected: bool = False,
    ) -> None:
        """Enter WAITING; `retry` runs after `delay` seconds unless the feed was stopped meanwhile.

        An `expected` wait (the program behind the line is starting) is logged at DEBUG, not shown.
        """
        logging.getLogger(f"neoaprs.{self.name}").log(
            logging.DEBUG if expected else logging.WARNING, "%s: %s; trying again in %g s", self.label, problem, delay
        )
        self.problem = ""
        self._set_state(Source.State.WAITING, problem)
        if not expected:
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

    def _note(self, text: str) -> None:
        """Add a line for what the source did, prefixed "NeoAPRS: "."""
        self._add_line("NeoAPRS: " + text)

    def _saw(self, text: str) -> None:
        """Add a line for what the line said and count the frame."""
        self.stats.frames_in += 1
        self._add_line(text[:300])

    def _reject(self) -> None:
        self.stats.rejected += 1


CHECKING = Reason("the TNC is checking that the radio is there", "radio.checking")


def unusable_because(state: Source.State) -> Reason:
    """Return why a frame cannot be sent in this state (CONNECTED means settling into KISS)."""
    if state is Source.State.SILENT:
        return Reason("the radio is silent", "radio.silent")
    return (
        Reason("the TNC is restarting into KISS mode", "radio.settling")
        if state is Source.State.CONNECTED
        else Reason("the TNC is not connected", "radio.not_connected")
    )
