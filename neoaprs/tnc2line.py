"""TNC2 text, the form a LoRa APRS board puts a packet in (`SRC>DST,PATH:information`), as an `ax25.Frame` and back. A LoRa packet on the air is that text after a header of three bytes (`HEADER`): no
AX.25, no checksum of its own (the LoRa modem's is on), at most 255 bytes in all. A board hands the computer either KISS (AX.25 frames it made from the text) or lines of the text itself, ended by a line feed
with or without a carriage return before it.

`frame_of` reads a packet's text, `text_of` writes it, `air_of` and `from_air` add and take off the header; `LineReader` cuts what a board writes into lines and reads each: a line whose start is a TNC2
header is a packet (or one that cannot be AX.25, with the reason: a call of more than six characters, an SSID above 15, more than eight digipeaters, more text than a packet carries), any other line is the
board's own (its log). The information field is kept as the bytes it came as (a LoRa tracker sends UTF-8; a Mic-E field is no text at all). `Packet.raw` of a packet heard this way is the AX.25
encoding of the frame, made by us, so that the log, the digipeater, the iGate and the codec read it as they read any frame of the air.

The digipeaters' star: TNC2 text marks only the last digipeater the frame has been through (`Q2DIG*,WIDE2-1`), and AX.25 marks every one up to it; `frame_of` marks them all, `text_of` writes the one.

Pure code."""
import re
from dataclasses import dataclass

from . import ax25

HEADER = b"\x3c\xff\x01"                # what every LoRa APRS packet of text begins with on the air ("<", 0xFF, 0x01), as the firmwares in use send and require it
MAX_PACKET = 255                        # the longest LoRa packet (the radio chips' buffer), the header included: the text of one is at most MAX_PACKET - len(HEADER) bytes
MAX_TEXT = MAX_PACKET - len(HEADER)     # the longest text of a packet: 252 bytes
MAX_LINE = 1024                         # a line of a board longer than this is no packet and no log line worth keeping: it is cut off there
_PART = rb"[\x21-\x2b\x2d-\x39\x3b-\x3d\x3f-\x7e]{1,15}"     # a part of the header as loosely as a board writes it (any printable but the three signs between the parts), so that one that is no AX.25 address is told by its reason
_HEAD = re.compile(rb"(%s)>(%s)((?:,%s)*):" % (_PART, _PART, _PART))     # SRC>DST,PATH:


class Tnc2Error(ValueError):
    """A packet's text that is no AX.25 frame, with the reason (an address that cannot be one, no header at all)."""


def addresses(parts: list[bytes]) -> list[ax25.Address]:
    """The AX.25 addresses of the parts of a header (`OH2XYZ-9`, `WIDE2-1*`), by the rules of neoaprs/callsign.py; Tnc2Error naming the one that is none. The one grammar of the calls in TNC2 text, which the
    monitor text of a TNC (tnc2text.py) reads too."""
    try:
        return [ax25.Address.parse(part.decode("ascii")) for part in parts]
    except (ax25.Ax25Error, UnicodeDecodeError) as error:
        raise Tnc2Error(f"not an AX.25 address: {error}") from None


def frame_of(text: bytes) -> ax25.Frame:
    """The frame of a packet's text (no line end); Tnc2Error when it has no TNC2 header or an address of it cannot be AX.25."""
    head = _HEAD.match(text)
    if head is None:
        raise Tnc2Error("not a packet: no SRC>DST:information at its start")
    source, destination, path = head.group(1), head.group(2), head.group(3)
    [src, dst], digis = addresses([source, destination]), addresses([p for p in path.split(b",") if p])
    if src.repeated or dst.repeated:
        raise Tnc2Error("only a digipeater can be marked as repeated")
    last = max((i for i, d in enumerate(digis) if d.repeated), default=-1)
    try:
        return ax25.Frame(dst, src, tuple(ax25.Address(d.call, d.ssid, i <= last) for i, d in enumerate(digis)), info=text[head.end():])
    except ax25.Ax25Error as error:
        raise Tnc2Error(str(error)) from None


def text_of(frame: ax25.Frame) -> bytes:
    """The packet's text, as a board puts it on the air: the header in ASCII and the information field as its bytes (the frame's TNC2 line, whose Latin-1 gives each byte back as it was)."""
    return frame.tnc2().encode("latin-1")


def air_of(frame: ax25.Frame) -> bytes:
    """The LoRa packet of the frame: the header, then its text. It may be longer than MAX_PACKET; the one who sends it says whether it fits (`fits`)."""
    return HEADER + text_of(frame)


def fits(packet: bytes) -> bool:
    """Whether a LoRa packet is short enough to be sent."""
    return len(packet) <= MAX_PACKET


def from_air(packet: bytes) -> ax25.Frame:
    """The frame of a LoRa packet; Tnc2Error for one without the header (another kind of LoRa traffic) or whose text is no frame."""
    if not packet.startswith(HEADER):
        raise Tnc2Error("not a LoRa APRS packet: it does not begin with the header of one")
    return frame_of(packet[len(HEADER):])


@dataclass(frozen=True)
class TextLine:
    """One line a board wrote, without its line end: the packet it is (`frame`), or why a line that begins as a packet is none (`why`); a line of the board's own has neither."""
    text: bytes
    frame: ax25.Frame | None = None
    why: str = ""


class LineReader:
    """What a board writes, cut into lines at each line feed (a carriage return before it is dropped), each read as a packet or as the board's own line. A piece of a line waits for the rest; a line that
    grows past MAX_LINE is read as far as that, and the rest of it, up to its line feed, is dropped (it is no line of its own)."""

    def __init__(self) -> None:
        self._held = b""
        self._cut = False                       # the line being written was cut off at MAX_LINE: what comes up to its line feed is dropped

    def feed(self, data: bytes) -> list[TextLine]:
        *lines, self._held = (self._held + data).split(b"\n")
        out: list[TextLine] = []
        for line in lines:
            if self._cut:
                self._cut = False
            elif line.strip(b"\r"):
                out.append(read_line(line.removesuffix(b"\r")))
        if self._cut:
            self._held = b""
        elif len(self._held) > MAX_LINE:
            out.append(read_line(self._held))
            self._held, self._cut = b"", True
        return out


def read_line(text: bytes) -> TextLine:
    """A line of a board: a packet, a packet that is no AX.25 frame or is longer than a LoRa packet carries (with the reason), or a line of its own. The text is kept up to MAX_LINE bytes."""
    if _HEAD.match(text) is None:
        return TextLine(text[:MAX_LINE])
    if len(text) > MAX_TEXT:
        return TextLine(text[:MAX_LINE], why=f"{len(text)} bytes, longer than any LoRa packet ({MAX_TEXT} bytes of text)")
    try:
        return TextLine(text, frame_of(text))
    except Tnc2Error as error:
        return TextLine(text, why=str(error))
