"""The connection to an APRS-IS server, for a receive-only iGate. A `Source` like the TNC and the GPS feed: it has a state and a problem, it is started and stopped, it reconnects with `Backoff`, and it never raises out of its tasks.
It only writes: the lines it is given (`send_line`); what the server sends is read to keep the connection honest and thrown away, and nothing of it is handed to anything (the iGate is receive only: services/igate.py).

What it does, with the sources (https://www.aprs-is.net/Connecting.aspx, https://www.aprs-is.net/javAPRSFilter.aspx, and the servers' own answer, which the specification pages leave out):

* The server speaks first, a comment line (`# javAPRSSrvr 4.3.0b13`, `# aprsc 2.1.19`): a first line that is no comment is not an APRS-IS server and the connection is dropped. Lines that start with `#` are comments and are ignored.
* The client then sends the login line `user CALL pass PASSCODE vers NeoAPRS VERSION`, with no `filter`: a receive-only iGate needs none, and on port 14580 an unfiltered login receives only the messages for the stations it gated,
  which are thrown away here. TCP_NODELAY is set, as the specification asks of a bidirectional client. The call is unique to this program (APRS-IS wants a unique login).
* The server answers with `# logresp CALL verified, server NAME` or `unverified` (a wrong passcode, or -1). Only a verified login may put data on APRS-IS: with `unverified` nothing is sent, the connection is closed and
  it is not tried again until the settings change (the same wrong passcode would be refused again).
* Keep-alive: the server sends a comment line when its connection has been quiet, about every 20 seconds (aprsc; the specification gives no interval and asks nothing of a client). A connection that has said nothing for
  LOST_SEC (3 minutes) is lost and opened again; a client that has written nothing for QUIET_SEC (2 minutes) sends a comment line, which the server ignores, so that a connection that has died on our side is found by the write.
* Lines are TNC2 text that ends with CR LF, at most 512 bytes with it. The write queue holds at most QUEUE_MAX lines; when the server is slow the oldest are dropped (and counted), never the newest and never the loop.
* The password is never logged, noted, shown or put in an error: it is in the login line and nowhere else."""
import asyncio
import logging
import re
import socket
from collections import deque

from . import PROGRAM, VERSION
from .callsign import call_problem
from .clock import Clock, utcnow
from .source import Backoff, Source, os_error_text
from .tasks import cancel_all

log = logging.getLogger("neoaprs.aprsis")

CONNECT_SEC = 10.0                                   # how long opening the connection may take
GREETING_SEC = 15.0                                  # how long the server may take to greet
LOGIN_SEC = 15.0                                     # ... and to answer the login
QUIET_SEC = 120.0                                    # nothing written for this long: a comment line from us
LOST_SEC = 180.0                                     # nothing from the server for this long: the connection is lost
WRITE_SEC = 30.0                                     # a write the server does not take in this time: the connection is lost
QUEUE_MAX = 500                                      # lines waiting to be written; the oldest are dropped beyond it
MAX_LINE = 512                                       # bytes of a line with its CR LF
READ_LIMIT = 8192                                    # the longest line read from the server
NO_SERVER = "no server set: give igate/server the address of an APRS-IS server (host:port)"
NO_PASSWORD = "no password set: give igate/password the APRS-IS passcode of your call"
UNVERIFIED = "the server did not accept the password"
_LOGRESP = re.compile(r"#\s*logresp\s+(\S+)\s+(unverified|verified)\b(?:\s*,\s*server\s+(\S+))?", re.IGNORECASE)
CRLF = b"\r\n"


class AprsIsError(Exception):
    """The server is not what a connection should be (the words are the reason, for the operator)."""


class Unverified(AprsIsError):
    """The server did not verify the login."""

    def __init__(self, server: str) -> None:
        super().__init__(UNVERIFIED)
        self.server = server


def login_line(call: str, password: str) -> bytes:
    """The line that logs in; the only place the password is put into text."""
    return f"user {call} pass {password} vers {PROGRAM} {VERSION}".encode("ascii") + CRLF


def logresp_of(line: bytes) -> tuple[bool, str] | None:
    """Whether the login was verified and the server's name, from a `# logresp` line; None for any other line."""
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
        self.verified = False                                  # logged in and verified: lines may be written
        self.unverified = False                                # the server refused the password; nothing is tried again until the settings change
        self.server_name = ""                                  # the server's name from `# logresp`
        self.slow_dropped = 0                                  # lines dropped from the queue because the server took them too slowly
        self._generation = 0
        self._queue: deque[bytes] = deque(maxlen=queue_max)
        self._wake = asyncio.Event()
        self._last_tx = 0.0

    def configure(self, host: str, port: int, call: str, password: str) -> None:
        """What to connect to and log in as, for a feed that is stopped."""
        self.host, self.port, self.call, self._password = host, port, call, password

    def describe(self) -> str:
        return f"APRS-IS at {self.host}:{self.port}" if self.host else ""

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"

    def _missing(self) -> str:
        """What is not set that logging in needs, or empty."""
        if not self.host or not self.port:
            return NO_SERVER
        return call_problem(self.call) or ("" if self._password else NO_PASSWORD)

    # ---- life
    async def start(self) -> None:
        if self.state is not Source.State.STOPPED:
            await self.stop()
        self.backoff.reset()
        self.unverified, self.last_error = False, ""
        if missing := self._missing():                         # (a source without what it needs is a valid setting that cannot work yet: nothing is opened, and the problem says what to give)
            self._set_state(Source.State.CONNECTING)
            self._set_problem(missing)
            return
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
        """Queues one line (no line end) for the server. False when it cannot go: not logged in and verified, a CR or LF inside, or longer than a line of APRS-IS is."""
        if not self.verified or len(line) + len(CRLF) > MAX_LINE or b"\r" in line or b"\n" in line:
            return False
        if len(self._queue) == self._queue.maxlen:
            self.slow_dropped += 1                             # (the queue is a deque with a limit: the oldest line goes)
        self._queue.append(line)
        self._wake.set()
        return True

    # ---- the connection
    async def _run(self, generation: int) -> None:
        while generation == self._generation:
            problem = await self._attempt()
            if problem is None or generation != self._generation:
                return
            delay = self.backoff.next_delay_sec()
            log.warning("aprsis: %s; trying again in %g s", problem, delay)
            self.problem = ""                                  # (what was wrong before is replaced by why the line is down)
            self._set_state(Source.State.WAITING, problem)
            self._note(f"{problem}; trying again in {delay:g} s")
            await asyncio.sleep(delay)

    async def _attempt(self) -> str | None:
        """One connection, from opening to its end: why it ended, or None when it is not to be opened again (the login was not verified)."""
        self._set_state(Source.State.CONNECTING)
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await self._open()
            await self._login(reader, writer)
            await self._serve(reader, writer)
        except asyncio.CancelledError:
            raise
        except Unverified as e:
            self._refused(e.server)
            return None
        except Exception as e:                                 # (a feed never raises into the loop: it says why and tries again)
            return f"{self.target}: " + (os_error_text(e) if isinstance(e, OSError) else str(e) or type(e).__name__)
        finally:
            self._drop_session()
            if writer is not None:
                writer.transport.abort()
        return "the connection ended"

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
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
                pass                                           # (a socket that cannot be set is still a connection)
        log.info("aprsis: connected to %s", self.target)
        return reader, writer

    async def _line(self, reader: asyncio.StreamReader, hung_up: str) -> bytes:
        line = await reader.readline()
        self.stats.bytes_in += len(line)
        if not line.endswith(b"\n"):                           # (end of stream, or a line that was cut by the end of it)
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
        writer.write(login_line(self.call, self._password))
        self._last_tx = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(self.login_sec):
                verified, name = await self._answer(reader)
        except TimeoutError:
            raise AprsIsError(f"the server did not answer the login in {self.login_sec:g} s") from None
        self.server_name = name
        if not verified:
            raise Unverified(name)
        self.verified = True
        self.backoff.connected()
        self._set_state(Source.State.CONNECTED)
        text = f"logged in as {self.call}, verified" + (f", server {name}" if name else "")
        self._note(text)
        log.info("aprsis: %s", text)

    async def _answer(self, reader: asyncio.StreamReader) -> tuple[bool, str]:
        while True:
            answer = logresp_of(await self._line(reader, "the server hung up after the login"))
            if answer is not None:
                return answer

    def _refused(self, name: str) -> None:
        self.unverified = True
        self.problem = ""
        text = f"login as {self.call} was not verified" + (f" by {name}" if name else "")
        self._set_state(Source.State.WAITING, UNVERIFIED)
        self._note(f"{text}: {UNVERIFIED}; nothing is sent")
        log.warning("aprsis: %s: %s; nothing is sent until the settings change", text, UNVERIFIED)

    # ---- the connection while it is logged in
    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks = [asyncio.create_task(self._read(reader), name="aprsis-read"), asyncio.create_task(self._write(writer), name="aprsis-write")]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()                                  # (neither ends but by raising)
        finally:
            await cancel_all(tasks)
            for task in tasks:
                if task.done() and not task.cancelled():
                    task.exception()                           # (one that ended with the other is looked at, so that it is not reported as lost)

    async def _read(self, reader: asyncio.StreamReader) -> None:
        """Reads what the server sends and throws it away, for as long as it keeps sending something."""
        while True:
            try:
                async with asyncio.timeout(self.lost_sec):
                    await self._line(reader, "the server hung up")
            except TimeoutError:
                raise ConnectionError(f"nothing from the server for {self.lost_sec:g} s") from None
            except ValueError:                                 # (a line longer than the reader takes)
                raise ConnectionError("the server sent a line that is too long") from None
            self.last_byte_at = self.now()

    async def _write(self, writer: asyncio.StreamWriter) -> None:
        loop = asyncio.get_running_loop()
        while True:
            if not self._queue:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), max(0.0, self.quiet_sec - (loop.time() - self._last_tx)))
                except TimeoutError:
                    self._queue.append(f"# {PROGRAM} {VERSION}".encode("ascii"))          # (the server ignores a comment; the write finds a connection that has died)
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
