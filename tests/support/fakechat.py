"""A stand-in for the chat of the project's server (server/neo/api/v1/chat.php and the chat.json it
writes) on a free loopback port: it answers a GET with the ETag and Last-Modified it is set to give,
and 304 when the reader sends them back unchanged."""

import asyncio
import json
from typing import Any

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer

WRITTEN = "2026-11-28T12:00:00Z"


class FakeChat(LoopbackServer):
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] | None = None  # None: no chat yet (404)
        self.closed = False
        self.written = WRITTEN
        self.etag = True
        self.modified = True
        self.version = 0  # grows with each change, for the fingerprints
        self.refuse: tuple[str, int] | None = None
        self.down = False
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, str]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/chat.json"

    def chat(self) -> dict[str, Any]:
        return {"v": 1, "written": self.written, "closed": self.closed, "lines": self.lines or []}

    def add(self, call: str, text: str, at: str = WRITTEN) -> int:
        lines = self.lines if self.lines is not None else []
        ident = (lines[-1]["id"] if lines else 0) + 1
        self.lines = [*lines, {"id": ident, "at": at, "call": call, "text": text}][-100:]
        self.version += 1
        return ident

    def _fingerprints(self) -> dict[str, str]:
        said = {}
        if self.etag:
            said["ETag"] = f'"v{self.version}"'
        if self.modified:
            said["Last-Modified"] = f"Sat, 28 Nov 2026 12:00:{self.version % 60:02d} GMT"
        return said

    def _answer(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.posts.append(body)
        if self.refuse is not None:
            return self.refuse[1], {"ok": False, "reason": self.refuse[0]}
        if body.get("action") != "say":
            return 400, {"ok": False, "reason": "bad_request"}
        ident = self.add(body["call"], body["text"])
        return 200, {"ok": True, "id": ident, "chat": self.chat()}

    def _get(self, headers: dict[str, str]) -> tuple[int, bytes, dict[str, str]]:
        self.gets.append(headers)
        if self.lines is None:
            return 404, b"", {}
        said = self._fingerprints()
        if (self.etag and headers.get("if-none-match") == said["ETag"]) or (
            not self.etag and self.modified and headers.get("if-modified-since") == said["Last-Modified"]
        ):
            return 304, b"", said
        return 200, json.dumps(self.chat()).encode(), said

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            headers = {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)}
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            if self.down:
                return
            extra: dict[str, str] = {}
            if head[0].startswith("POST "):
                status, data = self._answer(json.loads(body))
                sent = json.dumps(data).encode()
            else:
                status, sent, extra = self._get(headers)
            lines = "".join(f"{k}: {v}\r\n" for k, v in extra.items())
            writer.write(
                f"HTTP/1.0 {status} X\r\nContent-Type: application/json\r\n{lines}Content-Length: {len(sent)}\r\n\r\n".encode()
                + sent
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


async def chat_server() -> FakeChat:
    """A started fake chat, stopped when the test is over."""
    server = await FakeChat().start()
    remember_stop(server.stop)
    return server
