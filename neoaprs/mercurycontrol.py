"""The control port of the Mercury program (mercury.py: `parse_control_line`): a second TCP connection beside the KISS line, where Mercury says when it keys the radio (`PTT ON`, `PTT OFF`), when its busy
detector hears a signal on the channel (`BUSY ON`, `BUSY OFF`), the signal-to-noise ratio of what it decodes (`SN`) and that it is alive. One thing is written to it, the `TUNE` command of Tune and the keying
test (`write`); the other commands Mercury takes there (`MYCALL`, `LISTEN`, `CONNECT`) are the ARQ plane's, and NeoAPRS has no use for them. The line is opened again after the back-off when it drops, for as long as
the owner (mercurymodem.py) keeps it; a connection that is refused is Mercury not running, which the owner knows from the process. A Mercury from 1.9.24 on keeps its control port for the host that is connected and closes another one at once,
before a word (data_interfaces/tcp_interfaces.c, refuse_client). One connection closed so may be Mercury ending; a second in a row is another program holding the port of a Mercury something else runs, and after
an empty close the next connection is open only once Mercury writes on it."""
import asyncio
import logging
from collections.abc import Callable

from . import nodevices
from .mercury import ControlEvent, parse_control_line, split_control_lines
from .source import Backoff, os_error_text
from .tasks import TaskSet

log = logging.getLogger("neoaprs.mercury")

CONNECT_SEC = 3.0
READ_BYTES = 4096
EMPTY = "Mercury closed its control port before it wrote a line"                     # a connection closed before a byte came: Mercury ending, or the refusal below
HELD = "Mercury closed its control port at once: another program holds it"          # two such closes in a row: what a Mercury from 1.9.24 on does to a second host while the first is connected


class ControlLine:
    def __init__(self, host: str, port: int, on_event: Callable[[ControlEvent], None], on_state: Callable[[bool, str], None], backoff: Backoff | None = None) -> None:
        self.host, self.port = host, port
        self._on_event, self._on_state = on_event, on_state          # a line Mercury wrote; the connection made (True, "") or lost (False, why)
        self.backoff = backoff or Backoff([1.0, 2.0, 5.0])
        self._tasks = TaskSet(log, "mercury control")
        self.connected = False
        self._writer: asyncio.StreamWriter | None = None

    def start(self) -> None:
        self.backoff.reset()
        self._tasks.spawn(self._run(), "mercury-control")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        self.connected = False
        self._writer = None

    def write(self, line: str) -> bool:
        """A command to Mercury, CR-terminated as it reads them; False, with nothing written, while the line is not open."""
        if self._writer is None or not self.connected:
            return False
        try:
            self._writer.write(line.encode("ascii") + b"\r")
        except OSError as e:
            log.info("mercury control port %d: %s could not be written: %s", self.port, line, os_error_text(e))
            return False
        log.debug("mercury control port %d: %s", self.port, line)
        return True

    async def _run(self) -> None:
        empty = 0                                                # how many connections in a row Mercury closed before it wrote a byte (a Mercury from 1.9.24 on takes one host at a time and closes the next at once)
        while True:
            try:
                nodevices.check_host(self.host, "the control port of a Mercury")        # (under the no-devices switch a Mercury that something else runs on another computer is not there)
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CONNECT_SEC)
            except (OSError, TimeoutError) as e:
                await asyncio.sleep(self.backoff.next_delay_sec())
                log.debug("mercury control port %d: %s", self.port, os_error_text(e))
                continue
            up = not empty                                       # (after an empty close the line is open only once Mercury writes on it, so that a port another program keeps is not open and lost every few seconds)
            if up:
                self._up(writer)
            heard = False
            try:
                buffer = bytearray()
                while chunk := await reader.read(READ_BYTES):
                    if not heard:
                        heard = True
                        self.backoff.connected()
                        if not up:
                            up = True
                            self._up(writer)
                    buffer.extend(chunk)
                    for line in split_control_lines(buffer):
                        self._on_event(parse_control_line(line))
                why = "Mercury closed its control port" if heard else EMPTY
            except (OSError, asyncio.IncompleteReadError) as e:
                why = os_error_text(e)
            finally:
                self.connected = False
                self._writer = None
                writer.close()
            empty = empty + 1 if why == EMPTY else 0
            if empty == 2:
                log.info("mercury control port %d: %s", self.port, HELD)
            if up:
                self._on_state(False, why)
            await asyncio.sleep(self.backoff.next_delay_sec())

    def _up(self, writer: asyncio.StreamWriter) -> None:
        self.connected = True
        self._writer = writer
        self._on_state(True, "")
