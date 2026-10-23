"""AX.25 UI frames: the addresses with their SSIDs and repeated bits, the path, control, PID and the information field; decoding from bytes and encoding to bytes.

A frame as KISS delivers it has no flag bytes and no checksum: it starts with the address field. Each address is 7 bytes: six characters shifted left one bit and padded with spaces, then a byte
with the SSID in bits 1-4, bits 5-6 set, bit 7 the command/response bit of the destination and the source and the has-been-repeated bit of a digipeater, and bit 0 set on the last address only.
After the addresses come the control byte and, for a UI frame, the PID and the information field. Any other frame is kept as its control byte and the bytes after it."""
from dataclasses import dataclass

from neoaprs.callsign import CallsignError, format_call, parse_call

MAX_PATH = 8
MIN_FRAME = 15                         # destination, source, control
UI_CONTROL = 0x03
UI_MASK = 0xEF                         # the poll/final bit (0x10) does not make a frame another kind
PID_NO_LAYER3 = 0xF0
MAX_INFO = 256                         # the longest information field AX.25 allows (N1)
_ADDRESS_LEN = 7
_RESERVED_BITS = 0x60
_SSID_MASK = 0x1E
_FLAG_BIT = 0x80                       # command/response on the destination and source, has-been-repeated on a digipeater
_LAST_BIT = 0x01
_DELIMITERS = ",>:*-"                  # what the TNC2 text form uses; a call holding one could not be read back from it


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
        """'OH2GBA-7' or 'WIDE1-1*' (the star marks a digipeater the frame has been through). The call follows the rules of neoaprs.callsign."""
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
        """'WIDE1-1,WIDE2-1*': the way a TNC2 monitor shows it, with the star on the last digipeater the frame has been through and none before it."""
        last = max((i for i, a in enumerate(self.path) if a.repeated), default=-1)
        return ",".join(format_call(a.call, a.ssid) + ("*" if i == last else "") for i, a in enumerate(self.path))

    def tnc2(self) -> str:
        """'OH2GBA-7>APRS,WIDE1-1*:info', the information field as Latin-1 text."""
        path = self.path_text
        return f"{self.source}>{self.destination}{',' + path if path else ''}:{self.info.decode('latin-1')}"


def _decode_address(chunk: bytes, index: int) -> tuple[Address, bool]:
    """One 7-byte address and whether it is marked as the last. The flag bit is read as `repeated` for digipeaters (index 2 on) and ignored on the destination and the source."""
    letters = []
    for byte in chunk[:6]:
        letter = byte >> 1
        if not 0x20 <= letter <= 0x7E:
            raise Ax25Error(f"address {index} has a character outside the printable range (byte 0x{byte:02X})")
        letters.append(chr(letter))
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
        chunk = data[pos:pos + _ADDRESS_LEN]
        if len(chunk) < _ADDRESS_LEN:
            raise Ax25Error("the address field never ends: the frame stops before an address has its last-address bit")
        address, last = _decode_address(chunk, len(addresses))
        addresses.append(address)
        pos += _ADDRESS_LEN
        if last:
            return addresses, pos
        if len(addresses) == 2 + MAX_PATH:
            raise Ax25Error(f"more than {MAX_PATH} digipeaters in the address field")


def decode(data: bytes) -> Frame:
    """A frame from its bytes (no flags, no checksum). Raises Ax25Error with the reason when the bytes are not one."""
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


def encode(frame: Frame) -> bytes:
    """The bytes of a frame, as a command frame is sent: the destination's C bit set, the source's clear, the reserved bits set. Ax25Error when the information field is longer than MAX_INFO."""
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
