"""Send a radio's waterfall rows to the pages that have its scope open, as binary frames.

A page gets the kept rows of the seconds it asks for first, then every newer row; a page more than
`BEHIND` bytes behind is skipped. Frames name the radio: `RADIO_KIND`, the radio id, then the mercuryscope.py frame.
"""

import struct
import time
from collections.abc import Callable, Mapping

from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import HISTORY_SEC, KeptRow, history_frame, row_frame, scope_clock
from neoaprs.radiospec import RadioId

from .hub import BEHIND
from .session import Connection

RADIO_KIND = 3
# The kind, then the radio's id as a little-endian 32-bit number.
RADIO_HEADER = struct.Struct("<BI")


def radio_header(radio: RadioId) -> bytes:
    """Return the bytes that start a scope frame of the radio."""
    return RADIO_HEADER.pack(RADIO_KIND, radio)


def parse_radio_frame(frame: bytes) -> tuple[RadioId, bytes] | None:
    """Return (radio id, inner frame) of a radio frame, or None for another kind."""
    if len(frame) <= RADIO_HEADER.size or frame[0] != RADIO_KIND:
        return None
    return RADIO_HEADER.unpack_from(frame)[1], frame[RADIO_HEADER.size :]


class ScopeFeed:
    def __init__(self, modem: Mercury, header: bytes = b"") -> None:
        self._modem = modem
        self._header = header  # `radio_header` of the feed's radio
        self._pages: dict[Connection, int] = {}  # page -> newest row number sent or passed over
        self._sent: dict[Connection, int] = {}  # page -> newest row number it was sent and still holds
        self._stale: set[Connection] = set()
        self._reach: dict[Connection, float] = {}  # page -> the seconds of its last history
        self._owed: dict[Connection, float] = {}  # page -> the seconds of a history it was too far behind for

    @property
    def pages(self) -> int:
        return len(self._pages)

    def ask(self, conn: Connection, on: bool, seconds: float = HISTORY_SEC) -> None:
        """Start or stop sending rows to the page, the first of the last `seconds`; a page that already closed is
        ignored."""
        if not on:
            self._pages.pop(conn, None)
        elif not conn.closed:
            self._hand_over(conn, seconds)

    def forget(self, conn: Connection) -> None:
        self._pages.pop(conn, None)
        self._sent.pop(conn, None)
        self._stale.discard(conn)
        self._reach.pop(conn, None)
        self._owed.pop(conn, None)

    def _hand_over(self, conn: Connection, seconds: float) -> None:
        history, now = self._modem.scope_history, scope_clock()
        kept = history.after(0, now, seconds)
        self._pages[conn] = kept[-1].seq if kept else history.last
        if conn.buffered() <= BEHIND:
            self._stale.discard(conn)
            held = self._sent.get(conn)
            if held is not None and seconds <= self._reach.get(conn, 0) and kept and kept[0].seq < held <= kept[-1].seq:
                # Resend from the row before `held` so the page can find where they join.
                kept = kept[held - 1 - kept[0].seq :]
            self._reach[conn] = seconds
            self._owed.pop(conn, None)
            self._send_history(conn, kept, now)
        else:
            self._owed[conn] = seconds
        self._catch_up(conn)

    def row(self, kept: KeptRow) -> None:
        for conn in list(self._pages):
            self._catch_up(conn)

    def _catch_up(self, conn: Connection) -> None:
        """Send the page the kept rows newer than it holds; a stale page first gets an empty history, and
        one that was too far behind for the history it asked for gets it now."""
        if conn in self._owed and conn in self._pages and conn.buffered() <= BEHIND:
            self._hand_over(conn, self._owed.pop(conn))
            return
        while conn in self._pages and (newer := self._modem.scope_history.after(self._pages[conn], scope_clock())):
            self._pages[conn] = newer[0].seq
            if conn.buffered() <= BEHIND:
                if conn in self._stale:
                    self._stale.discard(conn)
                    self._send_history(conn, [], scope_clock())
                self._sent[conn] = newer[0].seq
                conn.send_binary(self._header + row_frame(newer[0].row))

    def cleared(self) -> None:
        """Handle the modem forgetting its rows: send an empty history, or mark a late page stale."""
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
        conn.send_binary(self._header + history_frame(rows, now, time.time() * 1000))


class RadioScopes:
    """One scope feed per radio that a page asked for."""

    def __init__(self, wire: Callable[[ScopeFeed, Mercury, bool], None]) -> None:
        self._wire = wire
        self._feeds: dict[RadioId, tuple[ScopeFeed, Mercury]] = {}

    def feed(self, radio: RadioId, modem: Mercury) -> ScopeFeed:
        """Return the radio's feed, made again if the modem changed."""
        held = self._feeds.get(radio)
        if held is None or held[1] is not modem:
            self._drop(radio)
            feed = ScopeFeed(modem, radio_header(radio))
            self._wire(feed, modem, True)
            held = self._feeds[radio] = (feed, modem)
        return held[0]

    def stop(self, conn: Connection, radio: RadioId) -> None:
        if (held := self._feeds.get(radio)) is not None:
            held[0].ask(conn, False)

    def forget(self, conn: Connection) -> None:
        for feed, _ in self._feeds.values():
            feed.forget(conn)

    def pages(self, radio: RadioId) -> int:
        held = self._feeds.get(radio)
        return 0 if held is None else held[0].pages

    def keep(self, modems: Mapping[RadioId, Mercury]) -> None:
        """Keep only the feeds of the given modems."""
        for radio, (_, modem) in list(self._feeds.items()):
            if modems.get(radio) is not modem:
                self._drop(radio)

    def _drop(self, radio: RadioId) -> None:
        held = self._feeds.pop(radio, None)
        if held is not None:
            self._wire(*held, False)

    def disconnect(self) -> None:
        """Release every feed."""
        for radio in list(self._feeds):
            self._drop(radio)
