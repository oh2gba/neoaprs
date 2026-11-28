"""The serial line of the Tnc: a port that reports bytes and its death by plain callbacks.

Also `Modem`, what the Tnc asks of the modem program behind its line, when there is one.
"""

from typing import Protocol

from .callbackport import CallbackPort
from .reading import Reading


class Modem(Protocol):
    """What the Tnc asks of the modem program behind its line (the Mercury modem).

    `starting`: a refused line is no fault yet; `hold`: why no frame may go now; `reason`: why it waits,
    a code; `test`: the tune tone or the keying test that has the radio; `deaf`: it runs and hears nothing;
    `refuses_line`: why the line may not be opened now (the program on its port is not the modem's);
    `frame_hold`: why no frame may go now, the modem not running included, the one question of the frame path;
    `rig_problem`: `rig_silent` or `rig_keyed_long` for a radio keyed through a rig program, else "".
    """

    @property
    def problem(self) -> str: ...
    @property
    def deaf(self) -> bool: ...
    @property
    def rig_problem(self) -> str: ...
    @property
    def state(self) -> str: ...
    @property
    def reason(self) -> str: ...
    @property
    def test(self) -> str: ...
    def take_reading(self) -> Reading: ...
    def hold(self) -> str: ...
    def refuses_line(self) -> str: ...
    def frame_hold(self) -> str: ...
    def starting(self) -> bool: ...
    def describe(self) -> str: ...
    def play(self, data: bytes) -> None: ...


class TncPort(CallbackPort):
    """The Tnc's line: a port that reports its bytes and its death to the Tnc."""

    def fail(self, reason: str) -> None:
        """Treat a failed write as a lost line, like a failed read."""
        if self.is_open:
            self._lost(reason)
