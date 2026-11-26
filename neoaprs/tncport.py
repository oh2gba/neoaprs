"""The serial line of the Tnc: a port that reports bytes and its death by plain callbacks.

Also `Modem`, what the Tnc asks of the modem program behind its line, when there is one.
"""

from typing import Protocol

from .callbackport import CallbackPort
from .reading import Reading


class Modem(Protocol):
    """What the Tnc asks of the modem program behind its line (the Mercury modem).

    `starting`: a refused line is no fault yet; `hold`: why no frame may go now; `reason`: why it waits,
    a code; `test`: the tune tone or the keying test that has the radio.
    """

    @property
    def problem(self) -> str: ...
    @property
    def state(self) -> str: ...
    @property
    def reason(self) -> str: ...
    @property
    def test(self) -> str: ...
    def take_reading(self) -> Reading: ...
    def hold(self) -> str: ...
    def starting(self) -> bool: ...
    def describe(self) -> str: ...
    def play(self, data: bytes) -> None: ...


class TncPort(CallbackPort):
    """The Tnc's line: a port that reports its bytes and its death to the Tnc."""

    def fail(self, reason: str) -> None:
        """Treat a failed write as a lost line, like a failed read."""
        if self.is_open:
            self._lost(reason)
