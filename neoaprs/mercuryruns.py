"""Whether the program on a Mercury radio's ports is the one the daemon started, and how its starts ended.

A mixin of `Mercury`: another program on the ports is never started over nor talked to.
"""

import asyncio
import logging
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from . import childprogram, tcplisten
from .clock import Clock
from .coded import Reason
from .mercury import Keying
from .mercurycontrol import ControlLine
from .mercuryhelper import Program
from .source import MODEM_NOT_RUNNING as NOT_RUNNING

log = logging.getLogger("neoaprs.mercury")

STARTS_KEPT = 10
# Why the state is `waiting`, as a code for the page.
REASONS = (
    "",
    "not_installed",
    "stopped",
    "network",
    "no_port",
    "not_started",
    "sound_card",
    "keying",
    "keying_in_use",
    "keying_missing",
    "ports_taken",
    "receive_stalled",
)
PORTS_TAKEN = "another program is already using Mercury's ports: NeoAPRS does not start a second Mercury beside it"
KEYING_WORDS = {
    "keying_in_use": "the keying port {port} is in use by another program",
    "keying_missing": "the keying port {port} is not there",
    "keying": "Mercury could not set up its keying ({keying})",
}


@dataclass
class StartEnd:
    """One start of the modem: when, whether its control port answered, and the reason it ended with."""

    at: datetime
    ran: bool = False
    ended: str = ""  # a reason code; "" while it is on, or when it was stopped

    def words(self) -> str:
        if self.ended:
            return f"{'ran, then ' if self.ran else ''}failed: {self.ended}"
        return "running" if self.ran else "starting"


def _owner(listener: tcplisten.Listener) -> str:
    if listener.pid is None:
        return ""
    image = childprogram._windows_image(listener.pid) if sys.platform == "win32" else None
    return f" (process {listener.pid}{f', {image}' if image else ''})"


def owners_of(ports: Sequence[int]) -> str:
    """Return what listens on the ports, for the log."""
    return owners_words(tcplisten.listeners(ports))


def owners_words(found: Sequence[tcplisten.Listener]) -> str:
    """Return the listeners for the log: port, address, process and, on Windows, its program."""
    return ", ".join(f"{f.port} on {f.address}{_owner(f)}" for f in found) or "it has gone since"


class Runs:
    clock: Clock
    state: str
    attached: str
    broadcast_port: int
    control_port: int
    keying: Keying
    _program: Program
    _control: ControlLine | None
    _generation: int

    def _stop_run_later(self, name: str) -> None:
        raise NotImplementedError

    def _gone(self, problem: str, reason: str) -> None:
        raise NotImplementedError

    def hold(self) -> str:
        raise NotImplementedError

    def _clear_channel(self) -> None:
        raise NotImplementedError

    def _forget_test(self) -> None:
        raise NotImplementedError

    def _set(self, state: str, problem: str, reason: str = "") -> None:
        raise NotImplementedError

    def _init_runs(self) -> None:
        self.start_log: deque[StartEnd] = deque(maxlen=STARTS_KEPT)
        self._init_failed = False  # this run said it cannot set up its keying

    @property
    def pid(self) -> int | None:
        raise NotImplementedError

    @property
    def engine_ran(self) -> bool:
        """Whether the current start's control port answered: its engine came up."""
        return bool(self.start_log) and self.start_log[-1].ran

    def _start_made(self) -> None:
        self.start_log.append(StartEnd(self.clock()))

    def _start_ran(self) -> None:
        if self.start_log and not self.start_log[-1].ran and not self.start_log[-1].ended:
            self.start_log[-1].ran = True

    def _start_ended(self, reason: str, attempt: bool = False) -> None:
        """Note the reason the current start ended with; `attempt`: one that never ran a program."""
        if attempt:
            self.start_log.append(StartEnd(self.clock(), ended=reason))
        elif self.start_log and not self.start_log[-1].ended:
            self.start_log[-1].ended = reason

    def others_on_ports(self) -> list[tcplisten.Listener]:
        """Return the listeners on the KISS and control ports that are not the program the daemon started."""
        if self.attached:
            return []
        return tcplisten.not_ours((self.broadcast_port, self.control_port), self.pid)

    def frame_hold(self) -> str:
        """Return why the radio takes no frame now: the modem is not running, keyed or the channel is busy; else ""."""
        return NOT_RUNNING if self.state != "running" else self.hold()

    def _keying_failed(self, reason: str, line: str) -> None:
        """Called on the loop when Mercury cannot set up its keying: it then never ends, so it is ended."""
        if self.state == "stopped":
            return
        self._init_failed = True
        problem = KEYING_WORDS[reason].format(port=self.keying.device or self.keying.text, keying=self.keying.text)
        log.warning("Mercury cannot key the radio: %s (%s); it is ended and started again later", problem, line)
        self._stop_run_later("mercury-keying-stop")
        self._gone(problem, reason)

    async def _control_refused(self) -> bool:
        """Asked before each connect of the control line: another program on the ports is not talked to."""
        if not (others := await asyncio.to_thread(self.others_on_ports)):
            return False
        if self._control is not None:
            log.warning("Mercury's control line is not connected: %s; %s", PORTS_TAKEN, owners_words(others))
            self._taken()
        return True

    def _taken(self) -> None:
        """Another program is on the modem's ports: end ours and try again after the back-off."""
        if self._program.running:
            self._stop_run_later("mercury-taken-stop")
        self._gone(PORTS_TAKEN, "ports_taken")

    async def _end_for_good(self, problem: str, reason: str) -> None:
        """End the program and do not start it again until the radio is started anew."""
        self._generation += 1
        control, self._control = self._control, None
        if control is not None:
            await control.stop()
        await asyncio.to_thread(self._program.stop)
        self._clear_channel()
        self._forget_test()
        self._start_ended(reason)
        self._set("waiting", problem, reason)

    def refuses_line(self) -> Reason | str:
        """Return why the radio's KISS line may not be opened now, else "": ours runs on its ports."""
        if self.state != "running":
            return NOT_RUNNING
        if found := self.others_on_ports():
            log.warning("Mercury's KISS line is not opened: %s; %s", PORTS_TAKEN, owners_words(found))
            return NOT_RUNNING
        return ""
