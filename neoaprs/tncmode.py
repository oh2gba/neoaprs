"""What the TNC's bytes say: its mode (KISS stream or command-mode text) and the packet in a frame.

No I/O. A Kenwood TH-D7 TNC starts in command mode (heard packets as TNC2 text, "cmd:" prompt);
`ModeDetector` tells that from a KISS stream.
"""

import logging
import re
from datetime import datetime
from enum import Enum
from typing import Literal

from . import aprsthirdparty, ax25, kiss
from .packet import Packet, channel_of
from .radiotype import FM_ID, RadioId
from .reading import NO_READING, Reading

log = logging.getLogger("neoaprs.tnc")

_TAIL_BYTES = 4096
_TEXT_BYTES = frozenset(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D, 0x11, 0x13}  # ASCII, space, XON/XOFF
# ends a command-mode text line (a TH-D7 sends XON after its prompt)
_LINE_BREAKS = re.compile(rb"[\r\n\x11\x13]")
# a monitored header: TNC-2 and TH-D7 "A>B,C*:", Kantronics "A>B,C <UI>:"
_TNC2_LINE = re.compile(r"[A-Za-z0-9]{1,6}(?:-\d{1,2})?>[A-Za-z0-9]{1,6}(?:-\d{1,2})?(?:,[A-Za-z0-9-]+\*?)*(?: <UI[^>]*>)?:")


class Mode(Enum):
    UNKNOWN = "unknown"
    MONITOR = "monitor"
    KISS = "kiss"


class ModeDetector:
    """Decide from the bytes of one open whether the TNC talks KISS or command-mode text.

    KISS is a complete UI frame (until `rearm`); MONITOR is a text line with "cmd:" or a header.
    """

    def __init__(self) -> None:
        self.mode = Mode.UNKNOWN
        self._decoder = kiss.KissDecoder()
        self._tail = bytearray()

    def rearm(self) -> None:
        self.mode = Mode.UNKNOWN
        self._decoder = kiss.KissDecoder()
        self._tail.clear()

    def feed(self, data: bytes) -> Mode:
        if self.mode is Mode.KISS:
            return self.mode
        if any(is_ui(f) for f in self._decoder.feed(data)):
            self.mode = Mode.KISS
            self._tail.clear()
            return self.mode
        self._tail.extend(data)
        del self._tail[:-_TAIL_BYTES]
        if self.mode is Mode.UNKNOWN and self._has_text_evidence():
            self.mode = Mode.MONITOR
        return self.mode

    def _has_text_evidence(self) -> bool:
        return any(typed_text(segment) for segment in bytes(self._tail).split(b"\xc0"))


class TextAfterKiss:
    """Watch the bytes since the latest FEND once KISS frames have come.

    A TNC in KISS mode sends only frames, so command-mode text means it restarted.
    """

    TAIL_BYTES = 512

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
    """Return whether this stretch between FENDs holds command-mode text.

    A stretch beginning with a non-text byte (the KISS command 0x00) is a frame.
    """
    if not segment or segment[0] not in _TEXT_BYTES:
        return False
    return any(_text_line(line) for line in _LINE_BREAKS.split(segment))


def _text_line(line: bytes) -> bool:
    end = next((i for i, b in enumerate(line) if b not in _TEXT_BYTES), len(line))
    text = line[:end].decode("ascii")
    return "cmd:" in text or _TNC2_LINE.match(text) is not None


def packet_of(direction: Literal["in", "out"], raw: bytes, frame: ax25.Frame, now: datetime, dummy: bool = False, reading: Reading = NO_READING, *,
              radio_id: RadioId | None = FM_ID) -> Packet:
    """Return the packet for an AX.25 frame; its channel is `rf`, `rf-gated` or `dummy`."""
    source, destination = str(frame.source), str(frame.destination)
    decoded, third_party = aprsthirdparty.parse_packet(frame.info, source, destination, now)
    return Packet(heard_at=now, direction=direction, raw=raw, source=source, destination=destination, path=tuple(str(a) for a in frame.path), info=frame.info, decoded=decoded, third_party=third_party,
                  via=channel_of(third_party, dummy=dummy), radio_id=radio_id, snr=reading.snr, rssi=reading.rssi)


def read_frame(kiss_frame: kiss.KissFrame, now: datetime, dummy: bool = False, reading: Reading = NO_READING, *,
               radio_id: RadioId | None = FM_ID) -> tuple[Packet, ax25.Frame] | str:
    try:
        if kiss_frame.command != 0:
            return f"KISS command {kiss_frame.command} on port {kiss_frame.port}, ignored"
        frame = ax25.decode(kiss_frame.payload)
        if not frame.is_ui:
            return f"not a UI frame (control 0x{frame.control:02X}, PID 0x{frame.pid:02X})"
        return packet_of("in", kiss_frame.payload, frame, now, dummy, reading, radio_id=radio_id), frame
    except ax25.Ax25Error as e:
        return f"not an AX.25 frame: {e}"
    except Exception:
        log.exception("tnc: a frame could not be handled")
        return "internal error"


def is_ui(frame: kiss.KissFrame) -> bool:
    if frame.command != 0:
        return False
    try:
        return ax25.decode(frame.payload).is_ui
    except ax25.Ax25Error:
        return False


def printable(text: str) -> str:
    return "".join(c if c.isprintable() else "?" for c in text)


def looks_valid(heard: bytes, enter_kiss: bool) -> bool:
    """Return whether these bytes make a port the radio's: KISS, or command mode if `enter_kiss`."""
    mode = ModeDetector().feed(heard)
    return mode is Mode.KISS or (enter_kiss and mode is Mode.MONITOR)
