"""A fake server for Send logs, on a free port of the loopback (no test sends anything to the project's real server): it reads the multipart form the daemon posts and keeps what it held.

    server = await support_server()                     # {"ok": true, "ref": "NEO-20261103-1015-7F3A"} to every post
    monkeypatch.setenv("NEOAPRS_SUPPORT_URL", server.url)
    server.requests[0].fields["note"]                  # the text fields
    server.requests[0].files["bundle"]                 # (file name, bytes)
    server.status, server.answer = 429, {"ok": False, "reason": "rate"}
    server.body = b"<html>"                            # sent instead of the JSON
    server.hang = True                                 # accepts, reads the request and says nothing
"""
import asyncio
import json
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from typing import Any

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer


@dataclass
class Received:
    path: str
    headers: dict[str, str]
    fields: dict[str, str] = field(default_factory=dict)
    files: dict[str, tuple[str, bytes]] = field(default_factory=dict)


def parse_form(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    """(the text fields, the files as name -> (file name, content)) of a multipart/form-data body."""
    message = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in message.iter_parts():
        name = str(part.get_param("name", header="content-disposition"))
        content = part.get_payload(decode=True)
        assert isinstance(content, bytes)
        filename = part.get_filename()
        if filename is None:
            fields[name] = content.decode("utf-8")
        else:
            files[name] = (filename, content)
    return fields, files


class FakeSupportServer(LoopbackServer):
    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        self.answer: dict[str, Any] = answer if answer is not None else {"ok": True, "ref": "NEO-20261103-1015-7F3A"}
        self.status = 200
        self.body: bytes | None = None
        self.hang = False
        self.requests: list[Received] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/support/send.php"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            headers = {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)}
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            received = Received(head[0].split(" ")[1], headers)
            if head[0].startswith("POST") and headers.get("content-type", "").startswith("multipart/form-data"):
                received.fields, received.files = parse_form(headers["content-type"], body)
            self.requests.append(received)
            if self.hang:
                await reader.read()
                return
            sent = self.body if self.body is not None else json.dumps(self.answer).encode()
            writer.write(f"HTTP/1.0 {self.status} X\r\nContent-Type: application/json\r\nContent-Length: {len(sent)}\r\n\r\n".encode() + sent)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


async def support_server(answer: dict[str, Any] | None = None) -> FakeSupportServer:
    """A started fake Send logs server, stopped when the test is over."""
    server = await FakeSupportServer(answer).start()
    remember_stop(server.stop)
    return server
