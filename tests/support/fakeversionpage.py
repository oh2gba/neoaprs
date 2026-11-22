"""A fake version page for the update check, on a free loopback port."""

import asyncio
import json
from typing import Any

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer


class FakeVersionPage(LoopbackServer):
    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        self.answer = answer
        self.status = 200
        self.body: bytes | None = None  # sent instead of the JSON of `answer` when set
        self.hang = False  # accepts and says nothing
        self.requests: list[tuple[str, dict[str, str]]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/version.php"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            self.requests.append(
                (
                    head[0].split(" ")[1],
                    {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)},
                )
            )
            if self.hang:
                await reader.read()  # until the client gives up and closes
                return
            body = self.body if self.body is not None else json.dumps(self.answer).encode()
            writer.write(
                f"HTTP/1.0 {self.status} X\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


async def version_page(answer: dict[str, Any] | None = None) -> FakeVersionPage:
    """A started fake version page, stopped when the test is over."""
    page = await FakeVersionPage(answer).start()
    remember_stop(page.stop)
    return page
