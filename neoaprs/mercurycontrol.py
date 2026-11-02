"""The control port of the Mercury program (mercury.py: `parse_control_line`): a second TCP connection beside the KISS line, where Mercury says when it keys the radio (`PTT ON`, `PTT OFF`), when its busy
detector hears a signal on the channel (`BUSY ON`, `BUSY OFF`), the signal-to-noise ratio of what it decodes (`SN`) and that it is alive. Nothing is written to it: Mercury takes commands there (`MYCALL`, `LISTEN`,
`CONNECT`) that are the ARQ plane's, and NeoAPRS has no use for them. The line is opened again after the back-off when it drops, for as long as the owner (mercurymodem.py) keeps it; a connection that is refused is
Mercury not running, which the owner knows from the process."""
import asyncio
import logging
from collections.abc import Callable

from .mercury import ControlEvent, parse_control_line, split_control_lines
from .source import Backoff, os_error_text
from .tasks import TaskSet

log = logging.getLogger("neoaprs.mercury")

CONNECT_SEC = 3.0
READ_BYTES = 4096


class ControlLine:
    def __init__(self, host: str, port: int, on_event: Callable[[ControlEvent], None], on_state: Callable[[bool, str], None], backoff: Backoff | None = None) -> None:
        self.host, self.port = host, port
        self._on_event, self._on_state = on_event, on_state          # a line Mercury wrote; the connection made (True, "") or lost (False, why)
        self.backoff = backoff or Backoff([1.0, 2.0, 5.0])
        self._tasks = TaskSet(log, "mercury control")
        self.connected = False

    def start(self) -> None:
        self.backoff.reset()
        self._tasks.spawn(self._run(), "mercury-control")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        self.connected = False

    async def _run(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CONNECT_SEC)
            except (OSError, TimeoutError) as e:
                await asyncio.sleep(self.backoff.next_delay_sec())
                log.debug("mercury control port %d: %s", self.port, os_error_text(e))
                continue
            self.backoff.connected()
            self.connected = True
            self._on_state(True, "")
            try:
                await self._read(reader)
                why = "Mercury closed its control port"
            except (OSError, asyncio.IncompleteReadError) as e:
                why = os_error_text(e)
            finally:
                self.connected = False
                writer.close()
            self._on_state(False, why)
            await asyncio.sleep(self.backoff.next_delay_sec())

    async def _read(self, reader: asyncio.StreamReader) -> None:
        buffer = bytearray()
        while chunk := await reader.read(READ_BYTES):
            buffer.extend(chunk)
            for line in split_control_lines(buffer):
                self._on_event(parse_control_line(line))
