"""The state of a radio's own modem program (direwolfmodem.py, mercurymodem.py) as the radio's row says it, and whether the program is within its start time.

The state, with why it is not running (`problem`, in English for the log) and the kind of the reason (`reason`, a code for the page), is set in one place, `_set`, which says a change in the log (a warning when
there is a problem) and tells who listens (`changed`). A program that was started a moment ago does not answer on its port yet: the line that connects to it is refused, which is no fault and nothing the
operator can act on, so the line asks `starting()` before it says that it waits (tnc.py). After START_SEC a program that still does not answer is a fault, said as any other."""
import logging
import time

from .signal import Signal

START_SEC = 10.0                                                 # how long a program may take to answer on its port before a line that is refused is a fault worth saying


class ModemState:
    """The state part of a modem: `_set`, and `starting()`. The class says its program's name (PROGRAM), its logger (LOG) and the states in which a start time can be running (STARTING: a program that is
    swapped while its state stays `running` names that one too, and then takes the start time away once the program answers: `_starting_since = 0.0`)."""
    PROGRAM = ""
    LOG = logging.getLogger("neoaprs")
    STARTING: tuple[str, ...] = ("starting",)
    state: str
    problem: str
    reason: str
    changed: Signal[[]]
    _starting_since = 0.0                                            # when the program was started last (the monotonic clock); 0: no start time is running

    def starting(self) -> bool:
        """The program was started (or swapped) less than START_SEC ago and does not answer yet: a line refused now is no fault."""
        return self.state in self.STARTING and self._starting_since > 0 and time.monotonic() - self._starting_since < START_SEC

    def _set(self, state: str, problem: str, reason: str = "") -> None:
        if (state, problem, reason) != (self.state, self.problem, self.reason):
            if state == "starting" and self.state != "starting":
                self._starting_since = time.monotonic()
            self.state, self.problem, self.reason = state, problem, reason
            self.LOG.log(logging.WARNING if problem else logging.INFO, "%s: %s%s", self.PROGRAM, state, f": {problem}" if problem else "")
        self.changed.emit()
