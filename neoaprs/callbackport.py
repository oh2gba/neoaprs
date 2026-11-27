"""A serial port that reports bytes and loss to its owner by plain callbacks, not signals.

It is the base of the Tnc's line (tncport.py) and of the GPS receiver's (gpsfeed.py). Each callback
is given the port itself, so an owner that has opened another port since can tell a late call.
"""

from collections.abc import Callable
from typing import Self, cast

from .serialport import SerialPort


class CallbackPort(SerialPort):
    OWNER_TELLS_LOSS = True  # its owner goes WAITING with the reason, a warning with its name
    _on_data: Callable[[Self, bytes], None]
    _on_lost: Callable[[Self, str], None]
    # told when the first write of an open went through
    on_written: Callable[[Self], None] | None = None

    def __init__(
        self, path: str, baud: int, on_data: Callable[[Self, bytes], None], on_lost: Callable[[Self, str], None]
    ) -> None:
        super().__init__(path, baud)
        self._on_data = on_data
        self._on_lost = on_lost

    def _deliver(self, chunk: bytes) -> None:
        self._on_data(cast(Self, self), chunk)

    def _lost(self, reason: str) -> None:
        super()._lost(reason)
        self._on_lost(cast(Self, self), reason)

    def _written(self) -> None:
        if self.on_written is not None:
            self.on_written(cast(Self, self))
