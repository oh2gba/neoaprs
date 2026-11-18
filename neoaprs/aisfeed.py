"""The connection to an own AIS receiver (map/ships My own receiver): a TCP connection the daemon opens to the receiver's NMEA output (the program that decodes the radio, AIS-catcher or rtl-ais, serves it), read
only, and cut into lines within the bounds. The daemon listens on no new port. Behind the no-devices switch a receiver that is not on this computer, or a port a real modem of this computer may listen on (the default 10110 is one), is refused as a server that is not there (nodevices).

`connect` opens it, `read` hands its lines on as they come, and `Lines` is the cutting: a line at most AIS_LINE_MAX bytes long (a longer one is passed over, to its end), and at most AIS_LINES_PER_SEC lines a
second (the rest of that second are passed over), so that a receiver that floods, or a thing that is not an AIS feed at all, cannot hold the daemon. What a line means is aisdecode's."""
import asyncio
import errno
import logging
import os
import socket
from collections.abc import Callable

from . import nodevices
from .layerthing import AIS_LINE_MAX, AIS_LINES_PER_SEC

CONNECT_SEC = 10.0                  # a connection that is not made by then is a failure
KEEPALIVE_IDLE_SEC = 30             # a connection quiet for this long is probed, every KEEPALIVE_INTERVAL_SEC, and given up after KEEPALIVE_PROBES lost probes
KEEPALIVE_INTERVAL_SEC = 10
KEEPALIVE_PROBES = 3
CHUNK = 16384                       # what is read at a time

log = logging.getLogger("neoaprs.aisfeed")


class Lines:
    """The bytes of a stream cut into the lines that are read: complete, short enough, and not more than the rate allows."""

    def __init__(self, per_sec: int = AIS_LINES_PER_SEC, max_bytes: int = AIS_LINE_MAX) -> None:
        self.per_sec, self.max_bytes = per_sec, max_bytes
        self._rest = b""                # the start of a line whose end has not come
        self._skipping = False          # in the rest of a line that was too long
        self._second = -1               # the second (by the clock given) the count is of
        self._count = 0
        self.passed_over = 0            # the lines let go, for the log

    def feed(self, data: bytes, now: float) -> list[str]:
        """The lines `data` completes (text, without the line end), `now` being seconds on any steady clock."""
        pieces = (self._rest + data).split(b"\n")
        self._rest = pieces.pop()
        if self._skipping and pieces:
            pieces.pop(0)               # (the end of the long line)
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


async def connect(host: str, port: int, timeout_sec: float = CONNECT_SEC) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """The connection to the receiver; an OSError or a TimeoutError when it cannot be made (and, behind the no-devices switch, for a host that is not this computer)."""
    nodevices.check_host(host, "the AIS receiver", logging.INFO)
    if nodevices.on() and nodevices.modem_port(port):                # (the default port is among those a real modem of this computer may listen on)
        nodevices.refused(f"the port {port} is not opened: a modem of this computer may listen there", logging.INFO)
        raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=CHUNK), timeout_sec)
    _keepalive(writer)
    return reader, writer


def _keepalive(writer: asyncio.StreamWriter) -> None:
    """The system probes a connection that has gone quiet, so that one that died without a word (a power cut, a lost Wi-Fi) ends in about a minute instead of never."""
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for name, value in (("TCP_KEEPIDLE", KEEPALIVE_IDLE_SEC), ("TCP_KEEPINTVL", KEEPALIVE_INTERVAL_SEC), ("TCP_KEEPCNT", KEEPALIVE_PROBES)):
            if hasattr(socket, name):                       # (not every system has each)
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), value)
    except OSError as e:
        log.debug("keepalive not set: %r", e)


async def read(reader: asyncio.StreamReader, lines: Lines, handle: Callable[[list[str]], None], clock: Callable[[], float]) -> None:
    """Reads the connection to its end, giving each batch of lines to `handle`; the loop gets its turn after every read. An OSError is the connection's loss."""
    while chunk := await reader.read(CHUNK):
        if batch := lines.feed(chunk, clock()):
            handle(batch)
        await asyncio.sleep(0)
