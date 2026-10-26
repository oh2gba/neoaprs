"""The serial line of the Tnc (tnc.py): a port that hands its bytes and its death to the Tnc that owns it by plain callbacks, not signals. The Dummy radio's line (dummyline.py) is another one."""
from collections.abc import Callable

from .serialport import SerialPort


class TncPort(SerialPort):
    """A serial port that hands its bytes and its death to the Tnc that owns it by plain callbacks, not signals."""

    def __init__(self, path: str, baud: int, on_data: Callable[["TncPort", bytes], None], on_lost: Callable[["TncPort", str], None]) -> None:
        super().__init__(path, baud)
        self._on_data = on_data
        self._on_lost = on_lost

    def _deliver(self, chunk: bytes) -> None:
        self._on_data(self, chunk)

    def _lost(self, reason: str) -> None:
        super()._lost(reason)
        self._on_lost(self, reason)

    def fail(self, reason: str) -> None:
        """A write failed: the line counts as lost, like a read that failed."""
        if self.is_open:
            self._lost(reason)
