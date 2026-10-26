"""The serial line of the Tnc (tnc.py): a port that hands its bytes and its death to the Tnc that owns it by plain callbacks, not signals. The Dummy radio's line (dummyline.py) is another one."""
from .callbackport import CallbackPort


class TncPort(CallbackPort):
    """The Tnc's line: a port that tells the Tnc of its bytes and its death."""

    def fail(self, reason: str) -> None:
        """A write failed: the line counts as lost, like a read that failed."""
        if self.is_open:
            self._lost(reason)
