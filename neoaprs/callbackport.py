"""A serial port that hands its bytes and its death to the feed that owns it by plain callbacks, not signals: the base of the Tnc's line (tncport.py) and of the GPS receiver's (gpsfeed.py). Each callback is given the port itself, so that
a feed that has opened another since can tell a late call of the old one."""
from collections.abc import Callable
from typing import Self, cast

from .serialport import SerialPort


class CallbackPort(SerialPort):
    _on_data: Callable[[Self, bytes], None]
    _on_lost: Callable[[Self, str], None]

    def __init__(self, path: str, baud: int, on_data: Callable[[Self, bytes], None], on_lost: Callable[[Self, str], None]) -> None:
        super().__init__(path, baud)
        self._on_data = on_data
        self._on_lost = on_lost

    def _deliver(self, chunk: bytes) -> None:
        self._on_data(cast(Self, self), chunk)

    def _lost(self, reason: str) -> None:
        super()._lost(reason)
        self._on_lost(cast(Self, self), reason)
