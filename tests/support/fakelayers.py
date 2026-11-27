"""A fake map layers server on a free loopback port: an aircraft receiver, a service address
through NEOAPRS_LAYERS_URL, or the project's satellites file through NEOAPRS_SATELLITES_URL. Each
request is kept with its headers; each path answers what the test laid down.
"""

import asyncio
import base64
import csv
import gzip
import io
import json
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.support.env import remember_stop
from tests.support.files import fixture_text
from tests.support.loopbackserver import LoopbackServer

SATELLITES_PATH = "/api/v1/satellites.php"
SATELLITE_LIST = Path(__file__).resolve().parents[2] / "server" / "neo" / "private" / "satellites-list.json"


def satellites_file(made: str = "2026-11-27T18:00:00Z", only: Collection[int] = (), **over: Any) -> bytes:
    """The file the project's server serves: its list merged with the elements of the fixture
    (CelesTrak's, 27 Nov 2026), as server/neo/api/v1/satellites.php merges them; `only` keeps those."""
    rows = {
        int(row["NORAD_CAT_ID"]): row for row in csv.DictReader(io.StringIO(fixture_text("satellites/amateur.csv")))
    }
    listed = json.loads(SATELLITE_LIST.read_text(encoding="utf-8"))["satellites"]
    satellites = [
        {**{k: v for k, v in one.items() if k != "source"}, "elements": rows.get(one["id"])}
        for one in listed
        if not only or one["id"] in only
    ]
    return json.dumps(
        {"v": 1, "made": made, "elements_at": "2026-11-27T17:59:24Z", "satellites": satellites, **over}
    ).encode()


@dataclass
class Answer:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    packed: bool = False  # sent with Content-Encoding: gzip
    drip_sec: float = 0.0  # the body sent one byte every this many seconds


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
            if (
                self.password is not None
                and headers.get("authorization")
                != "Basic " + base64.b64encode(":".join(self.password).encode()).decode()
            ):
                answer = Answer(status=401, headers={"WWW-Authenticate": 'Basic realm="receiver"'})
            body = gzip.compress(answer.body) if answer.packed else answer.body
            lines = [
                f"HTTP/1.1 {answer.status} X",
                f"Content-Length: {len(body)}",
                "Connection: close",
                *(["Content-Encoding: gzip"] if answer.packed else []),
                *(f"{k}: {v}" for k, v in answer.headers.items()),
            ]
            writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + (b"" if answer.drip_sec else body))
            await writer.drain()
            for at in range(len(body) if answer.drip_sec else 0):
                await asyncio.sleep(answer.drip_sec)
                if writer.is_closing():  # (the asker gave up)
                    break
                writer.write(body[at : at + 1])
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
