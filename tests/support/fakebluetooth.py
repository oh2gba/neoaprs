"""A Bluetooth device for the tests, the stand-in for a paired radio: no Bluetooth socket is ever made (the guard of tests/support/guards.py refuses one). The RFCOMM socket the code under test opens is one end of a
connected socket pair that accepts `connect((address, channel))`, and the L2CAP socket of the service-directory question is an object that answers it the way a device does.

    bt = FakeBluetooth(monkeypatch, channel=2)       # the device lists the serial port on channel 2 (None: it lists none)
    ...                                              # the code under test opens bt://00:11:22:33:44:55
    bt.connects                                      # [("00:11:22:33:44:55", 2)]
    bt.feed(b"...")                                  # the device talks
    heard = await bt.said(5)                         # what the code wrote
    bt.drop()                                        # the device goes away: the link is lost
    bt.fail(OSError(errno.EHOSTDOWN, "Host is down"))   # the next connections fail (None: they work again)"""
import asyncio
import socket
import struct
from typing import Any

import pytest

from neoaprs import btserial, btsdp

ADDRESS = "00:11:22:33:44:55"


def element(kind: int, body: bytes) -> bytes:
    """A data element with a one-byte size (or the size of a number): the way the questions and answers of the service directory are written."""
    if kind in (1, 3):
        return bytes([kind << 3 | {1: 0, 2: 1, 4: 2}[len(body)]]) + body
    return bytes([kind << 3 | 5, len(body)]) + body


def sequence(*parts: bytes) -> bytes:
    return element(6, b"".join(parts))


def uuid16(value: int) -> bytes:
    return element(3, struct.pack(">H", value))


def record(channel: int) -> bytes:
    """What a device lists for a service: the attribute 4 (protocols) with L2CAP and RFCOMM on `channel`."""
    return sequence(element(1, struct.pack(">H", 4)), sequence(sequence(uuid16(0x0100)), sequence(uuid16(0x0003), element(1, bytes([channel])))))


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
    """The service-directory socket: it keeps the questions and answers them from what the device lists."""

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
        self.connects: list[tuple[str, int]] = []              # every RFCOMM connection made, whether it worked or not
        self.sdp_connects: list[tuple[str, int]] = []
        self.error: OSError | None = None                      # the next RFCOMM connections fail with it
        self.sdp_error: OSError | None = None
        self.listed: list[int] | None = None                   # the channels the directory lists, when they are not just `channel`
        self.garbage = False                                   # the directory answers with nonsense
        self.parts = 1                                         # the answer comes in this many pieces (continuations)
        self.asked: list[FakeL2cap] = []
        self.peer: socket.socket | None = None                 # the device's end of the link
        self._pending: list[socket.socket] = []
        monkeypatch.setattr(btserial, "available", lambda: True)
        monkeypatch.setattr(btserial, "new_rfcomm_socket", self._new_rfcomm)
        monkeypatch.setattr(btsdp, "new_l2cap_socket", self._new_l2cap)

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
            raise self.error or OSError(111, "Connection refused")
        theirs.setblocking(False)
        self.peer = theirs

    def sdp_pdus(self, transaction: int, question: bytes) -> list[bytes]:
        if self.garbage:
            return [b"\x01\x02\x03"]
        channels = self.listed if self.listed is not None else [self.channel] if self.channel is not None else []
        lists = sequence(*(record(c) for c in channels))
        size = -(-len(lists) // self.parts)
        pieces = [lists[i:i + size] for i in range(0, len(lists), size)]
        index = question[-1]                                   # (the question ends with the continuation: none, or the number of the piece the device gave)
        return [answer(transaction, pieces[index], bytes([index + 1]) if index + 1 < len(pieces) else b"")]

    # ---- the device
    def fail(self, error: OSError | None) -> None:
        self.error = error

    def feed(self, data: bytes) -> None:
        assert self.peer is not None, "nobody is connected to the device"
        self.peer.setblocking(True)
        self.peer.sendall(data)
        self.peer.setblocking(False)

    async def connected(self, timeout_sec: float = 2.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        while self.peer is None:
            assert loop.time() < deadline, "nobody connected to the fake device"
            await asyncio.sleep(0.005)

    async def said(self, count: int = 1, timeout_sec: float = 2.0) -> bytes:
        """What the code under test has written: waits for at least `count` bytes (or the time) and returns all that came."""
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

