"""TCP connection to an AIS receiver's NMEA output (AIS-catcher, rtl-ais): read-only, bounded.

`Lines` caps line length and rate, so a flooding or non-AIS source cannot hold the daemon.
"""

import asyncio
import errno
import logging
import os
import socket
from collections.abc import Callable

from . import nodevices
from .layerthing import AIS_LINE_MAX, AIS_LINES_PER_SEC

CONNECT_SEC = 10.0
KEEPALIVE_IDLE_SEC = 30
KEEPALIVE_INTERVAL_SEC = 10
KEEPALIVE_PROBES = 3
CHUNK = 16384

log = logging.getLogger("neoaprs.aisfeed")


class Lines:
    """Cut a byte stream into complete, short lines, within the rate limit."""

    def __init__(self, per_sec: int = AIS_LINES_PER_SEC, max_bytes: int = AIS_LINE_MAX) -> None:
        self.per_sec, self.max_bytes = per_sec, max_bytes
        self._rest = b""
        self._skipping = False
        self._second = -1
        self._count = 0
        self.passed_over = 0

    def feed(self, data: bytes, now: float) -> list[str]:
        """Return the lines `data` completes; `now` is seconds on any steady clock."""
        pieces = (self._rest + data).split(b"\n")
        self._rest = pieces.pop()
        if self._skipping and pieces:
            pieces.pop(0)
            self._skipping = False
        elif self._skipping:
            self._rest = b""
        if len(self._rest) > self.max_bytes:
            self._rest, self._skipping = b"", True
            self.passed_over += 1
        lines = []
        for piece in pieces:
            if len(piece) > self.max_bytes or not self._within_rate(now):
                self.passed_over += 1
                continue
            text = piece.decode("ascii", "replace").strip()
            if text:
                lines.append(text)
        return lines

    def _within_rate(self, now: float) -> bool:
        if int(now) != self._second:
            self._second, self._count = int(now), 0
        self._count += 1
        return self._count <= self.per_sec


async def connect(
    host: str, port: int, timeout_sec: float = CONNECT_SEC
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open the connection; raise OSError or TimeoutError if it cannot be made or is refused."""
    nodevices.check_host(host, "the AIS receiver", logging.INFO)
    # the default port is one a real modem on this computer may listen on
    if nodevices.on() and nodevices.modem_port(port):
        nodevices.refused(f"the port {port} is not opened: a modem of this computer may listen there", logging.INFO)
        raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=CHUNK), timeout_sec)
    _keepalive(writer)
    return reader, writer


def _keepalive(writer: asyncio.StreamWriter) -> None:
    """Have the OS probe a quiet connection, so a silently dead one ends in about a minute."""
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for name, value in (
            ("TCP_KEEPIDLE", KEEPALIVE_IDLE_SEC),
            ("TCP_KEEPINTVL", KEEPALIVE_INTERVAL_SEC),
            ("TCP_KEEPCNT", KEEPALIVE_PROBES),
        ):
            if hasattr(socket, name):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), value)
    except OSError as e:
        log.debug("keepalive not set: %r", e)


async def read(
    reader: asyncio.StreamReader, lines: Lines, handle: Callable[[list[str]], None], clock: Callable[[], float]
) -> None:
    """Read to the end, passing each batch of lines to `handle`; an OSError ends the loop."""
    while chunk := await reader.read(CHUNK):
        if batch := lines.feed(chunk, clock()):
            handle(batch)
        await asyncio.sleep(0)
