"""The pages that have the HF radio's scope open (`hf_scope`, neoaprs/web/tncwire.py): each is sent the rows of the waterfall the modem part makes (neoaprs/mercuryscoping.py) while it asks. A row is a binary frame (neoaprs/mercuryscope.py
`row_frame`); a page whose socket holds more than the hub's `BEHIND` of what it has not read is sent no row, which it would only add to the wait. A page that leaves is forgotten.

The hand-over is decided here and nowhere else: a page that begins to look is sent the rows the modem part keeps (`history_frame`, the last two minutes, each with its age), and from then on every row with a higher number than the
newest it was sent or passed over, in order, so that no row comes twice and none is lost between the two, whatever arrives while the history is being written. A page that is behind when it asks is sent no history (its own picture
stays), only the rows that come once it has read. When the modem part forgets what it kept, every page that looks is sent an empty history and forgets it too (a page that is behind
as soon as it has read, before any row), and a page that looks again after that is sent all of them.

A page that looks again on the same socket (it was on another tab) holds what it was sent before: while the modem part still keeps the newest row it was sent and the one before it, it is sent the rows from those two on (by
which it finds where they go on) instead of all of them again. Every history carries the daemon's clock, by which the page places the times the daemon writes."""
import time

from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import KeptRow, history_frame, row_frame, scope_clock

from .hub import BEHIND
from .session import Connection


class ScopeFeed:
    def __init__(self, modem: Mercury) -> None:
        self._modem = modem
        self._pages: dict[Connection, int] = {}          # each page that looks, and the number of the newest row it was sent or passed over
        self._sent: dict[Connection, int] = {}           # each page that was sent a row, and the number of the newest it was sent (it holds it), while it is on its socket
        self._stale: set[Connection] = set()             # the pages that look and were behind when the rows kept were forgotten: they are told before their next row

    @property
    def pages(self) -> int:
        return len(self._pages)

    def ask(self, conn: Connection, on: bool) -> None:
        """This page wants the rows (or no more of them). A page that has left meanwhile is not taken (its command ran after it closed: the command is a task, and the close came in the same read)."""
        if not on:
            self._pages.pop(conn, None)
        elif not conn.closed:
            self._hand_over(conn)

    def forget(self, conn: Connection) -> None:
        """The page left."""
        self._pages.pop(conn, None)
        self._sent.pop(conn, None)
        self._stale.discard(conn)

    def _hand_over(self, conn: Connection) -> None:
        history, now = self._modem.scope_history, scope_clock()
        kept = history.after(0, now)
        self._pages[conn] = kept[-1].seq if kept else history.last
        if conn.buffered() <= BEHIND:
            self._stale.discard(conn)
            held = self._sent.get(conn)
            if held is not None and kept and kept[0].seq < held <= kept[-1].seq:
                kept = kept[held - 1 - kept[0].seq:]       # (the page holds the rows up to its newest: from the one before that on, which it finds them by)
            self._send_history(conn, kept, now)
        self._catch_up(conn)

    def row(self, kept: KeptRow) -> None:
        """A row of the waterfall of the modem part (kept before it is told), sent to every page that asked and is not behind."""
        for conn in list(self._pages):
            self._catch_up(conn)

    def _catch_up(self, conn: Connection) -> None:
        """The rows kept that are newer than what this page was sent, one at a time and the number moved on before each is written: a row that arrives while one is written is sent by the call it makes, and found sent here.
        A page that was behind when the rows kept were forgotten is told so first."""
        while conn in self._pages and (newer := self._modem.scope_history.after(self._pages[conn], scope_clock())):
            self._pages[conn] = newer[0].seq
            if conn.buffered() <= BEHIND:
                if conn in self._stale:
                    self._stale.discard(conn)
                    self._send_history(conn, [], scope_clock())
                self._sent[conn] = newer[0].seq
                conn.send_binary(row_frame(newer[0].row))

    def cleared(self) -> None:
        """The modem part forgot the rows it kept: each page that looks forgets them too (an empty history), a page that is behind as soon as it has read; a page that does not look now holds none of the rows kept."""
        self._sent.clear()
        now = scope_clock()
        for conn in list(self._pages):
            if conn.buffered() <= BEHIND:
                self._send_history(conn, [], now)
            else:
                self._stale.add(conn)

    def _send_history(self, conn: Connection, rows: list[KeptRow], now: float) -> None:
        if rows:
            self._sent[conn] = rows[-1].seq
        else:
            self._sent.pop(conn, None)
        conn.send_binary(history_frame(rows, now, time.time() * 1000))
