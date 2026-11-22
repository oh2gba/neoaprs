"""What the Tnc makes of the bytes of one open line.

Covers the mode they show, entering KISS from command mode (the settle time discards the TNC's
output) and the KISS frames handed on. A LoRa board's line is read by its own reader (loraboard.py).
"""

import asyncio
import logging
from typing import Any, Coroutine, Protocol

from . import kiss
from .loraboard import LoraBoard
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
    path: str
    _port: TncPort | None
    _entry: KissEntry

    @property
    def label(self) -> str: ...
    def _hear(self, then: str = "") -> None: ...
    def _note(self, text: str) -> None: ...
    def _saw(self, text: str) -> None: ...
    def _add_line(self, text: str) -> None: ...
    def _reject(self) -> None: ...
    def _set_problem(self, text: str) -> None: ...
    def _handle(self, kiss_frame: kiss.KissFrame) -> None: ...
    def _write(self, port: TncPort, data: bytes) -> bool: ...
    def _spawn(self, coro: Coroutine[Any, Any, None]) -> "asyncio.Task[None]": ...


class Reader:
    def __init__(self, tnc: Line) -> None:
        self._tnc = tnc
        self.board: LoraBoard | None = None
        self.reset()

    def reset(self) -> None:
        if self.board is not None:
            self.board.close()
        self.board = LoraBoard(self._tnc) if self._tnc.profile.board else None  # a LoRa board has its own reader
        self.detector = ModeDetector()
        self.decoder = kiss.KissDecoder()
        self.dropped_seen = 0
        # KISS ON was sent on this open; a KISS frame came since; the text after it was reported
        self.entered = self.kiss_seen = self.told_text = False
        self.again = EntryAgain()  # repeats the entry for a TNC that still types text
        self.typed = TextAfterKiss()  # text after KISS frames: the radio was restarted
        self.settle_until = 0.0
        # a check or probe is under way: nothing is sent, and the keep-alive itself enters KISS
        self.looking = False

    def asked_afresh(self) -> None:
        self.looking = True
        self.entered = self.kiss_seen = self.told_text = False
        self.again.reset()
        self.detector.rearm()

    def board_quiet(self) -> str:
        """Return why a LoRa board's line takes no frame now, or ""."""
        return self.board.quiet() if self.board is not None else ""

    def command_mode_unanswered(self) -> bool:
        """Return whether the TNC sent command-mode text and no KISS frame followed."""
        return self._tnc.profile.detect_command_mode and self.told_text and not self.kiss_seen

    def read(self, port: TncPort, chunk: bytes) -> None:
        tnc = self._tnc
        loop_now = asyncio.get_running_loop().time()
        tnc.stats.bytes_in += len(chunk)
        # text since the latest FEND: after KISS frames, the radio was restarted
        typed = self.typed.feed(chunk)
        tnc.confirmed = True
        tnc.watchdog.heard()
        if self.board is not None:
            tnc._hear()
            self.board.read(chunk)
            self.kiss_seen = self.board.kiss_seen and not self.board.text_since_kiss
            return
        mode = self._heard(port, chunk, loop_now)
        if loop_now < self.settle_until:
            return
        if typed and mode is Mode.KISS and self.kiss_seen and tnc.profile.detect_command_mode:
            # switch to KISS now, not at the next check: text keeps the line quiet
            self.kiss_seen = self.told_text = False
            return self.enter_kiss(port, "the TNC is in command mode again (the radio was restarted)")
        if mode is Mode.KISS:
            if self.told_text and not self.kiss_seen:  # KISS at last after text: the problem is over
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
        """Return what the detector makes of the bytes, or None while an entry settles.

        From a silent radio KISS is entered only on text without a FEND: a piece of a frame is not text.
        """
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
        # what precedes the first FEND is the tail of a frame, never text
        mode = self.detector.feed(chunk[chunk.index(kiss.FEND):] if piece else chunk)
        enter = tnc.profile.detect_command_mode and mode is Mode.MONITOR and not piece
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
        # told first: a due repeat of the entry must not make the Tnc usable meanwhile
        if not self.told_text:
            self.told_text = True
            tnc._set_problem("the TNC sends text, not KISS frames: it is in command mode" + (" and the entry did not change that" if self.entered else f" and the profile {tnc.profile.name!r} does not enter KISS"))
            tnc._note(tnc.problem)
        if tnc.profile.detect_command_mode and not self.kiss_seen and self.again.due(asyncio.get_running_loop().time(), self.settle_until):
            why, level = self.again.repeat()
            self.enter_kiss(port, why, level)

    def enter_kiss(self, port: TncPort, why: str = "the TNC was in command mode", level: int = logging.INFO, note: bool = True) -> None:
        """Run the profile's entry steps, then the settle time that discards what the TNC says.

        `level` is the log level; `note` says whether the terminal gets a line too.
        """
        tnc = self._tnc
        self.entered = True
        log.log(level, "entering KISS mode on %s: %s", port.path, why)
        if note:
            tnc._note(f"entering KISS mode: {why}")
        took = tnc._entry.begin(tnc.profile, lambda: port is tnc._port)
        if took is not None:
            self.settle_until = asyncio.get_running_loop().time() + took
            self.detector, self.decoder, self.dropped_seen = ModeDetector(), kiss.KissDecoder(), 0
