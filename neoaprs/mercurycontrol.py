"""Client of the Mercury control port, a second TCP connection beside the KISS line.

Mercury reports PTT, BUSY and SNR there; only `TUNE` is written. The line reconnects after a back-off.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from . import nodevices
from .mercury import ControlEvent, parse_control_line, split_control_lines
from .source import Backoff, os_error_text
from .tasks import TaskSet

log = logging.getLogger("neoaprs.mercury")

CONNECT_SEC = 3.0
READ_BYTES = 4096
EMPTY = "Mercury closed its control port before it wrote a line"
# Mercury refuses a second host while the first is connected, closing at once before a word.
HELD = "Mercury closed its control port at once: another program holds it"


class ControlLine:
    def __init__(
        self,
        host: str,
        port: int,
        on_event: Callable[[ControlEvent], None],
        on_state: Callable[[bool, str], None],
        backoff: Backoff | None = None,
        refuses: Callable[[], bool | Awaitable[bool]] = lambda: False,
    ) -> None:
        self.host, self.port = host, port
        self._on_event, self._on_state = on_event, on_state
        self._refuses = refuses  # asked before each connect: True keeps the line from the port
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
        """Send a CR-terminated command; return False without writing if the line is not open."""
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
        empty = 0
        while True:
            refused = self._refuses()
            if refused if isinstance(refused, bool) else await refused:
                await asyncio.sleep(self.backoff.next_delay_sec())
                continue
            try:
                nodevices.check_host(self.host, "the control port of a Mercury")
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CONNECT_SEC)
            except (OSError, TimeoutError, OverflowError, ValueError) as e:  # (a port beyond 65535 overflows)
                await asyncio.sleep(self.backoff.next_delay_sec())
                log.debug("mercury control port %d: %s", self.port, os_error_text(e))
                continue
            # After an empty close, report up only once Mercury writes (a held port flaps otherwise).
            up = not empty
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
