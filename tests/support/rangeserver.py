"""A web server on the loopback that serves one file with range requests, the way a map server does (206 and Content-Range), and the ways one goes wrong, for the cut of the base map (neoaprs/pmtilescut.py).

    server = await range_server(data)                   # stopped when the test is over; server.url is the address of the file
    server.mode = "whole"                               # ranges (default); whole: 200 and a body that does not end; wrong: other bytes than those asked for; missing: 404;
                                                        # moved: 302 to `server.moved_to`; mute: nothing at all, not even the status line, until the test sets `server.release` or the client closes
    server.cut = 2                                      # the next two answers stop halfway and the connection is closed
    server.busy = 1                                     # the next answer is 503
    server.hold_from = offset                           # an answer for bytes from there sends a little and then nothing, until the test sets `server.release` or the client closes
    server.asked                                        # (first, last) of every request, in order; server.cuts: the cuts begun (each reads the header first); server.sent: the bytes of the bodies sent; server.holding: the answers held now"""
import asyncio
import re

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer

_RANGE = re.compile(r"range:\s*bytes=(\d+)-(\d+)", re.IGNORECASE)


class RangeServer(LoopbackServer):
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.mode = "ranges"
        self.cut = 0
        self.busy = 0
        self.hold_from: int | None = None
        self.moved_to = ""
        self.release = asyncio.Event()
        self.asked: list[tuple[int, int]] = []
        self.sent = 0
        self.holding = 0

    @property
    def cuts(self) -> int:
        return self.asked.count((0, 126))

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/20261020.pmtiles"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
            found = _RANGE.search(head)
            first, last = (int(found.group(1)), int(found.group(2))) if found else (0, len(self.data) - 1)
            self.asked.append((first, last))
            await self._answer(reader, writer, first, min(last, len(self.data) - 1))
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def _answer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, first: int, last: int) -> None:
        if self.busy:
            self.busy -= 1
            writer.write(b"HTTP/1.1 503 Busy\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        if self.mode == "mute":
            await self._hold(reader, writer, b"")
            return
        if self.mode == "moved":
            writer.write(f"HTTP/1.1 302 Found\r\nLocation: {self.moved_to}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode("latin-1"))
            return
        if self.mode == "missing":
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        if self.mode == "whole":
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 100000000000\r\nConnection: close\r\n\r\n")
            while True:
                writer.write(bytes(65536))
                self.sent += 65536
                await writer.drain()
        shift = 1 if self.mode == "wrong" else 0
        body = self.data[first + shift:last + 1 + shift]
        writer.write(f"HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {first + shift}-{last + shift}/{len(self.data)}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("latin-1"))
        if self.cut:
            self.cut -= 1
            body = body[:len(body) // 2]
        elif self.hold_from is not None and first >= self.hold_from:
            await self._hold(reader, writer, body[:1])
            return
        writer.write(body)
        self.sent += len(body)
        await writer.drain()

    async def _hold(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, start: bytes) -> None:
        writer.write(start)
        await writer.drain()
        self.holding += 1
        try:
            closed, released = asyncio.ensure_future(reader.read()), asyncio.ensure_future(self.release.wait())
            await asyncio.wait([closed, released], return_when=asyncio.FIRST_COMPLETED)
            for waiting in (closed, released):
                waiting.cancel()
        finally:
            self.holding -= 1


async def range_server(data: bytes) -> RangeServer:
    server = await RangeServer(data).start()
    remember_stop(server.stop)
    return server
