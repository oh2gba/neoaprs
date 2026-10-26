"""The feed of GPS fixes: a gpsd to ask over TCP, or a GPS receiver's NMEA 0183 on a serial port. A `Source` like the TNC: it has a state and a problem, it is started and stopped, it reconnects with `Backoff`, and
it never raises out of its tasks. `fixed` is emitted with each fix, `fix` is the latest one (kept when the receiver then says it has none: the service that uses it judges how old it is) and `fix_age_sec` how long ago it came.

gpsd (`kind` "gpsd", `target` host:port): one connection, over which `?WATCH={"enable":true,"json":true}` is sent; gpsd answers with a JSON object on each line (VERSION, DEVICES, WATCH, then TPV and SKY reports), which `GpsdFixes`
reads. A connection that is refused, lost or hung up is opened again after the back-off.

Serial (`kind` "serial", `target` the port, `baud`): a `SerialPort` (neoaprs/serialport.py: a device, or `socket://host:port` for a receiver behind a TCP serial server) whose bytes are cut into lines for `NmeaFixes`; a port
that cannot be opened or is lost is opened again after the back-off. A receiver that reports no fix is a problem the page can show ("no satellite fix"), not a loss of the line."""
import asyncio
import json
import logging
from typing import Any

from .callbackport import CallbackPort
from .clock import Clock, utcnow
from .gpsfix import Fix, GpsdFixes, NmeaFixes
from .serialport import SerialError, is_socket
from .signal import Signal
from .source import Backoff, Source, os_error_text

log = logging.getLogger("neoaprs.gps")

CONNECT_SEC = 5.0                                              # how long the connection to gpsd may take
WATCH = b'?WATCH={"enable":true,"json":true}\n'
NO_FIX = "the receiver has no position fix yet"
NO_PORT = "no port set: give gps/device the receiver's port"
NO_ADDRESS = "no address set: give gps/host the gpsd's host:port"
MAX_LINE_BYTES = 4096                                          # a piece of serial data this long without a line end is not NMEA: it is thrown away


class _GpsPort(CallbackPort):
    """The GPS receiver's line: a port that tells the feed of its bytes and its death."""


def split_address(target: str) -> tuple[str, int]:
    """host and port of `host:port` (an IPv6 address may be in brackets); ValueError when it is not."""
    host, _, port = target.strip().rpartition(":")
    if not host.strip("[]") or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError(f"{target!r} is not host:port")
    return host.strip("[]"), int(port)


class GpsFeed(Source):
    def __init__(self, clock: Clock = utcnow, backoff: Backoff | None = None, connect_sec: float = CONNECT_SEC) -> None:
        super().__init__("gps", clock)
        self.kind = "off"                                      # "off", "gpsd" or "serial"
        self.target = ""                                       # host:port of the gpsd, or the serial port
        self.baud = 4800
        self.backoff = backoff or Backoff()
        self.connect_sec = connect_sec
        self.fixed: Signal[[Fix]] = Signal("gps.fixed")
        self.fix: Fix | None = None                            # the latest fix
        self._generation = 0                                   # changes at stop(), so that an attempt that was under way knows it is over
        self._port: _GpsPort | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._nmea = NmeaFixes()
        self._pending = bytearray()

    def configure(self, kind: str, target: str, baud: int) -> None:
        """What to read, for a feed that is stopped."""
        self.kind, self.target, self.baud = kind, target, baud

    @property
    def fix_age_sec(self) -> float | None:
        """Seconds since the latest fix came; None before the first."""
        return None if self.fix is None else (self.now() - self.fix.at).total_seconds()

    def describe(self) -> str:
        """What is read, for the log: "gpsd at 127.0.0.1:2947", "GPS on /dev/ttyUSB1 at 4800" (a TCP port has no speed)."""
        if not self.target.strip():
            return ""
        if self.kind == "gpsd":
            return f"gpsd at {self.target}"
        if self.kind == "serial":
            return f"GPS on {self.target}" + ("" if is_socket(self.target) else f" at {self.baud}")
        return ""

    # ---- life
    async def start(self) -> None:
        if self.state is not Source.State.STOPPED:
            await self.stop()
        if self.kind == "off":
            return
        self.backoff.reset()
        if not self.target.strip():                            # (a source without what it reads is a valid setting that cannot work yet: nothing is opened, and the problem says what to give)
            self._set_state(Source.State.CONNECTING)
            self._set_problem(NO_ADDRESS if self.kind == "gpsd" else NO_PORT)
            return
        await self._connect()

    async def stop(self) -> None:
        self._generation += 1
        await self._cancel_tasks()
        self._close()
        self.fix = None
        self._nmea, self._pending = NmeaFixes(), bytearray()
        self._set_state(Source.State.STOPPED)

    def _close(self) -> None:
        port, self._port = self._port, None
        if port is not None:
            port.close()
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.transport.abort()

    async def _connect(self) -> None:
        generation = self._generation
        self._set_state(Source.State.CONNECTING)
        try:
            if self.kind == "gpsd":
                await self._open_gpsd(generation)
            else:
                await self._open_serial(generation)
        except asyncio.CancelledError:
            raise
        except Exception as e:                                 # (a feed never raises into the loop: it says why and tries again)
            if generation == self._generation:
                self._wait((f"{self.describe()}: " if self.kind == "gpsd" else "") + self._words(e))          # (a serial error names its port already)

    @staticmethod
    def _words(e: BaseException) -> str:
        return os_error_text(e) if isinstance(e, OSError) else str(e) or type(e).__name__

    def _wait(self, problem: str) -> None:
        delay = self.backoff.next_delay_sec()
        log.warning("gps: %s; trying again in %g s", problem, delay)
        self.problem = ""                                      # (what was wrong before is replaced by why the line is down)
        self._set_state(Source.State.WAITING, problem)
        self._note(f"{problem}; trying again in {delay:g} s")
        self._spawn(self._retry(delay, self._generation))

    async def _retry(self, delay: float, generation: int) -> None:
        await asyncio.sleep(delay)
        if generation == self._generation:
            await self._connect()

    def _connected(self, what: str) -> None:
        self.backoff.connected()
        self._set_state(Source.State.CONNECTED)
        self._note(what)
        log.info("gps: %s", what)

    # ---- gpsd
    async def _open_gpsd(self, generation: int) -> None:
        host, port = split_address(self.target)
        try:
            async with asyncio.timeout(self.connect_sec):
                reader, writer = await asyncio.open_connection(host, port)
        except TimeoutError:
            raise OSError(f"{self.target}: no answer in time") from None
        if generation != self._generation:
            writer.transport.abort()
            return
        self._writer = writer
        self._connected(f"connected to gpsd at {self.target}")
        writer.write(WATCH)
        self._spawn(self._read_gpsd(reader, writer, generation))

    async def _read_gpsd(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, generation: int) -> None:
        reports = GpsdFixes()
        try:
            while True:
                line = await reader.readline()
                if generation != self._generation:
                    return
                if not line:
                    raise ConnectionError("gpsd hung up")
                self._gpsd_line(reports, line)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError) as e:                     # (ValueError: a line longer than the reader takes)
            if generation == self._generation:
                self._writer = None
                writer.transport.abort()
                self._wait(f"{self.target}: {self._words(e)}")

    def _gpsd_line(self, reports: GpsdFixes, line: bytes) -> None:
        self.stats.bytes_in += len(line)
        try:
            report: Any = json.loads(line)
        except ValueError:
            return self._reject()
        if not isinstance(report, dict):
            return self._reject()
        fix = reports.feed(report, self.now())
        if fix is not None:
            self._take(fix)
        elif reports.said_none:
            self._no_fix()

    # ---- a serial receiver
    async def _open_serial(self, generation: int) -> None:
        port = _GpsPort(self.target, self.baud, self._on_data, self._on_lost)
        try:
            await port.open()
        except SerialError as e:
            raise OSError(str(e)) from None
        if generation != self._generation:
            port.close()
            return
        self._port = port
        self._connected(f"opened {self.describe()}")

    def _on_data(self, port: _GpsPort, chunk: bytes) -> None:
        if port is not self._port:
            return
        self.stats.bytes_in += len(chunk)
        self._pending += chunk
        while (end := self._pending.find(b"\n")) >= 0:
            line = bytes(self._pending[:end])
            del self._pending[:end + 1]
            self._nmea_line(line)
        if len(self._pending) > MAX_LINE_BYTES:
            self._pending.clear()
            self._reject()

    def _nmea_line(self, line: bytes) -> None:
        before = self._nmea.damaged
        fix = self._nmea.feed(line, self.now())
        if self._nmea.damaged > before:
            self._reject()
        if fix is not None:
            self._take(fix)
        elif self._nmea.said_none:
            self._no_fix()

    def _on_lost(self, port: _GpsPort, reason: str) -> None:
        if port is not self._port:
            return
        self._port = None
        self._pending.clear()
        self._wait(f"{port.path} lost: {reason}")

    # ---- what the receiver said
    def _take(self, fix: Fix) -> None:
        self.fix = fix
        self.stats.packets += 1
        self.stats.last_packet = fix.at
        self.last_byte_at = fix.at
        if self.problem == NO_FIX:
            self._set_problem("")
        try:
            self.fixed.emit(fix)
        except Exception:                                      # (Signal logs a handler that fails; this is for anything else)
            log.exception("gps: the fix was not taken")

    def _no_fix(self) -> None:
        if self.state is Source.State.CONNECTED and self.problem != NO_FIX:
            self._set_problem(NO_FIX)

