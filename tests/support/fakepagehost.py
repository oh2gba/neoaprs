"""The WebServer as the page's socket (neoaprs/web/pagesocket.py) sees it, made of fakes: a host that lets every request in and an Api that writes down what it is told, behind a real Tornado server on a free port
of the loopback, for the tests of the socket on its own (the daemon's Api and the whole WebServer are in tests/test_web.py).

    host = await page_host()                       # started; stopped when the test is over
    ws = await websocket_connect(host.url)         # a real WebSocket client
    host.api.sockets                               # the Socket handlers that were attached, in order
    host.api.commands                              # (the handler, the text) of every command
"""
import asyncio
from typing import Any

import tornado.httpserver
import tornado.httputil
import tornado.web
from tornado.iostream import IOStream
from tornado.netutil import bind_sockets

from neoaprs.web.pagesocket import Socket
from tests.support.env import remember_stop


class FakeApi:
    def __init__(self) -> None:
        self.sockets: list[Socket] = []
        self.commands: list[tuple[Socket, str]] = []
        self.detached: list[Socket] = []

    def attach(self, socket: Socket, ip: str = "") -> None:
        self.sockets.append(socket)

    def on_command(self, socket: Socket, text: str) -> None:
        self.commands.append((socket, text))

    def detach(self, socket: Socket) -> None:
        self.detached.append(socket)


class FakeGate:
    def allowed(self, request: tornado.httputil.HTTPServerRequest) -> bool:
        return True


class FakePageHost:
    """Everything a Socket asks of its server: the checks say yes, the Api writes down."""

    def __init__(self) -> None:
        self.api = FakeApi()
        self.access = FakeGate()
        self.proved: list[IOStream] = []
        self.port = 0
        self._server: tornado.httpserver.HTTPServer | None = None

    def host_allowed(self, header: str) -> bool:
        return True

    def note_foreign_host(self, shown: str) -> None:
        pass

    def secure_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None:
        return None

    def page_proved(self, stream: IOStream) -> None:
        self.proved.append(stream)

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws"

    async def start(self) -> "FakePageHost":
        app: Any = tornado.web.Application([(r"/ws", Socket, {"server": self})], websocket_ping_interval=30, websocket_max_message_size=64 * 1024)
        sockets = bind_sockets(0, "127.0.0.1")
        self.port = sockets[0].getsockname()[1]
        self._server = tornado.httpserver.HTTPServer(app)
        self._server.add_sockets(sockets)
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.stop()
            await asyncio.wait_for(self._server.close_all_connections(), 5)


async def page_host() -> FakePageHost:
    host = await FakePageHost().start()
    remember_stop(host.stop)
    return host
