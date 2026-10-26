"""The errors that pages report about themselves (`page_error`, neoaprs/web/supportwire.py): each is a warning in the log, the latest 100 are kept for the support bundle, and a page that reports in a flood is held to 20 log lines in a minute, the
rest counted in one line."""
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakKeyDictionary

from neoaprs.clock import Clock, iso, utcnow

from .session import Connection
from .supportwire import PageError

log = logging.getLogger("neoaprs.web")

LOGGED_PER_MINUTE = 20
KEPT = 100
WINDOW_SEC = 60.0
MAX_STACK_LINE = 300


def one_line(text: str, limit: int) -> str:
    """The text on one line, with nothing in it that could pass for a line of the log (the page is not trusted with the log's format), cut to `limit` characters."""
    shown = " ".join("".join(c if c.isprintable() else " " for c in text).split())
    return shown if len(shown) <= limit else shown[:limit - 1] + "…"


@dataclass
class _Window:
    """What one connection has reported in the minute that began at `start`."""
    start: float
    logged: int = 0
    dropped: int = 0
    timer: asyncio.TimerHandle | None = field(default=None, repr=False)


class PageErrors:
    def __init__(self, clock: Clock = utcnow, window_sec: float = WINDOW_SEC) -> None:
        self.clock = clock
        self.window_sec = window_sec                        # the minute (a test makes it short)
        self.kept: deque[dict[str, Any]] = deque(maxlen=KEPT)
        self._windows: WeakKeyDictionary[Connection, _Window] = WeakKeyDictionary()

    def note(self, conn: Connection, report: PageError) -> None:
        now = self.clock()
        at = now.timestamp()
        window = self._windows.get(conn)
        if window is None or at - window.start >= self.window_sec:
            self._close(window)
            window = self._windows[conn] = _Window(at)
        self.kept.append({"received_at": iso(now), "at": report.at, "from": conn.ip, "source": report.source, "build": report.build, "message": report.message, "stack": report.stack})
        if window.logged < LOGGED_PER_MINUTE:
            window.logged += 1
            first = next((line for line in report.stack.splitlines() if line.strip()), "")
            log.warning("page error (%s) on page %s: %s | %s", report.source, one_line(report.build, 64), one_line(report.message, 2000), one_line(first, MAX_STACK_LINE))
            return
        window.dropped += 1
        if window.dropped == 1:
            self._remind(conn, window)

    def _remind(self, conn: Connection, window: _Window) -> None:
        """The line about the reports that were not logged comes when the minute is over, though no other report follows."""
        try:
            left = max(0.0, window.start + self.window_sec - self.clock().timestamp())
            window.timer = asyncio.get_running_loop().call_later(left, self._close, window)
        except RuntimeError:
            pass                                             # (no loop: the next report or the close of the connection says it)

    def _close(self, window: _Window | None) -> None:
        if window is None:
            return
        if window.timer is not None:
            window.timer.cancel()
            window.timer = None
        if window.dropped:
            log.warning("%d more page error%s not logged this minute", window.dropped, "" if window.dropped == 1 else "s")
            window.dropped = 0

    def forget(self, conn: Connection) -> None:
        """The page left: what it was not allowed to log in its last minute is told now."""
        self._close(self._windows.pop(conn, None))

    def stop(self) -> None:
        for conn in list(self._windows):
            self.forget(conn)

    def snapshot(self) -> list[dict[str, Any]]:
        """The kept reports, the newest last."""
        return list(self.kept)
