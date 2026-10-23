"""The line of the radio, on every system: a serial port (`/dev/ttyUSB0`, `COM3`), a TCP socket (`socket://host:port`, KISS over TCP: Direwolf on 8001, the sound-card modems; `tcp://host:port` is accepted for it) or, on Linux,
a Bluetooth serial port that is paired with the system (`bt://AA:BB:CC:DD:EE:FF`, `btserial.py`).

`SerialPort` reports what happens as signals (`data`, `dropped`); it never reopens by itself: the TNC that owns it decides when to try again. The port is made with pyserial's `serial_for_url`, the control lines held low
before the open (a sound-card interface keys the transmitter on RTS), the open run in a thread (a Bluetooth COM port can take seconds to say no), and each open line has a thread that reads it and a thread that writes it,
so nothing here waits on the event loop and no descriptor is given to the loop to wait for, which Windows could not do for a serial handle. The loop gets the bytes by `call_soon_threadsafe`, in the order they came."""
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

from .btserial import BluetoothSerial, is_bluetooth
from .signal import Signal
from .source import os_error_text

log = logging.getLogger("neoaprs.serialport")

READ_TIMEOUT_SEC = 0.1              # the reader looks at its stop flag this often
WRITE_TIMEOUT_SEC = 2.0             # a write that the line does not take in this time fails the line (0 does not work on Windows)
JOIN_SEC = 0.5                      # how long close() waits for a thread to end
MAX_CHUNK_BYTES = 4096              # the most one delivery to the loop holds
MAX_QUEUED_WRITES = 256             # writes waiting for a line that does not take them: more than this and write() refuses
NETWORK_SCHEMES = ("socket://", "rfc2217://")


class SerialError(Exception):
    """The port could not be opened, or read, or written; the text is the system's words."""


def normalize(path: str) -> str:
    """The port as pyserial opens it: `tcp://host:port`, which is what people type for a KISS TCP port, is `socket://host:port`."""
    path = path.strip()
    return "socket://" + path[len("tcp://"):] if path.lower().startswith("tcp://") else path


def is_url(path: str) -> bool:
    return "://" in path


def is_socket(path: str) -> bool:
    """A TCP KISS port or a Bluetooth one: a stream socket with no speed, no device file to look for holders of, and no cable to pull."""
    return normalize(path).lower().startswith("socket://") or is_bluetooth(path)


def _on_windows() -> bool:
    return sys.platform == "win32"


def _words(path: str, e: BaseException) -> str:
    """The reason an open or a read failed, in the system's words: pyserial's wording of a Windows error or a refused connection is taken apart."""
    text = os_error_text(e)
    if match := re.search(r"\(\d+, '([^']+)'", text):                 # PermissionError(13, 'Access is denied.', None, 5)
        text = match.group(1).rstrip(".")
    elif match := re.search(r"\[(?:Errno|WinError) \d+\] ([^\[\]]+)$", text):      # Could not open port socket://h:1: [Errno 111] Connection refused (on Windows: [WinError 10061] No connection could be made ...)
        text = match.group(1)
    return f"{path}: {text}"


def _in_use(e: BaseException) -> bool:
    """The open was refused because another program has the port: on Windows "Access is denied" (the port is always exclusive there), elsewhere the lock pyserial takes."""
    code = getattr(e, "errno", None)
    if _on_windows():
        text = str(e).lower()
        return isinstance(e, PermissionError) or code == errno.EACCES or "access is denied" in text or "permissionerror" in text
    return code in (errno.EAGAIN, errno.EBUSY)


def _build(path: str, baud: int) -> Any:
    """The pyserial object, not yet open: 8N1, no flow control, DTR and RTS low before the open (they are what a sound-card interface keys the transmitter with), and exclusive on a POSIX device."""
    url = normalize(path)
    settings: dict[str, Any] = dict(baudrate=baud, bytesize=8, parity="N", stopbits=1, xonxoff=False, rtscts=False, dsrdtr=False, timeout=READ_TIMEOUT_SEC, write_timeout=WRITE_TIMEOUT_SEC)
    if is_bluetooth(url):                                 # (pyserial does not know bt://: its port class is made here, as serial_for_url would)
        ser = BluetoothSerial(None, **settings)
        ser.port = url
    else:
        ser = serial.serial_for_url(url, do_not_open=True, **settings)
    ser.dtr = False
    ser.rts = False
    if os.name == "posix" and not is_url(url):
        ser.exclusive = True
    return ser


def _keep_alive(ser: Any) -> None:
    """A TCP line that nobody answers is found dead by the operating system in the end, not never. (A Bluetooth link has its own supervision timeout.)"""
    sock = getattr(ser, "_socket", None)
    if sock is not None and not isinstance(ser, BluetoothSerial):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError as e:
            log.debug("keep-alive not set: %s", os_error_text(e))


class _Handover:
    """The pyserial object an open made in its thread, passed to the awaiting coroutine; when that was cancelled meanwhile the thread closes the object itself, so that no port is left open."""

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
    except Exception as e:                                # a close that fails leaves nothing to do but say so
        log.info("closing: %s", os_error_text(e))


class _Line:
    """One open of a port: the pyserial object and its two threads. `on_data(line, chunk)` and `on_lost(line, reason)` are called on the event loop; the line says which open they are about, so that a
    late call from a line that has been closed can be told from the current one."""

    def __init__(self, ser: Any, loop: asyncio.AbstractEventLoop, name: str, on_data: Callable[["_Line", bytes], None], on_lost: Callable[["_Line", str], None]) -> None:
        self.ser, self._loop, self._on_data, self._on_lost = ser, loop, on_data, on_lost
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
        except RuntimeError:                              # the loop is closed: nobody is left to tell
            pass

    def _read(self) -> None:
        ser = self.ser
        while not self._stop.is_set():
            try:
                chunk = ser.read(ser.in_waiting or 1)
                while chunk and len(chunk) < MAX_CHUNK_BYTES and (more := ser.in_waiting):          # (a socket says 1 at a time: what is there is delivered together)
                    chunk += ser.read(more)
            except Exception as e:                        # the device went away, the socket was closed, the port was closed under us
                if not self._stop.is_set():
                    self._post(self._on_lost, os_error_text(e))
                return
            if chunk:
                self._post(self._on_data, bytes(chunk))

    def _write(self) -> None:
        while (data := self.outbox.get()) is not None:
            try:
                self.ser.write(data)
            except Exception as e:
                if not self._stop.is_set():
                    self._post(self._on_lost, f"write failed: {os_error_text(e)}")
                return

    def end(self) -> None:
        """Stops both threads and waits a moment for them. The reader is woken (pyserial's cancel_read, or a shutdown of the socket's receiving side) and told by the flag; the writer first writes what is queued, and
        is cut short (cancel_write, a shutdown of the socket) only if that takes more than a moment."""
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
        except Exception as e:                            # (the port was already closed, or the peer is gone)
            log.debug("waking a thread of %s: %s", self.ser, os_error_text(e))

    @staticmethod
    def _join(thread: threading.Thread, seconds: float = JOIN_SEC) -> None:
        if thread is not threading.current_thread():
            thread.join(seconds)


class SerialPort:
    def __init__(self, path: str, baud: int = 9600) -> None:
        self.path = path
        self.baud = baud
        self.data: Signal[[bytes]] = Signal("serialport.data")           # each chunk as it was read
        self.dropped: Signal[[str]] = Signal("serialport.dropped")       # why the line died; the port is closed by then
        self._line: _Line | None = None
        self._opening = False

    @property
    def is_open(self) -> bool:
        return self._line is not None

    @property
    def is_socket(self) -> bool:
        return is_socket(self.path)

    async def open(self) -> None:
        """Opens the line (in a thread: a port that does not answer must not stop the loop) and starts reading it. Raises SerialError with the reason. Cancelled, it leaves no port open."""
        if self._line is not None or self._opening:
            raise SerialError(f"{self.path}: already open")
        self._opening = True
        hand = _Handover()
        try:
            ser = await asyncio.to_thread(self._open_blocking, hand)
        except BaseException:
            hand.abandon()
            raise
        finally:
            self._opening = False
        self._line = line = _Line(ser, asyncio.get_running_loop(), self.path, self._line_data, self._line_lost)
        line.start()

    def _open_blocking(self, hand: _Handover) -> Any:
        try:
            ser = _build(self.path, self.baud)
            ser.open()
        except (serial.SerialException, OSError, ValueError) as e:
            what = f"{self.path}: in use by another program (close it: a terminal, Direwolf, a rig program)" if _in_use(e) else _words(self.path, e)
            raise SerialError(what) from e
        _keep_alive(ser)
        if not hand.offer(ser):
            raise SerialError(f"{self.path}: the open was cancelled")
        return ser

    def close(self) -> None:
        line, self._line = self._line, None
        if line is None:
            return
        line.end()
        if self.is_socket:                                # pyserial's socket close sleeps a third of a second, so it is done off the loop (a Bluetooth link closes slowly too)
            threading.Thread(target=_close_quietly, args=(line.ser,), name=f"serial-close {self.path}", daemon=True).start()
        else:
            _close_quietly(line.ser)

    def write(self, data: bytes) -> int:
        """Hands `data` to the writer thread, which writes it in order; returns at once. A line that does not take it (it fails, or the write times out) is lost a moment later, like a read that fails."""
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

    def _deliver(self, chunk: bytes) -> None:
        self.data.emit(chunk)

    def _lost(self, reason: str) -> None:
        log.warning("serial port %s lost: %s", self.path, reason)
        self.close()
        self.dropped.emit(reason)
