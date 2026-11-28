"""A classic Bluetooth serial port (RFCOMM) as a pyserial port: `bt://AA:BB:CC:DD:EE:FF[/channel]`.

It is pyserial's socket:// port over an RFCOMM socket, on Linux and Windows; a paired device needs no
`rfcomm bind`, COM port or root. Without a channel in the URL, the channels the device lists, then 1
to 3, are tried in turn.
"""

import errno
import logging
import re
import socket
import sys

import serial  # type: ignore[import-untyped]
from serial.urlhandler import protocol_socket  # type: ignore[import-untyped]

from . import btsdp

log = logging.getLogger("neoaprs.btserial")

SCHEME = "bt://"
FALLBACK_CHANNELS = (1, 2, 3)
CONNECT_TIMEOUT_SEC = 12.0
# Linux's refusals, and Windows' 10064: the device answered DM (the channel is busy or not offered)
REFUSED = (errno.ECONNREFUSED, errno.ECONNRESET, 10064)
_URL = re.compile(r"^bt://([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})(?:/(\d{1,2}))?/?$", re.IGNORECASE)


def is_bluetooth(path: str) -> bool:
    return path.strip().lower().startswith(SCHEME)


def parse_url(path: str) -> tuple[str, int | None]:
    """Return the device address and the channel (None if absent); raise ValueError if malformed."""
    match = _URL.match(path.strip())
    if match is None:
        raise ValueError(
            f"{path!r} is not a Bluetooth port: write bt://AA:BB:CC:DD:EE:FF, or bt://AA:BB:CC:DD:EE:FF/2 with the RFCOMM channel"
        )
    address = match.group(1).replace("-", ":").upper()
    channel = int(match.group(2)) if match.group(2) else None
    if channel is not None and not 1 <= channel <= 30:
        raise ValueError(f"{path!r}: the RFCOMM channel is 1 to 30")
    return address, channel


def available() -> bool:
    """Return True if this Python can make RFCOMM sockets (Linux with BlueZ, Windows with its Bluetooth library)."""
    if _on_windows():
        from . import winbluetooth  # ctypes only where it is used

        return winbluetooth.usable()
    return sys.platform.startswith("linux") and hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")


def _on_windows() -> bool:
    return sys.platform == "win32"


def new_rfcomm_socket() -> socket.socket:
    return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)


def listed_channels(address: str) -> list[int]:
    """Return the serial channels the device lists; raise OSError if it cannot be reached (Linux)."""
    if _on_windows():
        from . import winbluetooth

        try:
            return winbluetooth.serial_channels(address, winbluetooth.ws2_32())
        except TimeoutError:
            raise  # a device that does not answer: no connect waits its own time after this
        except OSError as e:
            log.info("%s: the service directory was not read: %s", address, e)
            return []
    return btsdp.serial_channels(address)


def channels_for(address: str) -> list[int]:
    """Return the device's listed serial channels, then the fallback ones."""
    listed = listed_channels(address)
    return listed + [c for c in FALLBACK_CHANNELS if c not in listed]


def _number(e: OSError) -> int | None:
    winerror = getattr(e, "winerror", None)
    return winerror if isinstance(winerror, int) else e.errno


def connect(address: str, channel: int | None) -> socket.socket:
    """Return an RFCOMM socket; a refusal tries the next channel, any other failure is raised."""
    channels = [channel] if channel else channels_for(address)
    for number in channels:
        sock = new_rfcomm_socket()
        try:
            sock.settimeout(CONNECT_TIMEOUT_SEC)
            sock.connect((address, number))
        except OSError as e:
            sock.close()
            if _number(e) not in REFUSED or number == channels[-1]:
                raise
            log.info("%s: nothing on RFCOMM channel %d (%s)", address, number, e)
            continue
        except BaseException:
            sock.close()
            raise
        log.info("%s: connected on RFCOMM channel %d%s", address, number, "" if channel else " (none was named)")
        return sock
    raise OSError(errno.ECONNREFUSED, "Connection refused")


class BluetoothSerial(protocol_socket.Serial):  # type: ignore[misc]
    """pyserial's socket port over RFCOMM; port parameters are ignored."""

    is_open: bool

    def open(self) -> None:
        self.logger = None
        if self._port is None:
            raise serial.SerialException("Port must be configured before it can be used.")
        if self.is_open:
            raise serial.SerialException("Port is already open.")
        try:
            address, channel = parse_url(self.portstr)
            if not available():
                raise OSError(
                    "Bluetooth ports (bt://) are for Linux and Windows; on macOS use the device's /dev/cu.* port"
                )
            sock = connect(address, channel)
        except (OSError, ValueError) as e:
            self._socket = None
            raise serial.SerialException(f"Could not open port {self.portstr}: {e}") from e
        sock.setblocking(False)
        self._socket = sock
        self.is_open = True
        self.reset_input_buffer()
        self.reset_output_buffer()
