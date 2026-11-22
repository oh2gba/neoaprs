"""The text a TNC or radio prints of the packets it hears, read as AX.25 frames.

Sources: a Yaesu FTM data port with Output PACKET, a TNC-2, KPC-3 or PK-232 in monitor mode.
Each packet becomes a UI frame with PID F0. A TNC at 7 bits with a parity bit is detected.
"""
import logging
import re
from dataclasses import dataclass

from . import ax25
from .tnc2line import Tnc2Error, addresses

log = logging.getLogger("neoaprs.tnc")

# a partial line or lone header is forgotten after this long with no byte (aprx: 2 s)
PENDING_SEC = 2.0
# a longer line is no TNC packet: dropped with what follows up to its line end
MAX_LINE = 512
# bytes keeping one parity, one above 0x7F, before the line is taken as 7 bits with parity
DECIDE_BYTES = 32
# the fewest such bytes that decide it when the line goes quiet first
DECIDE_QUIET = 12
# what ends a line: CR, LF, XON, XOFF (as tncmode._LINE_BREAKS)
_BREAKS = frozenset(b"\r\n\x11\x13")
_PROMPT = b"cmd:"
# a call as loosely as a header can hold one; tnc2line.addresses says why one is invalid
_PART = rb"[0-9A-Za-z-]{1,12}\*?"
_MONITOR = re.compile(rb"(?:[0-9A-Za-z/.:-]+ +){0,2}?(?P<chain>%s(?:>%s)+)(?P<path>(?:,%s)*)(?: \[[^\]]*\])?(?::? <(?P<mark>[^>]*)>)?:" % (_PART, _PART, _PART))
_UI_MARK = re.compile(rb"UI[^>]*")


@dataclass(frozen=True)
class Rejected:
    """A line that began like a packet header and is none, with the reason."""
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
    end = text.rfind(b":")
    return end > 0 and b">" in text[:end]


class TextReader:
    """The frames in the text a TNC or Yaesu prints, from bytes as they come (one per open)."""

    def __init__(self, *, pending_sec: float = PENDING_SEC, max_line: int = MAX_LINE) -> None:
        self.pending_sec, self.max_line = pending_sec, max_line
        self.bits = 0  # 0 while not decided, else 7 (with a parity bit) or 8
        self.parity = ""  # "even" or "odd" for a line of 7 bits
        self._seen: set[int] = set()  # parities of the bytes so far (count of one bits, mod 2)
        self._counted = 0
        self._high = False  # a byte above 0x7F came
        # the bytes from the first above 0x7F, until the line is decided
        self._waiting = bytearray()
        self._line = bytearray()
        self._skip = False  # the line was too long: what comes up to its end is dropped
        self._held: _Head | None = None  # a header that waits for its information
        self._last: float | None = None
        self._now = 0.0
        self._out: list[ax25.Frame | Rejected] = []

    @property
    def seven_bit(self) -> bool:
        return self.bits == 7

    def feed(self, data: bytes, now: float) -> list[ax25.Frame | Rejected]:
        """Return the frames and rejected lines these bytes complete; `now` is monotonic seconds."""
        self._out, self._now = [], now
        if self._last is not None and now - self._last > self.pending_sec:
            self._quiet()
        self._last = now
        for byte in data:
            self._byte(byte)
        return self._out

    def _quiet(self) -> None:
        if self._waiting and self._counted >= DECIDE_QUIET:
            self._decide(7)
        # too few bytes to tell 7 bits from 8: forgotten with the line; parities seen still count
        self._waiting.clear()
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
            return self._take(byte)  # the same in 7 bits and in 8
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
        if self._held is not None and self._now - self._held.at > self.pending_sec:
            self._held = None
        text = line
        while text.startswith(_PROMPT):
            text = text[len(_PROMPT):]
        match = _MONITOR.match(text)
        if self._held is not None and match is None:
            if text:  # a prompt alone is no information
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
        # a garbled line, two run together: no AX.25 frame carries that
        if len(info) > ax25.MAX_INFO:
            self._out.append(Rejected(line.decode("latin-1"), f"an information field of {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows"))
            return
        try:
            self._out.append(ax25.Frame(destination, source, path, info=info))
        except ax25.Ax25Error as error:
            self._out.append(Rejected(line.decode("latin-1"), str(error)))


def looks_like_text(heard: bytes) -> bool:
    reader = TextReader()
    found = reader.feed(heard, 0.0) + reader.feed(b"", reader.pending_sec + 1.0)
    return any(isinstance(item, ax25.Frame) for item in found)
