"""Follow a USB serial adapter that comes back as another port after being replugged.

The Tnc remembers the adapter behind the named port and, if that port is gone, opens the port the
adapter is on now (Linux searches instead). The memory is made in a task after the open.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from . import serialprobe
from .serialport import SerialError, is_socket

log = logging.getLogger("neoaprs.tnc")
Port = TypeVar("Port")


def has_adapter(path: str) -> bool:
    """Return True if the port can be a USB adapter; TCP sockets and Bluetooth ports cannot."""
    return not is_socket(path)


class AdapterFollow:
    def __init__(self, label: Callable[[], str] = lambda: "tnc") -> None:
        self._label = label
        self._adapter: serialprobe.AdapterId | None = None
        # the named path and the one that opened; a port named instead is not the adapter's
        self._learnt_for: tuple[str, ...] = ()

    def following(self, path: str, named: bool) -> bool:
        return named and not serialprobe.can_search() and has_adapter(path)

    def _remembered(self, path: str) -> serialprobe.AdapterId | None:
        return self._adapter if path in self._learnt_for else None

    def knows(self, path: str) -> bool:
        return self._remembered(path) is not None

    async def open(
        self,
        path: str,
        named: bool,
        opener: Callable[[str], Awaitable[Port]],
        note: Callable[[str], None],
        taken: Callable[[str], str] = lambda path: "",
    ) -> tuple[Port, str]:
        """Open `path`, or the adapter's new port if that fails; return the port and its path.

        A new port that is another radio's (`taken` says why) is left alone. Raise SerialError.
        """
        try:
            return await opener(path), path
        except SerialError:
            moved = (
                await asyncio.to_thread(serialprobe.moved_to, self._remembered(path), path)
                if self.following(path, named)
                else None
            )
            if moved is None:
                raise
            if why := taken(moved):
                log.info(
                    "%s: %s is gone; an adapter like it is on %s, which is left alone: %s",
                    self._label(),
                    path,
                    moved,
                    why,
                )
                raise
        note(f"{path} is gone; the adapter is on {moved}")
        log.warning("%s: %s is gone; the adapter is on %s", self._label(), path, moved)
        return await opener(moved), moved

    async def remember(self, asked: str, where: str) -> None:
        """Keep the identity of the adapter behind `where`, which opened for the named `asked`."""
        adapter = await asyncio.to_thread(serialprobe.identity_of, where)
        self._adapter, self._learnt_for = adapter, (asked, where)
