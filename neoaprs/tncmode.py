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
_TNC2_LINE = re.compile(r"^[A-Za-z0-9]{1,6}(?:-\d{1,2})?>[A-Za-z0-9]{1,6}(?:-\d{1,2})?(?:,[A-Za-z0-9-]+\*?)*:", re.MULTILINE)


class Mode(Enum):
    UNKNOWN = "unknown"
    MONITOR = "monitor"               # the TNC is in command mode and prints what it hears as text
    KISS = "kiss"


class ModeDetector:
    """Decides from the bytes of one open whether the TNC talks KISS or command-mode text. KISS is a complete frame that decodes as an AX.25 UI frame, and once seen it stays (a later "cmd:" inside a frame
    means nothing) until `rearm` forgets it. MONITOR is "cmd:" or a TNC2 line (a call, ">", a destination, an optional ",path", ":") in a stretch of bytes between FENDs that is all text: a KISS frame always has
    bytes that are not (the address bytes are shifted past ASCII, the control byte and PID are 0x03 and 0xF0), so the letters "cmd:" inside a frame are not taken for the prompt. No I/O."""

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
    """Is this stretch of bytes between FENDs the text of command mode: all text, with "cmd:" or a TNC2 line in it? A KISS frame never is: its first byte, the command, is 0x00 for data, and its addresses are shifted past ASCII."""
    if not segment or not all(b in _TEXT_BYTES for b in segment):
        return False
    text = segment.decode("ascii").replace("\r", "\n").replace("\x11", "\n").replace("\x13", "\n")
    return "cmd:" in text or bool(_TNC2_LINE.search(text))


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
