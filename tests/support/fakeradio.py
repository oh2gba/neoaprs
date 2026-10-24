"""A radio that is a TCP server on the loopback: the stand-in for the TNC in the tests, the same on every system (a pseudo-terminal exists only on POSIX). The code under test opens its `url`
(`socket://127.0.0.1:PORT`) as it would open a Direwolf on 8001, and what it writes and what the test feeds it are plain bytes.

    radio = FakeRadio()
    await radio.start()                  # listening on 127.0.0.1, a free port: radio.url
    ...                                  # the code under test opens radio.url
    radio.feed(kiss_bytes)               # the radio talks (to everyone who is connected)
    heard = await radio.said(5)          # what the code wrote: waits for 5 bytes (or the time), returns all that came
    radio.drop()                         # the radio closes the connection: the line is lost
    radio.refuse(); await radio.accept() # nobody listens (a connection is refused), then the radio is back on the same port
    await radio.aclose()

The port is bound when the radio is made (so `url` is known at once, before an event loop runs); `start()` serves it. There are no tasks in it, only the transports of the connections."""
import asyncio
import socket
import sys
from typing import cast


REFUSED = "No connection could be made because the target machine actively refused it" if sys.platform == "win32" else "Connection refused"      # a refused connection in the system's words


class FakeRadio:
    def __init__(self) -> None:
        self._sock: socket.socket | None = self._listening(0)
        self.port: int = self._sock.getsockname()[1]
        self.url = f"socket://127.0.0.1:{self.port}"
        self.connections = 0                              # how many times the code under test connected
        self._server: asyncio.Server | None = None
        self._clients: list[asyncio.Transport] = []
        self._heard = bytearray()
        self._unsent = bytearray()                        # what was fed while nobody was connected
        self._held: socket.socket | None = None          # the port while it refuses (refuse)

    @staticmethod
    def _holding(port: int) -> socket.socket | None:
        """A socket bound to the port and not listening, so that a connection is refused and the port is not given to another program; None when the system will not bind it again at once."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform != "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.close()
            return None
        return sock

    @staticmethod
    def _listening(port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform != "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # (on Windows the option would let a second program take the port)
        sock.bind(("127.0.0.1", port))
        sock.listen(8)
        return sock

    async def start(self) -> None:
        if self._server is None and self._sock is not None:
            self._server = await asyncio.get_running_loop().create_server(lambda: _Tap(self), sock=self._sock)

    # ---- the radio talks and the radio is heard
    def feed(self, data: bytes) -> None:
        """The radio sends these bytes to every client. With no client yet they are kept for the next one: the daemon's open returns a moment before this side has accepted the connection, and a test that feeds
        as soon as the daemon says it is connected would otherwise lose the race."""
        if not self._clients:
            self._unsent.extend(data)
            return
        for client in self._clients:
            client.write(data)

    async def said(self, count: int = 1, timeout_sec: float = 2.0) -> bytes:
        """What the code under test has written since the last call: waits until at least `count` bytes came or the time is up, and returns all of it."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        while len(self._heard) < count and loop.time() < deadline:
            await asyncio.sleep(0.005)
        out, self._heard = bytes(self._heard), bytearray()
        return out

    def put_back(self, data: bytes) -> None:
        """Bytes read with `said` that the test has not looked at yet: the next `said` returns them first."""
        self._heard[:0] = data

    async def connected(self, timeout_sec: float = 2.0) -> None:
        """Waits until a client is connected."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        while not self._clients:
            assert loop.time() < deadline, "nobody connected to the fake radio"
            await asyncio.sleep(0.005)

    @property
    def clients(self) -> int:
        return len(self._clients)

    # ---- the cable
    def drop(self) -> None:
        """Closes the connections: the code under test finds its line lost. The radio still listens."""
        clients, self._clients = self._clients, []
        for client in clients:
            client.close()

    def refuse(self) -> None:
        """Stops listening: a connection attempt is refused, as when a Direwolf is not running. Connections that are open stay (`drop` closes them)."""
        server, sock, self._server, self._sock = self._server, self._sock, None, None
        if server is not None:
            server.close()
        elif sock is not None:
            sock.close()
        self._held = self._holding(self.port)                # (the port stays ours, bound and not listening: refused, and never another test's radio meanwhile)

    async def accept(self) -> None:
        """Listens again on the same port after `refuse`."""
        if self._server is None:
            if self._held is not None:
                self._held.close()
                self._held = None
            self._sock = self._listening(self.port)
            await self.start()

    async def aclose(self) -> None:
        self.drop()
        server, self._server = self._server, None
        if server is not None:
            server.close()
            try:
                await asyncio.wait_for(server.wait_closed(), 1.0)
            except TimeoutError:
                pass
        if self._sock is not None:                         # made but never served
            self._sock.close()
            self._sock = None
        if self._held is not None:
            self._held.close()
            self._held = None


class _Tap(asyncio.Protocol):
    """One connection to the fake radio."""

    def __init__(self, radio: FakeRadio) -> None:
        self._radio = radio
        self._transport: asyncio.Transport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast(asyncio.Transport, transport)
        self._radio._clients.append(self._transport)
        self._radio.connections += 1
        if self._radio._unsent:
            self._transport.write(bytes(self._radio._unsent))
            self._radio._unsent.clear()

    def data_received(self, data: bytes) -> None:
        self._radio._heard.extend(data)

    def connection_lost(self, exc: Exception | None) -> None:
        if self._transport in self._radio._clients:
            self._radio._clients.remove(self._transport)
