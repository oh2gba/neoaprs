"""A small WebSocket client (RFC 6455) over asyncio streams, for the one server NeoAPRS reads that way: the UI interface of the Mercury it starts, on the loopback. It opens a connection with the handshake, reads whole messages (text or
binary, the fragments joined, a ping answered with a pong, a close answered and reported as the end) and writes text messages. No extensions, no compression, no TLS: the server is on this computer and speaks plain `ws://`. The pages
of the daemon are served by Tornado, which has a client of its own, but Tornado may be imported by neoaprs/web/ only."""
import asyncio
import base64
import hashlib
import os
import struct

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HEADER_MAX = 8192                # the longest reply to the handshake read
MAX_MESSAGE = 1 << 20            # a message longer than this is read and thrown away (Mercury's longest, the list of radios, is 64 KB)
CONNECT_SEC = 3.0

CONTINUATION, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocketError(Exception):
    """The server did not do what the protocol says."""


def accept_of(key: str) -> str:
    """The `Sec-WebSocket-Accept` a server answers the key with."""
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii"), usedforsecurity=False).digest()).decode("ascii")      # (the SHA-1 is the protocol's, RFC 6455: it shows that the server read the key, and protects nothing)


def frame(opcode: int, payload: bytes, mask: bytes | None = None) -> bytes:
    """One frame, final, with the payload masked by `mask` (four bytes) when given: a client's frames are always masked."""
    size = len(payload)
    head = bytes([0x80 | opcode])
    flag = 0x80 if mask is not None else 0
    if size < 126:
        head += bytes([flag | size])
    elif size < 1 << 16:
        head += bytes([flag | 126]) + struct.pack(">H", size)
    else:
        head += bytes([flag | 127]) + struct.pack(">Q", size)
    if mask is None:
        return head + payload
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class WebSocketClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader, self._writer = reader, writer
        self.closed = False

    @classmethod
    async def connect(cls, host: str, port: int, path: str = "/", timeout: float = CONNECT_SEC) -> "WebSocketClient":
        """Opens the connection and does the handshake. OSError when the server is not there, WebSocketError (or TimeoutError) when it does not agree to the upgrade."""
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            writer.write(request.encode("ascii"))
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
            lines = head.decode("latin-1").split("\r\n")
            if len(head) > HEADER_MAX or len(lines[0].split()) < 2 or lines[0].split()[1] != "101":
                raise WebSocketError(f"the server did not upgrade the connection: {lines[0][:80]}")
            headers = {name.strip().lower(): value.strip() for name, _, value in (line.partition(":") for line in lines[1:] if ":" in line)}
            if headers.get("sec-websocket-accept") != accept_of(key):
                raise WebSocketError("the server's answer to the handshake is not the one for this key")
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, WebSocketError, TimeoutError) as error:
            writer.close()
            if isinstance(error, asyncio.IncompleteReadError | asyncio.LimitOverrunError):
                raise WebSocketError("the server closed the connection during the handshake") from None
            raise
        return cls(reader, writer)

    async def send_text(self, text: str) -> None:
        self._writer.write(frame(TEXT, text.encode("utf-8"), os.urandom(4)))
        await self._writer.drain()

    async def recv(self) -> tuple[bool, bytes] | None:
        """The next message as (is_text, bytes), or None when the server closed the connection. WebSocketError for a frame the protocol does not allow. A message over MAX_MESSAGE is skipped."""
        parts: list[bytes] = []
        size, kind, skipping = 0, TEXT, False
        while True:
            try:
                opcode, final, payload = await self._frame()
            except (asyncio.IncompleteReadError, ConnectionError):
                self.closed = True
                return None
            if opcode == PING:
                self._writer.write(frame(PONG, payload, os.urandom(4)))
                continue
            if opcode == PONG:
                continue
            if opcode == CLOSE:
                self.closed = True
                self._writer.write(frame(CLOSE, payload[:2], os.urandom(4)))
                return None
            if opcode in (TEXT, BINARY):
                parts, size, kind, skipping = [], 0, opcode, False
            elif opcode != CONTINUATION:
                raise WebSocketError(f"a frame of the type {opcode}")
            size += len(payload)
            skipping = skipping or size > MAX_MESSAGE
            if not skipping:
                parts.append(payload)
            if final:
                if skipping:
                    parts, size, skipping = [], 0, False
                    continue
                return kind == TEXT, b"".join(parts)

    async def _frame(self) -> tuple[int, bool, bytes]:
        first, second = await self._reader.readexactly(2)
        if first & 0x70:
            raise WebSocketError("a frame with extension bits set")
        size = second & 0x7F
        if size == 126:
            size = struct.unpack(">H", await self._reader.readexactly(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", await self._reader.readexactly(8))[0]
        mask = await self._reader.readexactly(4) if second & 0x80 else None
        if size > 4 * MAX_MESSAGE:
            raise WebSocketError(f"a frame of {size} bytes")
        payload = await self._reader.readexactly(size)
        if mask is not None:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return first & 0x0F, bool(first & 0x80), payload

    def close(self) -> None:
        """Closes the connection now (a close frame is tried first, without waiting for the answer)."""
        if not self.closed:
            self.closed = True
            try:
                self._writer.write(frame(CLOSE, struct.pack(">H", 1000), os.urandom(4)))
            except OSError:
                pass
        self._writer.close()
