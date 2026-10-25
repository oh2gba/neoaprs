"""What the TNC's bytes say: about its mode, a KISS stream or the text of command mode, and, for a KISS frame, the packet in it. No I/O; the `Tnc` (tnc.py) acts on it.

The Kenwood TH-D7's TNC starts in command mode (it prints heard packets as TNC2 text and answers a carriage return with "cmd:"). `ModeDetector` tells that from a KISS stream."""
import logging
import re
from datetime import datetime
from enum import Enum
from typing import Literal

from . import aprsthirdparty, ax25, kiss
from .packet import Packet

log = logging.getLogger("neoaprs.tnc")

_TAIL_BYTES = 4096                    # the detector looks at this much of the latest bytes
_TEXT_BYTES = frozenset(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D, 0x11, 0x13}      # printable ASCII, white space, XON and XOFF
_LINE_BREAKS = re.compile(rb"[\r\n\x11\x13]")                                     # what ends a line of command-mode text (a TH-D7 types XON after its prompt)
_TNC2_LINE = re.compile(r"[A-Za-z0-9]{1,6}(?:-\d{1,2})?>[A-Za-z0-9]{1,6}(?:-\d{1,2})?(?:,[A-Za-z0-9-]+\*?)*(?: <UI[^>]*>)?:")     # a monitored packet's header: TNC-2 and TH-D7 "A>B,C*:", Kantronics "A>B,C <UI>:" or "<UI pid=F0 Len=20>:"


class Mode(Enum):
    UNKNOWN = "unknown"
    MONITOR = "monitor"               # the TNC is in command mode and prints what it hears as text
    KISS = "kiss"


class ModeDetector:
    """Decides from the bytes of one open whether the TNC talks KISS or command-mode text. KISS is a complete frame that decodes as an AX.25 UI frame, and once seen it stays (a later "cmd:" inside a frame
    means nothing) until `rearm` forgets it. MONITOR is a line of text with "cmd:" or a TNC2 header (a call, ">", a destination, an optional ",path", ":") in it, in a stretch of bytes between FENDs that begins with
    text (`typed_text`): each line is judged by itself, so one comment with a letter outside ASCII, or a Mic-E byte, hides nothing, and a KISS frame never qualifies, because its first byte, the command, is not
    text, whatever the letters inside it say. No I/O."""

    def __init__(self) -> None:
        self.mode = Mode.UNKNOWN
        self._decoder = kiss.KissDecoder()
        self._tail = bytearray()

    def rearm(self) -> None:
        """Forgets what was seen, KISS included: the next bytes decide again. For a TNC that may have been switched off and on, or reset, since its frames last came."""
        self.mode = Mode.UNKNOWN
        self._decoder = kiss.KissDecoder()
        self._tail.clear()

    def feed(self, data: bytes) -> Mode:
        if self.mode is Mode.KISS:
            return self.mode
        if any(self._is_ui(f) for f in self._decoder.feed(data)):
            self.mode = Mode.KISS
            self._tail.clear()
            return self.mode
        self._tail.extend(data)
        del self._tail[:-_TAIL_BYTES]
        if self.mode is Mode.UNKNOWN and self._has_text_evidence():
            self.mode = Mode.MONITOR
        return self.mode

    @staticmethod
    def _is_ui(frame: kiss.KissFrame) -> bool:
        if frame.command != 0:
            return False
        try:
            return ax25.decode(frame.payload).is_ui
        except ax25.Ax25Error:
            return False

    def _has_text_evidence(self) -> bool:
        return any(typed_text(segment) for segment in bytes(self._tail).split(b"\xc0"))


class TextAfterKiss:
    """Watches the bytes since the latest FEND once KISS frames have come: a TNC in KISS sends nothing but frames, so the text of command mode there means it has been restarted (the radio switched off and on)
    and types what it hears. A frame on its way never looks like that: its first byte, the command, is not text."""

    TAIL_BYTES = 512                  # how much of the bytes since the latest FEND is looked at

    def __init__(self) -> None:
        self._since_fend = bytearray()

    def feed(self, chunk: bytes) -> bool:
        end = chunk.rfind(kiss.FEND)
        if end >= 0:
            self._since_fend = bytearray(chunk[end + 1:])
        else:
            self._since_fend.extend(chunk)
            del self._since_fend[:-self.TAIL_BYTES]
        return typed_text(bytes(self._since_fend))


def typed_text(segment: bytes) -> bool:
    """Does this stretch of bytes between FENDs hold a line of command-mode text: one that is all text, with "cmd:" or a TNC2 header in it? Each line is judged by itself, so that a comment with a letter outside
    ASCII (or a Mic-E byte) does not hide the lines around it. A KISS frame never qualifies: its first byte, the command, is 0x00 for data, so a stretch that begins with a byte that is not text is a frame on its
    way (or the tail of one), whatever comes after that byte."""
    if not segment or segment[0] not in _TEXT_BYTES:
        return False
    return any(_text_line(line) for line in _LINE_BREAKS.split(segment))


def _text_line(line: bytes) -> bool:
    """The line up to its first byte that is not text (a monitored packet's header is text even when its comment is not) has "cmd:" or begins with a TNC2 header."""
    end = next((i for i, b in enumerate(line) if b not in _TEXT_BYTES), len(line))
    text = line[:end].decode("ascii")
    return "cmd:" in text or _TNC2_LINE.match(text) is not None


def packet_of(direction: Literal["in", "out"], raw: bytes, frame: ax25.Frame, now: datetime) -> Packet:
    """The packet for an AX.25 frame that came in or went out at `now`."""
    source, destination = str(frame.source), str(frame.destination)
    decoded, third_party = aprsthirdparty.parse_packet(frame.info, source, destination, now)
    return Packet(heard_at=now, direction=direction, raw=raw, source=source, destination=destination, path=tuple(str(a) for a in frame.path),
                  info=frame.info, decoded=decoded, third_party=third_party)


def read_frame(kiss_frame: kiss.KissFrame, now: datetime) -> tuple[Packet, ax25.Frame] | str:
    """The packet in a KISS frame and its AX.25 frame, or the reason it is none (a KISS command, not a UI frame, not AX.25 at all)."""
    try:
        if kiss_frame.command != 0:
            return f"KISS command {kiss_frame.command} on port {kiss_frame.port}, ignored"
        frame = ax25.decode(kiss_frame.payload)
        if not frame.is_ui:
            return f"not a UI frame (control 0x{frame.control:02X}, PID 0x{frame.pid:02X})"
        return packet_of("in", kiss_frame.payload, frame, now), frame
    except ax25.Ax25Error as e:
        return f"not an AX.25 frame: {e}"
    except Exception:
        log.exception("tnc: a frame could not be handled")
        return "internal error"


def looks_valid(heard: bytes, enter_kiss: bool) -> bool:
    """Whether these bytes make a port the radio's: a KISS frame with an AX.25 UI frame in it. A TNC that is still in command mode counts when `enter_kiss` will switch it."""
    mode = ModeDetector().feed(heard)
    return mode is Mode.KISS or (enter_kiss and mode is Mode.MONITOR)
