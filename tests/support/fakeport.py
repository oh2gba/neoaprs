"""The Tnc's serial line in memory (neoaprs/tncport.py): a port that opens nothing, so a test can
fail the open or a write and feed the Tnc bytes when it chooses, on a loop whose time is skipped.
"""
from collections.abc import Awaitable, Callable

import pytest

from neoaprs.serialport import SerialError


class FakePort:
    """What the Tnc holds as its port. `ports` is the registry that made it, which says how the open
    and the writes of every port go."""

    def __init__(self, ports: "FakePorts", path: str, baud: int, on_data: Callable[["FakePort", bytes], None], on_lost: Callable[["FakePort", str], None]) -> None:
        self.ports, self.path, self.baud = ports, path, baud
        self._on_data, self._on_lost = on_data, on_lost
        self.is_open = False
        self.written: list[bytes] = []                    # every write that was taken, in order
        self.closes = 0

    async def open(self) -> None:
        self.ports.opened.append(self)
        if self.ports.open_error is not None:
            raise self.ports.open_error
        await self.ports.open_gate()
        self.is_open = True

    def close(self) -> None:
        self.closes += 1
        self.is_open = False

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise SerialError(f"{self.path}: not open")
        if self.ports.write_error is not None:
            raise self.ports.write_error
        self.written.append(data)
        return len(data)

    def fail(self, reason: str) -> None:
        """A write failed: the line is lost, like a read that failed (as TncPort does)."""
        if self.is_open:
            self.lose(reason)

    # ---- what the test does to the line
    def feed(self, data: bytes) -> None:
        """The radio sends these bytes."""
        self._on_data(self, data)

    def lose(self, reason: str = "the cable was pulled") -> None:
        self.is_open = False
        self._on_lost(self, reason)

    @property
    def said(self) -> bytes:
        return b"".join(self.written)


class FakePorts:
    """The ports a Tnc made, and how they behave. `open_error` / `write_error` are raised by every
    open / write while set."""

    def __init__(self) -> None:
        self.opened: list[FakePort] = []
        self.open_error: BaseException | None = None
        self.write_error: BaseException | None = None

        async def open_now() -> None:
            return None

        # An awaitable the open waits for (a test that holds the open puts its own)
        self.open_gate: Callable[[], Awaitable[None]] = open_now

    def make(self, path: str, baud: int, on_data: Callable[[FakePort, bytes], None], on_lost: Callable[[FakePort, str], None]) -> FakePort:
        return FakePort(self, path, baud, on_data, on_lost)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "FakePorts":
        monkeypatch.setattr("neoaprs.tnc.TncPort", self.make)
        return self

    @property
    def port(self) -> FakePort:
        """The latest port the Tnc opened."""
        return self.opened[-1]
