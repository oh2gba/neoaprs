"""The pages that have a radio's scope open (`radio_scope`, neoaprs/web/radiowire.py): each is sent the rows of the waterfall the modem part makes (neoaprs/mercuryscoping.py) while it asks. A row is a binary frame (neoaprs/mercuryscope.py
`row_frame`); a page whose socket holds more than the hub's `BEHIND` of what it has not read is sent no row, which it would only add to the wait. A page that leaves is forgotten.

The hand-over is decided here and nowhere else: a page that begins to look is sent the rows the modem part keeps (`history_frame`, the last two minutes, each with its age), and from then on every row with a higher number than the
newest it was sent or passed over, in order, so that no row comes twice and none is lost between the two, whatever arrives while the history is being written. A page that is behind when it asks is sent no history (its own picture
stays), only the rows that come once it has read. When the modem part forgets what it kept, every page that looks is sent an empty history and forgets it too (a page that is behind
as soon as it has read, before any row), and a page that looks again after that is sent all of them.

A page that looks again on the same socket (it was on another tab) holds what it was sent before: while the modem part still keeps the newest row it was sent and the one before it, it is sent the rows from those two on (by
which it finds where they go on) instead of all of them again. Every history carries the daemon's clock, by which the page places the times the daemon writes.

Each radio's scope is a feed of that radio's modem (`RadioScopes`), in frames that name the radio (`RADIO_KIND`: the kind, the radio's id, then the frame of neoaprs/mercuryscope.py whole). A feed is made when a
page first asks for that radio, and follows that modem's rows from then on."""
import struct
import time
from collections.abc import Callable, Mapping

from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import KeptRow, history_frame, row_frame, scope_clock
from neoaprs.radiospec import RadioId

from .hub import BEHIND
from .session import Connection

RADIO_KIND = 3                           # a binary frame of this kind names its radio: RADIO_HEADER, then a frame of the kinds of neoaprs/mercuryscope.py (a row, the rows kept) whole
RADIO_HEADER = struct.Struct("<BI")      # the kind, and the radio's id as a little-endian 32-bit number


def radio_header(radio: RadioId) -> bytes:
    """What a frame of the radio's scope begins with, before the frame of neoaprs/mercuryscope.py."""
    return RADIO_HEADER.pack(RADIO_KIND, radio)


def parse_radio_frame(frame: bytes) -> tuple[RadioId, bytes] | None:
    """The radio's id and the frame of neoaprs/mercuryscope.py inside a frame that names its radio, or None for a frame of another kind (for the tests; the page has its own)."""
    if len(frame) <= RADIO_HEADER.size or frame[0] != RADIO_KIND:
        return None
    return RADIO_HEADER.unpack_from(frame)[1], frame[RADIO_HEADER.size:]


class ScopeFeed:
    def __init__(self, modem: Mercury, header: bytes = b"") -> None:
        self._modem = modem
        self._header = header                            # what each frame begins with: `radio_header` of the radio the feed is of
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
                conn.send_binary(self._header + row_frame(newer[0].row))

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
        conn.send_binary(self._header + history_frame(rows, now, time.time() * 1000))


class RadioScopes:
    """The feeds of the radios' scopes (`radio_scope`): one for each radio a page asked for, in frames that name the radio, each connected to its modem's rows while it is kept: `wire` connects a feed to its modem's
    signals, or lets go of them (neoaprs/web/topics.py, which connects)."""

    def __init__(self, wire: Callable[[ScopeFeed, Mercury, bool], None]) -> None:
        self._wire = wire
        self._feeds: dict[RadioId, tuple[ScopeFeed, Mercury]] = {}

    def feed(self, radio: RadioId, modem: Mercury) -> ScopeFeed:
        """The feed of the radio's modem, made now (again when the radio's modem is another one)."""
        held = self._feeds.get(radio)
        if held is None or held[1] is not modem:
            self._drop(radio)
            feed = ScopeFeed(modem, radio_header(radio))
            self._wire(feed, modem, True)
            held = self._feeds[radio] = (feed, modem)
        return held[0]

    def stop(self, conn: Connection, radio: RadioId) -> None:
        """This page wants no more of the radio's rows; a radio that is none any more stops all the same."""
        if (held := self._feeds.get(radio)) is not None:
            held[0].ask(conn, False)

    def forget(self, conn: Connection) -> None:
        """The page left: every feed forgets it."""
        for feed, _ in self._feeds.values():
            feed.forget(conn)

    def pages(self, radio: RadioId) -> int:
        """How many pages look at the radio's rows."""
        held = self._feeds.get(radio)
        return 0 if held is None else held[0].pages

    def keep(self, modems: Mapping[RadioId, Mercury]) -> None:
        """Only the feeds of these radios' modems as they are now are kept: one of a radio removed, or of a modem the radio no longer has, lets go of that modem's signals."""
        for radio, (_, modem) in list(self._feeds.items()):
            if modems.get(radio) is not modem:
                self._drop(radio)

    def _drop(self, radio: RadioId) -> None:
        held = self._feeds.pop(radio, None)
        if held is not None:
            self._wire(*held, False)

    def disconnect(self) -> None:
        """The pages are told nothing more: every feed of a radio is let go."""
        for radio in list(self._feeds):
            self._drop(radio)
