"""A fake server of the map's layers on a free port of the loopback: an own aircraft receiver, or a service's address through NEOAPRS_LAYERS_URL (no test asks adsb.fi, adsb.lol or Fintraffic). Each request is
kept with its headers; each path answers what the test laid down, packed or not.

    server = await layers_server()
    server.route("/tar1090/data/aircraft.json", body=b'{"now": 1, "aircraft": []}')
    server.route("/api/v3/lat/60.2/lon/24.7/dist/86", status=429, headers={"Retry-After": "120"})
    server.answer = lambda path: (200, body, {})                      # every path not routed (a service's path carries the position)
    server.requests                                                   # [(path, headers lower-cased), ...]
    server.password = ("user", "pw")                                  # every path asks for basic authentication with these (401 without them)
    server.route("/slow", body=b"...", drip_sec=0.3)                  # the head at once, then the body one byte at a time
    server.address                                                    # 127.0.0.1:PORT, what map/aircraft_host is set to
"""
import asyncio
import base64
import gzip
from collections.abc import Callable
from dataclasses import dataclass, field

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer


@dataclass
class Answer:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    packed: bool = False                     # sent with Content-Encoding: gzip
    drip_sec: float = 0.0                    # the body sent one byte every this many seconds


class FakeLayers(LoopbackServer):
    def __init__(self) -> None:
        self.routes: dict[str, Answer] = {}
        self.answer: Callable[[str], Answer] | None = None
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.password: tuple[str, str] | None = None

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def route(self, path: str, **options: object) -> None:
        self.routes[path] = Answer(**options)  # type: ignore[arg-type]

    def paths(self) -> list[str]:
        return [path for path, _ in self.requests]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            path = head[0].split(" ")[1]
            headers = {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)}
            self.requests.append((path, headers))
            answer = self.routes.get(path) or (self.answer(path) if self.answer is not None else Answer(status=404))
            if self.password is not None and headers.get("authorization") != "Basic " + base64.b64encode(":".join(self.password).encode()).decode():
                answer = Answer(status=401, headers={"WWW-Authenticate": 'Basic realm="receiver"'})
            body = gzip.compress(answer.body) if answer.packed else answer.body
            lines = [f"HTTP/1.1 {answer.status} X", f"Content-Length: {len(body)}", "Connection: close", *(["Content-Encoding: gzip"] if answer.packed else []), *(f"{k}: {v}" for k, v in answer.headers.items())]
            writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + (b"" if answer.drip_sec else body))
            await writer.drain()
            for at in range(len(body) if answer.drip_sec else 0):
                await asyncio.sleep(answer.drip_sec)
                if writer.is_closing():                 # (the asker gave up)
                    break
                writer.write(body[at:at + 1])
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


async def layers_server() -> FakeLayers:
    """A started fake server, stopped when the test is over."""
    server = await FakeLayers().start()
    remember_stop(server.stop)
    return server
