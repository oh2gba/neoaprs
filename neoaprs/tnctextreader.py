"""Reader for a line whose profile reads text (`Profile.framing == "text"`, such as a Yaesu FTM).

It enters no KISS and writes nothing. If a KISS UI frame arrives on an open, the line is read
as KISS from then on, still never written.
"""
import asyncio
import logging
from datetime import datetime
from typing import Protocol

from . import ax25
from .packet import Packet
from .radiotype import RadioId
from .tnc2text import Rejected, TextReader, looks_like_text
from .tncmode import is_ui, looks_valid, packet_of, printable
from .tncport import TncPort
from .tncprofile import Profile
from .tncreader import Line, Reader
from .coded import Reason

log = logging.getLogger("neoaprs.tnc")

# Why a line that reads text takes no frame.
RX_ONLY = Reason("RX only: nothing is sent", "transmit.off")


class TextLine(Line, Protocol):
    radio_id: RadioId

    @property
    def label(self) -> str: ...
    def now(self) -> datetime: ...
    def _saw(self, text: str) -> None: ...
    def _reject(self) -> None: ...
    def _take(self, packet: Packet, frame: ax25.Frame) -> None: ...


class TextLineReader(Reader):
    def __init__(self, tnc: TextLine) -> None:
        self._text_line = tnc
        super().__init__(tnc)

    def reset(self) -> None:
        super().reset()
        self.text = TextReader()
        # the log has said that this line is 7 bits
        self.told_bits = False

    def command_mode_unanswered(self) -> bool:
        return False

    def enter_kiss(self, port: TncPort, why: str = "", level: int = logging.INFO, note: bool = True) -> None:
        """Nothing is written to a line that reads text: there is no KISS to enter."""
        log.debug("%s: no KISS is entered on a line that reads text (%s)", self._text_line.label, why)

    def read(self, port: TncPort, chunk: bytes) -> None:
        tnc = self._text_line
        tnc.stats.bytes_in += len(chunk)
        tnc.confirmed = True
        tnc._hear()
        frames = self.decoder.feed(chunk)
        if not self.kiss_seen and any(is_ui(frame) for frame in frames):
            self.kiss_seen, self.dropped_seen = True, self.decoder.dropped
            tnc._note("the radio sends KISS frames: they are read as KISS (nothing is sent to it)")
            log.info("%s: the radio sends KISS frames on a line set to read text: they are read as KISS", tnc.label)
        if self.kiss_seen:
            for frame in frames:
                tnc._handle(frame)
            self.dropped_seen = self.decoder.dropped
            return
        for item in self.text.feed(chunk, asyncio.get_running_loop().time()):
            if isinstance(item, Rejected):
                tnc._saw(printable(f"rejected, not a frame ({item.reason}): {item.text}"))
                tnc._reject()
            else:
                self._packet(item)
        if self.text.seven_bit and not self.told_bits:
            self.told_bits = True
            log.info("%s: the TNC sends 7-bit characters (%s parity): letters outside ASCII are lost", tnc.label, self.text.parity)

    def _packet(self, frame: ax25.Frame) -> None:
        tnc = self._text_line
        try:
            packet = packet_of("in", ax25.encode(frame), frame, tnc.now(), radio_id=tnc.radio_id)
        except Exception:
            log.exception("%s: a line of text could not be handled", tnc.label)
            tnc._saw("rejected, internal error")
            tnc._reject()
            return
        tnc._take(packet, frame)


def reader_for(tnc: TextLine, current: Reader | None = None) -> Reader:
    wanted = TextLineReader if tnc.profile.framing == "text" else Reader
    return current if type(current) is wanted else wanted(tnc)


def accepts(profile: Profile, heard: bytes) -> bool:
    """Return True if what a port said makes it the radio: KISS, or text for a text profile."""
    if profile.framing == "text":
        return looks_like_text(heard) or looks_valid(heard, False)
    return looks_valid(heard, profile.detect_command_mode)
