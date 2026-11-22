"""A fake APRS-IS server: it greets, answers the login line with `# logresp`, keeps every line it
receives and sends the client what the test `send`s. The iGate tests give the iGate its `address`.
"""

import asyncio

from tests.support.env import remember_stop
from tests.support.fakes import FakeLineServer

GREETING = b"# fake-aprsd 1.0\r\n"
SERVER_NAME = "TESTSRV"


class FakeAprsIs(FakeLineServer):
    def __init__(
        self,
        verified: bool = True,
        greeting: bytes | None = GREETING,
        answer: bool = True,
        silent: bool = False,
        name: str = SERVER_NAME,
    ) -> None:
        super().__init__()
        self.verified, self.greeting, self.answer, self.silent, self.name = verified, greeting, answer, silent, name
        self.on_client = self._greet
        self.responder = self._respond

    async def _greet(self, writer: asyncio.StreamWriter) -> None:
        if not self.silent and self.greeting is not None:
            writer.write(self.greeting)

    def _respond(self, line: str) -> bytes:
        if not line.startswith("user ") or not self.answer or self.silent:
            return b""
        call = line.split()[1]
        return f"# logresp {call} {'verified' if self.verified else 'unverified'}, server {self.name}\r\n".encode()

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def logins(self) -> list[str]:
        return [line for line in self.received if line.startswith("user ")]

    @property
    def comments(self) -> list[str]:
        return [line for line in self.received if line.startswith("#")]

    @property
    def packets(self) -> list[str]:
        return [line for line in self.received if not line.startswith(("#", "user "))]

    def send(self, line: bytes) -> None:
        for client in self.clients:
            if not client.is_closing():
                client.write(line + b"\r\n")

    def hang_up(self) -> None:
        for client in self.clients:
            client.close()
        self.clients.clear()


async def fake_aprsis(**options: object) -> FakeAprsIs:
    """A fake APRS-IS server on a free port, stopped by stop_all() when the test is over."""
    server = FakeAprsIs(**options)  # type: ignore[arg-type]
    await server.start()
    remember_stop(server.stop)
    return server
