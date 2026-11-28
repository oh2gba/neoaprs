"""A browser tab for the tests: a WebSocket client against the daemon's /ws that keeps every message
it is sent and the topics as the page would have them.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from tornado.websocket import WebSocketClientConnection, websocket_connect

from tests.support.patience import PATIENCE_SEC


class WsClient:
    def __init__(self, ws: WebSocketClientConnection) -> None:
        self.ws = ws
        self.messages: list[dict[str, Any]] = []
        # The binary frames (the rows of the waterfall), which are no messages
        self.binary: list[bytes] = []
        self.topics: dict[str, Any] = {}  # the page's copy of each topic
        self.revs: dict[str, int] = {}
        self.closed_with: tuple[int | None, str | None] | None = None
        self._read = 0  # messages[:_read] have been returned by recv / expect
        self._arrived = asyncio.Event()
        self.task = asyncio.get_running_loop().create_task(self._reader(), name="test-ws-reader")

    async def _reader(self) -> None:
        while True:
            raw = await self.ws.read_message()
            if raw is None:
                self.closed_with = (self.ws.close_code, self.ws.close_reason)
                self._arrived.set()
                return
            if isinstance(raw, bytes):
                self.binary.append(raw)
                self._arrived.set()
                continue
            message = json.loads(raw)
            self.messages.append(message)
            self._apply(message)
            self._arrived.set()

    def _apply(self, message: dict[str, Any]) -> None:
        if message["type"] == "state":
            self.topics[message["topic"]] = message["value"]
            self.revs[message["topic"]] = message["rev"]
        elif message["type"] == "patch":
            name = message["topic"]
            self.revs[name] = message["rev"]
            for op in message["ops"]:
                if op["op"] == "replace":
                    self.topics[name] = op["value"]
                elif op["op"] == "set":
                    self.topics[name][op["key"]] = op["value"]
                else:
                    self.topics[name].pop(op["key"], None)

    # ---- sending
    async def send(self, command: dict[str, Any]) -> None:
        await self.ws.write_message(json.dumps(command))

    async def send_text(self, text: str) -> None:
        """A frame as it is, to show what the daemon does with one that is not a command."""
        await self.ws.write_message(text)

    # ---- reading
    def of(self, kind: str, topic: str | None = None) -> list[dict[str, Any]]:
        """All the messages of a type so far (of a topic, for `state` and `patch`), read or not."""
        return [m for m in self.messages if m["type"] == kind and (topic is None or m.get("topic") == topic)]

    def ops(self, topic: str) -> list[dict[str, Any]]:
        """Every op of every patch of the topic so far, in order."""
        return [op for m in self.of("patch", topic) for op in m["ops"]]

    async def _wait(self, deadline: float) -> None:
        self._arrived.clear()
        left = deadline - asyncio.get_running_loop().time()
        if left <= 0:
            raise TimeoutError
        try:
            await asyncio.wait_for(self._arrived.wait(), left)
        except asyncio.TimeoutError:
            raise TimeoutError from None

    async def frames(self, count: int, timeout: float = 5.0) -> list[bytes]:
        """Waits until `count` binary frames have come, and gives all that have."""
        deadline = asyncio.get_running_loop().time() + timeout
        while len(self.binary) < count:
            try:
                await self._wait(deadline)
            except TimeoutError:
                raise AssertionError(f"{len(self.binary)} binary frames came, not {count}") from None
        return list(self.binary)

    async def recv(self, timeout: float = 5.0) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while self._read >= len(self.messages):
            assert self.closed_with is None, f"the socket was closed {self.closed_with}"
            try:
                await self._wait(deadline)
            except TimeoutError:
                raise AssertionError("no message came") from None
        self._read += 1
        return self.messages[self._read - 1]

    async def expect(self, kind: str, topic: str | None = None, timeout: float = 5.0) -> dict[str, Any]:
        """The next message of the type (of the topic, for `state` and `patch`); the ones before it
        are read and stay in `messages`."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                message = await self.recv(max(0.0, deadline - asyncio.get_running_loop().time()))
            except AssertionError:
                raise AssertionError(
                    f"no {kind}{' of ' + topic if topic else ''} message came; got {[self._label(m) for m in self.messages]}"
                ) from None
            if message["type"] == kind and (topic is None or message.get("topic") == topic):
                return message

    @staticmethod
    def _label(message: dict[str, Any]) -> str:
        return f"{message['type']}:{message['topic']}" if "topic" in message else str(message["type"])

    async def until(self, condition: Callable[[], object], timeout: float = PATIENCE_SEC) -> None:
        """Waits until the condition holds (it is looked at when a message arrives). A condition
        that looks at a topic or a row that has not come yet (KeyError) does not hold yet."""

        def holds() -> bool:
            try:
                return bool(condition())
            except KeyError:
                return False

        deadline = asyncio.get_running_loop().time() + timeout
        while not holds():
            try:
                await self._wait(deadline)
            except TimeoutError:
                raise AssertionError(
                    f"the condition did not come true; got {[self._label(m) for m in self.messages]}"
                ) from None
            if self.closed_with is not None and not holds():
                raise AssertionError(f"the socket was closed {self.closed_with}")

    async def quiet(self, seconds: float = 0.3) -> None:
        """Lets `seconds` pass, so that what is going to arrive has."""
        await asyncio.sleep(seconds)

    async def aclose(self) -> None:
        """Closes the socket and waits until the reader has ended."""
        self.ws.close()
        try:
            await asyncio.wait_for(asyncio.shield(self.task), 5.0)
        except asyncio.TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


async def connect(port: int, host: str | None = None, origin: str | None = None, cookie: str | None = None) -> WsClient:
    """The daemon's socket at 127.0.0.1:port; `host`, `origin` and `cookie` set those headers when
    given."""
    from tornado.httpclient import HTTPRequest

    headers = {
        **({} if host is None else {"Host": host}),
        **({} if origin is None else {"Origin": origin}),
        **({} if cookie is None else {"Cookie": cookie}),
    }
    request = HTTPRequest(f"ws://127.0.0.1:{port}/ws", headers=headers or None, connect_timeout=5)
    return WsClient(await websocket_connect(request))
