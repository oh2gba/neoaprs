"""The text a TNC or a radio prints of the packets it hears, read as AX.25 frames (aprs-reference/text-monitor-plan.md, section 5.4): a Yaesu FTM on its data port with Output PACKET, a TAPR TNC-2, a
Kantronics KPC-3 or an AEA PK-232 in its own monitor mode, or (`monitor=False`) the one-line TNC2 text of a LoRa board. Each heard packet becomes `ax25.Frame(destination, source, path, UI, F0, information)`,
so that the log, the codec, the SQL and the iGate read it as they read a frame that came in KISS.

`TextReader.feed` takes the bytes as they come, in any pieces, and gives the frames, and the lines that began like a header and are none (`Rejected`, with the reason). What it reads, in this order:

- **7 bits with a parity bit, found by itself.** A TNC-2 or a PK-232 at its factory setting sends 7 data bits and an even parity bit, and a line opened at 8N1 has the same timing: the parity bit arrives as bit 7. So
  every byte of such a TNC has an even (or every one an odd) number of one bits, and about half of them have bit 7 set. Bytes pass straight through until the first one with bit 7 set; from it the bytes wait
  until the line is decided: 8 bits at the first byte that breaks the parity of those before it (plain text does within a few bytes), 7 bits after DECIDE_BYTES bytes that all keep one parity with one of them
  above 0x7F, or when the line goes quiet after DECIDE_QUIET such bytes (after fewer, what waits is forgotten as a piece of a line, and the line stays undecided). Once 7 bits, every byte is masked with 0x7F (a CR comes as 0x8D, so the mask is before the line ends are looked for). The letters
  outside ASCII of such a line are lost in the TNC itself; Mic-E's position bytes are 0x1C to 0x7F and come through.
- **Lines** end at CR, LF, XON or XOFF. An empty line is passed over (a Yaesu puts several line feeds between its two lines). A line longer than `max_line` is dropped, with what follows it up to the next
  line end. A piece of a line is forgotten when `pending_sec` pass with no byte.
- **The header** is ASCII up to the colon that ends it. A leading `cmd:` (the prompt, or a Kenwood's) is taken off as often as it is there. Then: up to two words of a time stamp (the PK-232's
  `22:51:33 ` or `10-Jul-86 22:54:25 `); the addresses, `SRC>DST,DIGI,DIGI*` or the PK-232's chain `SRC*>DIGI*>DST` (more than one `>`, or a star on the source: a TNC2 destination never holds a `>`, and a
  TNC2 source never carries a star); a Yaesu's ` [06/02/18 13:47:54]`; a Kantronics' or a Yaesu's ` <UI>` (`<UI…>`; any other mark is a frame of another kind, passed over), after a colon or not; then the
  colon. The calls are read by the one grammar of TNC2 text (tnc2line.addresses). The digipeaters up to and including the last one with a star are the ones the frame has been through (a TNC-2 marks each
  of them, a Kantronics the last, a PK-232 the one heard); a star on a PK-232's source marks none (the station was heard direct).
- **The information** is the bytes after that colon, as they came. A header with none is held for the next line that is no header (the two-line form of HEADERLN ON and of a Yaesu): that line is its
  information if it comes within `pending_sec`, else the header is dropped; a header that comes meanwhile drops the one held.
- **Passed over:** a line with no `>` before its last colon (`cmd:`, `?EH`, `*** CONNECTED to`, a sign-on banner, an echo, `$GPRMC`, `$PKWDWPL`); it is said at DEBUG in the log. A line that began like a
  header and is none (a mark that is not `<UI…>`, a call that is no call, more than eight digipeaters, curly braces) is a `Rejected`.

What the text cannot say, the frame takes as given: a UI frame with PID F0; the time it came; a CR or LF inside the information ends the line there. `looks_like_text` is the search's: whether some line of
what a port said reads as a frame. Pure code."""
import logging
import re
from dataclasses import dataclass

from . import ax25
from .tnc2line import Tnc2Error, addresses, frame_of

log = logging.getLogger("neoaprs.tnc")

PENDING_SEC = 2.0               # a piece of a line, or a header without its information, is forgotten after this long with no byte (aprx does 2 s)
MAX_LINE = 512                  # a line longer than this is no packet of a TNC: it is dropped, with what follows up to its line end
DECIDE_BYTES = 32               # bytes that all keep one parity, one of them above 0x7F, before the line is taken as 7 bits with a parity bit
DECIDE_QUIET = 12               # the fewest such bytes that decide it when the line goes quiet first; fewer, and the line stays undecided (what waits is forgotten)
_BREAKS = frozenset(b"\r\n\x11\x13")     # what ends a line: CR, LF, XON, XOFF (as tncmode._LINE_BREAKS)
_PROMPT = b"cmd:"
_PART = rb"[0-9A-Za-z-]{1,12}\*?"         # a call as loosely as the header can hold one, its star after it: the call's own rules say why one is none (tnc2line.addresses)
_MONITOR = re.compile(rb"(?:[0-9A-Za-z/.:-]+ +){0,2}?(?P<chain>%s(?:>%s)+)(?P<path>(?:,%s)*)(?: \[[^\]]*\])?(?::? <(?P<mark>[^>]*)>)?:" % (_PART, _PART, _PART))
_UI_MARK = re.compile(rb"UI[^>]*")


@dataclass(frozen=True)
class Rejected:
    """A line that began like a header of a heard packet and is none, with the reason; the line as Latin-1 text."""
    text: str
    reason: str


@dataclass(frozen=True)
class _Head:
    """A header whose information is the next line."""
    destination: ax25.Address
    source: ax25.Address
    path: tuple[ax25.Address, ...]
    at: float


class _NotAFrame(ValueError):
    pass


def _head_of(match: re.Match[bytes]) -> tuple[ax25.Address, ax25.Address, tuple[ax25.Address, ...]]:
    """The destination, the source and the path of a header; _NotAFrame with the reason."""
    mark = match.group("mark")
    if mark is not None and _UI_MARK.fullmatch(mark) is None:
        raise _NotAFrame(f"a frame of another kind (<{mark.decode('latin-1')}>), not a UI frame")
    parts, digis = match.group("chain").split(b">"), [p for p in match.group("path").split(b",") if p]
    chain = len(parts) > 2 or parts[0].endswith(b"*")
    if chain and digis:
        raise _NotAFrame("a header with both a chain of '>' and a path of ','")
    try:
        if chain:
            [source], [destination], via = addresses([parts[0].rstrip(b"*")]), addresses([parts[-1]]), addresses(parts[1:-1])
        else:
            [source, destination], via = addresses(parts), addresses(digis)
    except Tnc2Error as error:
        raise _NotAFrame(str(error)) from None
    if source.repeated or destination.repeated:
        raise _NotAFrame("only a digipeater can be marked as repeated")
    if len(via) > ax25.MAX_PATH:
        raise _NotAFrame(f"a path has at most {ax25.MAX_PATH} digipeaters, not {len(via)}")
    last = max((i for i, d in enumerate(via) if d.repeated), default=-1)
    return destination, source, tuple(ax25.Address(d.call, d.ssid, i <= last) for i, d in enumerate(via))


def _looks_like_header(text: bytes) -> bool:
    """Whether a line begins like a header: a `>` before its last colon."""
    end = text.rfind(b":")
    return end > 0 and b">" in text[:end]


class TextReader:
    """The frames in the text a TNC prints, from its bytes as they come (one reader for one open of the line). `monitor`: every form of a TNC's monitor mode and of a Yaesu; else the one-line TNC2 text alone."""

    def __init__(self, *, monitor: bool, pending_sec: float = PENDING_SEC, max_line: int = MAX_LINE) -> None:
        self.monitor, self.pending_sec, self.max_line = monitor, pending_sec, max_line
        self.bits = 0                           # 0 while not decided, else 7 (with a parity bit) or 8
        self.parity = ""                        # "even" or "odd" for a line of 7 bits
        self._seen: set[int] = set()            # the parities of the bytes so far (the count of one bits, mod 2)
        self._counted = 0
        self._high = False                      # a byte above 0x7F came
        self._waiting = bytearray()             # the bytes from the first above 0x7F, until the line is decided
        self._line = bytearray()
        self._skip = False                      # the line was too long: what comes up to its end is dropped
        self._held: _Head | None = None         # a header that waits for its information
        self._last: float | None = None
        self._now = 0.0
        self._out: list[ax25.Frame | Rejected] = []

    @property
    def seven_bit(self) -> bool:
        """The line carries 7-bit characters with a parity bit (found by itself)."""
        return self.bits == 7

    def feed(self, data: bytes, now: float) -> list[ax25.Frame | Rejected]:
        """The frames and the rejected lines that these bytes complete; `now` is the time they came, in seconds of any clock that only goes forward."""
        self._out, self._now = [], now
        if self._last is not None and now - self._last > self.pending_sec:
            self._quiet()
        self._last = now
        for byte in data:
            self._byte(byte)
        return self._out

    def _quiet(self) -> None:
        """No byte for `pending_sec`: the bytes that wait are decided on what came, and a piece of a line and a header without its information are forgotten."""
        if self._waiting and self._counted >= DECIDE_QUIET:
            self._decide(7)
        self._waiting.clear()                   # (too few bytes to tell 7 bits from 8: a piece of a line, forgotten with it; the parities seen so far still count)
        self._line.clear()
        self._skip, self._held = False, None

    def _byte(self, byte: int) -> None:
        if self.bits:
            return self._take(byte & 0x7F if self.bits == 7 else byte)
        self._seen.add(byte.bit_count() & 1)
        self._counted += 1
        self._high = self._high or byte > 0x7F
        if len(self._seen) == 2:
            self._decide(8)
            return self._take(byte)
        if not self._waiting and byte <= 0x7F:
            return self._take(byte)                 # (the same in 7 bits and in 8)
        self._waiting.append(byte)
        if self._counted >= DECIDE_BYTES and self._high:
            self._decide(7)

    def _decide(self, bits: int) -> None:
        self.bits = bits
        if bits == 7:
            self.parity = "odd" if self._seen == {1} else "even"
        waiting, self._waiting = bytes(self._waiting), bytearray()
        for byte in waiting:
            self._take(byte & 0x7F if bits == 7 else byte)

    def _take(self, byte: int) -> None:
        if byte not in _BREAKS:
            if not self._skip:
                self._line.append(byte)
                if len(self._line) > self.max_line:
                    self._line.clear()
                    self._skip = True
            return
        line, self._line = bytes(self._line), bytearray()
        if self._skip:
            self._skip = False
        elif line:
            self._read(line)

    def _read(self, line: bytes) -> None:
        if not self.monitor:
            return self._plain(line)
        if self._held is not None and self._now - self._held.at > self.pending_sec:
            self._held = None
        text = line
        while text.startswith(_PROMPT):
            text = text[len(_PROMPT):]
        match = _MONITOR.match(text)
        if self._held is not None and match is None:
            if text:                                                    # (a prompt alone is no information)
                held, self._held = self._held, None
                self._frame(held.destination, held.source, held.path, line, line)
            return
        self._held = None
        if match is None:
            if _looks_like_header(text):
                self._out.append(Rejected(line.decode("latin-1"), "a frame that is not AX.25" if b"{" in text else "not a header of a heard packet"))
            else:
                log.debug("tnc: a line of text that is no packet: %r", line[:80])
            return
        try:
            destination, source, path = _head_of(match)
        except _NotAFrame as error:
            self._out.append(Rejected(line.decode("latin-1"), str(error)))
            return
        info = text[match.end():]
        if info:
            self._frame(destination, source, path, info, line)
        else:
            self._held = _Head(destination, source, path, self._now)

    def _frame(self, destination: ax25.Address, source: ax25.Address, path: tuple[ax25.Address, ...], info: bytes, line: bytes) -> None:
        try:
            self._out.append(ax25.Frame(destination, source, path, info=info))
        except ax25.Ax25Error as error:
            self._out.append(Rejected(line.decode("latin-1"), str(error)))

    def _plain(self, line: bytes) -> None:
        """A line of one-line TNC2 text (a LoRa board's): a frame, a Rejected for a line that begins like a header and is none, nothing for any other."""
        try:
            self._out.append(frame_of(line))
        except Tnc2Error as error:
            if _looks_like_header(line):
                self._out.append(Rejected(line.decode("latin-1"), str(error)))


def looks_like_text(heard: bytes) -> bool:
    """Whether some line of what a port said reads as a heard packet (the search for a radio of a type that reads text)."""
    reader = TextReader(monitor=True)
    found = reader.feed(heard, 0.0) + reader.feed(b"", reader.pending_sec + 1.0)
    return any(isinstance(item, ax25.Frame) for item in found)
