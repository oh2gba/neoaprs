"""Fakes for the tests: a line based TCP server on a free port of the loopback, and a rigctld made of it. No test ever contacts a real service (tests/support/guards.py keeps them off 4532 and 4533).

    rig = await rigctld()                     # rig.port is a free port, rig.address the setting status/rigctld; stopped when the test is over
    rig.hz, rig.mode = 7074000, "LSB"         # what `f` and `m` answer
    rig.radio_on = False                      # `f` and `m` answer RPRT -5, as rigctld does for a radio that is off
"""
import asyncio
from collections.abc import Awaitable, Callable

from tests.support.env import remember_stop


class FakeLineServer:
    """Accepts connections, collects every line it receives and answers with what `responder` returns for a line."""

    def __init__(self) -> None:
        self.received: list[str] = []
        self.clients: list[asyncio.StreamWriter] = []
        self.connections = 0
        self.on_client: Callable[[asyncio.StreamWriter], Awaitable[None] | None] | None = None
        self.responder: Callable[[str], bytes] | None = None
        self._server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> "FakeLineServer":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        for w in self.clients:
            w.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.clients.append(writer)
        self.connections += 1
        if self.on_client:
            r = self.on_client(writer)
            if asyncio.iscoroutine(r):
                await r
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("latin-1").strip()
                self.received.append(line)
                if self.responder:
                    answer = self.responder(line)
                    if answer:
                        writer.write(answer)
                        await writer.drain()
        except (ConnectionError, asyncio.CancelledError, asyncio.IncompleteReadError):
            pass


class FakeRigctld(FakeLineServer):
    """rigctld's text protocol as far as the status needs it: `f` is the frequency in Hz on a line, `m` the mode and the passband on two, and `RPRT -5` for either while the radio is off."""

    def __init__(self, hz: int = 14074000, mode: str = "USB", passband: int = 2400) -> None:
        super().__init__()
        self.hz, self.mode, self.passband = hz, mode, passband
        self.radio_on = True
        self.responder = self._answer

    def _answer(self, line: str) -> bytes:
        if not self.radio_on:
            return b"RPRT -5\n"
        if line == "f":
            return f"{self.hz}\n".encode()
        if line == "m":
            return f"{self.mode}\n{self.passband}\n".encode()
        return b"RPRT -1\n"

    @property
    def address(self) -> str:
        """The setting status/rigctld that reaches this server."""
        return f"127.0.0.1:{self.port}"

    async def start(self) -> "FakeRigctld":
        await super().start()
        return self


async def rigctld(**options: object) -> FakeRigctld:
    """A fake rigctld listening on a free port, stopped by stop_all() when the test is over."""
    rig = await FakeRigctld(**options).start()                     # type: ignore[arg-type]
    remember_stop(rig.stop)
    return rig
