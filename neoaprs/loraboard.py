"""The line of a LoRa APRS board as the Tnc reads it (a profile whose `board` is true, tncprofile.py; aprs-reference/lora-plan.md section 3.4): a board is no TNC with a command mode, so its text is never
taken for one and no KISS ON is ever sent to it.

What comes on the line is cut into KISS frames and the text between them (`KissText`), and each is read for what it is:

- a KISS data frame is a packet, as any TNC's; on a board that says the signal (`board_readings`) DL9SAU's element of the path is taken off and read first, and a frame waits (`reading.Following`) for a
  reading said after it: esp32_loraprs's KISS command 7, once the board has sent one, or the CA2RXU iGate's list of heard packets (loralist.py) on a board on the network, while the list answers;
- any other KISS command is a line of the terminal, never a fault (esp32_loraprs sends its battery every minute);
- a line of text that is a TNC2 packet is that packet: the board was left in TNC2 text, so it is written the nudge once (the KISS frame that turns a CA2RXU Tracker on classic Bluetooth to KISS; never on
  Bluetooth LE, where the Tracker keys whatever is written to its TNC2 service as a packet) and, until a
  KISS frame comes, the radio receives and sends nothing (`TEXT_LINES`); a line that begins as a packet and cannot be AX.25 is refused with its reason; any other line is the board's log, for the terminal;
- on the CA2RXU iGate's log (`console`) a line of a packet heard is that packet with its signal, and every other line is for the terminal; nothing is ever written to that line (`RECEIVE_ONLY`);
- a frame whose path says APRS-IS is the iGate's bridge handing on the internet, not the air (`drop_internet`): it is passed over and counted."""
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
from .tncport import TncPort
from .tncprofile import Profile, names_tcp
from .tncwatchdog import TncStats
from .coded import Reason

log = logging.getLogger("neoaprs.tnc")

TEXT_LINES = Reason("the board sends text lines: set it to KISS", "radio.text_lines")
RECEIVE_ONLY = ONLY_RECEIVES
KEPT_USED = 64                         # how many entries of the board's list are remembered as given to a frame (it holds 10)
OPENING_SEC = 2.0                      # how long after the list's answer at the open no frame may come for that answer to be what the board heard before: it hands a packet on right after it lists it


class Owner(Protocol):
    """What the board's reader needs of the Tnc (tnc.py)."""
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


def printable(text: str) -> str:
    return "".join(c if c.isprintable() else "?" for c in text)


def _words(text: bytes) -> str:
    return printable(text.decode("utf-8", "replace"))


def host_of(path: str) -> str:
    """The host of a TCP line's address (`socket://192.168.1.20:8001`, an IPv6 address in brackets); "" for a line that is none."""
    if not names_tcp(path):
        return ""
    rest = path.split("://", 1)[1].rsplit(":", 1)[0]
    return rest[1:-1] if rest.startswith("[") and rest.endswith("]") else rest


class KissText:
    """The bytes of a board's line cut into KISS frames and the text outside them. A FEND opens a frame; after the FEND that closes one, a FEND or a command byte (a frame that shares its FEND) goes on in
    frames, and anything else is text again, up to the next FEND. A frame that opens with text was a FEND on its own before a line: its bytes are text."""

    def __init__(self) -> None:
        self._state = "out"              # "out" text, "in" a frame, "after" the FEND that closed one
        self._frame = bytearray()
        self.dropped = 0                  # frames the KISS decoder threw away (a bad escape, too long)

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
            if byte == 0x0A and self._frame[0] >= 0x10:          # (text after a FEND on its own: a line, not a frame)
                text.extend(self._frame)
                self._state, self._frame = "out", bytearray()
            elif len(self._frame) > 2 * kiss.MAX_FRAME:
                self.dropped += 1
                self._state, self._frame = "out", bytearray()
            return
        if not self._frame:
            return                                                  # (FEND FEND: still between frames)
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
    """The reading of one open of a board's line (made afresh by tncreader.Reader at each open)."""

    def __init__(self, tnc: Owner) -> None:
        self._tnc = tnc
        self._port = tnc._port                                         # the open it belongs to: what comes after that line is gone is no one's
        self._split = KissText()
        self._lines = LineReader()
        self._reading = NO_READING                                     # the reading of the frame being handed to the Tnc (`take_reading`)
        self.kiss_seen = False                                         # a KISS frame came on this open
        self.text_since_kiss = False                                   # a packet came as text, and no KISS frame since: nothing is sent
        self._nudged = False
        self._reports = False                                          # esp32_loraprs's command 7 came on this open: its frames wait for theirs
        self._list = tnc.profile.board_readings and tnc.profile.transport == "tcp" and bool(host_of(tnc.path))     # the iGate's list, on the board on the network: asked for until it fails once
        self._asking = self._again = False
        self._used: deque[tuple[str, str, Reading]] = deque(maxlen=KEPT_USED)
        self._start = False                                            # where this open's entries begin in the list is known: what it held at the open is in `_used`
        self._opening: tuple[list[loralist.Heard], float] | None = None  # the list's answer at the open, and when it came, until the first frame
        self._held: dict[str, tuple[bytes, str]] = {}                  # each frame that waits: its AX.25 bytes and its text as the list writes it
        self._since: deque[tuple[str, str]] = deque(maxlen=KEPT_USED)   # each frame no answer asked after it has named yet, waiting or gone on: its key and its text as the list writes it
        self._serial = 0
        self._following: Following[str] = Following(LIST_WAIT_SEC if self._list else REPORT_WAIT_SEC)
        self._timers: dict[str, asyncio.TimerHandle] = {}              # the end of the wait of each frame that waits
        if self._list and self._port is not None:
            self._ask()                                                # (what the list holds before the first frame is no frame's of this open)

    def take_reading(self) -> Reading:
        return self._reading

    def quiet(self) -> str:
        """Why nothing is sent on the line now, as a clause; "" when frames may go."""
        return RECEIVE_ONLY if self._tnc.profile.receive_only else TEXT_LINES if self.text_since_kiss else ""

    def close(self) -> None:
        """The open is over: what still waits for its reading goes no further."""
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
        if frame.command == 7 and self._tnc.profile.board_readings and (reading := signal_report(frame.payload)) is not None:
            return self._report(reading)
        self._tnc._saw(f"KISS command {frame.command} from the board: passed over ({len(frame.payload)} bytes)")

    def _data(self, payload: bytes) -> None:
        reading = None
        if self._tnc.profile.board_readings and (ninth := ninth_element(payload)) is not None:
            payload, reading = ninth                                   # (DL9SAU's element after eight digipeaters: one address more than AX.25 holds)
        try:
            frame = ax25.decode(payload)
        except ax25.Ax25Error:
            return self._hand(payload, NO_READING)                     # (the Tnc says why it is no packet)
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
        """esp32_loraprs's KISS command 7, said right after its frame: the first of an open went with a frame that did not wait for it."""
        if not self._reports:
            self._reports = True
            log.debug("%s: the board says the signal after each frame (%s); its frames wait for it from now on", self._tnc.label, reading)
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
        self._tnc._spawn(self._fetch(host_of(self._tnc.path), self._serial))

    async def _fetch(self, host: str, sent: int) -> None:
        """The list asked once `sent` frames had come on this open: the board put each of them in its list before it handed it on, so the answer holds the entry of each, if the list still has it."""
        try:
            entries = await loralist.fetch(host)
        except loralist.ListError as e:
            self._asking = False
            if self._list and self._tnc._port is self._port:
                self._list = False
                log.info("%s: the board's list of heard packets did not answer (%s): packets come without their signal", self._tnc.label, e)
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
        """Each frame that waits gets its own entry, or none. The board puts a packet in its list before it hands it on, and in the same order, so an answer asked after a frame came holds its entry
        unless the list has lost it (it keeps the last 10); the frames held after the list was asked wait for the answer asked after them, which follows. What the list holds at the open (asked before the
        first frame, which came OPENING_SEC or more after the answer) is no frame's of this open. From there the frames held since the last entry given take the entries after it one by one, each the first
        of its text: a frame that went on without its reading still takes its own, and an entry of a frame not read yet (the list's answer slower than the next packet on the air) is left for that frame.
        A frame whose entry is not in the answer goes on without, and so does each frame of its text named in this answer, one of which may hold the entry of the next; when every entry given has fallen out
        of the list, what fell out with them cannot be told: no frame asked for is named, and the list starts afresh. Without that start (a frame came while the open's answer was on its way, or right after
        it), each frame that waits takes the newest entry of its text, the latest frame first: a station that beacons the same text every few minutes leaves older entries that are none of these frames'."""
        now = self._now()
        if self._start:
            out = self._line_up(entries, sent, now)
        elif self._serial != sent:
            out = []                                                       # (a frame came after the list was asked: the answer asked after it, which follows, is for it)
        elif not sent:
            self._opening = (entries, now)
            return
        else:
            out = self._newest(entries, now)
        self._release(out + self._following.due(now))

    def _newest(self, entries: list[loralist.Heard], now: float) -> list[tuple[str, Reading]]:
        """Without a start: each frame that waits takes the newest entry of its text, the latest frame first; one whose text is not in the answer goes on without."""
        out: list[tuple[str, Reading]] = []
        for key in reversed(self._following.keys()):
            entry = next((e for e in reversed(entries) if e.key == self._held[key][1] and (e.when, e.key, e.reading) not in self._used), None)
            if entry is not None:
                self._used.append((entry.when, entry.key, entry.reading))
            out += self._following.report(NO_READING if entry is None else entry.reading, now, key)
        self._start = bool(self._used)
        self._since.clear()
        return out

    def _line_up(self, entries: list[loralist.Heard], sent: int, now: float) -> list[tuple[str, Reading]]:
        """From the start: the frames asked for take the entries after the last one given, in their order, each the first of its text; the readings of the frames that wait, said."""
        used = set(self._used)
        at = max((i for i, e in enumerate(entries) if (e.when, e.key, e.reading) in used), default=-1) + 1
        asked = list(itertools.takewhile(lambda item: int(item[0]) < sent, self._since))     # (one held after the list was asked: the answer asked after it, which follows, is for it)
        given: list[tuple[str, str, Reading]] = []
        lost: list[tuple[str, str]] = []
        if self._used and not at:
            lost = asked                                                            # (every entry given has fallen out of the list, and what fell out with them cannot be told: the list starts afresh)
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

    def _named(self, asked: list[tuple[str, str]], entries: list[loralist.Heard], at: int) -> tuple[list[tuple[str, str, Reading]], list[tuple[str, str]]]:
        """The frames asked for, each with the first entry of its text after the one before it, from `at`; and those whose text is not there (the board listed each before it handed it on: its entry
        is gone from the list)."""
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
        """A line that is a packet (with the reading its line says), a packet that cannot be one, or none."""
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
        """A packet came as text: the nudge once on this open, and nothing is sent until KISS comes."""
        tnc = self._tnc
        if tnc.profile.nudge and not self._nudged and tnc._port is not None and not tnc.profile.receive_only and not is_ble(tnc.path):     # (the Tracker over BLE keys every write on its TNC2 service: its service is chosen on the board)
            self._nudged = True
            tnc._write(tnc._port, tnc.profile.nudge)
        if not self.text_since_kiss:
            self.text_since_kiss = True
            tnc._set_problem(TEXT_LINES)
            tnc._note(TEXT_LINES)
