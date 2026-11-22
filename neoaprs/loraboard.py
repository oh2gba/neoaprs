"""Reader of the line of a LoRa APRS board (a profile with `board` true, see tncprofile.py).
A board has no TNC command mode: no KISS ON is sent. The line is split into KISS frames and text
lines; frames wait for a signal reading where the board reports one.
"""

import asyncio
import itertools
import logging
from collections import deque
from typing import Any, Coroutine, Protocol

from . import ax25, kiss, loralist
from .btle import is_ble
from .lorasignal import console_line, from_internet, list_key, ninth_element, path_reading, signal_report
from .radiotype import ONLY_RECEIVES
from .reading import LIST_WAIT_SEC, NO_READING, REPORT_WAIT_SEC, Following, Reading
from .tnc2line import LineReader, TextLine, read_line, text_of
from .tncmode import printable
from .tncport import TncPort
from .tncprofile import Profile, tcp_host
from .tncwatchdog import TncStats
from .coded import Reason

log = logging.getLogger("neoaprs.tnc")

TEXT_LINES = Reason("the board sends text lines: set it to KISS", "radio.text_lines")
RECEIVE_ONLY = ONLY_RECEIVES
# entries of the board's list (which holds 10) remembered as given to a frame
KEPT_USED = 64
# a frame this soon after the list's answer at the open is already in that answer
OPENING_SEC = 2.0


class Owner(Protocol):
    profile: Profile
    stats: TncStats
    path: str
    _port: TncPort | None

    @property
    def label(self) -> str: ...
    def _handle(self, kiss_frame: kiss.KissFrame) -> None: ...
    def _saw(self, text: str) -> None: ...
    def _note(self, text: str) -> None: ...
    def _add_line(self, text: str) -> None: ...
    def _reject(self) -> None: ...
    def _set_problem(self, text: str) -> None: ...
    def _write(self, port: TncPort, data: bytes) -> bool: ...
    def _spawn(self, coro: Coroutine[Any, Any, None]) -> "asyncio.Task[None]": ...


def _words(text: bytes) -> str:
    return printable(text.decode("utf-8", "replace"))


class KissText:
    """Split a board's byte stream into KISS frames and the text outside them.
    After a frame closes, a FEND or command byte continues in frames; anything else is text.
    """

    def __init__(self) -> None:
        # "out" text, "in" a frame, "after" the FEND that closed a frame
        self._state = "out"
        self._frame = bytearray()
        self.dropped = 0

    def feed(self, data: bytes) -> list[kiss.KissFrame | bytes]:
        out: list[kiss.KissFrame | bytes] = []
        text = bytearray()
        for byte in data:
            if self._state == "in":
                self._in(byte, out, text)
            elif byte == kiss.FEND or (self._state == "after" and byte < 0x10 and byte not in (0x0A, 0x0D)):
                self._put_text(text, out)
                self._state, self._frame = "in", bytearray(() if byte == kiss.FEND else (byte,))
            else:
                self._state = "out"
                text.append(byte)
        self._put_text(text, out)
        return out

    def _in(self, byte: int, out: list[kiss.KissFrame | bytes], text: bytearray) -> None:
        if byte != kiss.FEND:
            self._frame.append(byte)
            if byte == 0x0A and self._frame[0] >= 0x10:
                text.extend(self._frame)
                self._state, self._frame = "out", bytearray()
            elif len(self._frame) > 2 * kiss.MAX_FRAME:
                self.dropped += 1
                self._state, self._frame = "out", bytearray()
            return
        if not self._frame:
            return
        if self._frame[0] >= 0x10:
            text.extend(self._frame)
        else:
            decoder = kiss.KissDecoder()
            frames = decoder.feed(bytes([kiss.FEND]) + bytes(self._frame) + bytes([kiss.FEND]))
            self.dropped += decoder.dropped
            self._put_text(text, out)
            out.extend(frames)
        self._state, self._frame = "after", bytearray()

    @staticmethod
    def _put_text(text: bytearray, out: list[kiss.KissFrame | bytes]) -> None:
        if text:
            out.append(bytes(text))
            text.clear()


class LoraBoard:
    """The reading of one open of a board's line; a new one is made at each open."""

    def __init__(self, tnc: Owner) -> None:
        self._tnc = tnc
        # anything after this open's line is gone is ignored
        self._port = tnc._port
        self._split = KissText()
        self._lines = LineReader()
        self._reading = NO_READING
        self.kiss_seen = False
        self.text_since_kiss = False
        self._nudged = False
        # esp32_loraprs's command 7 came on this open: frames wait for their readings
        self._reports = False
        # the iGate's list of heard packets, used until it fails once
        self._list = tnc.profile.board_readings and tnc.profile.transport == "tcp" and bool(tcp_host(tnc.path))
        self._asking = self._again = False
        self._used: deque[tuple[str, str, Reading]] = deque(maxlen=KEPT_USED)
        self._start = False  # the position of this open's entries in the list is known
        # the list's answer at the open and its time, until the first frame arrives
        self._opening: tuple[list[loralist.Heard], float] | None = None
        # each waiting frame: AX.25 bytes and text as the list writes it
        self._held: dict[str, tuple[bytes, str]] = {}
        # frames not yet named by an answer asked after them
        self._since: deque[tuple[str, str]] = deque(maxlen=KEPT_USED)
        self._serial = 0
        self._following: Following[str] = Following(LIST_WAIT_SEC if self._list else REPORT_WAIT_SEC)
        self._timers: dict[str, asyncio.TimerHandle] = {}
        if self._list and self._port is not None:
            # what the list held before the first frame belongs to no frame
            self._ask()

    def take_reading(self) -> Reading:
        return self._reading

    def quiet(self) -> str:
        """Return why nothing is sent on the line now, or "" when frames may go."""
        return RECEIVE_ONLY if self._tnc.profile.receive_only else TEXT_LINES if self.text_since_kiss else ""

    def close(self) -> None:
        """End the open; frames still waiting for a reading are dropped."""
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()

    def read(self, chunk: bytes) -> None:
        dropped = self._split.dropped
        for item in self._split.feed(chunk):
            if isinstance(item, kiss.KissFrame):
                self._kiss(item)
            else:
                self._text(item)
        if self._split.dropped > dropped:
            self._tnc.stats.rejected += self._split.dropped - dropped
            self._tnc._note(f"{self._split.dropped - dropped} damaged KISS frame(s) dropped")

    # ---- KISS
    def _kiss(self, frame: kiss.KissFrame) -> None:
        self.kiss_seen = True
        if self.text_since_kiss:
            self.text_since_kiss = False
            self._tnc._set_problem("")
            self._tnc._note("the board sends KISS")
        if frame.command == 0:
            return self._data(frame.payload)
        if (
            frame.command == 7
            and self._tnc.profile.board_readings
            and (reading := signal_report(frame.payload)) is not None
        ):
            return self._report(reading)
        self._tnc._saw(f"KISS command {frame.command} from the board: passed over ({len(frame.payload)} bytes)")

    def _data(self, payload: bytes) -> None:
        reading = None
        if self._tnc.profile.board_readings and (ninth := ninth_element(payload)) is not None:
            # DL9SAU's ninth path element, beyond what AX.25 allows
            payload, reading = ninth
        try:
            frame = ax25.decode(payload)
        except ax25.Ax25Error:
            return self._hand(payload, NO_READING)
        if self._tnc.profile.drop_internet and from_internet(frame):
            return self._tnc._saw(printable(f"from the internet, not heard on the air: passed over: {frame.tnc2()}"))
        if self._tnc.profile.board_readings:
            bare, first = path_reading(frame)
            if first is not None:
                frame, payload, reading = bare, ax25.encode(bare), first
        if not (self._reports or self._list or self._following.waiting()):
            return self._hand(payload, reading or NO_READING)
        key = self._hold(payload, frame)
        if reading is not None:
            self._release(self._following.report(reading, self._now(), key))
        elif self._list:
            self._ask()

    def _report(self, reading: Reading) -> None:
        """Handle esp32_loraprs's KISS command 7, sent right after its frame."""
        if not self._reports:
            self._reports = True
            log.debug(
                "%s: the board says the signal after each frame (%s); its frames wait for it from now on",
                self._tnc.label,
                reading,
            )
            return
        self._release(self._following.report(reading, self._now()))

    def _hold(self, payload: bytes, frame: ax25.Frame) -> str:
        if self._opening is not None:
            entries, came = self._opening
            self._opening = None
            if self._now() - came >= OPENING_SEC:
                self._used.extend((e.when, e.key, e.reading) for e in entries)
                self._start = True
        key = str(self._serial)
        self._serial += 1
        self._held[key] = (payload, list_key(text_of(frame)))
        self._since.append((key, self._held[key][1]))
        self._following.hold(key, key, self._now())
        self._timers[key] = asyncio.get_running_loop().call_later(self._following.wait_sec + 0.01, self._due)
        return key

    def _due(self) -> None:
        if self._tnc._port is self._port:
            self._release(self._following.due(self._now()))

    def _release(self, frames: list[tuple[str, Reading]]) -> None:
        for key, reading in frames:
            payload, _ = self._held.pop(key)
            if (timer := self._timers.pop(key, None)) is not None:
                timer.cancel()
            self._hand(payload, reading)

    def _hand(self, payload: bytes, reading: Reading) -> None:
        self._reading = reading
        try:
            self._tnc._handle(kiss.KissFrame(0, 0, payload))
        finally:
            self._reading = NO_READING

    @staticmethod
    def _now() -> float:
        return asyncio.get_running_loop().time()

    # ---- the CA2RXU iGate's list of heard packets
    def _ask(self) -> None:
        if self._asking:
            self._again = True
            return
        self._asking = True
        self._tnc._spawn(self._fetch(tcp_host(self._tnc.path), self._serial))

    async def _fetch(self, host: str, sent: int) -> None:
        """Ask the list once `sent` frames have come on this open."""
        try:
            entries = await loralist.fetch(host)
        except loralist.ListError as e:
            self._asking = False
            if self._list and self._tnc._port is self._port:
                self._list = False
                log.info(
                    "%s: the board's list of heard packets did not answer (%s): packets come without their signal",
                    self._tnc.label,
                    e,
                )
                self._release(self._following.release())
            return
        self._asking = False
        if self._tnc._port is not self._port:
            return
        self._match(entries, sent)
        if self._again:
            self._again = False
            self._ask()

    def _match(self, entries: list[loralist.Heard], sent: int) -> None:
        """Give each waiting frame its own list entry, or none.
        An answer asked after a frame holds its entry unless it fell out of the list.
        """
        now = self._now()
        if self._start:
            out = self._line_up(entries, sent, now)
        elif self._serial != sent:
            # a frame came after the list was asked: the next answer is for it
            out = []
        elif not sent:
            self._opening = (entries, now)
            return
        else:
            out = self._newest(entries, now)
        self._release(out + self._following.due(now))

    def _newest(self, entries: list[loralist.Heard], now: float) -> list[tuple[str, Reading]]:
        out: list[tuple[str, Reading]] = []
        for key in reversed(self._following.keys()):
            entry = next(
                (
                    e
                    for e in reversed(entries)
                    if e.key == self._held[key][1] and (e.when, e.key, e.reading) not in self._used
                ),
                None,
            )
            if entry is not None:
                self._used.append((entry.when, entry.key, entry.reading))
            out += self._following.report(NO_READING if entry is None else entry.reading, now, key)
        self._start = bool(self._used)
        self._since.clear()
        return out

    def _line_up(self, entries: list[loralist.Heard], sent: int, now: float) -> list[tuple[str, Reading]]:
        used = set(self._used)
        at = max((i for i, e in enumerate(entries) if (e.when, e.key, e.reading) in used), default=-1) + 1
        asked = list(itertools.takewhile(lambda item: int(item[0]) < sent, self._since))
        given: list[tuple[str, str, Reading]] = []
        lost: list[tuple[str, str]] = []
        if self._used and not at:
            # every entry given has fallen out: start afresh
            lost = asked
            self._used.clear()
            self._used.extend((e.when, e.key, e.reading) for e in entries)
        else:
            given, lost = self._named(asked, entries, at)
        self._since = deque((item for item in self._since if int(item[0]) >= sent), maxlen=KEPT_USED)
        waiting, lost_texts = set(self._following.keys()), {text for _, text in lost}
        out: list[tuple[str, Reading]] = []
        for key, text, reading in given + [(key, text, NO_READING) for key, text in lost]:
            if key in waiting:
                out += self._following.report(NO_READING if text in lost_texts else reading, now, key)
        return out

    def _named(
        self, asked: list[tuple[str, str]], entries: list[loralist.Heard], at: int
    ) -> tuple[list[tuple[str, str, Reading]], list[tuple[str, str]]]:
        """Return the frames matched to entries from `at` on, and those without one."""
        given: list[tuple[str, str, Reading]] = []
        lost: list[tuple[str, str]] = []
        for key, text in asked:
            found = next((i for i in range(at, len(entries)) if entries[i].key == text), None)
            if found is None:
                lost.append((key, text))
                continue
            entry, at = entries[found], found + 1
            self._used.append((entry.when, entry.key, entry.reading))
            given.append((key, text, entry.reading))
        return given, lost

    # ---- text
    def _text(self, data: bytes) -> None:
        tnc = self._tnc
        for line in self._lines.feed(data):
            if tnc.profile.text_lines == "console":
                found = console_line(line.text)
                if found is None:
                    tnc._add_line(_words(line.text))
                else:
                    self._packet_line(read_line(found[0]), found[1] or NO_READING)
            elif tnc.profile.text_lines == "tnc2" and (line.frame is not None or line.why):
                self._as_text()
                self._packet_line(line, NO_READING)
            else:
                tnc._add_line(_words(line.text))

    def _packet_line(self, line: TextLine, reading: Reading) -> None:
        """Handle a text line: a packet, a malformed packet, or terminal text."""
        tnc = self._tnc
        if line.frame is None and line.why:
            tnc._saw(f"not taken: {line.why}: {_words(line.text)}")
            tnc._reject()
        elif line.frame is None:
            tnc._add_line(_words(line.text))
        elif tnc.profile.drop_internet and from_internet(line.frame):
            tnc._saw(printable(f"from the internet, not heard on the air: passed over: {line.frame.tnc2()}"))
        else:
            self._hand(ax25.encode(line.frame), reading)

    def _as_text(self) -> None:
        """Handle a packet that came as text: nudge once per open; send nothing until KISS comes."""
        tnc = self._tnc
        # over BLE the Tracker transmits every write to its TNC2 service: never nudge there
        if (
            tnc.profile.nudge
            and not self._nudged
            and tnc._port is not None
            and not tnc.profile.receive_only
            and not is_ble(tnc.path)
        ):
            self._nudged = True
            tnc._write(tnc._port, tnc.profile.nudge)
        if not self.text_since_kiss:
            self.text_since_kiss = True
            tnc._set_problem(TEXT_LINES)
            tnc._note(TEXT_LINES)
