"""The state of a radio's modem program and its start time.

`_set` changes state, `problem` (for the log) and `reason` (a code for the page) in one place.
"""

import logging
import time

from .signal import Signal

# a refused connection is no fault until the program has had this long to start
START_SEC = 10.0


class ModemState:
    """The state part of a modem; a subclass names PROGRAM, LOG and the STARTING states."""

    PROGRAM = ""
    LOG = logging.getLogger("neoaprs")
    STARTING: tuple[str, ...] = ("starting",)
    state: str
    problem: str
    reason: str
    changed: Signal[[]]
    # monotonic time of the last start; 0 when no start time is running
    _starting_since = 0.0

    def starting(self) -> bool:
        """Return whether the program started less than START_SEC ago and does not answer yet."""
        return (
            self.state in self.STARTING
            and self._starting_since > 0
            and time.monotonic() - self._starting_since < START_SEC
        )

    def _set(self, state: str, problem: str, reason: str = "") -> None:
        if (state, problem, reason) != (self.state, self.problem, self.reason):
            if state == "starting" and self.state != "starting":
                self._starting_since = time.monotonic()
            self.state, self.problem, self.reason = state, problem, reason
            self.LOG.log(
                logging.WARNING if problem else logging.INFO,
                "%s: %s%s",
                self.PROGRAM,
                state,
                f": {problem}" if problem else "",
            )
        self.changed.emit()
