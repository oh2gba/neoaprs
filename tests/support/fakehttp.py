"""A small HTTP server on a free port of the loopback whose answers a test lays down path by path, for the code that makes real requests with urllib (the downloads of Update now): a body, a status, a redirect, a
body cut short, a chunked body that stops in a chunk, an answer that is not HTTP, a server that says nothing.

    server = await http_server()
    server.route("/a", body=b"abc")                                  # 200 with Content-Length
    server.route("/gone", status=404)
    server.route("/go", status=302, headers={"Location": server.url("/a")})
    server.route("/cut", body=b"x" * 10, announce=100)                # says 100 bytes, sends 10 and closes
    server.route("/chunk", chunked_cut=b"x" * 10)                    # a chunked body that stops in the middle of a chunk
    server.route("/junk", raw=b"not http at all\r\n")
    server.route("/hang", hang=True)                                 # takes the request and never answers
    await asyncio.to_thread(urllib.request.urlopen, server.url("/a")) # (the client blocks: run it in a thread)
    server.requests                                                  # the path of every request, in order

The test is responsible for allowing the address: the daemon's own check lets only GitHub through, and a test of the guard hands its own."""
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
                await reader.read()                       # until the client gives up and closes
                return
            if route.raw is not None:
                writer.write(route.raw)
            elif route.chunked_cut is not None:
                writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + b"%x\r\n" % (len(route.chunked_cut) + 100) + route.chunked_cut)
            else:
                length = len(route.body) if route.announce is None else route.announce
                lines = [f"HTTP/1.1 {route.status} {'OK' if route.status == 200 else 'Other'}", f"Content-Length: {length}", "Connection: close", *(f"{k}: {v}" for k, v in route.headers.items())]
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
