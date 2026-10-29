"""The adapter the Tnc follows: where the radio is not looked for among the ports (Windows, macOS), the radio is the port that was named, and a USB adapter that is pulled out and plugged in again may come back as another
COM port (or another /dev/cu device). The Tnc remembers which adapter the named port was (`serialprobe.identity_of`) and, when the port cannot be opened and is no longer listed, opens the port the adapter is on now
(`serialprobe.moved_to`: its serial number, or its vendor and product ids when it is the only one). It is the operator's to choose when that is not clear: the memory belongs to the port it was learnt for, and a port
the operator names instead is not the adapter's. A socket and a Bluetooth port have no adapter. On Linux the search for the radio does this.

The memory is made after the line is open and handed to the Tnc, in a task of the Tnc (`remember`): the system's list of ports is read in a thread and can take a while, and nothing may be awaited while a port that is
open belongs to no one."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from . import serialprobe
from .serialport import SerialError, is_socket

log = logging.getLogger("neoaprs.tnc")
Port = TypeVar("Port")


def has_adapter(path: str) -> bool:
    """Whether the port can be a USB adapter: a TCP socket and a Bluetooth port are none."""
    return not is_socket(path)


class AdapterFollow:
    def __init__(self) -> None:
        self._adapter: serialprobe.AdapterId | None = None
        self._learnt_for: tuple[str, ...] = ()                           # the paths the adapter was found at: the one that was named and the one that opened

    def following(self, path: str, named: bool) -> bool:
        """Whether the adapter behind this port is followed: a port that was named, where the radio is not searched for, that can be an adapter."""
        return named and not serialprobe.can_search() and has_adapter(path)

    def _remembered(self, path: str) -> serialprobe.AdapterId | None:
        return self._adapter if path in self._learnt_for else None

    def knows(self, path: str) -> bool:
        """Whether the adapter behind the port has been learnt (the memory is made a moment after the port opens)."""
        return self._remembered(path) is not None

    async def open(self, path: str, named: bool, opener: Callable[[str], Awaitable[Port]], note: Callable[[str], None]) -> tuple[Port, str]:
        """`opener(path)`; for a named adapter that cannot be opened and is at another port now, `opener` of that port. The port opened, and its path. Raises SerialError. Nothing is awaited once a port is open."""
        try:
            return await opener(path), path
        except SerialError:
            moved = await asyncio.to_thread(serialprobe.moved_to, self._remembered(path), path) if self.following(path, named) else None
            if moved is None:
                raise
        note(f"{path} is gone; the adapter is on {moved}")
        log.warning("tnc: %s is gone; the adapter is on %s", path, moved)
        return await opener(moved), moved

    async def remember(self, asked: str, where: str) -> None:
        """The adapter behind `where`, the port that opened for the named `asked`, kept for the next time the named port cannot be opened (the system's list is read in a thread)."""
        adapter = await asyncio.to_thread(serialprobe.identity_of, where)
        self._adapter, self._learnt_for = adapter, (asked, where)
