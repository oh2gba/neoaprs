"""The TNC's keep-alive: how the Tnc learns that the radio is there. A TH-D7 that is switched off leaves the USB adapter and its port in place, a TNC in KISS mode sends nothing until it hears a packet, and a
radio that is power-cycled comes back in command mode, so a quiet line is not proof of anything; the radio's absence has to be asked for.

When nothing at all has been heard for `sec` (and a random part of it more, TNC_CHECK_JITTER, so that the checks never keep step with a station that beacons at a fixed rate) the watchdog makes a check (only for a TNC profile that can be asked, tncprofile.py): the profile's KISS exit frame, a pause, a bare carriage return (a TH-D7 that is on answers that with text, "cmd:", within about a second),
then the profile's entry (KISS ON). Any byte in answer means the radio is there, and the clock starts again from the latest byte; the check costs a few seconds of reception, which is why it runs only after a quiet period. A line that was just opened has not shown yet that the radio is there (the Tnc is not `usable`, `confirmed` is False), so its first check is made at once. No
byte at all within `answer_sec` of the carriage return and KISS ON makes the radio silent (`Source.went_silent`): then the same sequence is a probe, made every `probe_sec`, and the first byte that comes,
whatever it is, ends the silence (the Tnc does that, in `_on_data`). Every 5th probe also closes the port and opens it again, for a USB adapter that dropped. Nothing is logged above DEBUG for a check or a probe;
the Tnc says once when the silence begins and once when it ends. The `Tnc` does each action (its `look_*` methods); this module keeps the clock, the count and the words."""
import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .policy import TNC_CHECK_JITTER
from .source import Source, Stats
from .tncprofile import Profile

log = logging.getLogger("neoaprs.tnc")

PROMPT = b"\r"                        # a bare carriage return: a TNC in command mode answers "cmd:"
CHECK_PAUSE_SEC = 0.5                 # between the KISS exit frame and the carriage return
REPLY_SEC = 1.0                       # how long the carriage return is given to be answered before KISS ON is sent anyway
ANSWER_SEC = 2.0                      # how long a check waits for any byte after KISS ON before it calls the radio silent
PROBE_SEC = 30.0                      # how often a silent radio is probed
REOPEN_EVERY = 5                      # every this many probes the port is closed and opened again


@dataclass
class TncStats(Stats):
    keepalive_checks: int = 0
    watchdog_probes: int = 0
    port_reopens: int = 0
    digipeated: int = 0        # frames the fill-in digipeater (services/digipeater.py) sent again


class Watched(Protocol):
    """What the watchdog needs of the Tnc."""
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


def how_long(seconds: float) -> str:
    """"15 min" from a minute on, else "12 s"."""
    return f"{round(seconds / 60, 1):g} min" if seconds >= 60 else f"{round(seconds, 1):g} s"


class Watchdog:
    def __init__(self, tnc: Watched, sec: float, pause_sec: float = CHECK_PAUSE_SEC, reply_sec: float = REPLY_SEC, answer_sec: float = ANSWER_SEC, probe_sec: float = PROBE_SEC) -> None:
        self.tnc = tnc
        self.sec = sec                         # the quiet period that makes a check; 0: no checks (a silent radio is still probed)
        self.pause_sec, self.reply_sec, self.answer_sec, self.probe_sec = pause_sec, reply_sec, answer_sec, probe_sec
        self.probes = 0                        # probes since the latest byte
        self._heard_at = 0.0                   # loop time of the latest byte (or of the open)
        self._extra = 0.0                      # the random part of this quiet period (TNC_CHECK_JITTER)

    def heard(self) -> None:
        """A byte came: the quiet period starts again."""
        self.probes = 0
        self._restart()

    def opened(self) -> None:
        self._restart()

    @property
    def quiet_sec(self) -> float:
        """The quiet period now in force: `sec` and its random part."""
        return self.sec + self._extra

    def _restart(self) -> None:
        self._heard_at = asyncio.get_running_loop().time()
        self._extra = random.uniform(0.0, TNC_CHECK_JITTER) * self.sec

    async def run(self, alive: Callable[[], bool], check_first: bool = False) -> None:
        """Waits and looks while `alive()` (the line this was started for is still the Tnc's). `check_first`: a line that was just opened has not shown yet that the radio is there, so the first check is made at once,
        unless a byte has come by the time this runs. Ends when the checks are off and the radio is not silent."""
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
        """The check sequence: exit frame, pause, carriage return, KISS ON. True when any byte came meanwhile, or when the line went away (which says nothing about the radio)."""
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
