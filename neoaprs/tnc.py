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
from .interlock import Interlock
from .packet import Packet
from .policy import TNC_CHECK_SEC
from .serialholders import held_by
from .serialport import SerialError, SerialPort, is_socket
from .signal import Signal
from .source import CHECKING, Backoff, Source, minutes_between, unusable_because
from .tncentry import KissEntry
from .tnclines import TimedSource
from .tncmode import Mode, ModeDetector, TextAfterKiss, looks_valid, packet_of, read_frame
from .tncsearch import PortSearch
from .tncprofile import KENWOOD_TNC2, KISS_EXIT as KISS_EXIT, Profile
from .tncwatchdog import ANSWER_SEC, CHECK_PAUSE_SEC, PROBE_SEC, PROMPT, REPLY_SEC, EntryAgain, TncStats, Watchdog

log = logging.getLogger("neoaprs.tnc")

COMMAND_MODE = "the TNC is in command mode (KISS ON is sent again)"
ENTER_KISS = KENWOOD_TNC2.enter[0][0]       # what the default profile writes (the Kenwood TNC-2's), for the tests


class _TncPort(SerialPort):
    """A serial port that hands its bytes and its death to the Tnc that owns it by plain callbacks, not signals."""

    def __init__(self, path: str, baud: int, on_data: Callable[["_TncPort", bytes], None], on_lost: Callable[["_TncPort", str], None]) -> None:
        super().__init__(path, baud)
        self._on_data = on_data
        self._on_lost = on_lost

    def _deliver(self, chunk: bytes) -> None:
        self._on_data(self, chunk)

    def _lost(self, reason: str) -> None:
        super()._lost(reason)
        self._on_lost(self, reason)

    def fail(self, reason: str) -> None:
        """A write failed: the line counts as lost, like a read that failed."""
        if self.is_open:
            self._lost(reason)


def _speed(path: str, baud: int) -> str:
    """" at 9600" for a serial line; a TCP line has no speed."""
    return "" if is_socket(path) else f" at {baud}"


def _printable(text: str) -> str:
    return "".join(c if c.isprintable() else "?" for c in text)


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
        self.interlock: Interlock | None = None                          # the transmit interlock (neoaprs/interlock.py, set by app.py): while it refuses, no frame is sent; none when not given
        self.fallback_probe, self._probe_next = fallback_probe, False    # a port that was named and cannot be opened: the next attempt listens to the ports that match the pattern instead
        self.backoff = backoff or Backoff()
        self.packet: Signal[[Packet]] = Signal("tnc.packet")             # every packet in and out
        self.path, self.dummy = "", False                                # the port in use; whether the radio is the Dummy one (it makes up traffic to try the program with): its packets are marked `dummy` and are never gated to the internet (packet.GATEABLE)
        self._search = PortSearch(self._spawn, self._note, PROMPT)
        self._entry = KissEntry(self._spawn, lambda data: self._port is not None and self._write(self._port, data), settle_sec, pace)    # the wait after the last step (None: the profile's), the factor on the others
        self._port: _TncPort | None = None
        self._generation = 0                                             # changes at stop(), so that an attempt that was under way knows it is over
        self._watchdog_task: asyncio.Task[None] | None = None
        self.watchdog = Watchdog(self, check_sec, check_pause_sec, reply_sec, answer_sec, probe_sec)    # check_sec 0: no checks
        self.last_watchdog_action = ""                                   # "check", "probe" or "reopen"; empty until the watchdog has done anything
        self.last_watchdog_at: datetime | None = None
        self._open_reset()

    def _open_reset(self) -> None:
        """What belongs to one open of the line."""
        self._detector = ModeDetector()
        self._decoder = kiss.KissDecoder()
        self._dropped_seen = 0
        self._entered = self._kiss_seen = self._told_text = False        # KISS ON was sent on this open; a KISS frame came since; the text that came after the entry has been told
        self._again = EntryAgain()                                       # when the entry is repeated for a TNC that still types text
        self._typed = TextAfterKiss()                                    # text after KISS frames: the radio was restarted
        self.confirmed = not (self.profile.can_probe and self.profile.detect_command_mode and self.watchdog.sec > 0)     # a byte came on this open, or nothing is asked (the checks off, a profile that cannot be asked): until then a TNC that can be asked is not `usable`
        self._settle_until = 0.0
        self._looking = False                                            # a check or probe is under way: nothing is sent, and the keep-alive itself enters KISS

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
            path, heard = (reopen or self.port, b"") if named else await self._search.find(self.pattern, self.baud, self.probe_seconds, lambda heard: looks_valid(heard, self.profile.detect_command_mode), self.profile.can_probe, self.probe_nudge_sec, self.skip, lambda: generation == self._generation, self.port)     # (`heard`: what the search heard from the port it chose; the named port is listened to as well)
            if generation != self._generation:
                return
            if named and (held := held_by(path)):
                raise SerialError(f"{path}: {held}")
            port = _TncPort(path, self.baud, self._on_data, self._on_lost)
            await port.open()
        except SerialError as e:
            self._probe_next = named and self.fallback_probe and self._search.possible
            self._wait(str(e))
            return
        except Exception as e:
            log.exception("tnc: connecting failed")
            self._wait(f"{type(e).__name__}: {e}")
            return
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
            self._enter_kiss(port, "the search found the TNC in command mode")
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

    def _on_lost(self, port: _TncPort, reason: str) -> None:
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
    def _on_data(self, port: _TncPort, chunk: bytes) -> None:
        if port is not self._port:
            return
        loop_now = asyncio.get_running_loop().time()
        self.stats.bytes_in += len(chunk)
        typed = self._typed.feed(chunk)                                  # (text since the latest FEND: after KISS frames, the radio was restarted)
        self.confirmed = True
        self.watchdog.heard()
        mode = self._heard(port, chunk, loop_now)
        if loop_now < self._settle_until:
            return
        if typed and mode is Mode.KISS and self._kiss_seen and self.profile.detect_command_mode:
            self._kiss_seen = self._told_text = False                    # switched to KISS again now, not at the next check: text keeps the line from going quiet
            return self._enter_kiss(port, "the TNC is in command mode again (the radio was restarted)")
        if mode is Mode.KISS:
            if self._told_text and not self._kiss_seen:                  # (KISS at last after text: the problem it made is over)
                self._told_text = False
                self._set_problem("")
            self._kiss_seen = True
            self._again.reset()
        elif mode is Mode.MONITOR:
            self._command_mode(port)
            if loop_now < self._settle_until or self._port is not port:
                return
        for frame in self._decoder.feed(chunk):
            self._handle(frame)
        if self._decoder.dropped > self._dropped_seen:
            self.stats.rejected += self._decoder.dropped - self._dropped_seen
            self._note(f"{self._decoder.dropped - self._dropped_seen} damaged KISS frame(s) dropped")
            self._dropped_seen = self._decoder.dropped

    def _heard(self, port: _TncPort, chunk: bytes, loop_now: float) -> Mode | None:
        """Bytes came: what the detector makes of them, None while an entry settles (they are thrown away). From a silent radio, which may have been switched on (a TH-D7 starts with its TNC in command mode),
        the allowance to enter KISS is given back and the detector starts over; KISS is entered unless the bytes are a KISS frame already, or a piece of one (a FEND among them and no whole frame: a line
        delivers a frame in several reads, and command-mode text never has a FEND), when what follows decides, or an entry of the keep-alive's own is settling."""
        if self.state is not Source.State.SILENT:
            self._hear()
            return None if loop_now < self._settle_until else self._detector.feed(chunk)
        if loop_now < self._settle_until:
            self._hear("; entering KISS")
            return None
        self._entered = self._kiss_seen = self._told_text = False
        self._again.reset()
        self._detector.rearm()
        piece = kiss.FEND in chunk
        mode = self._detector.feed(chunk[chunk.index(kiss.FEND):] if piece else chunk)      # (what is before the first FEND is the tail of a frame, never text)
        enter = self.profile.detect_command_mode and mode is not Mode.KISS and not piece
        self._hear("; entering KISS" if enter else "")
        if enter:
            self._enter_kiss(port, "the radio answers again", logging.DEBUG, note=False)
        return mode

    def _command_mode(self, port: _TncPort) -> None:
        if self._looking:
            return
        if self.profile.detect_command_mode and not self._entered:
            self._enter_kiss(port, "the TNC was in command mode")
        elif self.profile.detect_command_mode and not self._kiss_seen and self._again.due(asyncio.get_running_loop().time(), self._settle_until):
            why, level = self._again.repeat()
            self._enter_kiss(port, why, level)
        elif not self._told_text:
            self._told_text = True
            self._set_problem("the TNC sends text, not KISS frames: it is in command mode" + (" and the entry did not change that" if self._entered else f" and the profile {self.profile.name!r} does not enter KISS"))
            self._note(self.problem)

    def _enter_kiss(self, port: _TncPort, why: str = "the TNC was in command mode", level: int = logging.INFO, note: bool = True) -> None:
        """The profile's steps (KISS ON and RESTART for a TNC-2), then the settle time of throwing away what the TNC says. `level` is the log's (DEBUG for a check or a return from SILENT, which have told their
        own news, and for the later repeats of the entry); `note`: whether the terminal gets a line too (not for the check and the return from SILENT)."""
        self._entered = True
        log.log(level, "entering KISS mode on %s: %s", port.path, why)
        if note:
            self._note(f"entering KISS mode: {why}")
        took = self._entry.begin(self.profile, lambda: port is self._port)
        if took is not None:
            self._settle_until = asyncio.get_running_loop().time() + took
            self._detector, self._decoder, self._dropped_seen = ModeDetector(), kiss.KissDecoder(), 0

    def _handle(self, kiss_frame: kiss.KissFrame) -> None:
        read = read_frame(kiss_frame, self.now(), self.dummy)
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
        return self.state is Source.State.CONNECTED and self.confirmed and not self._looking and not (self.profile.detect_command_mode and self._told_text and not self._kiss_seen) and asyncio.get_running_loop().time() >= self._settle_until

    def why_unusable(self) -> str:
        return _why_unusable(self)

    def look_begin(self) -> bool:
        """A check or probe starts: nothing is sent meanwhile and the TNC is asked afresh. False when there is no line."""
        if self._port is None:
            return False
        self._looking = True
        self._entered = self._kiss_seen = self._told_text = False
        self._again.reset()
        self._detector.rearm()
        return True

    def look_send(self, data: bytes) -> bool:
        return self._port is not None and self._write(self._port, data)

    def look_enter_kiss(self) -> None:
        """KISS ON, unless an answer already made the Tnc enter it, or the answer was a KISS frame (the TNC did not leave KISS for the exit frame: it is in KISS already, and the entry would only cost reception)."""
        if self._port is not None and not self._entered and not self._kiss_seen:
            self._enter_kiss(self._port, "the keep-alive asked the TNC", logging.DEBUG, note=False)

    def look_end(self) -> None:
        self._looking = False

    async def reopen_port(self) -> None:
        """The line is closed and the same path opened again (a USB adapter that dropped); a radio that was silent stays silent. A path that cannot be opened is a failed open, which is followed by the search for the radio."""
        port, self._port = self._port, None
        if port is not None:
            silent = self.state is Source.State.SILENT
            self._drop_tasks()
            port.close()
            await self._connect(reopen=port.path, silent=silent)

    # ---- writing
    def _write(self, port: _TncPort, data: bytes) -> bool:
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
        packet = packet_of("out", raw, frame, self.now(), self.dummy)
        self._note(_printable(f"sent {frame.tnc2()}"))
        self.packet.emit(packet)
        return True

    @property
    def searching(self) -> list[str]:
        """The ports the search for the radio is listening to; none while a port is open or no search is under way."""
        return list(self._search.listening) if self._port is None else []

    def describe(self) -> str:
        return _describe(self)


def _describe(tnc: "Tnc") -> str:
    """The Tnc in a few words, for the radio's status line."""
    if tnc.state is Source.State.SILENT and tnc.last_byte_at is not None:
        return f"silent since {tnc.last_byte_at:%H:%M} ({minutes_between(tnc.last_byte_at, tnc.now())})"
    if tnc.searching:
        return f"listening on {', '.join(tnc.searching)} for the radio"
    if tnc._port is None:
        return f"{tnc.path or tnc.port or 'no port'}{_speed(tnc.path or tnc.port, tnc.baud)}, {tnc.state.value}"
    mode = "KISS" if tnc._kiss_seen else ("entering KISS" if tnc._entered else "listening")
    return f"{tnc.path}{_speed(tnc.path, tnc.baud)}, {mode}, {tnc.stats.packets} packets"


def _why_unusable(tnc: "Tnc") -> str:
    """Why nothing is sent now, as a clause: a fresh line not yet confirmed, a TNC that types text (it is in command mode, KISS ON is sent again), else what the state says."""
    if tnc.state is Source.State.CONNECTED and not tnc.confirmed:
        return CHECKING
    if tnc.state is Source.State.CONNECTED and tnc.profile.detect_command_mode and tnc._told_text and not tnc._kiss_seen:
        return COMMAND_MODE
    return unusable_because(tnc.state)
