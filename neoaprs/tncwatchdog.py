"""The TNC's keep-alive: how the Tnc learns that the radio is there.

A quiet line proves nothing, so after a quiet period the watchdog asks the radio; no answer makes
it silent and it is then probed. `EntryAgain` schedules repeats of the KISS entry.
"""

import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .policy import TNC_CHECK_JITTER
from .radiotype import RadioId
from .source import Source, Stats
from .tncprofile import Profile

log = logging.getLogger("neoaprs.tnc")

# a bare carriage return: a TNC in command mode answers "cmd:"
PROMPT = b"\r"
CHECK_PAUSE_SEC = 0.5  # between the KISS exit frame and the carriage return
# time the carriage return is given to be answered before KISS ON is sent anyway
REPLY_SEC = 1.0
# how long a check waits for any byte after KISS ON before calling the radio silent
ANSWER_SEC = 2.0
PROBE_SEC = 30.0  # how often a silent radio is probed
REOPEN_EVERY = 5  # every this many probes the port is reopened
ENTRY_AGAIN_SEC = 10.0  # a TNC still typing text this long after entry
ENTRY_AGAIN_MAX_SEC = 60.0  # later repeats double the wait up to this


@dataclass
class PassCount:
    """What the pairs passed onto a radio from one other radio."""
    sent: int = 0
    sent_at: datetime | None = None
    held: int = 0
    too_long: int = 0


@dataclass
class TncStats(Stats):
    keepalive_checks: int = 0
    watchdog_probes: int = 0
    port_reopens: int = 0
    # frames the digipeater sent again, including the pairs' passed frames
    digipeated: int = 0
    digipeated_at: datetime | None = None
    # frames the fill-in left unsent because the burst limit was reached
    digipeat_held: int = 0
    passed: dict[RadioId, PassCount] = field(default_factory=dict)  # by radio heard on


class Watched(Protocol):
    stats: TncStats
    state: Source.State
    confirmed: bool
    profile: Profile
    last_watchdog_action: str
    last_watchdog_at: datetime | None

    def now(self) -> datetime: ...
    def look_begin(self) -> bool: ...
    def look_send(self, data: bytes) -> bool: ...
    def look_enter_kiss(self) -> None: ...
    def look_end(self) -> None: ...
    async def reopen_port(self) -> None: ...
    def went_silent(self, then: str = "") -> None: ...


class EntryAgain:
    """The schedule of KISS entry repeats for a TNC that keeps typing text."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.wait_sec, self.count = ENTRY_AGAIN_SEC, 0

    def due(self, loop_now: float, settled_at: float) -> bool:
        return loop_now >= settled_at + self.wait_sec

    def repeat(self) -> tuple[str, int]:
        self.count += 1
        self.wait_sec = min(self.wait_sec * 2, ENTRY_AGAIN_MAX_SEC)
        return f"the TNC is still in command mode (entry {self.count + 1}; the next not before {self.wait_sec:g} s after this one settles)", logging.INFO if self.count == 1 else logging.DEBUG


def how_long(seconds: float) -> str:
    return f"{round(seconds / 60, 1):g} min" if seconds >= 60 else f"{round(seconds, 1):g} s"


class Watchdog:
    def __init__(self, tnc: Watched, sec: float, pause_sec: float = CHECK_PAUSE_SEC, reply_sec: float = REPLY_SEC, answer_sec: float = ANSWER_SEC, probe_sec: float = PROBE_SEC) -> None:
        self.tnc = tnc
        # the quiet period that makes a check; 0: no checks (a silent radio is still probed)
        self.sec = sec
        self.pause_sec, self.reply_sec, self.answer_sec, self.probe_sec = pause_sec, reply_sec, answer_sec, probe_sec
        self.probes = 0
        self._heard_at = 0.0  # loop time of the latest byte (or of the open)
        self._extra = 0.0  # random part of the quiet period (TNC_CHECK_JITTER)

    def heard(self) -> None:
        self.probes = 0
        self._restart()

    def opened(self) -> None:
        self._restart()

    @property
    def quiet_sec(self) -> float:
        return self.sec + self._extra

    def _restart(self) -> None:
        self._heard_at = asyncio.get_running_loop().time()
        self._extra = random.uniform(0.0, TNC_CHECK_JITTER) * self.sec  # noqa: S311  (the random part of a waiting time, no secret)

    async def run(self, alive: Callable[[], bool], check_first: bool = False) -> None:
        """Wait and look while `alive()`; `check_first` checks a fresh line at once.

        Return when checks are off and the radio is not silent.
        """
        loop = asyncio.get_running_loop()
        if check_first and alive() and not self.tnc.confirmed and self.tnc.state is Source.State.CONNECTED:
            await self._look("check", alive)
        while alive():
            if self.tnc.state is Source.State.SILENT:
                await asyncio.sleep(self.probe_sec)
                if alive() and self.tnc.state is Source.State.SILENT:
                    await self._look("probe", alive)
            elif self.sec > 0:
                if (left := self._heard_at + self.quiet_sec - loop.time()) > 0:
                    await asyncio.sleep(left)
                elif self.tnc.state is Source.State.CONNECTED:
                    await self._look("check", alive)
                else:
                    await asyncio.sleep(self.sec)
            else:
                return

    async def _look(self, action: str, alive: Callable[[], bool]) -> None:
        tnc = self.tnc
        if action == "check":
            tnc.stats.keepalive_checks += 1
        else:
            tnc.stats.watchdog_probes += 1
            self.probes += 1
        self._did(action)
        if await self._find_radio(alive):
            log.debug("tnc: the radio answers the %s", action)
        elif action == "check":
            tnc.went_silent(f"; probing every {how_long(self.probe_sec)}")
        elif self.probes % REOPEN_EVERY == 0:
            self._did("reopen")
            tnc.stats.port_reopens += 1
            await tnc.reopen_port()

    async def _find_radio(self, alive: Callable[[], bool]) -> bool:
        """Run the check sequence; return True if any byte came, or the line went away."""
        tnc = self.tnc
        heard = tnc.stats.bytes_in
        if not tnc.look_begin():
            return True
        try:
            if (exit_kiss := tnc.profile.exit_kiss) is not None and not tnc.look_send(exit_kiss):
                return True
            await asyncio.sleep(self.pause_sec)
            if not alive() or not tnc.look_send(PROMPT):
                return True
            await self._wait_for_byte(heard, self.reply_sec)
            if not alive():
                return True
            tnc.look_enter_kiss()
            await self._wait_for_byte(heard, self.answer_sec)
            return tnc.stats.bytes_in > heard or not alive()
        finally:
            tnc.look_end()

    async def _wait_for_byte(self, heard: int, limit_sec: float) -> None:
        loop = asyncio.get_running_loop()
        end = loop.time() + limit_sec
        while self.tnc.stats.bytes_in <= heard and loop.time() < end:
            await asyncio.sleep(min(0.02, max(0.0, end - loop.time())))

    def _did(self, action: str) -> None:
        self.tnc.last_watchdog_action, self.tnc.last_watchdog_at = action, self.tnc.now()
        log.debug("tnc: keep-alive %s", action)
