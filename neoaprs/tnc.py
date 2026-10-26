"""The one source: the serial line, the KISS decoder, the AX.25 decoder and the APRS parser in a row, emitting packets.

What is said to the TNC comes from its profile (tncprofile.py): the steps that switch it to KISS, the frame that takes it out again, whether it may be asked if it is there, and whether text from it means
command mode. A profile that cannot be asked is sent nothing but KISS frames: no entry, no keep-alive, no carriage return, no silent state.

The Kenwood TH-D7's TNC starts in command mode (it prints heard packets as TNC2 text and answers a carriage return with "cmd:"). `ModeDetector` (tncmode.py) tells that from a KISS stream, and the `Tnc`
switches the radio to KISS ("KISS ON", "RESTART") when it finds it in command mode, once for every answer it gets: a fresh open, a return from SILENT and each check or probe of the keep-alive allow one entry.
A TNC that goes on typing text after the entry has settled is sent it again, later and later each time (`EntryAgain`, tncwatchdog.py), and nothing is sent to it meanwhile. A port that is not given by name is
found by listening to all the ports that match a pattern at the same time, for as long as it takes (a TNC in KISS mode sends nothing until it hears a packet); the search hands over what the port said, and a TNC
it found typing command-mode text is put into KISS right at the open: its bytes show that the radio is there, not that it speaks KISS, and the entry is the one its next line would have made, without a frame being
typed into it first. A line that goes quiet after it was opened is looked after by the keep-alive (tncwatchdog.py).

SILENT: the line is open, but the radio does not answer (it is switched off; the USB adapter is still there). The keep-alive's check sends the KISS exit frame, a carriage return and KISS ON, and a radio that
is on answers that with text within a second or two; when no byte at all comes within `answer_sec` the Tnc is SILENT. It sends nothing while SILENT (`usable` is False) and the keep-alive probes the line every
`probe_sec`. The first byte that arrives from the line, whatever it is, ends it: the allowance to enter KISS is given back, the mode detector starts over, and the Tnc enters KISS unless the bytes are a KISS frame
already or a piece of one (a FEND among them: a line delivers a frame in several reads, and command-mode text has no FEND), when what follows decides. The Tnc is `usable` only when CONNECTED and not settling: not
while a check is under way and not for the settle time after the entry, so that no frame is typed into a TNC in command mode.

A fresh open of a line to a TNC that can be asked is not `usable` until the radio has shown that it is there (`confirmed`): the keep-alive makes its check at once, the first byte that arrives from the line, a packet or the
answer to the check, confirms, and no answer within the check's answer time makes the Tnc SILENT. A USB adapter is there with the radio switched off, so an open line proves nothing. With the checks off
(`check_sec` 0) nothing is asked and the line is usable as soon as it is open, as it is for a profile that cannot be asked."""
import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from . import ax25, kiss, serialprobe
from .clock import Clock, utcnow
from .dummyline import DUMMY_PATH, DummyPort
from .interlock import Interlock
from .packet import Packet
from .policy import TNC_CHECK_SEC
from .serialholders import held_by
from .serialport import SerialError, is_socket
from .signal import Signal
from .source import CHECKING, Backoff, Source, minutes_between, unusable_because
from .tncentry import KissEntry
from .tncfollow import AdapterFollow
from .tnclines import TimedSource
from .tncmode import Mode, ModeDetector, looks_valid, packet_of, read_frame
from .tncport import TncPort
from .tncreader import Reader
from .tncsearch import PortSearch
from .tncprofile import KENWOOD_TNC2, KISS_EXIT as KISS_EXIT, Profile
from .tncwatchdog import ANSWER_SEC, CHECK_PAUSE_SEC, PROBE_SEC, PROMPT, REPLY_SEC, TncStats, Watchdog

log = logging.getLogger("neoaprs.tnc")

COMMAND_MODE = "the TNC is in command mode (KISS ON is sent again)"
ENTER_KISS = KENWOOD_TNC2.enter[0][0]       # what the default profile writes (the Kenwood TNC-2's), for the tests


def _speed(path: str, baud: int) -> str:
    """" at 9600" for a serial line; a TCP line and the dummy radio have no speed."""
    return "" if is_socket(path) or path == DUMMY_PATH else f" at {baud}"


async def open_port(tnc: "Tnc", path: str) -> TncPort | DummyPort:
    """The line at `path`, open: the Dummy radio's, or a serial port (a socket) of the Tnc's speed. Raises SerialError."""
    port = DummyPort(tnc._on_data, tnc._on_lost, tnc.where, tnc.clock) if tnc.is_dummy else TncPort(path, tnc.baud, tnc._on_data, tnc._on_lost)
    await port.open()
    return port


def _printable(text: str) -> str:
    return "".join(c if c.isprintable() else "?" for c in text)


def _describe(tnc: "Tnc") -> str:
    """The Tnc in a few words, for the radio's status line."""
    if tnc.is_dummy:
        return f"dummy radio, made-up traffic, {tnc.stats.packets} packets, nothing goes on the air"
    if tnc.state is Source.State.SILENT and tnc.last_byte_at is not None:
        return f"silent since {tnc.last_byte_at:%H:%M} ({minutes_between(tnc.last_byte_at, tnc.now())})"
    if tnc.searching:
        return f"listening on {', '.join(tnc.searching)} for the radio"
    if tnc._port is None:
        return f"{tnc.path or tnc.port or 'no port'}{_speed(tnc.path or tnc.port, tnc.baud)}, {tnc.state.value}"
    mode = "KISS" if tnc._reader.kiss_seen else ("entering KISS" if tnc._reader.entered else "listening")
    return f"{tnc.path}{_speed(tnc.path, tnc.baud)}, {mode}, {tnc.stats.packets} packets"


def _why_unusable(tnc: "Tnc") -> str:
    """Why nothing is sent now, as a clause: a fresh line not yet confirmed, a TNC that types text (it is in command mode, KISS ON is sent again), else what the state says."""
    if tnc.state is Source.State.CONNECTED and not tnc.confirmed:
        return CHECKING
    if tnc.state is Source.State.CONNECTED and tnc._reader.command_mode_unanswered():
        return COMMAND_MODE
    return unusable_because(tnc.state)


class Tnc(TimedSource):
    stats: TncStats

    def __init__(self, port: str = "", baud: int = 9600, profile: Profile = KENWOOD_TNC2, pattern: str = "", clock: Clock = utcnow, probe_seconds: float = 0.0,
                 backoff: Backoff | None = None, settle_sec: float | None = None, pace: float = 1.0, fallback_probe: bool = True, probe_nudge_sec: float = 10.0,
                 skip: tuple[str, ...] = (), check_sec: float = TNC_CHECK_SEC, check_pause_sec: float = CHECK_PAUSE_SEC, reply_sec: float = REPLY_SEC, answer_sec: float = ANSWER_SEC, probe_sec: float = PROBE_SEC) -> None:
        super().__init__("tnc", clock)
        self.stats = TncStats()
        self.port, self.baud, self.profile, self.pattern = port, baud, profile, pattern or serialprobe.search_pattern()
        self.probe_seconds = probe_seconds                                                                 # the whole wait of the search, 0 = no limit
        self.probe_nudge_sec, self.skip = probe_nudge_sec, skip          # how long the search listens before it sends a carriage return to the ports; the device paths it never opens (the operator's serial/skip)
        self.where: Callable[[], tuple[float, float] | None] = lambda: None   # the station's position (latitude, longitude), for the Dummy radio's traffic to be made round it (set by app.py)
        self.interlock: Interlock | None = None                          # the transmit interlock (neoaprs/interlock.py, set by app.py): while it refuses, no frame is sent; none when not given
        self.fallback_probe, self._probe_next = fallback_probe, False    # a port that was named and cannot be opened: the next attempt listens to the ports that match the pattern instead
        self.backoff = backoff or Backoff()
        self.packet: Signal[[Packet]] = Signal("tnc.packet")             # every packet in and out
        self.path = ""                                                   # the port in use
        self._search = PortSearch(self._spawn, self._note, PROMPT)
        self._entry = KissEntry(self._spawn, lambda data: self._port is not None and self._write(self._port, data), settle_sec, pace)    # the wait after the last step (None: the profile's), the factor on the others
        self._port: TncPort | None = None
        self._follow = AdapterFollow()                                   # the USB adapter of the named port, found again when the system gives it another name
        self._generation = 0                                             # changes at stop(), so that an attempt that was under way knows it is over
        self._watchdog_task: asyncio.Task[None] | None = None
        self.watchdog = Watchdog(self, check_sec, check_pause_sec, reply_sec, answer_sec, probe_sec)    # check_sec 0: no checks
        self.last_watchdog_action = ""                                   # "check", "probe" or "reopen"; empty until the watchdog has done anything
        self.last_watchdog_at: datetime | None = None
        self._reader = Reader(self)                                      # what the bytes of the open line say: the mode, the entry into KISS, the frames (tncreader.py)
        self._open_reset()

    def _open_reset(self) -> None:
        """What belongs to one open of the line."""
        self._reader.reset()
        self.confirmed = not (self.profile.can_probe and self.profile.detect_command_mode and self.watchdog.sec > 0)     # a byte came on this open, or nothing is asked (the checks off, a profile that cannot be asked): until then a TNC that can be asked is not `usable`

    # ---- life
    async def start(self) -> None:
        if self.state is not Source.State.STOPPED:
            await self.stop()
        self._probe_next = False
        await self._connect()

    async def stop(self) -> None:
        self._generation += 1
        await self._cancel_tasks()
        port, self._port = self._port, None
        if port is not None:
            port.close()
        self._watchdog_task = None
        self.watchdog.probes = 0
        self._set_state(Source.State.STOPPED)

    async def _connect(self, reopen: str = "", silent: bool = False) -> None:
        """Opens the line: `reopen` is the path to open again (the keep-alive's, which says nothing of it above DEBUG and keeps a silent radio silent), else the named port, else the one the search finds."""
        generation = self._generation
        self._set_state(Source.State.CONNECTING)
        named = bool(reopen or self.port) and not self._probe_next       # (a probe attempt is followed by one at the named port again)
        self._probe_next = False
        try:
            found = await self._find_line(reopen, named, generation)
        except SerialError as e:
            self._probe_next = named and self.fallback_probe and self._search.possible
            self._wait(str(e))
            return
        except Exception as e:
            log.exception("tnc: connecting failed")
            self._wait(f"{type(e).__name__}: {e}")
            return
        if found is not None:
            self._opened(*found, named, reopen, silent)

    async def _find_line(self, reopen: str, named: bool, generation: int) -> tuple[TncPort | DummyPort, str, bytes] | None:
        """The line, open, with its path and what the search heard on it; None when `stop` came meanwhile. Raises SerialError."""
        path, heard = (reopen or self.port, b"") if named else await self._search.find(self.pattern, self.baud, self.probe_seconds, lambda heard: looks_valid(heard, self.profile.detect_command_mode), self.profile.can_probe, self.probe_nudge_sec, self.skip, lambda: generation == self._generation, self.port)     # (`heard`: what the search heard from the port it chose; the named port is listened to as well)
        if generation != self._generation:
            return None
        if named and not self.is_dummy and (held := held_by(path)):
            raise SerialError(f"{path}: {held}")
        port, path = await self._follow.open(path, named and not self.is_dummy, lambda where: open_port(self, where), self._note)
        return port, path, heard

    def _opened(self, port: TncPort | DummyPort, path: str, heard: bytes, named: bool, reopen: str, silent: bool) -> None:
        """The line is open: its state starts over, and a TNC that the search found in command mode is put into KISS at once."""
        self._port, self.path = port, path
        self._open_reset()
        self.confirmed = self.confirmed or not named                     # (a port the search chose has just been heard from)
        self.last_byte_at = self.last_byte_at or self.now()
        self.stats.opens += 1
        self.backoff.connected()
        self._set_state(Source.State.SILENT if silent else Source.State.CONNECTED)
        if not reopen:
            self._note(f"opened {path}{_speed(path, self.baud)}")
        log.log(logging.DEBUG if reopen else logging.INFO, "tnc: opened %s%s", path, _speed(path, self.baud))
        if heard and self.profile.detect_command_mode and ModeDetector().feed(heard) is Mode.MONITOR:
            self._reader.enter_kiss(port, "the search found the TNC in command mode")
        self._start_watchdog()

    def _wait(self, problem: str) -> None:
        delay = self.backoff.next_delay_sec()
        self.watchdog.probes = 0
        log.warning("tnc: %s; trying again in %g s", problem, delay)
        self._set_state(Source.State.WAITING, problem)
        self._note(f"{problem}; trying again in {delay:g} s")
        self._spawn(self._retry(delay))

    async def _retry(self, delay: float) -> None:
        await asyncio.sleep(delay)
        await self._connect()

    def _on_lost(self, port: TncPort, reason: str) -> None:
        if port is not self._port:
            return
        self._port = None
        self._drop_tasks()
        self._wait(f"{port.path} lost: {reason}")

    def _drop_tasks(self) -> None:
        """Ends the watch of the line, which is gone or is to be watched afresh (not the task that is asking, which is on its way out)."""
        watchdog, self._watchdog_task = self._watchdog_task, None
        if watchdog is not None and watchdog is not asyncio.current_task():
            watchdog.cancel()

    # ---- reading
    def _on_data(self, port: TncPort, chunk: bytes) -> None:
        if port is self._port:
            self._reader.read(port, chunk)

    def _handle(self, kiss_frame: kiss.KissFrame) -> None:
        read = read_frame(kiss_frame, self.now(), self.is_dummy)
        if isinstance(read, str):
            self._saw(f"rejected, {read}: {kiss_frame.payload[:40].hex()}")
            return self._reject()
        packet, frame = read
        self.stats.packets += 1
        self.stats.last_packet = packet.heard_at
        self._saw(_printable(f"{frame.tnc2()}  ->  {packet.summary}"))
        self.packet.emit(packet)

    # ---- the keep-alive (tncwatchdog.py decides when; these are the actions)
    def set_check(self, seconds: float) -> None:
        """Puts a new quiet period in force (0 = no checks), now, on the line that is open; with the checks off a line that waits to be confirmed is usable."""
        self.watchdog.sec = seconds
        self.confirmed = self.confirmed or seconds <= 0
        self._start_watchdog()

    def _start_watchdog(self) -> None:
        self._drop_tasks()
        port = self._port
        if port is not None and self.profile.can_probe and self.profile.detect_command_mode and (self.watchdog.sec > 0 or self.state is Source.State.SILENT):
            self.watchdog.opened()
            self._watchdog_task = self._spawn(self.watchdog.run(lambda: port is self._port, not self.confirmed))

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED and self.confirmed and not self._reader.looking and not self._reader.command_mode_unanswered() and asyncio.get_running_loop().time() >= self._reader.settle_until

    describe, why_unusable = _describe, _why_unusable
    _looking, _entered = property(lambda self: self._reader.looking), property(lambda self: self._reader.entered)      # (what a test looks at)
    is_dummy = property(lambda self: self.profile.transport == "dummy")      # the Dummy profile: it makes up traffic to try the program with, and every packet it hears or sends is marked `dummy` (packet.DUMMY), which never goes to the internet (packet.GATEABLE)

    def look_begin(self) -> bool:
        """A check or probe starts: nothing is sent meanwhile and the TNC is asked afresh. False when there is no line."""
        if self._port is None:
            return False
        self._reader.asked_afresh()
        return True

    def look_send(self, data: bytes) -> bool:
        return self._port is not None and self._write(self._port, data)

    def look_enter_kiss(self) -> None:
        """KISS ON, unless an answer already made the Tnc enter it, or the answer was a KISS frame (the TNC did not leave KISS for the exit frame: it is in KISS already, and the entry would only cost reception)."""
        if self._port is not None and not self._reader.entered and not self._reader.kiss_seen:
            self._reader.enter_kiss(self._port, "the keep-alive asked the TNC", logging.DEBUG, note=False)

    def look_end(self) -> None:
        self._reader.looking = False

    async def reopen_port(self) -> None:
        """The line is closed and the same path opened again (a USB adapter that dropped); a radio that was silent stays silent. A path that cannot be opened is a failed open, which is followed by the search for the radio."""
        port, self._port = self._port, None
        if port is not None:
            silent = self.state is Source.State.SILENT
            self._drop_tasks()
            port.close()
            await self._connect(reopen=port.path, silent=silent)

    # ---- writing
    def _write(self, port: TncPort, data: bytes) -> bool:
        try:
            port.write(data)
        except SerialError as e:
            self._note(f"write failed: {e}")
            port.fail(str(e))
            return False
        self.stats.bytes_out += len(data)
        return True

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        """Sends the frame; `raw` is its bytes when they are to go as they are (the digipeater's: what was heard with only the path changed)."""
        return self._transmit(ax25.encode(frame) if raw is None else raw, frame)

    async def send(self, data: bytes) -> bool:
        try:
            frame = ax25.decode(data)
        except ax25.Ax25Error as e:
            self._note(f"not sent, not an AX.25 frame: {e}")
            return False
        return self._transmit(data, frame)

    def _transmit(self, raw: bytes, frame: ax25.Frame) -> bool:
        if self.interlock is not None and self.interlock.refused("frame"):
            return False
        port = self._port
        if not self.usable or port is None:
            self._note(f"not sent: {self.why_unusable()}")
            return False
        if not self._write(port, kiss.encode(raw)):
            return False
        packet = packet_of("out", raw, frame, self.now(), self.is_dummy)
        self._note(_printable(f"sent {frame.tnc2()}"))
        self.packet.emit(packet)
        return True

    @property
    def searching(self) -> list[str]:
        """The ports the search for the radio is listening to; none while a port is open or no search is under way."""
        return list(self._search.listening) if self._port is None else []
