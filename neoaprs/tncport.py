"""The serial line of the Tnc (tnc.py): a port that hands its bytes and its death to the Tnc that owns it by plain callbacks, not signals. The Dummy radio's line (dummyline.py) is another one. And what the Tnc
asks of the modem program behind its line, when there is one (`Modem`)."""
from typing import Protocol

from .callbackport import CallbackPort
from .reading import Reading


class Modem(Protocol):
    """What the Tnc asks of the modem program behind its line when the profile is a modem's (the Mercury HF modem, mercurymodem.py, set by app.py): why the line cannot be opened (the program is not there, it stopped),
    whether the program was started a moment ago and has not answered yet (`starting`: the line refused then is no fault), why no frame is to go now (the modem is transmitting a frame, the channel is busy), its words for the radio's status line and the reading it said of the frame that has just come (`take_reading`,
    neoaprs/reading.py); and, when the profile is the Dummy HF radio's, that it plays the frames the Tnc writes through the computer's speakers (`play`)."""
    @property
    def problem(self) -> str: ...
    def take_reading(self) -> Reading: ...
    def hold(self) -> str: ...
    def starting(self) -> bool: ...
    def describe(self) -> str: ...
    def play(self, data: bytes) -> None: ...


class TncPort(CallbackPort):
    """The Tnc's line: a port that tells the Tnc of its bytes and its death."""

    def fail(self, reason: str) -> None:
        """A write failed: the line counts as lost, like a read that failed."""
        if self.is_open:
            self._lost(reason)
