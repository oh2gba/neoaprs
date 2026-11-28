"""The one source: serial line, KISS and AX.25 decoders and APRS parser in a row, emitting packets.

What is sent to the TNC comes from its profile (tncprofile.py). SILENT is an open line to a radio
that does not answer: nothing is sent until a byte comes.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from . import ax25, kiss, serialprobe
from .claims import Claims
from .clock import Clock, utcnow
from .dummyline import DUMMY_PATH, DummyPort
from .dummyworlds import dummy_line, dummy_words
from .interlock import Interlock
from .mercury import frame_words, station_message
from .packet import Packet
from .radiotype import FM_ID, HF_ID, RadioId, RadioType
from .radiotypes import type_of
from .reading import NO_READING, Reading
from .policy import TNC_CHECK_SEC
from .serialport import HeldError, NotChosenError, SerialError, is_socket
from .signal import Signal
from .source import MODEM_NOT_RUNNING, Backoff, Source, minutes_between
from .tncentry import KissEntry
from .tncfollow import AdapterFollow
from .tnclines import TimedSource
from .tncmode import Mode, ModeDetector, packet_of, printable as _printable, read_frame
from .tncport import Modem, TncPort
from .tnctextreader import accepts, reader_for
from .tnchealth import COMMAND_MODE as COMMAND_MODE
from .tnchealth import takes_frames, why_unusable
from .tnc2line import text_of
from .tncsearch import PortSearch, hold_port, may_open, release_port, taken
from .tncprofile import KENWOOD_TNC2, KISS_EXIT as KISS_EXIT, Profile
from .tncwatchdog import ANSWER_SEC, CHECK_PAUSE_SEC, PROBE_SEC, PROMPT, REPLY_SEC, TncStats, Watchdog
from .coded import Reason, code_of

log = logging.getLogger("neoaprs.tnc")

ENTER_KISS = KENWOOD_TNC2.enter[0][0]  # the default profile's entry, for the tests


def _speed(path: str, baud: int) -> str:
    """Return " at 9600" for a serial line; "" for a TCP line and the Dummy."""
    return "" if is_socket(path) or path == DUMMY_PATH else f" at {baud}"


async def open_port(tnc: "Tnc", path: str) -> TncPort | DummyPort:
    """Return the open line at `path` (serial, socket or Dummy); raise SerialError."""
    port: TncPort | DummyPort = dummy_line(tnc) if tnc.is_dummy else TncPort(path, tnc.baud, tnc._on_data, tnc._on_lost)
    if isinstance(port, DummyPort):
        port.label = tnc.label
    else:
        port.on_written = tnc._on_written
    await port.open()
    return port


def _describe(tnc: "Tnc") -> str:
    if tnc.is_dummy:
        return f"{dummy_words(tnc.profile.key)}, made-up traffic, {tnc.stats.packets} packets, nothing goes on the air"
    if tnc.state is Source.State.SILENT and tnc.last_byte_at is not None:
        return f"silent since {tnc.last_byte_at:%H:%M} ({minutes_between(tnc.last_byte_at, tnc.now())})"
    if tnc._port is None and (words := tnc._search.words):
        return words
    if (modem := tnc._modem()) is not None:
        return f"{modem.describe()}, {tnc.stats.packets} packets"
    if tnc._port is None:
        return f"{tnc.path or tnc.port or 'no port'}{_speed(tnc.path or tnc.port, tnc.baud)}, {tnc.state.value}"
    mode = (
        "KISS"
        if tnc._reader.kiss_seen
        else "text"
        if tnc.profile.framing == "text"
        else ("entering KISS" if tnc.entering_kiss else "listening")
    )
    return f"{tnc.path}{_speed(tnc.path, tnc.baud)}, {mode}, {tnc.stats.packets} packets"


def _until_settings_change(tnc: "Tnc", problem: str) -> None:
    """Go WAITING with no retry: the radio cannot be opened until its settings change."""
    log.warning("%s: %s", tnc.label, problem)
    tnc.problem = ""
    tnc._set_state(Source.State.WAITING, problem)
    tnc._note(problem)


class Tnc(TimedSource):
    stats: TncStats

    def __init__(
        self,
        port: str = "",
        baud: int = 9600,
        profile: Profile = KENWOOD_TNC2,
        pattern: str = "",
        clock: Clock = utcnow,
        probe_seconds: float = 0.0,
        backoff: Backoff | None = None,
        settle_sec: float | None = None,
        pace: float = 1.0,
        fallback_probe: bool = True,
        probe_nudge_sec: float = serialprobe.NUDGE_SEC,
        skip: tuple[str, ...] = (),
        check_sec: float = TNC_CHECK_SEC,
        check_pause_sec: float = CHECK_PAUSE_SEC,
        reply_sec: float = REPLY_SEC,
        answer_sec: float = ANSWER_SEC,
        probe_sec: float = PROBE_SEC,
        *,
        claims: Claims | None = None,
        search_lock: asyncio.Lock | None = None,
    ) -> None:
        super().__init__("tnc", clock)
        self.stats = TncStats()
        self.port, self.baud, self.profile, self.pattern = port, baud, profile, pattern or serialprobe.search_pattern()
        self.probe_seconds, self.probe_nudge_sec, self.skip, self.claims, self.search_lock = (
            probe_seconds,
            probe_nudge_sec,
            skip,
            claims,
            search_lock,
        )
        self.where: Callable[[], tuple[float, float] | None] = lambda: None
        self.interlock: Interlock | None = None
        self.modem: Modem | None = None
        self.radio_id: RadioId = HF_ID if self.rtype.kind == "hf" else FM_ID
        self.radio_name = ""
        self.fallback_probe, self._probe_next = fallback_probe, False
        self.remembered = False
        self.backoff = backoff or Backoff()
        self.packet: Signal[[Packet]] = Signal("tnc.packet")
        self.path = ""
        self._search = PortSearch(self._spawn, self._note, PROMPT, lambda: self.label)
        self._entry = KissEntry(
            self._spawn, lambda data: self._port is not None and self._write(self._port, data), settle_sec, pace
        )
        self._port: TncPort | None = None
        self._follow = AdapterFollow(lambda: self.label)
        self._watchdog_task: asyncio.Task[None] | None = None
        self.watchdog = Watchdog(self, check_sec, check_pause_sec, reply_sec, answer_sec, probe_sec)
        self.last_watchdog_action = ""
        self.last_watchdog_at: datetime | None = None
        self._reader = reader_for(self)
        # why the last line was lost when a write timed out; None once a write went through or a byte came
        self.write_stuck: Reason | None = None
        self._open_reset()

    def _open_reset(self) -> None:
        self._reader = reader_for(self, self._reader)
        self._reader.reset()
        self.confirmed = not (self.profile.can_probe and self.profile.detect_command_mode and self.watchdog.sec > 0)

    async def start(self) -> None:
        if self.state is not Source.State.STOPPED:
            await self.stop()
        self._probe_next = False
        self.write_stuck = None
        self.backoff.reset()  # a start is a fresh try
        await self._connect()

    async def stop(self) -> None:
        self._generation += 1
        port, self._port = self._port, None  # first: what the line says meanwhile is no one's
        if port is not None:
            port.close()
        await self._cancel_tasks()
        self._watchdog_task = None
        self.watchdog.probes = 0
        release_port(self.claims, self.radio_id)
        self._set_state(Source.State.STOPPED)

    async def _connect(self, reopen: str = "", silent: bool = False) -> None:
        """Open the line: `reopen`, else the named port, else the one the search finds."""
        generation = self._generation
        if not silent:
            self._set_state(Source.State.CONNECTING)
        named = bool(reopen or self.port) and not self._probe_next
        self._probe_next = False
        try:
            found = await self._find_line(reopen, named, generation)
        except SerialError as e:
            if generation != self._generation:
                return  # stopped meanwhile: no retry
            self.write_stuck = None  # the open failed: that is the problem now
            self._probe_next = named and self.fallback_probe and self._search.possible and not isinstance(e, HeldError)
            said = e.args[0] if e.args and isinstance(e.args[0], Reason) else str(e)
            self._wait(said, again=not isinstance(e, NotChosenError))
            return
        except Exception:
            if generation != self._generation:
                return
            log.exception("%s: connecting failed", self.label)
            self._wait("the radio could not be opened; the log says why")
            return
        if found is not None:
            try:
                self._opened(*found, named, reopen, silent)
            except BaseException:
                self._port = None
                found[0].close()
                raise

    async def _find_line(
        self, reopen: str, named: bool, generation: int
    ) -> tuple[TncPort | DummyPort, str, bytes] | None:
        """Return the open line, its path and what the search heard; None if `stop` came."""
        if not named and (not self.profile.search or self._modem() is not None):
            raise NotChosenError(
                "no address is chosen: type the board's address in the settings"
                if self.profile.transport == "tcp"
                else "no port is chosen: choose the radio's port in the settings"
            )
        path, heard = (
            (reopen or self.port, b"")
            if named
            else await self._search.find(
                self.pattern,
                self.baud,
                self.probe_seconds,
                lambda heard: accepts(self.profile, heard),
                self.profile.can_probe,
                self.probe_nudge_sec,
                self.skip,
                lambda: generation == self._generation,
                self.port,
                claims=self.claims,
                holder=self.radio_id,
                lock=self.search_lock,
            )
        )
        if generation != self._generation:
            return None
        if named and (modem := self._modem()) is not None and (why := modem.refuses_line()):
            raise SerialError(why)
        if named and not self.is_dummy and await asyncio.to_thread(serialprobe.incoming_bluetooth, path):
            raise NotChosenError(serialprobe.incoming_port_reason(path))
        if named and not self.is_dummy:
            await may_open(self.claims, self.radio_id, path, self.remembered and not reopen)
        asked = path
        port, path = await self._follow.open(
            path,
            named and not self.is_dummy,
            lambda where: open_port(self, where),
            self._note,
            lambda where: taken(self.claims, self.radio_id, where),
        )
        if generation != self._generation:
            port.close()
            return None
        hold_port(None if self.is_dummy else self.claims, self.radio_id, path, port.close)
        if self._follow.following(path, named and not self.is_dummy):
            self._spawn(self._follow.remember(asked, path))
        return port, path, heard

    def _opened(
        self, port: TncPort | DummyPort, path: str, heard: bytes, named: bool, reopen: str, silent: bool
    ) -> None:
        self._port, self.path = port, path
        self._open_reset()
        self.confirmed = self.confirmed or not named
        self.last_byte_at = self.last_byte_at or self.now()
        self.stats.opens += 1
        self.backoff.connected()
        self._set_state(Source.State.SILENT if silent else Source.State.CONNECTED)
        if not reopen:
            self._note(
                "opened the line to the modem"
                if self._modem() is not None
                else f"opened {path}{_speed(path, self.baud)}"
            )
        log.log(logging.DEBUG if reopen else logging.INFO, "%s: opened %s%s", self.label, path, _speed(path, self.baud))
        if heard and self.profile.detect_command_mode and ModeDetector().feed(heard) is Mode.MONITOR:
            self._reader.enter_kiss(port, "the search found the TNC in command mode")
        self._start_watchdog()

    def _wait(self, problem: str, again: bool = True) -> None:
        """Go WAITING and retry after the back-off; with `again` False, only new settings retry."""
        self.watchdog.probes = 0
        expected = False
        if (modem := self._modem()) is not None:
            # the modem says why it does not run; the line's wait follows from it
            expected = modem.starting() or modem.state == "waiting"
            problem = modem.problem or f"waiting for {modem.describe()}"
        self._waiting(
            problem, self.backoff.next_delay_sec(), self._connect, expected=expected
        ) if again else _until_settings_change(self, problem)

    def _modem(self) -> Modem | None:
        return self.modem if self.profile.transport == "modem" else None

    @property
    def modem_in_use(self) -> Modem | None:
        """The modem program behind the line, for a type that has one."""
        return self._modem()

    def modem_changed(self) -> None:
        """Follow the modem: the line is closed while the modem does not run, and opened once it does."""
        if (modem := self._modem()) is None or self.state is Source.State.STOPPED:
            return
        if modem.state != "running" and (port := self._port) is not None:
            self._port = None
            self._drop_tasks()
            port.close()
            self._wait(MODEM_NOT_RUNNING)
        elif modem.state == "running" and self.state is Source.State.WAITING and self._port is None:
            self._generation += 1  # the retry already due is void: this one connects now
            self._spawn(self._connect())

    def _held(self) -> str:
        """Return why the modem wants no frame now (not running, transmitting, channel busy), else ""."""
        modem = self._modem()
        return modem.frame_hold() if modem is not None else ""

    @property
    def label(self) -> str:
        return self.radio_name or ("hf radio" if self.rtype.kind == "hf" else "tnc")

    @property
    def rtype(self) -> RadioType:
        return type_of(self.profile.key)

    @property
    def max_frame(self) -> int | None:
        return self.rtype.limits.max_frame

    def _on_lost(self, port: TncPort, reason: str) -> None:
        if port is not self._port:
            return
        self._port = None
        self._drop_tasks()
        text = f"{port.path} lost: {reason}"
        self.write_stuck = (
            Reason.of(reason, f"{port.path}: a write timed out: {reason}")
            if code_of(reason)[0] == "radio.write_timeout"
            else None
        )
        self._wait(self.write_stuck or text)

    def _on_written(self, port: TncPort) -> None:
        if port is self._port and self.write_stuck is not None:
            self._took_data("a write went through")

    def _drop_tasks(self) -> None:
        watchdog, self._watchdog_task = self._watchdog_task, None
        if watchdog is not None and watchdog is not asyncio.current_task():
            watchdog.cancel()

    def _on_data(self, port: TncPort, chunk: bytes) -> None:
        if port is self._port:
            if self.write_stuck is not None:
                self._took_data("a byte came")
            self._reader.read(port, chunk)

    def _took_data(self, how: str) -> None:
        """The line works again after a write timed out: the radio is shown connected."""
        self.write_stuck = None
        log.info("%s: the port takes data again: %s", self.label, how)
        self._note(f"the port takes data again: {how}")
        self.changed.emit()

    def _handle(self, kiss_frame: kiss.KissFrame) -> None:
        if self.rtype.kind == "hf" and station_message(kiss_frame.command, kiss_frame.payload):
            self._reading()
            self._saw(f"another program's station message, not APRS: passed over ({len(kiss_frame.payload)} bytes)")
            return
        read = read_frame(
            kiss_frame,
            self.now(),
            self.is_dummy,
            reading=self._reading() if kiss_frame.command == 0 else NO_READING,
            radio_id=self.radio_id,
        )
        if isinstance(read, str):
            self._saw(f"rejected, {read}: {kiss_frame.payload[:40].hex()}")
            return self._reject()
        self._take(*read)

    def _take(self, packet: Packet, frame: ax25.Frame) -> None:
        self.stats.packets, self.stats.last_packet = self.stats.packets + 1, packet.heard_at
        self._saw(_printable(f"{frame.tnc2()}  ->  {packet.summary}"))
        if self.rtype.kind == "hf":
            log.info("%s", frame_words("in", len(packet.raw), packet.source, packet.snr))
        self.packet.emit(packet)

    def _reading(self) -> Reading:
        port = self._port
        source = port if isinstance(port, DummyPort) else self._modem() or self._reader.board
        return NO_READING if source is None else source.take_reading().only(self.profile.readings)

    def set_check(self, seconds: float) -> None:
        self.watchdog.sec = seconds
        self.confirmed = self.confirmed or seconds <= 0
        self._start_watchdog()

    def _start_watchdog(self) -> None:
        self._drop_tasks()
        port = self._port
        if (
            port is not None
            and self.profile.can_probe
            and self.profile.detect_command_mode
            and (self.watchdog.sec > 0 or self.state is Source.State.SILENT)
        ):
            self.watchdog.opened()
            self._watchdog_task = self._spawn(self.watchdog.run(lambda: port is self._port, not self.confirmed))

    @property
    def usable(self) -> bool:
        return takes_frames(self)

    describe, why_unusable = _describe, why_unusable
    _looking, _entered = property(lambda self: self._reader.looking), property(lambda self: self._reader.entered)
    entering_kiss = property(
        lambda self: self._port is not None and self._reader.entered and not self._reader.kiss_seen
    )
    is_dummy = property(lambda self: self.profile.transport == "dummy")

    def look_begin(self) -> bool:
        """Start a check or probe (nothing is sent meanwhile); False when there is no line."""
        if self._port is None:
            return False
        self._reader.asked_afresh()
        return True

    def look_send(self, data: bytes) -> bool:
        return self._port is not None and self._write(self._port, data)

    def look_enter_kiss(self) -> None:
        """Send KISS ON unless it was entered already or a KISS frame came."""
        if self._port is not None and not self._reader.entered and not self._reader.kiss_seen:
            self._reader.enter_kiss(self._port, "the keep-alive asked the TNC", logging.DEBUG, note=False)

    def look_end(self) -> None:
        self._reader.looking = False

    async def reopen_port(self) -> None:
        port, self._port = self._port, None
        if port is not None:
            silent = self.state is Source.State.SILENT
            self._drop_tasks()
            port.close()
            await self._connect(reopen=port.path, silent=silent)

    def _write(self, port: TncPort, data: bytes) -> bool:
        if self.profile.writes_nothing:
            return False
        try:
            port.write(data)
        except SerialError as e:
            self._note(f"write failed: {e}")
            port.fail(str(e))
            return False
        self.stats.bytes_out += len(data)
        return True

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        """Send the frame; `raw` is its bytes when they are to go unchanged (the digipeater's)."""
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
            if self.rtype.kind == "hf":
                log.info(
                    "%s: a frame from %s (%d bytes) was not sent: %s",
                    self.label,
                    frame.source,
                    len(raw),
                    self.why_unusable(),
                )
            return False
        if why := self.rtype.limits.too_long(raw, text_of(frame)):
            self._note(_printable(f"not sent: {why}: {frame.tnc2()}"))
            log.warning("%s: a frame was not sent: %s", self.label, why)
            return False
        if not self._write(port, kiss.encode(raw)):
            return False
        packet = packet_of("out", raw, frame, self.now(), self.is_dummy, radio_id=self.radio_id)
        self._note(_printable(f"sent {frame.tnc2()}"))
        if self.rtype.kind == "hf":
            log.info("%s", frame_words("out", len(raw), packet.source, None))
        self.packet.emit(packet)
        return True

    @property
    def searching(self) -> list[str]:
        return list(self._search.listening) if self._port is None else []
