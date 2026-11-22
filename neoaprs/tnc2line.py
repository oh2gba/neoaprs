"""TNC2 text, the form a LoRa APRS board puts a packet in, as an `ax25.Frame` and back.

A LoRa packet is `SRC>DST,PATH:information` after a three-byte header, at most 255 bytes.
"""

import re
from dataclasses import dataclass

from . import ax25

HEADER = b"\x3c\xff\x01"
MAX_PACKET = 255
MAX_TEXT = MAX_PACKET - len(HEADER)  # the longest text of a packet: 252 bytes
# a board line longer than this is cut there
MAX_LINE = 1024
# a header part as loosely as a board writes it, so a bad address gets a reason
_PART = rb"[\x21-\x2b\x2d-\x39\x3b-\x3d\x3f-\x7e]{1,15}"
_HEAD = re.compile(rb"(%s)>(%s)((?:,%s)*):" % (_PART, _PART, _PART))  # SRC>DST,PATH:


class Tnc2Error(ValueError):
    """A packet's text that is no AX.25 frame."""


def addresses(parts: list[bytes]) -> list[ax25.Address]:
    """Return the AX.25 addresses of a header's parts; raise Tnc2Error naming the invalid one."""
    try:
        return [ax25.Address.parse(part.decode("ascii")) for part in parts]
    except (ax25.Ax25Error, UnicodeDecodeError) as error:
        raise Tnc2Error(f"not an AX.25 address: {error}") from None


def frame_of(text: bytes) -> ax25.Frame:
    """Return the frame of a packet's text; raise Tnc2Error if it is not one."""
    head = _HEAD.match(text)
    if head is None:
        raise Tnc2Error("not a packet: no SRC>DST:information at its start")
    source, destination, path = head.group(1), head.group(2), head.group(3)
    [src, dst], digis = addresses([source, destination]), addresses([p for p in path.split(b",") if p])
    if src.repeated or dst.repeated:
        raise Tnc2Error("only a digipeater can be marked as repeated")
    last = max((i for i, d in enumerate(digis) if d.repeated), default=-1)
    try:
        return ax25.Frame(
            dst,
            src,
            tuple(ax25.Address(d.call, d.ssid, i <= last) for i, d in enumerate(digis)),
            info=text[head.end() :],
        )
    except ax25.Ax25Error as error:
        raise Tnc2Error(str(error)) from None


def text_of(frame: ax25.Frame) -> bytes:
    return frame.tnc2().encode("latin-1")


def air_of(frame: ax25.Frame) -> bytes:
    return HEADER + text_of(frame)


def fits(packet: bytes) -> bool:
    return len(packet) <= MAX_PACKET


def from_air(packet: bytes) -> ax25.Frame:
    """Return the frame of a LoRa packet; raise Tnc2Error."""
    if not packet.startswith(HEADER):
        raise Tnc2Error("not a LoRa APRS packet: it does not begin with the header of one")
    return frame_of(packet[len(HEADER) :])


@dataclass(frozen=True)
class TextLine:
    """One line a board wrote: the packet (`frame`), or why it is none (`why`)."""

    text: bytes
    frame: ax25.Frame | None = None
    why: str = ""


class LineReader:
    """What a board writes, cut into lines; a line past MAX_LINE is cut and its rest dropped."""

    def __init__(self) -> None:
        self._held = b""
        # the line was cut at MAX_LINE: what comes up to its line feed is dropped
        self._cut = False

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
    if _HEAD.match(text) is None:
        return TextLine(text[:MAX_LINE])
    if len(text) > MAX_TEXT:
        return TextLine(
            text[:MAX_LINE], why=f"{len(text)} bytes, longer than any LoRa packet ({MAX_TEXT} bytes of text)"
        )
    try:
        return TextLine(text, frame_of(text))
    except Tnc2Error as error:
        return TextLine(text, why=str(error))
