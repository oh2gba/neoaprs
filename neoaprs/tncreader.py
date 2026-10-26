"""What the Tnc makes of the bytes of one open line: the mode they show (a KISS stream, or the text of a TNC in command mode, tncmode.py), the entry into KISS when the TNC is in command mode, the settle time
after it in which what the TNC says is thrown away, the repeats of the entry for a TNC that goes on typing (`EntryAgain`, tncwatchdog.py), and the KISS frames that are handed on. It holds the state of the reading
that belongs to one open (`reset` starts it over); the `Tnc` (tnc.py) holds the line, the states and the words, and the keep-alive (tncwatchdog.py) asks for its `look_*` actions."""
import asyncio
import logging
from typing import Protocol

from . import kiss
from .source import Source
from .tncentry import KissEntry
from .tncmode import Mode, ModeDetector, TextAfterKiss
from .tncport import TncPort
from .tncprofile import Profile
from .tncwatchdog import EntryAgain, TncStats, Watchdog

log = logging.getLogger("neoaprs.tnc")


class Line(Protocol):
    """What the reader needs of the Tnc."""
    stats: TncStats
    state: Source.State
    profile: Profile
    confirmed: bool
    watchdog: Watchdog
    problem: str
    _port: TncPort | None
    _entry: KissEntry

    def _hear(self, then: str = "") -> None: ...
    def _note(self, text: str) -> None: ...
    def _set_problem(self, text: str) -> None: ...
    def _handle(self, kiss_frame: kiss.KissFrame) -> None: ...


class Reader:
    def __init__(self, tnc: Line) -> None:
        self._tnc = tnc
        self.reset()

    def reset(self) -> None:
        """What belongs to one open of the line."""
        self.detector = ModeDetector()
        self.decoder = kiss.KissDecoder()
        self.dropped_seen = 0
        self.entered = self.kiss_seen = self.told_text = False           # KISS ON was sent on this open; a KISS frame came since; the text that came after the entry has been told
        self.again = EntryAgain()                                        # when the entry is repeated for a TNC that still types text
        self.typed = TextAfterKiss()                                     # text after KISS frames: the radio was restarted
        self.settle_until = 0.0
        self.looking = False                                             # a check or probe is under way: nothing is sent, and the keep-alive itself enters KISS

    def asked_afresh(self) -> None:
        """A check or probe starts: the TNC is asked afresh, and what was seen of its mode is forgotten."""
        self.looking = True
        self.entered = self.kiss_seen = self.told_text = False
        self.again.reset()
        self.detector.rearm()

    def command_mode_unanswered(self) -> bool:
        """Text from a TNC that the profile says may be in command mode, and no KISS frame since: nothing is sent to it."""
        return self._tnc.profile.detect_command_mode and self.told_text and not self.kiss_seen

    def read(self, port: TncPort, chunk: bytes) -> None:
        """Bytes came from `port`, which is the Tnc's line."""
        tnc = self._tnc
        loop_now = asyncio.get_running_loop().time()
        tnc.stats.bytes_in += len(chunk)
        typed = self.typed.feed(chunk)                                   # (text since the latest FEND: after KISS frames, the radio was restarted)
        tnc.confirmed = True
        tnc.watchdog.heard()
        mode = self._heard(port, chunk, loop_now)
        if loop_now < self.settle_until:
            return
        if typed and mode is Mode.KISS and self.kiss_seen and tnc.profile.detect_command_mode:
            self.kiss_seen = self.told_text = False                      # switched to KISS again now, not at the next check: text keeps the line from going quiet
            return self.enter_kiss(port, "the TNC is in command mode again (the radio was restarted)")
        if mode is Mode.KISS:
            if self.told_text and not self.kiss_seen:                    # (KISS at last after text: the problem it made is over)
                self.told_text = False
                tnc._set_problem("")
            self.kiss_seen = True
            self.again.reset()
        elif mode is Mode.MONITOR:
            self._command_mode(port)
            if loop_now < self.settle_until or tnc._port is not port:
                return
        self._decode(chunk)

    def _decode(self, chunk: bytes) -> None:
        for frame in self.decoder.feed(chunk):
            self._tnc._handle(frame)
        if self.decoder.dropped > self.dropped_seen:
            self._tnc.stats.rejected += self.decoder.dropped - self.dropped_seen
            self._tnc._note(f"{self.decoder.dropped - self.dropped_seen} damaged KISS frame(s) dropped")
            self.dropped_seen = self.decoder.dropped

    def _heard(self, port: TncPort, chunk: bytes, loop_now: float) -> Mode | None:
        """Bytes came: what the detector makes of them, None while an entry settles (they are thrown away). From a silent radio, which may have been switched on (a TH-D7 starts with its TNC in command mode),
        the allowance to enter KISS is given back and the detector starts over; KISS is entered unless the bytes are a KISS frame already, or a piece of one (a FEND among them and no whole frame: a line
        delivers a frame in several reads, and command-mode text never has a FEND), when what follows decides, or an entry of the keep-alive's own is settling."""
        tnc = self._tnc
        if tnc.state is not Source.State.SILENT:
            tnc._hear()
            return None if loop_now < self.settle_until else self.detector.feed(chunk)
        if loop_now < self.settle_until:
            tnc._hear("; entering KISS")
            return None
        self.entered = self.kiss_seen = self.told_text = False
        self.again.reset()
        self.detector.rearm()
        piece = kiss.FEND in chunk
        mode = self.detector.feed(chunk[chunk.index(kiss.FEND):] if piece else chunk)      # (what is before the first FEND is the tail of a frame, never text)
        enter = tnc.profile.detect_command_mode and mode is not Mode.KISS and not piece
        tnc._hear("; entering KISS" if enter else "")
        if enter:
            self.enter_kiss(port, "the radio answers again", logging.DEBUG, note=False)
        return mode

    def _command_mode(self, port: TncPort) -> None:
        tnc = self._tnc
        if self.looking:
            return
        if tnc.profile.detect_command_mode and not self.entered:
            self.enter_kiss(port, "the TNC was in command mode")
            return
        if not self.told_text:                                           # (told first, whenever the text comes: a repeat of the entry that is due does not make the Tnc usable meanwhile)
            self.told_text = True
            tnc._set_problem("the TNC sends text, not KISS frames: it is in command mode" + (" and the entry did not change that" if self.entered else f" and the profile {tnc.profile.name!r} does not enter KISS"))
            tnc._note(tnc.problem)
        if tnc.profile.detect_command_mode and not self.kiss_seen and self.again.due(asyncio.get_running_loop().time(), self.settle_until):
            why, level = self.again.repeat()
            self.enter_kiss(port, why, level)

    def enter_kiss(self, port: TncPort, why: str = "the TNC was in command mode", level: int = logging.INFO, note: bool = True) -> None:
        """The profile's steps (KISS ON and RESTART for a TNC-2), then the settle time of throwing away what the TNC says. `level` is the log's (DEBUG for a check or a return from SILENT, which have told their
        own news, and for the later repeats of the entry); `note`: whether the terminal gets a line too (not for the check and the return from SILENT)."""
        tnc = self._tnc
        self.entered = True
        log.log(level, "entering KISS mode on %s: %s", port.path, why)
        if note:
            tnc._note(f"entering KISS mode: {why}")
        took = tnc._entry.begin(tnc.profile, lambda: port is tnc._port)
        if took is not None:
            self.settle_until = asyncio.get_running_loop().time() + took
            self.detector, self.decoder, self.dropped_seen = ModeDetector(), kiss.KissDecoder(), 0
