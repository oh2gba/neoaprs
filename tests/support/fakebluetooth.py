"""A paired Bluetooth device for the tests: the RFCOMM socket is one end of a connected socket pair
and the L2CAP socket answers the service-directory question as a device does. No real socket is
made.
"""

import asyncio
import errno
import socket
import struct
from typing import Any

import pytest

from neoaprs import btserial, btsdp, winbluetooth
from tests.support.patience import PATIENCE_SEC

ADDRESS = "00:11:22:33:44:55"


def element(kind: int, body: bytes) -> bytes:
    """A data element with a one-byte size (or the size of a number): the way the questions and
    answers of the service directory are written."""
    if kind in (1, 3):
        return bytes([kind << 3 | {1: 0, 2: 1, 4: 2}[len(body)]]) + body
    return bytes([kind << 3 | 5, len(body)]) + body


def sequence(*parts: bytes) -> bytes:
    return element(6, b"".join(parts))


def uuid16(value: int) -> bytes:
    return element(3, struct.pack(">H", value))


def record(channel: int) -> bytes:
    """What a device lists for a service: the attribute 4 (protocols) with L2CAP and RFCOMM on
    `channel`."""
    return sequence(
        element(1, struct.pack(">H", 4)),
        sequence(sequence(uuid16(0x0100)), sequence(uuid16(0x0003), element(1, bytes([channel])))),
    )


def answer(transaction: int, attribute_lists: bytes, continuation: bytes = b"") -> bytes:
    """A ServiceSearchAttributeResponse for the question with this transaction number."""
    body = struct.pack(">H", len(attribute_lists)) + attribute_lists + bytes([len(continuation)]) + continuation
    return struct.pack(">BHH", btsdp.SEARCH_ATTRIBUTES_ANSWER, transaction, len(body)) + body


class FakeRfcomm(socket.socket):
    """One end of a socket pair that accepts a connect, as an RFCOMM socket does."""

    def __init__(self, device: "FakeBluetooth", fileno: int) -> None:
        super().__init__(fileno=fileno)
        self.device = device

    def connect(self, address: Any) -> None:
        self.device.connect_rfcomm(address)


class FakeL2cap:
    """The service-directory socket: it keeps the questions and answers them from what the device
    lists."""

    def __init__(self, device: "FakeBluetooth") -> None:
        self.device = device
        self.asked: list[bytes] = []
        self.replies: list[bytes] = []

    def settimeout(self, seconds: float | None) -> None:
        pass

    def connect(self, address: tuple[str, int]) -> None:
        self.device.sdp_connects.append(address)
        if self.device.sdp_error is not None:
            raise self.device.sdp_error

    def send(self, data: bytes) -> int:
        self.asked.append(data)
        transaction = struct.unpack(">H", data[1:3])[0]
        self.replies.extend(self.device.sdp_pdus(transaction, data))
        return len(data)

    def recv(self, size: int) -> bytes:
        return self.replies.pop(0)

    def close(self) -> None:
        pass


class FakeBluetooth:
    """The device, installed in place of the Bluetooth sockets for the test."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, channel: int | None = 2, address: str = ADDRESS) -> None:
        self.address, self.channel = address, channel
        self.connects: list[tuple[str, int]] = []  # every RFCOMM connection made, whether it worked or not
        self.sdp_connects: list[tuple[str, int]] = []
        self.error: OSError | None = None  # the next RFCOMM connections fail with it
        self.sdp_error: OSError | None = None
        # The channels the directory lists, when they are not just `channel`
        self.listed: list[int] | None = None
        self.garbage = False  # the directory answers with nonsense
        self.parts = 1  # the answer comes in this many pieces (continuations)
        self.asked: list[FakeL2cap] = []
        self.peer: socket.socket | None = None  # the device's end of the link
        self._pending: list[socket.socket] = []
        monkeypatch.setattr(btserial, "available", lambda: True)
        monkeypatch.setattr(btserial, "new_rfcomm_socket", self._new_rfcomm)
        monkeypatch.setattr(btsdp, "new_l2cap_socket", self._new_l2cap)
        monkeypatch.setattr(winbluetooth, "ws2_32", lambda: None)
        monkeypatch.setattr(winbluetooth, "serial_channels", self._windows_directory)

    def _windows_directory(self, address: str, _library: object) -> list[int]:
        """Windows' lookup of the device's serial service, answered as the device's directory answers."""
        if self.sdp_error is not None:
            raise self.sdp_error
        if self.garbage:
            return []
        return self.listed if self.listed is not None else [self.channel] if self.channel is not None else []

    # ---- the sockets of the code under test
    def _new_rfcomm(self) -> socket.socket:
        mine, theirs = socket.socketpair()
        self._pending.append(theirs)
        return FakeRfcomm(self, mine.detach())

    def _new_l2cap(self) -> socket.socket:
        sock = FakeL2cap(self)
        self.asked.append(sock)
        return sock  # type: ignore[return-value]

    def connect_rfcomm(self, address: tuple[str, int]) -> None:
        self.connects.append(address)
        theirs = self._pending.pop(0)
        if self.error is not None or address[1] != self.channel:
            theirs.close()
            raise self.error or OSError(errno.ECONNREFUSED, "Connection refused")
        theirs.setblocking(False)
        self.peer = theirs

    def sdp_pdus(self, transaction: int, question: bytes) -> list[bytes]:
        if self.garbage:
            return [b"\x01\x02\x03"]
        channels = self.listed if self.listed is not None else [self.channel] if self.channel is not None else []
        lists = sequence(*(record(c) for c in channels))
        size = -(-len(lists) // self.parts)
        pieces = [lists[i : i + size] for i in range(0, len(lists), size)]
        # The question ends with the continuation: none, or the number of the piece the device gave
        index = question[-1]
        return [answer(transaction, pieces[index], bytes([index + 1]) if index + 1 < len(pieces) else b"")]

    # ---- the device
    def fail(self, error: OSError | None) -> None:
        self.error = error

    def feed(self, data: bytes) -> None:
        assert self.peer is not None, "nobody is connected to the device"
        self.peer.setblocking(True)
        self.peer.sendall(data)
        self.peer.setblocking(False)

    async def connected(self, timeout_sec: float = PATIENCE_SEC) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        while self.peer is None:
            assert loop.time() < deadline, "nobody connected to the fake device"
            await asyncio.sleep(0.005)

    async def said(self, count: int = 1, timeout_sec: float = PATIENCE_SEC) -> bytes:
        """What the code under test has written: waits for at least `count` bytes (or the time) and
        returns all that came."""
        assert self.peer is not None, "nobody is connected to the device"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        heard = bytearray()
        while len(heard) < count and loop.time() < deadline:
            try:
                chunk = self.peer.recv(65536)
            except BlockingIOError:
                await asyncio.sleep(0.005)
                continue
            if not chunk:
                break
            heard.extend(chunk)
        return bytes(heard)

    def drop(self) -> None:
        """The device is switched off or out of range: its end of the link closes."""
        if self.peer is not None:
            self.peer.close()
            self.peer = None

    def close(self) -> None:
        self.drop()
        for theirs in self._pending:
            theirs.close()
        self._pending.clear()
