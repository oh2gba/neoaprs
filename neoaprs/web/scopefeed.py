"""The pages that have the HF radio's scope open (`hf_scope`, neoaprs/web/tncwire.py): each is sent the rows of the waterfall the modem part makes (neoaprs/mercuryscoping.py) while it asks. A row is a binary frame (neoaprs/mercuryscope.py
`row_frame`); a page whose socket holds more than the hub's `BEHIND` of what it has not read is sent no row, which it would only add to the wait. A page that leaves is forgotten.

The hand-over is decided here and nowhere else: a page that begins to look is sent the rows the modem part keeps (`history_frame`, the last two minutes, each with its age), and from then on every row with a higher number than the
newest it was sent or passed over, in order, so that no row comes twice and none is lost between the two, whatever arrives while the history is being written. A page that is behind when it asks is sent no history (its own picture
stays), only the rows that come once it has read. When the modem part forgets what it kept, every page that looks is sent an empty history and forgets it too (a page that is behind
as soon as it has read, before any row), and a page that looks again after that is sent all of them.

A page that looks again on the same socket (it was on another tab) holds what it was sent before: while the modem part still keeps the newest row it was sent and the one before it, it is sent the rows from those two on (by
which it finds where they go on) instead of all of them again. Every history carries the daemon's clock, by which the page places the times the daemon writes.

A radio's scope asked for by radio (`radio_scope`) is a feed of that radio's modem (`RadioScopes`): radio 2's modem of the process (the HF radio of before) in today's frames, the feed `hf_scope` shares, unless the page asks for frames
that name the radio (`named`); every other radio's in frames that name it (`RADIO_KIND`: the kind, the radio's id, then today's frame whole). A feed is made when a page first asks for that radio, and follows that modem's
rows from then on."""
import struct
import time
from collections.abc import Callable

from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import KeptRow, history_frame, row_frame, scope_clock
from neoaprs.radiospec import HF_ID, RadioId

from .hub import BEHIND
from .session import Connection

RADIO_KIND = 3                           # a binary frame of this kind names its radio: RADIO_HEADER, then a frame of the kinds of neoaprs/mercuryscope.py (a row, the rows kept) whole
RADIO_HEADER = struct.Struct("<BI")      # the kind, and the radio's id as a little-endian 32-bit number


def radio_header(radio: RadioId) -> bytes:
    """What a frame of the radio's scope begins with, before today's frame."""
    return RADIO_HEADER.pack(RADIO_KIND, radio)


def parse_radio_frame(frame: bytes) -> tuple[RadioId, bytes] | None:
    """The radio's id and today's frame inside a frame that names its radio, or None for a frame of another kind (for the tests; the page has its own)."""
    if len(frame) <= RADIO_HEADER.size or frame[0] != RADIO_KIND:
        return None
    return RADIO_HEADER.unpack_from(frame)[1], frame[RADIO_HEADER.size:]


class ScopeFeed:
    def __init__(self, modem: Mercury, header: bytes = b"") -> None:
        self._modem = modem
        self._header = header                            # what each frame begins with: nothing for today's frames, `radio_header` for frames that name their radio
        self._pages: dict[Connection, int] = {}          # each page that looks, and the number of the newest row it was sent or passed over
        self._sent: dict[Connection, int] = {}           # each page that was sent a row, and the number of the newest it was sent (it holds it), while it is on its socket
        self._stale: set[Connection] = set()             # the pages that look and were behind when the rows kept were forgotten: they are told before their next row

    @property
    def pages(self) -> int:
        return len(self._pages)

    def follows(self, modem: object) -> bool:
        """Whether this feed's rows are of that modem (`radio_scope` names a radio: the rows a page is sent are those of radio 2's modem, which the binary frames do not name)."""
        return modem is self._modem

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
    """The feeds of the radios' scopes asked for by radio (`radio_scope`): `hf`, radio 2's modem of the process in today's frames, and one feed in frames that name the radio for each other radio a page asked for (and for
    radio 2 asked for so), each connected to its modem's rows while it is kept: `wire` connects a feed to its modem's signals, or lets go of them (neoaprs/web/topics.py, which connects)."""

    def __init__(self, hf: ScopeFeed, wire: Callable[[ScopeFeed, Mercury, bool], None]) -> None:
        self.hf = hf
        self._wire = wire
        self._feeds: dict[RadioId, tuple[ScopeFeed, Mercury]] = {}

    def feed(self, radio: RadioId, modem: Mercury, named: bool) -> ScopeFeed:
        """The feed of the radio's modem: today's for the modem `hf` follows, unless the frames are to name it; else the radio's own, made now (again when the radio's modem is another one)."""
        if not named and self.hf.follows(modem):
            return self.hf
        held = self._feeds.get(radio)
        if held is None or held[1] is not modem:
            self._drop(radio)
            feed = ScopeFeed(modem, radio_header(radio))
            self._wire(feed, modem, True)
            held = self._feeds[radio] = (feed, modem)
        return held[0]

    def stop(self, conn: Connection, radio: RadioId, named: bool) -> None:
        """This page wants no more of the radio's rows, in the frames it asked for (today's for radio 2 unless `named`); a radio that is none any more stops all the same."""
        if not named and radio == HF_ID:                                 # (radio 2 has the modem of the process, which `hf` follows)
            self.hf.ask(conn, False)
        elif (held := self._feeds.get(radio)) is not None:
            held[0].ask(conn, False)

    def forget(self, conn: Connection) -> None:
        """The page left: every feed forgets it (`hf` is forgotten by its owner, as before)."""
        for feed, _ in self._feeds.values():
            feed.forget(conn)

    def pages(self, radio: RadioId) -> int:
        """How many pages look at the radio's rows in frames that name it."""
        held = self._feeds.get(radio)
        return 0 if held is None else held[0].pages

    def _drop(self, radio: RadioId) -> None:
        held = self._feeds.pop(radio, None)
        if held is not None:
            self._wire(*held, False)

    def disconnect(self) -> None:
        """The pages are told nothing more: every feed of a radio is let go."""
        for radio in list(self._feeds):
            self._drop(radio)
