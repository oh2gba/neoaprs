"""Stand-ins for the rig programs an operator runs: flrig's XML-RPC server and Hamlib's rigctld.

Each records every key-down and key-up with its time (`time.monotonic`) and can be told to hang (read
and never answer), to refuse (flrig: no radio connected; rigctld: `RPRT -1`), to leave the rig keyed
(the key-up is not taken) or to die (stop listening and drop every connection).
"""

import asyncio
import time
import xmlrpc.client
from dataclasses import dataclass, field
from typing import Literal

from tests.support.env import remember_stop

Mode = Literal["ok", "hang", "refuse", "stuck"]


@dataclass
class Keyed:
    on: bool
    at: float


@dataclass
class FakeRig:
    """What both stand-ins share: the rig's PTT, what was asked, and how to misbehave."""

    mode: Mode = "ok"
    ptt: int = 0
    keyed: list[Keyed] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    port: int = 0
    _server: asyncio.Server | None = None
    _writers: list[asyncio.StreamWriter] = field(default_factory=list)
    _hanging: list[asyncio.Event] = field(default_factory=list)

    async def start(self) -> "FakeRig":
        self._server = await asyncio.start_server(self._client, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        remember_stop(self.die)
        return self

    async def die(self) -> None:
        """Stop listening and drop every connection: the program is gone."""
        for event in self._hanging:
            event.set()
        if self._server is not None:
            self._server.close()
            self._server = None
        for writer in self._writers:
            writer.transport.abort()
        self._writers.clear()

    @property
    def downs(self) -> list[float]:
        return [k.at for k in self.keyed if k.on]

    @property
    def ups(self) -> list[float]:
        return [k.at for k in self.keyed if not k.on]

    def _set(self, on: int) -> bool:
        """Take a set of the PTT; return whether it was refused."""
        if self.mode == "refuse":
            return True
        self.keyed.append(Keyed(bool(on), time.monotonic()))
        if not (self.mode == "stuck" and not on):
            self.ptt = on
        return False

    async def _hang(self) -> None:
        event = asyncio.Event()
        self._hanging.append(event)
        await event.wait()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.append(writer)
        try:
            await self._serve(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.transport.abort()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        raise NotImplementedError


class FakeFlrig(FakeRig):
    """flrig's XML-RPC server, answering in the bytes of its XmlRpc++ (src/xmlrpcpp/XmlRpcServer.cpp)."""

    @staticmethod
    def answer(value_xml: str) -> bytes:
        body = f'<?xml version="1.0"?>\r\n<methodResponse><params><param>\r\n\t{value_xml}\r\n</param></params></methodResponse>\r\n'
        head = (
            f"HTTP/1.1 200 OK\r\nServer: XMLRPC++ 0.8\r\nContent-Type: text/xml\r\nContent-length: {len(body)}\r\n\r\n"
        )
        return (head + body).encode()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
            length = next(
                int(f.split(":", 1)[1]) for f in head.split("\r\n") if f.lower().startswith("content-length:")
            )
            params, method = xmlrpc.client.loads((await reader.readexactly(length)).decode())
            self.asked.append(str(method))
            if self.mode == "hang":
                await self._hang()
                return
            if method == "rig.set_ptt":
                # flrig answers 0 at once while it has no radio, else nothing (an invalid XmlRpcValue)
                writer.write(self.answer("<value><i4>0</i4></value>" if self._set(int(str(params[0]))) else ""))
            elif method == "rig.get_ptt":
                writer.write(self.answer(f"<value><i4>{self.ptt}</i4></value>"))
            elif method == "main.get_version":
                writer.write(self.answer("<value>2.0.05</value>"))
            await writer.drain()


class FakeRigctld(FakeRig):
    """rigctld's default protocol for `T` and `t`: `RPRT 0` for a set, the PTT on a line for a get."""

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while raw := await reader.readline():
            line = raw.decode("latin-1").strip()
            self.asked.append(line)
            if self.mode == "hang":
                await self._hang()
                return
            if line.startswith("T "):
                writer.write(b"RPRT -1\n" if self._set(int(line[2:])) else b"RPRT 0\n")
            elif line == "t":
                writer.write(b"RPRT -1\n" if self.mode == "refuse" else f"{self.ptt}\n".encode())
            await writer.drain()
