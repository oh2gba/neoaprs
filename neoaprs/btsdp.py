"""Which RFCOMM channel a Bluetooth device serves its serial port on: one question to the device's service directory (SDP, an L2CAP connection to port 1), "which channel does your Serial Port Profile (0x1101) use?", in the
few bytes that takes. The separate `sdptool` and `bluetoothctl` are not needed, nor a library. Pure parts (the request, the reading of the answer) and one small function that does the talking; the answer is a
channel number, or None when the device lists none."""
import logging
import socket
import struct
from collections.abc import Callable
from typing import NamedTuple

log = logging.getLogger("neoaprs.btsdp")

SDP_PSM = 1                          # the L2CAP port of the service directory
SERIAL_PORT_UUID = 0x1101            # Serial Port Profile
RFCOMM_UUID = 0x0003
PROTOCOL_LIST_ATTRIBUTE = 0x0004     # ProtocolDescriptorList: the L2CAP and RFCOMM layers of a service, with the channel
SEARCH_ATTRIBUTES, SEARCH_ATTRIBUTES_ANSWER = 0x06, 0x07
SDP_TIMEOUT_SEC = 8.0
MAX_PDUS = 8                         # a device whose answer needs more continuations than this is not asked further
MAX_DEPTH = 8                        # how deep data elements may nest
RECV_BYTES = 4096


class Uuid(NamedTuple):
    value: int


class SdpError(Exception):
    """The device's answer could not be read."""


def request(uuid: int, attribute: int, transaction: int, continuation: bytes = b"\x00") -> bytes:
    """A ServiceSearchAttributeRequest for the services with `uuid`, asking for the one `attribute` of each."""
    params = bytes([0x35, 3, 0x19]) + struct.pack(">H", uuid) + struct.pack(">H", 1024) + bytes([0x35, 3, 0x09]) + struct.pack(">H", attribute) + continuation
    return struct.pack(">BHH", SEARCH_ATTRIBUTES, transaction, len(params)) + params


def _take(data: bytes, at: int, depth: int) -> tuple[object, int]:
    """The data element that starts at `at`: an int for numbers and booleans, a `Uuid`, bytes for text, a list for a sequence; and where the next one starts."""
    if at >= len(data):
        raise SdpError("an element is cut off")
    kind, size_index = data[at] >> 3, data[at] & 7
    at += 1
    if kind == 0:
        return None, at
    if size_index < 5:
        size = (1, 2, 4, 8, 16)[size_index]
    else:
        width = (1, 2, 4)[size_index - 5]
        if at + width > len(data):
            raise SdpError("an element is cut off")
        size, at = int.from_bytes(data[at:at + width], "big"), at + width
    if at + size > len(data):
        raise SdpError("an element is cut off")
    body, end = data[at:at + size], at + size
    if kind in (1, 2, 5):
        return int.from_bytes(body, "big", signed=kind == 2), end
    if kind == 3:
        return Uuid(int.from_bytes(body, "big")), end
    if kind in (6, 7):
        return _items(body, depth + 1), end
    return bytes(body), end


def _items(data: bytes, depth: int) -> list[object]:
    if depth > MAX_DEPTH:
        raise SdpError("elements nest too deep")
    items: list[object] = []
    at = 0
    while at < len(data):
        item, at = _take(data, at, depth)
        items.append(item)
    return items


def parse_elements(data: bytes) -> list[object]:
    """The data elements of `data`, one after the other."""
    return _items(data, 0)


def rfcomm_channels(elements: list[object]) -> list[int]:
    """The RFCOMM channels in a list of attribute lists, in the order the device gave them: a protocol list holds (L2CAP) and (RFCOMM, channel)."""
    found: list[int] = []

    def walk(item: object) -> None:
        if not isinstance(item, list):
            return
        if len(item) == 2 and item[0] == Uuid(RFCOMM_UUID) and isinstance(item[1], int):
            found.append(item[1])
        for part in item:
            walk(part)

    walk(elements)
    return found


def read_answer(pdu: bytes, transaction: int) -> tuple[bytes, bytes]:
    """The attribute lists a ServiceSearchAttributeResponse holds, and its continuation state (empty when the answer is whole)."""
    if len(pdu) < 7 or pdu[0] != SEARCH_ATTRIBUTES_ANSWER:
        raise SdpError("not an answer to the question")
    sent_transaction, _length, count = struct.unpack(">HHH", pdu[1:7])
    if sent_transaction != transaction:
        raise SdpError("an answer to another question")
    lists, state = pdu[7:7 + count], pdu[7 + count:]
    if len(lists) != count or not state or len(state) < 1 + state[0]:
        raise SdpError("the answer is cut off")
    return lists, state[1:1 + state[0]]


def ask(sock: socket.socket) -> bytes:
    """Asks over an open service-directory connection, follows the continuations, and gives the attribute lists together."""
    lists = b""
    continuation = b"\x00"
    for transaction in range(1, MAX_PDUS + 1):
        sock.send(request(SERIAL_PORT_UUID, PROTOCOL_LIST_ATTRIBUTE, transaction, continuation))
        part, state = read_answer(sock.recv(RECV_BYTES), transaction)
        lists += part
        if not state:
            return lists
        continuation = bytes([len(state)]) + state
    raise SdpError("the answer does not end")


def new_l2cap_socket() -> socket.socket:
    return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)


def serial_channels(address: str, new_socket: Callable[[], socket.socket] | None = None) -> list[int]:
    """The RFCOMM channels of the device's serial ports in the order it lists them; empty when its directory lists none or cannot be read. A device that cannot be reached raises OSError, like any connection that fails."""
    sock = (new_socket or new_l2cap_socket)()
    try:
        sock.settimeout(SDP_TIMEOUT_SEC)
        sock.connect((address, SDP_PSM))
        try:
            return rfcomm_channels(parse_elements(ask(sock)))
        except (SdpError, struct.error, OSError) as e:
            log.info("%s: the service directory gave no channel: %s", address, e)
            return []
    finally:
        sock.close()
