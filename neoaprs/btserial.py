"""A classic Bluetooth serial port (RFCOMM, the Serial Port Profile) as a pyserial port: `bt://AA:BB:CC:DD:EE:FF` or `bt://AA:BB:CC:DD:EE:FF/2` (the channel). It is the socket:// port of pyserial with an RFCOMM socket in
place of the TCP one, so reading, writing, the write timeout and a line that dies work as they do for TCP, and `serialport.py` treats the two alike.

A device that is paired with the system needs no `rfcomm bind` and no root: Linux lets a user program open an RFCOMM socket to it. Python's `socket` has Bluetooth on Linux (and on Windows, which this does not use: there the paired
device's COM port is the way); where it has none, the open says so. Without a channel in the URL the device is asked (`btsdp.py`) for the channels of its serial ports; they are tried in turn, then channels 1 to 3 (a device that lists none, or lists one it does not serve), and the log says
which one connected. Only a refusal moves on to the next channel."""
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
FALLBACK_CHANNELS = (1, 2, 3)        # tried after the channels the device lists: 1 is what Mobilinkd, the VR-N76/UV-PRO and most serial modules use, 2 the Kenwood TH-D74/D75
CONNECT_TIMEOUT_SEC = 12.0           # a radio that is switched off or out of range answers after the page timeout of the link, a few seconds
REFUSED = (errno.ECONNREFUSED, errno.ECONNRESET)
_URL = re.compile(r"^bt://([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})(?:/(\d{1,2}))?/?$", re.IGNORECASE)


def is_bluetooth(path: str) -> bool:
    return path.strip().lower().startswith(SCHEME)


def parse_url(path: str) -> tuple[str, int | None]:
    """The device address (upper case, with colons) and the channel (None: not given) of a `bt://` port; ValueError says what is wrong."""
    match = _URL.match(path.strip())
    if match is None:
        raise ValueError(f"{path!r} is not a Bluetooth port: write bt://AA:BB:CC:DD:EE:FF, or bt://AA:BB:CC:DD:EE:FF/2 with the RFCOMM channel")
    address = match.group(1).replace("-", ":").upper()
    channel = int(match.group(2)) if match.group(2) else None
    if channel is not None and not 1 <= channel <= 30:
        raise ValueError(f"{path!r}: the RFCOMM channel is 1 to 30")
    return address, channel


def available() -> bool:
    """Whether this Python can make Bluetooth sockets (Linux builds with BlueZ support)."""
    return sys.platform.startswith("linux") and hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")


def new_rfcomm_socket() -> socket.socket:
    return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)


def channels_for(address: str) -> list[int]:
    """The channels to try for a device without one in the URL: those its service directory lists for the serial port, then the usual ones."""
    listed = btsdp.serial_channels(address)
    return listed + [c for c in FALLBACK_CHANNELS if c not in listed]


def connect(address: str, channel: int | None) -> socket.socket:
    """An RFCOMM socket connected to the device (the log says the channel). A channel that was named is the only one tried; otherwise each channel of `channels_for` in turn, the next one after a refusal
    (the device serves nothing on that channel); any other failure (out of range, switched off) ends it, as does the last refusal."""
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
    """pyserial's socket port with an RFCOMM socket: port parameters are ignored (a Bluetooth link has no speed to set, no control lines to hold)."""

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
                raise OSError("Bluetooth ports (bt://) are for Linux; on Windows use the COM port of the paired device, on macOS its /dev/cu.* port")
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
