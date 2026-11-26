"""A stand-in for PSK Reporter's collector on the loopback: a UDP port that keeps every datagram and
the address it came from, and reads it as the server does (tests/support/pskdecode.py)."""

import asyncio
from typing import Any

from tests.support.pskdecode import Collector, Datagram


class _Listening(asyncio.DatagramProtocol):
    def __init__(self, standin: "PskStandIn") -> None:
        self.standin = standin

    def datagram_received(self, data: bytes, addr: Any) -> None:
        self.standin.raw.append((data, addr))
        self.standin.datagrams.append(self.standin.collector.read(data))


class PskStandIn:
    def __init__(self) -> None:
        self.raw: list[tuple[bytes, Any]] = []
        self.datagrams: list[Datagram] = []
        self.collector = Collector()
        self.port = 0
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self) -> "PskStandIn":
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(lambda: _Listening(self), local_addr=("127.0.0.1", 0))
        self.port = self._transport.get_extra_info("sockname")[1]
        return self

    @property
    def target(self) -> str:
        """What NEOAPRS_PSKREPORTER is set to for this stand-in."""
        return f"127.0.0.1:{self.port}"

    @property
    def senders(self) -> list[dict[str, Any]]:
        """Every sender record of every datagram, in the order they came."""
        return [record for datagram in self.datagrams for record in datagram.senders]

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
