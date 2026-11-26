"""The radio's line on every system: a serial port, TCP socket, Bluetooth serial or BLE KISS TNC.

`SerialPort` reports what happens as signals and never reopens by itself; the open and the reading
run in threads, so nothing waits on the event loop.
"""

import asyncio
import errno
import logging
import os
import queue
import re
import socket
import sys
import threading
from collections.abc import Callable
from typing import Any

import serial  # type: ignore[import-untyped]

from . import nodevices
from .btle import BleSerial, is_ble
from .btserial import BluetoothSerial, is_bluetooth
from .coded import Reason
from .configvalues import port_scheme
from .signal import Signal
from .source import os_error_text
from .tncprofile import names_tcp

log = logging.getLogger("neoaprs.serialport")

READ_TIMEOUT_SEC = 0.1
WRITE_TIMEOUT_SEC = 2.0
JOIN_SEC = 0.5
MAX_CHUNK_BYTES = 4096
MAX_QUEUED_WRITES = 256


class SerialError(Exception):
    """The port could not be opened, or read, or written; the text is the system's words."""


class HeldError(SerialError):
    """The port is held by another radio or the GPS receiver (claims.py); the radio waits for it."""


class NotChosenError(SerialError):
    """The radio has no port or address to open; only new settings change that."""


def normalize(path: str) -> str:
    """Return the port as pyserial opens it (`tcp://` becomes `socket://`)."""
    path = path.strip()
    return "socket://" + path[len("tcp://") :] if path.lower().startswith("tcp://") else path


def is_url(path: str) -> bool:
    return "://" in path


def is_socket(path: str) -> bool:
    """Return whether the path is a TCP KISS port or a Bluetooth one (no speed, no cable)."""
    return names_tcp(path) or is_bluetooth(path) or is_ble(path)


def _on_windows() -> bool:
    return sys.platform == "win32"


def _words(path: str, e: BaseException) -> str:
    """Return why an open or a read failed, in the system's words."""
    text = os_error_text(e)
    if match := re.search(r"\(\d+, '([^']+)'", text):
        text = match.group(1).rstrip(".")
    elif match := re.search(r"\[(?:Errno|WinError) -?\d+\] ([^\[\]]+)$", text):
        text = match.group(1)
    return f"{path}: {text}"


LOST = "the line is gone (unplugged, or the other end closed it)"


def write_timed_out() -> Reason:
    return Reason(
        f"the device did not take the data within {WRITE_TIMEOUT_SEC:g} s",
        "radio.write_timeout",
        seconds=WRITE_TIMEOUT_SEC,
    )


def _lost_words(e: BaseException) -> str:
    """Return why a line that was open went away; pyserial's own prose goes to the log."""
    if isinstance(e, OSError) and (e.errno or e.strerror):
        return os_error_text(e)
    log.debug("the line was lost: %s: %s", type(e).__name__, e)
    return LOST


ERROR_ACCESS_DENIED = 5


def _in_use(e: BaseException) -> bool:
    """Return whether the open was refused because another program has the port."""
    if _on_windows():
        text = str(e)
        return (
            getattr(e, "winerror", None) == ERROR_ACCESS_DENIED
            or re.search(r", None, 5\)", text) is not None
            or "access is denied" in text.lower()
        )
    return getattr(e, "errno", None) in (errno.EAGAIN, errno.EBUSY)


def _build(path: str, baud: int) -> Any:
    """Return the pyserial object, not yet open: 8N1, DTR and RTS low, exclusive on POSIX."""
    # pyserial opens a file for `spy://`: the scheme check is repeated
    url = port_scheme(normalize(path))
    settings: dict[str, Any] = dict(
        baudrate=baud,
        bytesize=8,
        parity="N",
        stopbits=1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
        timeout=READ_TIMEOUT_SEC,
        write_timeout=WRITE_TIMEOUT_SEC,
    )
    if is_bluetooth(url) or is_ble(url):
        ser = (BluetoothSerial if is_bluetooth(url) else BleSerial)(None, **settings)
        ser.port = url
    else:
        ser = serial.serial_for_url(url, do_not_open=True, **settings)
    ser.dtr = False
    ser.rts = False
    if os.name == "posix" and not is_url(url):
        ser.exclusive = True
    return ser


def _keep_alive(ser: Any) -> None:
    """Make the system find a TCP line that nobody answers dead in the end."""
    sock = getattr(ser, "_socket", None)
    if sock is not None and not isinstance(ser, BluetoothSerial):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError as e:
            log.debug("keep-alive not set: %s", os_error_text(e))
            return
        _keep_alive_times(sock)


# a quiet TCP line is probed: a board that lost power is found gone in two minutes
KEEP_IDLE_SEC, KEEP_INTERVAL_SEC, KEEP_COUNT = 60, 15, 4


def _keep_alive_times(sock: socket.socket) -> None:
    """Ask the system to probe after KEEP_IDLE_SEC of quiet, KEEP_COUNT times."""
    idle = getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)
    options = [
        (idle, KEEP_IDLE_SEC),
        (getattr(socket, "TCP_KEEPINTVL", None), KEEP_INTERVAL_SEC),
        (getattr(socket, "TCP_KEEPCNT", None), KEEP_COUNT),
    ]
    if sys.platform == "win32" and all(option is None for option, _ in options):
        try:
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, KEEP_IDLE_SEC * 1000, KEEP_INTERVAL_SEC * 1000))
        except OSError as e:
            log.debug("keep-alive times not set: %s", os_error_text(e))
        return
    for option, value in options:
        if option is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, option, value)
            except OSError as e:
                log.debug("keep-alive time not set: %s", os_error_text(e))


class _Handover:
    """The pyserial object an open made in its thread; if cancelled the thread closes it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ser: Any = None
        self._abandoned = False

    def offer(self, ser: Any) -> bool:
        with self._lock:
            if not self._abandoned:
                self._ser = ser
                return True
        _close_quietly(ser)
        return False

    def abandon(self) -> None:
        with self._lock:
            self._abandoned = True
            ser, self._ser = self._ser, None
        if ser is not None:
            _close_quietly(ser)


def _close_quietly(ser: Any) -> None:
    try:
        ser.close()
    except Exception as e:  # a failed close can only be logged
        log.info("closing: %s", os_error_text(e))


class _Line:
    """One open of a port: the pyserial object and two threads; callbacks get the line."""

    def __init__(
        self,
        ser: Any,
        loop: asyncio.AbstractEventLoop,
        name: str,
        on_data: Callable[["_Line", bytes], None],
        on_lost: Callable[["_Line", str], None],
        on_written: Callable[["_Line"], None] | None = None,
    ) -> None:
        self.ser, self._loop, self._on_data, self._on_lost = ser, loop, on_data, on_lost
        self._on_written = on_written
        self._stop = threading.Event()
        self.outbox: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
        self._reader = threading.Thread(target=self._read, name=f"serial-read {name}", daemon=True)
        self._writer = threading.Thread(target=self._write, name=f"serial-write {name}", daemon=True)

    def start(self) -> None:
        self._reader.start()
        self._writer.start()

    def _post(self, call: Callable[..., None], *args: Any) -> None:
        try:
            self._loop.call_soon_threadsafe(call, self, *args)
        except RuntimeError:  # the loop is closed
            pass

    def _read(self) -> None:
        ser = self.ser
        while not self._stop.is_set():
            try:
                chunk = ser.read(ser.in_waiting or 1)
                while chunk and len(chunk) < MAX_CHUNK_BYTES and (more := ser.in_waiting):
                    chunk += ser.read(more)
            except Exception as e:
                if not self._stop.is_set():
                    self._post(self._on_lost, _lost_words(e))
                return
            if chunk:
                self._post(self._on_data, bytes(chunk))

    def _write(self) -> None:
        told = False  # the first write that went through is told, once
        while (data := self.outbox.get()) is not None:
            try:
                self.ser.write(data)
            except serial.SerialTimeoutException:
                if not self._stop.is_set():
                    self._post(self._on_lost, write_timed_out())
                return
            except Exception as e:
                if not self._stop.is_set():
                    self._post(self._on_lost, f"write failed: {_lost_words(e)}")
                return
            if not told and self._on_written is not None:
                told = True
                self._post(self._on_written)

    def end(self) -> None:
        """Stop both threads: wake the reader, let the writer flush, cut it short if slow."""
        self._stop.set()
        self._wake(getattr(self.ser, "cancel_read", None), socket.SHUT_RD)
        self.outbox.put(None)
        self._join(self._reader)
        self._join(self._writer, JOIN_SEC / 5)
        if self._writer.is_alive():
            self._wake(getattr(self.ser, "cancel_write", None), socket.SHUT_RDWR)
            self._join(self._writer)

    def _wake(self, cancel: Callable[[], None] | None, how: int) -> None:
        try:
            if cancel is not None:
                cancel()
            elif (sock := getattr(self.ser, "_socket", None)) is not None:
                sock.shutdown(how)
        except Exception as e:  # the port was closed or the peer is gone
            log.debug("waking a thread of %s: %s", self.ser, os_error_text(e))

    @staticmethod
    def _join(thread: threading.Thread, seconds: float = JOIN_SEC) -> None:
        if thread is not threading.current_thread():
            thread.join(seconds)


class SerialPort:
    def __init__(self, path: str, baud: int = 9600) -> None:
        self.path = path
        self.baud = baud
        self.data: Signal[[bytes]] = Signal("serialport.data")
        # why the line died; the port is closed by then
        self.dropped: Signal[[str]] = Signal("serialport.dropped")
        self._line: _Line | None = None
        self._opening = False
        self._closed_while_opening = False

    @property
    def is_open(self) -> bool:
        return self._line is not None

    @property
    def is_opening(self) -> bool:
        return self._opening

    @property
    def is_socket(self) -> bool:
        return is_socket(self.path)

    async def open(self) -> None:
        """Open the line in a thread and start reading; raise SerialError with the reason."""
        if self._line is not None or self._opening:
            raise SerialError(f"{self.path}: already open")
        self._opening, self._closed_while_opening = True, False
        hand = _Handover()
        try:
            ser = await asyncio.to_thread(self._open_blocking, hand)
        except BaseException:
            hand.abandon()
            raise
        finally:
            self._opening = False
        if self._closed_while_opening:
            self._close_line_of(ser)
            raise SerialError(f"{self.path}: closed while it was being opened")
        self._line = line = _Line(
            ser, asyncio.get_running_loop(), self.path, self._line_data, self._line_lost, self._line_written
        )
        line.start()

    def _open_blocking(self, hand: _Handover) -> Any:
        try:
            nodevices.check_port(self.path)
            ser = _build(self.path, self.baud)
            ser.open()
        except (serial.SerialException, OSError, ValueError) as e:
            what = (
                f"{self.path}: in use by another program (close it: a terminal, Direwolf, a rig program)"
                if _in_use(e)
                else _words(self.path, e)
            )
            raise SerialError(what) from e
        _keep_alive(ser)
        if not hand.offer(ser):
            raise SerialError(f"{self.path}: the open was cancelled")
        return ser

    def close(self) -> None:
        """Close the line; one being opened is closed when the open ends."""
        line, self._line = self._line, None
        if line is None:
            self._closed_while_opening = self._opening
            return
        line.end()
        self._close_line_of(line.ser)

    def _close_line_of(self, ser: Any) -> None:
        # a socket close sleeps, so do it off the loop
        if self.is_socket:
            threading.Thread(target=_close_quietly, args=(ser,), name=f"serial-close {self.path}", daemon=True).start()
        else:
            _close_quietly(ser)

    def let_go(self) -> None:
        """Close for a radio whose settings name the port (tncsearch.let_go)."""
        self.close()

    def write(self, data: bytes) -> int:
        """Hand `data` to the writer thread and return at once; a failing line is lost later."""
        line = self._line
        if line is None:
            raise SerialError(f"{self.path}: not open")
        if line.outbox.qsize() >= MAX_QUEUED_WRITES:
            raise SerialError(f"{self.path}: the line does not take what is written to it")
        line.outbox.put(bytes(data))
        return len(data)

    def _line_data(self, line: _Line, chunk: bytes) -> None:
        if line is self._line:
            self._deliver(chunk)

    def _line_lost(self, line: _Line, reason: str) -> None:
        if line is self._line:
            self._lost(reason)

    def _line_written(self, line: _Line) -> None:
        if line is self._line:
            self._written()

    def _written(self) -> None:
        """A write of this open went through (told once an open)."""

    def _deliver(self, chunk: bytes) -> None:
        self.data.emit(chunk)

    def _lost(self, reason: str) -> None:
        timed_out = getattr(reason, "code", "") == "radio.write_timeout"
        # the owner's own line, with its name, is the warning
        log.debug("%s %s: %s", self.path, "write timed out" if timed_out else "lost", reason)
        self.close()
        self.dropped.emit(reason)
