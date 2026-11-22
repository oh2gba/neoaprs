"""Connection to an APRS-IS server for the iGate: a `Source` that reconnects and never raises.

Writes only after a verified login; every non-comment server line goes to the signal `heard`.
Protocol: https://www.aprs-is.net/Connecting.aspx (`pass -1` listens only).
"""
import asyncio
import logging
import re
import socket
from collections import deque
from typing import Literal

from . import PROGRAM, VERSION, nodevices
from .aprsisline import MAX_LINE, is_comment, parse_is_line
from .callsign import call_problem
from .clock import Clock, utcnow
from .packet import Packet
from .signal import Signal
from .source import Backoff, Source, os_error_text
from .tasks import cancel_all

log = logging.getLogger("neoaprs.aprsis")

CONNECT_SEC = 10.0
GREETING_SEC = 15.0
LOGIN_SEC = 15.0
QUIET_SEC = 120.0  # nothing written for this long: send a comment
LOST_SEC = 180.0  # nothing from the server for this long: lost
WRITE_SEC = 30.0  # a write not taken in this time: lost
QUEUE_MAX = 500  # the oldest lines are dropped beyond it
READ_LIMIT = 8192
FILTER_MOVE_KM = 10  # the station moves this far: resend the filter
READ_ONLY = "-1"  # passcode of a listen-only login
NO_SERVER = "no server set: give igate/server the address of an APRS-IS server (host:port)"
UNVERIFIED = "the server did not accept the password"
_LOGRESP = re.compile(r"#\s*logresp\s+(\S+)\s+(unverified|verified)\b(?:\s*,\s*server\s+(\S+))?", re.IGNORECASE)
CRLF = b"\r\n"


# why the link is not logged in, as a code (the page's words: IgateState.reason)
LinkReason = Literal["", "no_server", "no_call", "unreachable", "offline", "not_server", "lost"]


def _reason_of(e: Exception) -> LinkReason:
    """Return the code of what ended an attempt: no server, unreachable, not APRS-IS, or lost."""
    if isinstance(e, socket.gaierror):
        return "offline"
    if isinstance(e, AprsIsError):
        return "not_server"
    return "lost" if isinstance(e, ConnectionError) and not isinstance(e, ConnectionRefusedError) else "unreachable"


class AprsIsError(Exception):
    """The server is not what a connection should be."""


def range_filter(lat: float, lon: float, km: int) -> str:
    """Return the filter for stations within `km` (the map radius) of a position (degrees)."""
    return f"r/{lat:.2f}/{lon:.2f}/{km}"


def login_line(call: str, password: str, filter_spec: str = "") -> bytes:
    """Return the login line, the only place the password becomes text; none means `pass -1`."""
    text = f"user {call} pass {password or READ_ONLY} vers {PROGRAM} {VERSION}" + (f" filter {filter_spec}" if filter_spec else "")
    return text.encode("ascii") + CRLF


def logresp_of(line: bytes) -> tuple[bool, str] | None:
    """Return whether the login was verified and the server name from `# logresp`; else None."""
    found = _LOGRESP.match(line.decode("latin-1").strip())
    return None if found is None else (found.group(2).lower() == "verified", found.group(3) or "")


def _snippet(line: bytes) -> str:
    return "".join(c if c.isprintable() and c.isascii() else "?" for c in line[:40].decode("latin-1").strip())


class AprsIs(Source):
    def __init__(self, clock: Clock = utcnow, backoff: Backoff | None = None, connect_sec: float = CONNECT_SEC, greeting_sec: float = GREETING_SEC, login_sec: float = LOGIN_SEC,
                 quiet_sec: float = QUIET_SEC, lost_sec: float = LOST_SEC, write_sec: float = WRITE_SEC, queue_max: int = QUEUE_MAX) -> None:
        super().__init__("aprsis", clock)
        self.host, self.port, self.call, self._password = "", 0, "", ""
        self.backoff = backoff or Backoff()
        self.connect_sec, self.greeting_sec, self.login_sec = connect_sec, greeting_sec, login_sec
        self.quiet_sec, self.lost_sec, self.write_sec = quiet_sec, lost_sec, write_sec
        self.verified = False  # lines may be written
        self.reason: LinkReason = ""  # why it is not logged in
        self.unverified = False  # the password was refused; listen only
        self.server_name = ""
        self.slow_dropped = 0  # queue overflows
        self.filter = ""  # empty sends nothing
        self.heard: Signal[[Packet]] = Signal("aprsis.heard")
        self.read = 0
        self.unreadable = 0
        self._queue: deque[bytes] = deque(maxlen=queue_max)
        self._wake = asyncio.Event()
        self._last_tx = 0.0

    def configure(self, host: str, port: int, call: str, password: str) -> None:
        """Set what to connect to and log in as, while the feed is stopped."""
        self.host, self.port, self.call, self._password = host, port, call, password

    def describe(self) -> str:
        return f"APRS-IS at {self.host}:{self.port}" if self.host else ""

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def read_only(self) -> bool:
        """Return whether there is no passcode, so the connection only listens."""
        return not self._password or self._password == READ_ONLY

    @property
    def listening(self) -> bool:
        """Return whether it is logged in but not verified (reads, does not write)."""
        return self.state is Source.State.CONNECTED and not self.verified

    def _missing(self) -> str:
        """Return what the login needs that is not set, or empty."""
        if not self.host or not self.port:
            return NO_SERVER
        return call_problem(self.call)

    def set_filter(self, spec: str) -> None:
        """Set what the server sends: used at the next login, sent now as `#filter SPEC` if up."""
        if spec == self.filter:
            return
        self.filter = spec
        if spec and self.state is Source.State.CONNECTED:
            self._enqueue(f"#filter {spec}".encode("ascii"))

    # ---- life
    async def start(self) -> None:
        if self.state is not Source.State.STOPPED:
            await self.stop()
        self.backoff.reset()
        self.unverified, self.last_error, self.read, self.unreadable = False, "", 0, 0
        if missing := self._missing():
            self._set_state(Source.State.CONNECTING)
            self.reason = "no_server" if missing == NO_SERVER else "no_call"
            self._set_problem(missing)
            return
        self.reason = ""
        self._spawn(self._run(self._generation))

    async def stop(self) -> None:
        self._generation += 1
        await self._cancel_tasks()
        self._drop_session()
        self.unverified = False
        was = self.state is Source.State.CONNECTED
        self._set_state(Source.State.STOPPED)
        if was:
            log.info("aprsis: disconnected from %s", self.target)

    def _drop_session(self) -> None:
        self.verified = False
        self.server_name = ""
        self._queue.clear()

    # ---- writing
    def send_line(self, line: bytes) -> bool:
        """Queue one line (no line end); False if not verified, has CR or LF, or is too long."""
        if not self.verified or len(line) + len(CRLF) > MAX_LINE or b"\r" in line or b"\n" in line:
            return False
        self._enqueue(line)
        return True

    def _enqueue(self, line: bytes) -> None:
        if len(self._queue) == self._queue.maxlen:
            self.slow_dropped += 1
        self._queue.append(line)
        self._wake.set()

    # ---- the connection
    async def _run(self, generation: int) -> None:
        while generation == self._generation:
            problem, self.reason = await self._attempt()
            if generation != self._generation:
                return
            delay = self.backoff.next_delay_sec()
            self._waiting(problem, delay)
            await asyncio.sleep(delay)

    async def _attempt(self) -> tuple[str, LinkReason]:
        """Run one connection to its end; return why it ended, as log text and as a code."""
        self._set_state(Source.State.CONNECTING)
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await self._open()
            await self._login(reader, writer)
            await self._serve(reader, writer)
        except asyncio.CancelledError:
            raise
        # a feed never raises into its loop: it says why and tries again
        except Exception as e:
            return f"{self.target}: " + (os_error_text(e) if isinstance(e, OSError) else str(e) or type(e).__name__), _reason_of(e)
        finally:
            self._drop_session()
            if writer is not None:
                writer.transport.abort()
        return "the connection ended", "lost"

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        nodevices.check_host(self.host, "APRS-IS")
        try:
            async with asyncio.timeout(self.connect_sec):
                reader, writer = await asyncio.open_connection(self.host, self.port, limit=READ_LIMIT)
        except TimeoutError:
            raise OSError("no answer in time") from None
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass  # a socket that cannot be set is still a connection
        log.info("aprsis: connected to %s", self.target)
        return reader, writer

    async def _line(self, reader: asyncio.StreamReader, hung_up: str) -> bytes:
        try:
            line = await reader.readline()
        # a line longer than the reader takes, at any stage of the session
        except ValueError:
            raise ConnectionError("the server sent a line that is too long") from None
        self.stats.bytes_in += len(line)
        if not line.endswith(b"\n"):
            raise ConnectionError(hung_up)
        return line

    async def _login(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(self.greeting_sec):
                greeting = await self._line(reader, "the server hung up before it greeted")
        except TimeoutError:
            raise AprsIsError(f"the server said nothing in {self.greeting_sec:g} s") from None
        if not greeting.startswith(b"#"):
            raise AprsIsError(f"not an APRS-IS server (it began with {_snippet(greeting)!r})")
        sent_filter = self.filter
        writer.write(login_line(self.call, self._password, sent_filter))
        self._last_tx = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(self.login_sec):
                verified, name = await self._answer(reader)
        except TimeoutError:
            raise AprsIsError(f"the server did not answer the login in {self.login_sec:g} s") from None
        self.server_name = name
        self.verified = verified
        self.unverified = self.unverified or (not verified and not self.read_only)
        self.backoff.connected()
        self.reason = ""
        self._set_state(Source.State.CONNECTED)
        if self.filter and self.filter != sent_filter:
            self._enqueue(f"#filter {self.filter}".encode("ascii"))
        text = f"logged in as {self.call}, " + ("verified" if verified else "listening only" if self.read_only else f"not verified ({UNVERIFIED}), listening only") + (f", server {name}" if name else "")
        self._note(text)
        (log.warning if self.unverified else log.info)("aprsis: %s", text)

    async def _answer(self, reader: asyncio.StreamReader) -> tuple[bool, str]:
        while True:
            answer = logresp_of(await self._line(reader, "the server hung up after the login"))
            if answer is not None:
                return answer

    # ---- while logged in
    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks = [asyncio.create_task(self._read(reader), name="aprsis-read"), asyncio.create_task(self._write(writer), name="aprsis-write")]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()  # neither ends except by raising
        finally:
            await cancel_all(tasks)
            for task in tasks:
                if task.done() and not task.cancelled():
                    task.exception()  # retrieved so it is not reported as lost

    async def _read(self, reader: asyncio.StreamReader) -> None:
        """Read what the server sends; a comment is the keep-alive, any other line is a packet."""
        while True:
            try:
                async with asyncio.timeout(self.lost_sec):
                    line = await self._line(reader, "the server hung up")
            except TimeoutError:
                raise ConnectionError(f"nothing from the server for {self.lost_sec:g} s") from None
            self.last_byte_at = self.now()
            self._take(line.rstrip(b"\r\n"))

    def _take(self, line: bytes) -> None:
        """Hand a non-comment server line to `heard`, or count it as unreadable; never raise."""
        if not line or is_comment(line):
            return
        try:
            packet = parse_is_line(line, self.now())
        except Exception:  # any parser fault: the line is unreadable
            self.unreadable += 1
            log.debug("aprsis: not a packet: %s", _snippet(line))
            return
        self.read += 1
        self.heard.emit(packet)

    async def _write(self, writer: asyncio.StreamWriter) -> None:
        loop = asyncio.get_running_loop()
        while True:
            if not self._queue:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), max(0.0, self.quiet_sec - (loop.time() - self._last_tx)))
                except TimeoutError:
                    # the server ignores a comment; the write finds a dead connection
                    self._queue.append(f"# {PROGRAM} {VERSION}".encode("ascii"))

                continue
            line = self._queue.popleft()
            writer.write(line + CRLF)
            self._last_tx = loop.time()
            self.stats.bytes_out += len(line) + len(CRLF)
            try:
                async with asyncio.timeout(self.write_sec):
                    await writer.drain()
            except TimeoutError:
                raise ConnectionError(f"the server does not take what is sent (nothing in {self.write_sec:g} s)") from None
            if not line.startswith(b"#"):
                self.stats.packets += 1
                self.stats.last_packet = self.now()
