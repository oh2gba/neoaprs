"""A small WebSocket client (RFC 6455) over asyncio streams: Mercury's UI interface on loopback, and
AISStream over TLS with permessage-deflate (RFC 7692) for what the server sends.

Tornado has a client but may be imported by neoaprs/web/ only."""

import asyncio
import base64
import hashlib
import os
import ssl
import struct
import zlib

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HEADER_MAX = 8192  # the longest reply to the handshake read
# A longer message is read and dropped (Mercury's longest is 64 KB).
MAX_MESSAGE = 1 << 20
CONNECT_SEC = 3.0
DEFLATE = "permessage-deflate"
# RFC 7692 7.2.2: the tail a sender removes from each compressed message.
DEFLATE_TAIL = b"\x00\x00\xff\xff"

CONTINUATION, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocketError(Exception):
    """The server did not do what the protocol says."""


def accept_of(key: str) -> str:
    """Return the `Sec-WebSocket-Accept` a server answers the key with."""
    # The SHA-1 is the protocol's (RFC 6455): it shows the server read the key and protects nothing.
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii"), usedforsecurity=False).digest()).decode("ascii")


def frame(opcode: int, payload: bytes, mask: bytes | None = None) -> bytes:
    """Return one final frame, masked by `mask` (four bytes) when given; a client's always is."""
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


class Inflater:
    """Undoes permessage-deflate for each message the server sends compressed."""

    def __init__(self, extension: str) -> None:
        self._fresh = "server_no_context_takeover" in extension
        self._inflate = zlib.decompressobj(-zlib.MAX_WBITS)

    def message(self, data: bytes) -> bytes | None:
        """Return the message, or None when it is larger than MAX_MESSAGE; raise WebSocketError when corrupt."""
        if self._fresh:
            self._inflate = zlib.decompressobj(-zlib.MAX_WBITS)
        try:
            out = self._inflate.decompress(data + DEFLATE_TAIL, MAX_MESSAGE + 1)
        except zlib.error as e:
            raise WebSocketError(f"a compressed message that does not inflate: {e}") from None
        if len(out) > MAX_MESSAGE or self._inflate.unconsumed_tail:
            self._inflate = zlib.decompressobj(-zlib.MAX_WBITS)  # the rest of its window is lost with it
            return None
        return out


class WebSocketClient:
    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, inflater: Inflater | None = None
    ) -> None:
        self._reader, self._writer, self._inflater = reader, writer, inflater
        self.closed = False
        self.close_reason = ""  # the server's words in its close frame
        self.heard_data = False  # a message came
        self.lost = False  # the connection broke (a reset), not a close by the server
        self.heard = asyncio.get_running_loop().time()  # loop time of the last frame read

    @classmethod
    async def connect(
        cls,
        host: str,
        port: int,
        path: str = "/",
        timeout: float = CONNECT_SEC,
        tls: ssl.SSLContext | None = None,
        deflate: bool = False,
        agent: str = "",
    ) -> "WebSocketClient":
        """Open the connection and do the handshake; `deflate` offers permessage-deflate.

        Raise OSError if the server is not there, WebSocketError or TimeoutError if no upgrade.
        """
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=tls, server_hostname=host if tls else None), timeout
        )
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            default_port = 443 if tls else 80
            extra = (f"Sec-WebSocket-Extensions: {DEFLATE}\r\n" if deflate else "") + (
                f"User-Agent: {agent}\r\n" if agent else ""
            )
            request = (
                f"GET {path} HTTP/1.1\r\nHost: {host if port == default_port else f'{host}:{port}'}\r\n"
                f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n{extra}\r\n"
            )
            writer.write(request.encode("ascii"))
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
            lines = head.decode("latin-1").split("\r\n")
            if len(head) > HEADER_MAX or len(lines[0].split()) < 2 or lines[0].split()[1] != "101":
                raise WebSocketError(f"the server did not upgrade the connection: {lines[0][:80]}")
            headers = {
                name.strip().lower(): value.strip()
                for name, _, value in (line.partition(":") for line in lines[1:] if ":" in line)
            }
            if headers.get("sec-websocket-accept") != accept_of(key):
                raise WebSocketError("the server's answer to the handshake is not the one for this key")
            extension = headers.get("sec-websocket-extensions", "")
            if extension and not (deflate and extension.split(";")[0].strip() == DEFLATE):
                raise WebSocketError(f"the server chose an extension that was not offered: {extension[:80]}")
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, WebSocketError, TimeoutError) as error:
            writer.close()
            if isinstance(error, asyncio.IncompleteReadError | asyncio.LimitOverrunError):
                raise WebSocketError("the server closed the connection during the handshake") from None
            raise
        return cls(reader, writer, Inflater(extension) if extension else None)

    async def send_text(self, text: str) -> None:
        self._writer.write(frame(TEXT, text.encode("utf-8"), os.urandom(4)))
        await self._writer.drain()

    async def ping(self) -> None:
        self._writer.write(frame(PING, b"", os.urandom(4)))
        await self._writer.drain()

    async def recv(self) -> tuple[bool, bytes] | None:
        """Return the next message as (is_text, bytes), or None once the server closed.

        Raise WebSocketError for a disallowed frame. A message over MAX_MESSAGE is skipped.
        """
        parts: list[bytes] = []
        size, kind, skipping, packed = 0, TEXT, False, False
        while True:
            try:
                opcode, final, payload, rsv1 = await self._frame()
            except asyncio.IncompleteReadError:
                self.closed = True
                return None
            except ConnectionError:
                self.closed = self.lost = True
                return None
            if opcode == PING:
                self._writer.write(frame(PONG, payload, os.urandom(4)))
                continue
            if opcode == PONG:
                continue
            if opcode == CLOSE:
                self.closed = True
                self.close_reason = payload[2:].decode("utf-8", "replace")
                self._writer.write(frame(CLOSE, payload[:2], os.urandom(4)))
                return None
            if opcode in (TEXT, BINARY):
                parts, size, kind, skipping, packed = [], 0, opcode, False, rsv1
            elif opcode != CONTINUATION:
                raise WebSocketError(f"a frame of the type {opcode}")
            size += len(payload)
            skipping = skipping or size > MAX_MESSAGE
            if not skipping:
                parts.append(payload)
            if final:
                message: bytes | None = None if skipping else b"".join(parts)
                if message is not None and packed and self._inflater is not None:
                    message = self._inflater.message(message)
                if message is None:
                    parts, size, skipping = [], 0, False
                    continue
                self.heard_data = True
                return kind == TEXT, message

    async def _frame(self) -> tuple[int, bool, bytes, bool]:
        """Return (opcode, final, payload, compressed); only RSV1 of permessage-deflate is allowed."""
        first, second = await self._reader.readexactly(2)
        if first & (0x30 if self._inflater is not None else 0x70):
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
        self.heard = asyncio.get_running_loop().time()
        if mask is not None:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return first & 0x0F, bool(first & 0x80), payload, bool(first & 0x40)

    def close(self) -> None:
        """Close the connection now; a close frame is tried first, with no wait for the answer."""
        if not self.closed:
            self.closed = True
            try:
                self._writer.write(frame(CLOSE, struct.pack(">H", 1000), os.urandom(4)))
            except OSError:
                pass
        self._writer.close()
