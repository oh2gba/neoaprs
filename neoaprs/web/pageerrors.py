"""Log and keep the errors pages report (`page_error`).

Each is a warning in the log and the latest 100 are kept for the support bundle. A flooding page is
limited to 20 log lines a minute; the rest are counted in one line.
"""
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
    """Return `text` on one line without control characters, cut to `limit`.

    Pages must not forge log lines.
    """
    shown = " ".join("".join(c if c.isprintable() else " " for c in text).split())
    return shown if len(shown) <= limit else shown[:limit - 1] + "…"


@dataclass
class _Window:
    """Reports of one connection in the window that began at `start`."""
    start: float
    logged: int = 0
    dropped: int = 0
    timer: asyncio.TimerHandle | None = field(default=None, repr=False)


class PageErrors:
    def __init__(self, clock: Clock = utcnow, window_sec: float = WINDOW_SEC) -> None:
        self.clock = clock
        self.window_sec = window_sec
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
        """Log the count of dropped reports when the window ends, even if no report follows."""
        try:
            left = max(0.0, window.start + self.window_sec - self.clock().timestamp())
            window.timer = asyncio.get_running_loop().call_later(left, self._close, window)
        except RuntimeError:
# No loop: the next report or the close of the connection logs the count.
            pass

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
        """Close the page's window and log any dropped count."""
        self._close(self._windows.pop(conn, None))

    def stop(self) -> None:
        for conn in list(self._windows):
            self.forget(conn)

    def snapshot(self) -> list[dict[str, Any]]:
        """Return the kept reports, newest last."""
        return list(self.kept)
