"""The UI interface of the Mercury program, as a client: a WebSocket on the loopback (mercuryscope.py says what it carries) that the daemon turns on in the ini it writes (`ui_enabled`, `ui_port`, the waterfall off) and reads for the
spectrum scope and the transmit level. It is opened after the back-off when it drops, for as long as the owner (mercuryscoping.py) keeps it, and it is an extra: a Mercury without the interface (a refused connection, a server that does not
upgrade) is told once in the log and tried again slowly, and nothing else of the modem depends on it.

The spectrum is switched on when somebody wants it (`want_waterfall`; the modem part wants it whenever the link is open, for the channel-busy control): Mercury then makes twenty frames a second, and the daemon reads and parses them. What is wanted is sent again whenever the link opens."""
import asyncio
import logging
from collections.abc import Callable

from .mercuryscope import tx_gain_command, waterfall_command
from .source import Backoff, os_error_text
from .tasks import TaskSet, cancel_all
from .websocketclient import WebSocketClient, WebSocketError

log = logging.getLogger("neoaprs.mercury")

PATH = "/websocket"                  # the endpoint of Mercury's UI server (mercury_websocket.c)
OUTBOX_MAX = 32                      # commands waiting to be written; the oldest is dropped beyond this


class MercuryUi:
    def __init__(self, host: str, port: int, on_text: Callable[[str], None], on_binary: Callable[[bytes], None], on_state: Callable[[bool], None], backoff: Backoff | None = None) -> None:
        self.host, self.port = host, port
        self._on_text, self._on_binary, self._on_state = on_text, on_binary, on_state        # a text message and a binary frame of Mercury's; the link opened (True) or lost (False)
        self.backoff = backoff or Backoff([1.0, 2.0, 5.0, 10.0, 30.0])
        self._tasks = TaskSet(log, "mercury ui")
        self.connected = False
        self.want_waterfall = False
        self._outbox: asyncio.Queue[str] = asyncio.Queue(OUTBOX_MAX)
        self._told = False                     # the first failure of a series is in the log, the others are not

    def start(self) -> None:
        self.backoff.reset()
        self._told = False
        self._tasks.spawn(self._run(), "mercury-ui")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        self.connected = False

    def waterfall(self, on: bool) -> None:
        """The spectrum feed is wanted (or not any more): remembered, and sent when the link is open."""
        self.want_waterfall = on
        self._send(waterfall_command(on))

    def tx_gain(self, db: float) -> bool:
        """The transmit gain, sent now; False, with nothing sent, while the link is not open (Mercury has it from the ini at its next start)."""
        return self._send(tx_gain_command(db))

    def _send(self, text: str) -> bool:
        if not self.connected:
            return False
        if self._outbox.full():
            self._outbox.get_nowait()
        self._outbox.put_nowait(text)
        return True

    async def _run(self) -> None:
        while True:
            try:
                client = await WebSocketClient.connect(self.host, self.port, PATH)
            except (OSError, TimeoutError, WebSocketError) as e:
                self._failed(e)
                await asyncio.sleep(self.backoff.next_delay_sec())
                continue
            self.backoff.connected()
            self._told = False
            await self._session(client)
            await asyncio.sleep(self.backoff.next_delay_sec())

    def _failed(self, error: BaseException) -> None:
        why = os_error_text(error) if isinstance(error, OSError) else str(error) or type(error).__name__
        if not self._told:
            self._told = True
            log.info("Mercury's UI interface on port %d cannot be reached (%s): there is no scope and no live transmit level, and it is tried again now and then", self.port, why)
        else:
            log.debug("Mercury's UI interface on port %d: %s", self.port, why)

    async def _session(self, client: WebSocketClient) -> None:
        self.connected = True
        while not self._outbox.empty():
            self._outbox.get_nowait()
        writer = asyncio.get_running_loop().create_task(self._write(client), name="mercury-ui-write")
        log.info("Mercury's UI interface on port %d is open", self.port)
        self._on_state(True)
        self._send(waterfall_command(self.want_waterfall))
        why = "Mercury closed it"
        try:
            while (message := await client.recv()) is not None:
                self._deliver(message)
        except (OSError, WebSocketError) as e:
            why = os_error_text(e) if isinstance(e, OSError) else str(e)
        finally:
            self.connected = False
            await cancel_all([writer])
            client.close()
        log.info("Mercury's UI interface on port %d was lost: %s", self.port, why)
        self._on_state(False)

    def _deliver(self, message: tuple[bool, bytes]) -> None:
        is_text, data = message
        try:
            if is_text:
                self._on_text(data.decode("utf-8", "replace"))
            else:
                self._on_binary(data)
        except Exception:
            log.exception("a message of Mercury's UI interface could not be handled")

    async def _write(self, client: WebSocketClient) -> None:
        try:
            while True:
                await client.send_text(await self._outbox.get())
        except (OSError, ConnectionError):
            return
