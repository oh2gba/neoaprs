"""A stand-in for AISStream on a free loopback port: a WebSocket server (permessage-deflate when the
client offers it) that keeps every subscription with the seconds it came after the upgrade, refuses
a key that is not the one it was given, closes a connection whose first subscription is later than
3 s, sends the test's reports to every subscribed connection, and can drop or stall them."""

import asyncio
import contextlib
import json
import struct
import time
import zlib
from dataclasses import dataclass, field
from typing import Any

from neoaprs.websocketclient import BINARY, CLOSE, PING, PONG, TEXT, accept_of, frame
from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer

KEY = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"  # made up
REFUSAL = {"error": "Api Key Is Not Valid"}
FIRST_SUBSCRIPTION_SEC = 3.0


@dataclass
class Subscription:
    key: str
    boxes: list[list[list[float]]]
    types: list[str]
    after_sec: float  # since the upgrade of its connection


@dataclass
class _Client:
    writer: asyncio.StreamWriter
    packer: Any | None  # a zlib compressobj while permessage-deflate is on
    subscribed: bool = False


@dataclass
class FakeAisStream(LoopbackServer):
    key: str = KEY
    subscriptions: list[Subscription] = field(default_factory=list)
    connections: int = 0
    closed: int = 0  # connections ended, by either side
    compressed: bool = False  # the last connection asked for permessage-deflate
    stalled: bool = False  # while true nothing is sent, pings are not answered
    _clients: list[_Client] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/v0/stream"

    @property
    def open(self) -> int:
        return len(self._clients)

    def send(self, *messages: dict[str, Any]) -> None:
        """Send each message to every subscribed connection, as a binary frame of JSON."""
        for client in [c for c in self._clients if c.subscribed]:
            for message in messages:
                self._write(client, BINARY, json.dumps(message).encode())

    def drop(self) -> None:
        for client in list(self._clients):
            client.writer.close()
        self._clients.clear()

    def _write(self, client: _Client, opcode: int, payload: bytes) -> None:
        if self.stalled:
            return
        if client.packer is None:
            client.writer.write(frame(opcode, payload))
            return
        packed = client.packer.compress(payload) + client.packer.flush(zlib.Z_SYNC_FLUSH)
        head = frame(opcode, packed[:-4])  # (RFC 7692: without the empty block's tail)
        client.writer.write(bytes([head[0] | 0x40]) + head[1:])

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            writer.close()
            return
        headers = {
            n.strip().lower(): v.strip()
            for n, _, v in (line.partition(":") for line in head.split("\r\n")[1:] if ":" in line)
        }
        deflate = "permessage-deflate" in headers.get("sec-websocket-extensions", "")
        self.compressed = deflate
        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            + f"Sec-WebSocket-Accept: {accept_of(headers.get('sec-websocket-key', ''))}\r\n".encode()
            + (b"Sec-WebSocket-Extensions: permessage-deflate\r\n" if deflate else b"")
            + b"\r\n"
        )
        client = _Client(writer, zlib.compressobj(wbits=-zlib.MAX_WBITS) if deflate else None)
        self.connections += 1
        self._clients.append(client)
        upgraded = time.monotonic()
        try:
            await self._read(reader, client, upgraded)
        except (OSError, asyncio.IncompleteReadError, TimeoutError):
            pass
        finally:
            self.closed += 1
            if client in self._clients:
                self._clients.remove(client)
            writer.close()

    async def _read(self, reader: asyncio.StreamReader, client: _Client, upgraded: float) -> None:
        while True:
            wait = None if client.subscribed else FIRST_SUBSCRIPTION_SEC - (time.monotonic() - upgraded)
            if wait is not None and wait <= 0:
                return  # the 3 second rule
            first, second = await asyncio.wait_for(reader.readexactly(2), wait)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack(">H", await reader.readexactly(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", await reader.readexactly(8))[0]
            mask = await reader.readexactly(4)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(await reader.readexactly(size)))
            opcode = first & 0x0F
            if opcode == CLOSE:
                client.writer.write(frame(CLOSE, data[:2]))
                return
            if opcode == PING and not self.stalled:
                client.writer.write(frame(PONG, data))
            elif opcode == TEXT and not self._subscribe(client, data, upgraded):
                return

    def _subscribe(self, client: _Client, data: bytes, upgraded: float) -> bool:
        """Keep the subscription; False when the connection is to end (a wrong key)."""
        message = json.loads(data)
        self.subscriptions.append(
            Subscription(
                message.get("APIKey", ""),
                message.get("BoundingBoxes", []),
                message.get("FilterMessageTypes", []),
                time.monotonic() - upgraded,
            )
        )
        if message.get("APIKey") != self.key:
            self._write(client, BINARY, json.dumps(REFUSAL).encode())
            return False
        if not client.subscribed:
            client.subscribed = True
            confirmation = {"MessageType": "SubscriptionConfirmation", "Message": {"CompressionEnabled": True}}
            self._write(client, BINARY, json.dumps(confirmation).encode())
        return True

    async def stop(self) -> None:
        self.drop()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(super().stop(), 5.0)


async def aisstream() -> FakeAisStream:
    """A started stand-in, stopped when the test is over."""
    server = await FakeAisStream().start()
    remember_stop(server.stop)
    return server


def position(
    mmsi: int,
    lat: float,
    lon: float,
    at: str,
    sog: float = 12.0,
    cog: float = 90.0,
    heading: int = 511,
    name: str = "",
    kind: str = "PositionReport",
) -> dict[str, Any]:
    """A position report as AISStream sends it; `at` is the time as `2026-11-27 12:00:00`."""
    return {
        "MessageType": kind,
        "MetaData": {
            "MMSI": mmsi,
            "MMSI_String": mmsi,
            "ShipName": name.ljust(20),
            "latitude": lat,
            "longitude": lon,
            "time_utc": f"{at}.123456789 +0000 UTC",
        },
        "Message": {
            kind: {
                "UserID": mmsi,
                "Latitude": lat,
                "Longitude": lon,
                "Sog": sog,
                "Cog": cog,
                "TrueHeading": heading,
                "NavigationalStatus": 0,
                "Valid": True,
            }
        },
    }


def static(mmsi: int, name: str, ship_type: int, destination: str, at: str) -> dict[str, Any]:
    """A ShipStaticData message as AISStream sends it."""
    return {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": mmsi, "ShipName": name, "latitude": 0, "longitude": 0, "time_utc": f"{at} +0000 UTC"},
        "Message": {
            "ShipStaticData": {
                "UserID": mmsi,
                "Name": name.ljust(20, "@"),
                "Type": ship_type,
                "Destination": destination.ljust(20),
                "Dimension": {"A": 100, "B": 20, "C": 10, "D": 10},
                "Valid": True,
            }
        },
    }
