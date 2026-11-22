"""A small HTTP server on a free loopback port whose answers a test lays down path by path: a body,
a status, a redirect, a cut-short or chunked body, an answer that is not HTTP, or silence.
"""

import asyncio
from dataclasses import dataclass, field

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer


@dataclass
class Route:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    announce: int | None = None
    chunked_cut: bytes | None = None
    raw: bytes | None = None
    hang: bool = False


class FakeHttp(LoopbackServer):
    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.requests: list[str] = []

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def route(self, path: str, **options: object) -> None:
        self.routes[path] = Route(**options)  # type: ignore[arg-type]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            path = head[0].split(" ")[1]
            self.requests.append(path)
            route = self.routes.get(path, Route(status=404))
            if route.hang:
                await reader.read()  # until the client gives up and closes
                return
            if route.raw is not None:
                writer.write(route.raw)
            elif route.chunked_cut is not None:
                writer.write(
                    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                    + b"%x\r\n" % (len(route.chunked_cut) + 100)
                    + route.chunked_cut
                )
            else:
                length = len(route.body) if route.announce is None else route.announce
                lines = [
                    f"HTTP/1.1 {route.status} {'OK' if route.status == 200 else 'Other'}",
                    f"Content-Length: {length}",
                    "Connection: close",
                    *(f"{k}: {v}" for k, v in route.headers.items()),
                ]
                writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + route.body)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


async def http_server() -> FakeHttp:
    """A started fake server, stopped when the test is over."""
    server = await FakeHttp().start()
    remember_stop(server.stop)
    return server
