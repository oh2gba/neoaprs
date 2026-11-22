"""A classic Bluetooth serial port (RFCOMM) as a pyserial port: `bt://AA:BB:CC:DD:EE:FF[/channel]`.

It is pyserial's socket:// port over an RFCOMM socket; a paired device needs no `rfcomm bind` or
root. Without a channel in the URL, the channels the device lists, then 1 to 3, are tried in turn.
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
REFUSED = (errno.ECONNREFUSED, errno.ECONNRESET)
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
    """Return True if this Python can make RFCOMM sockets (Linux with BlueZ)."""
    return sys.platform.startswith("linux") and hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")


def new_rfcomm_socket() -> socket.socket:
    return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)


def channels_for(address: str) -> list[int]:
    """Return the device's listed serial channels, then the fallback ones."""
    listed = btsdp.serial_channels(address)
    return listed + [c for c in FALLBACK_CHANNELS if c not in listed]


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
            if e.errno not in REFUSED or number == channels[-1]:
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
                    "Bluetooth ports (bt://) are for Linux; on Windows use the COM port of the paired device, on macOS its /dev/cu.* port"
                )
            sock = connect(address, channel)
        except (OSError, ValueError) as e:
            self._socket = None
            why = "no answer from the device (is it switched on and in range?)" if isinstance(e, TimeoutError) else e
            raise serial.SerialException(f"Could not open port {self.portstr}: {why}") from e
        sock.setblocking(False)
        self._socket = sock
        self.is_open = True
        self.reset_input_buffer()
        self.reset_output_buffer()
