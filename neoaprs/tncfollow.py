"""The adapter the Tnc follows: where the radio is not looked for among the ports (Windows, macOS), the radio is the port that was named, and a USB adapter that is pulled out and plugged in again may come back as another
COM port (or another /dev/cu device). The Tnc remembers which adapter the named port was (`serialprobe.identity_of`) and, when the port cannot be opened and is no longer listed, opens the port the adapter is on now
(`serialprobe.moved_to`: its serial number, or its vendor and product ids when it is the only one). It is the operator's to choose when that is not clear. On Linux the search for the radio does this."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from . import serialprobe
from .serialport import SerialError

log = logging.getLogger("neoaprs.tnc")
Port = TypeVar("Port")


class AdapterFollow:
    def __init__(self) -> None:
        self._adapter: serialprobe.AdapterId | None = None

    @property
    def active(self) -> bool:
        return not serialprobe.can_search()

    async def open(self, path: str, named: bool, opener: Callable[[str], Awaitable[Port]], note: Callable[[str], None]) -> tuple[Port, str]:
        """`opener(path)`; for a named adapter that cannot be opened and is at another port now, `opener` of that port. The port opened, and its path. Raises SerialError. A named port that opened is the adapter remembered
        (the system's list is read in a thread)."""
        try:
            port, where = await opener(path), path
        except SerialError:
            moved = await asyncio.to_thread(serialprobe.moved_to, self._adapter, path) if named and self.active else None
            if moved is None:
                raise
            note(f"{path} is gone; the adapter is on {moved}")
            log.warning("tnc: %s is gone; the adapter is on %s", path, moved)
            port, where = await opener(moved), moved
        if named and self.active:
            self._adapter = await asyncio.to_thread(serialprobe.identity_of, where)
        return port, where
