"""Send the lines that Send what I hear put on APRS-IS to the pages that look at them, as `igate_sent` messages.

A page that looks is sent the kept lines at once and then each line as it is sent; a page more than the hub's
`BEHIND` bytes behind is skipped and gets the whole list again with the next line.
"""

from collections import deque
from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.igaterules import SentLine

from .hub import BEHIND
from .session import Connection


class Sent(Protocol):
    sent: deque[SentLine]


def sent_row(sent: SentLine) -> dict[str, Any]:
    return {"at": iso(sent.at), "radio": sent.radio, "line": sent.line}


def sent_message(whole: bool, lines: list[SentLine]) -> dict[str, Any]:
    """Return the `igate_sent` message."""
    return {"type": "igate_sent", "whole": whole, "lines": [sent_row(one) for one in lines]}


class IgateLooks:
    def __init__(self, igate: Sent) -> None:
        self._igate = igate
        self._pages: set[Connection] = set()
        self._behind: set[Connection] = set()

    def look(self, conn: Connection, on: bool) -> None:
        """Start or stop a page's look; a page that already closed is ignored."""
        if not on:
            self.forget(conn)
            return
        if conn.closed:
            return
        self._pages.add(conn)
        self._behind.discard(conn)
        conn.send(sent_message(True, list(self._igate.sent)))

    def forget(self, conn: Connection) -> None:
        self._pages.discard(conn)
        self._behind.discard(conn)

    def pages(self) -> int:
        return len(self._pages)

    def told(self, sent: SentLine) -> None:
        """Send the line to every page that looks."""
        for conn in list(self._pages):
            if conn.buffered() > BEHIND:
                self._behind.add(conn)
            elif conn in self._behind:
                self._behind.discard(conn)
                conn.send(sent_message(True, list(self._igate.sent)))
            else:
                conn.send(sent_message(False, [sent]))
