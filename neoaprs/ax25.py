"""AX.25 UI frames: addresses, SSIDs, repeated bits, path, control, PID and information field.

A KISS frame has no flags and no checksum. An address is 7 bytes: six characters shifted left,
then SSID, flag bit and last-address bit. A frame that is not UI keeps its control byte and rest.
"""

from dataclasses import dataclass

from neoaprs.callsign import CallsignError, format_call, parse_call

MAX_PATH = 8
MIN_FRAME = 15  # destination, source, control
UI_CONTROL = 0x03
# the poll/final bit (0x10) does not make a frame another kind
UI_MASK = 0xEF
PID_NO_LAYER3 = 0xF0
MAX_INFO = 256  # the longest information field AX.25 allows (N1)
ADDRESS_LEN = 7
_RESERVED_BITS = 0x60
_SSID_MASK = 0x1E
# command/response on destination and source, has-been-repeated on a digipeater
_FLAG_BIT = 0x80
_LAST_BIT = 0x01
# TNC2 text delimiters: a call holding one could not be read back
_DELIMITERS = ",>:*-"


class Ax25Error(ValueError):
    pass


@dataclass(frozen=True)
class Address:
    call: str
    ssid: int = 0
    repeated: bool = False

    def __post_init__(self) -> None:
        if not 1 <= len(self.call) <= 6:
            raise Ax25Error(f"call {self.call!r} must have 1 to 6 characters")
        bad = [c for c in self.call if not 0x21 <= ord(c) <= 0x7E or c in _DELIMITERS]
        if bad:
            raise Ax25Error(f"call {self.call!r} has a character that cannot be in an address: {bad[0]!r}")
        if not 0 <= self.ssid <= 15:
            raise Ax25Error(f"SSID {self.ssid!r} of {self.call!r} is not 0 to 15")

    def __str__(self) -> str:
        return format_call(self.call, self.ssid) + ("*" if self.repeated else "")

    @classmethod
    def parse(cls, text: str) -> "Address":
        """Return 'OH2GBA-7' or 'WIDE1-1*' (the star marks a digipeater the frame went through)."""
        repeated = text.endswith("*")
        try:
            call, ssid = parse_call(text[:-1] if repeated else text)
        except CallsignError as error:
            raise Ax25Error(str(error)) from error
        return cls(call, ssid, repeated)


@dataclass(frozen=True)
class Frame:
    destination: Address
    source: Address
    path: tuple[Address, ...] = ()
    control: int = UI_CONTROL
    pid: int = PID_NO_LAYER3
    info: bytes = b""

    def __post_init__(self) -> None:
        if len(self.path) > MAX_PATH:
            raise Ax25Error(f"a path has at most {MAX_PATH} digipeaters, not {len(self.path)}")
        if self.destination.repeated or self.source.repeated:
            raise Ax25Error("only a digipeater can be marked as repeated, not the destination or the source")
        if not (0 <= self.control <= 255 and 0 <= self.pid <= 255):
            raise Ax25Error("control and PID are bytes")

    @property
    def is_ui(self) -> bool:
        return self.control & UI_MASK == UI_CONTROL and self.pid == PID_NO_LAYER3

    @property
    def path_text(self) -> str:
        """Return 'WIDE1-1,WIDE2-1*' as a TNC2 monitor shows it (star on the last used one only)."""
        last = max((i for i, a in enumerate(self.path) if a.repeated), default=-1)
        return ",".join(format_call(a.call, a.ssid) + ("*" if i == last else "") for i, a in enumerate(self.path))

    def tnc2(self) -> str:
        """Return 'OH2GBA-7>APRS,WIDE1-1*:info' with the information field as Latin-1 text."""
        path = self.path_text
        return f"{self.source}>{self.destination}{',' + path if path else ''}:{self.info.decode('latin-1')}"


def _decode_address(chunk: bytes, index: int) -> tuple[Address, bool]:
    """Return a 7-byte address and whether it is marked last; the flag bit counts for digipeaters."""
    letters = []
    for byte in chunk[:6]:
        letter = byte >> 1
        if not 0x20 <= letter <= 0x7E:
            raise Ax25Error(f"address {index} has a character outside the printable range (byte 0x{byte:02X})")
        # AX.25 addresses are capitals: a lower-case letter on the air is the same station
        letters.append(chr(letter).upper())
    call = "".join(letters).rstrip(" ")
    if not call or " " in call:
        raise Ax25Error(f"address {index} has a call of spaces or with a space inside: {''.join(letters)!r}")
    flags = chunk[6]
    try:
        address = Address(call, (flags & _SSID_MASK) >> 1, bool(flags & _FLAG_BIT) and index >= 2)
    except Ax25Error as error:
        raise Ax25Error(f"address {index}: {error}") from error
    return address, bool(flags & _LAST_BIT)


def _decode_addresses(data: bytes) -> tuple[list[Address], int]:
    addresses: list[Address] = []
    pos = 0
    while True:
        chunk = data[pos : pos + ADDRESS_LEN]
        if len(chunk) < ADDRESS_LEN:
            raise Ax25Error("the address field never ends: the frame stops before an address has its last-address bit")
        address, last = _decode_address(chunk, len(addresses))
        addresses.append(address)
        pos += ADDRESS_LEN
        if last:
            return addresses, pos
        if len(addresses) == 2 + MAX_PATH:
            raise Ax25Error(f"more than {MAX_PATH} digipeaters in the address field")


def decode(data: bytes) -> Frame:
    """Return a frame from its bytes (no flags, no checksum); raise Ax25Error if invalid."""
    if len(data) < MIN_FRAME:
        raise Ax25Error(f"frame of {len(data)} bytes is shorter than the 15 an address pair and a control byte need")
    addresses, pos = _decode_addresses(data)
    if len(addresses) < 2:
        raise Ax25Error("the address field ends after the destination: there is no source address")
    if pos >= len(data):
        raise Ax25Error("the frame ends after the address field: there is no control byte")
    control = data[pos]
    pos += 1
    pid = PID_NO_LAYER3
    if control & UI_MASK == UI_CONTROL:
        if pos >= len(data):
            raise Ax25Error("a UI frame ends after the control byte: there is no PID")
        pid = data[pos]
        pos += 1
    return Frame(addresses[0], addresses[1], tuple(addresses[2:]), control, pid, data[pos:])


def _encode_address(address: Address, flag: bool, last: bool) -> bytes:
    letters = address.call.ljust(6).encode("ascii")
    last_byte = _RESERVED_BITS | (address.ssid << 1) | (_FLAG_BIT if flag else 0) | (_LAST_BIT if last else 0)
    return bytes(b << 1 for b in letters) + bytes([last_byte])


def encode_path(path: tuple[Address, ...]) -> bytes:
    """Return the digipeater addresses of a path (repeated bit on used ones, last bit last)."""
    return b"".join(_encode_address(a, a.repeated, i == len(path) - 1) for i, a in enumerate(path))


def encode(frame: Frame) -> bytes:
    """Return a frame's bytes as a command frame (destination C bit set, source clear).

    Raise Ax25Error if the information field is longer than MAX_INFO.
    """
    if len(frame.info) > MAX_INFO:
        raise Ax25Error(f"the information field is {len(frame.info)} bytes, more than the {MAX_INFO} AX.25 allows")
    out = bytearray()
    addresses = (frame.destination, frame.source, *frame.path)
    for index, address in enumerate(addresses):
        flag = index == 0 or (index >= 2 and address.repeated)
        out += _encode_address(address, flag, index == len(addresses) - 1)
    out.append(frame.control)
    if frame.control & UI_MASK == UI_CONTROL:
        out.append(frame.pid)
    return bytes(out) + frame.info
