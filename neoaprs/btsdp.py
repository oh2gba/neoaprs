"""Find the RFCOMM channel of a Bluetooth device's serial port through SDP.

One SDP query over L2CAP asks which channel the Serial Port Profile (0x1101) uses; the request
and answer parsing are pure functions.
"""

import logging
import socket
import struct
from collections.abc import Callable
from typing import NamedTuple

log = logging.getLogger("neoaprs.btsdp")

SDP_PSM = 1
SERIAL_PORT_UUID = 0x1101
RFCOMM_UUID = 0x0003
PROTOCOL_LIST_ATTRIBUTE = 0x0004
SEARCH_ATTRIBUTES, SEARCH_ATTRIBUTES_ANSWER = 0x06, 0x07
SDP_TIMEOUT_SEC = 8.0
# Limits on a hostile or broken device: continuations followed and nesting depth accepted.
MAX_PDUS = 8
MAX_DEPTH = 8
RECV_BYTES = 4096


class Uuid(NamedTuple):
    value: int


class SdpError(Exception):
    """Raised when the device's answer cannot be parsed."""


def request(uuid: int, attribute: int, transaction: int, continuation: bytes = b"\x00") -> bytes:
    """Return a ServiceSearchAttributeRequest for services with `uuid`, asking for `attribute`."""
    params = (
        bytes([0x35, 3, 0x19])
        + struct.pack(">H", uuid)
        + struct.pack(">H", 1024)
        + bytes([0x35, 3, 0x09])
        + struct.pack(">H", attribute)
        + continuation
    )
    return struct.pack(">BHH", SEARCH_ATTRIBUTES, transaction, len(params)) + params


def _take(data: bytes, at: int, depth: int) -> tuple[object, int]:
    """Parse the data element at `at`; return it (int, `Uuid`, bytes or list) and the next offset."""
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
        size, at = int.from_bytes(data[at : at + width], "big"), at + width
    if at + size > len(data):
        raise SdpError("an element is cut off")
    body, end = data[at : at + size], at + size
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
    """Return the data elements of `data` in order."""
    return _items(data, 0)


def rfcomm_channels(elements: list[object]) -> list[int]:
    """Return the RFCOMM channels of the protocol lists in the device's order."""
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
    """Return the attribute lists of a response and its continuation state (empty when complete)."""
    if len(pdu) < 7 or pdu[0] != SEARCH_ATTRIBUTES_ANSWER:
        raise SdpError("not an answer to the question")
    sent_transaction, _length, count = struct.unpack(">HHH", pdu[1:7])
    if sent_transaction != transaction:
        raise SdpError("an answer to another question")
    lists, state = pdu[7 : 7 + count], pdu[7 + count :]
    if len(lists) != count or not state or len(state) < 1 + state[0]:
        raise SdpError("the answer is cut off")
    return lists, state[1 : 1 + state[0]]


def ask(sock: socket.socket) -> bytes:
    """Query an open SDP connection, follow continuations and return the joined attribute lists."""
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
    # Windows has AF_BLUETOOTH but no L2CAP, hence getattr.
    proto: int | None = getattr(socket, "BTPROTO_L2CAP", None)
    if proto is None:
        raise OSError("the service directory of a Bluetooth device is read on Linux only")
    return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, proto)


def serial_channels(address: str, new_socket: Callable[[], socket.socket] | None = None) -> list[int]:
    """Return the RFCOMM channels of the device's serial ports; raise OSError if unreachable."""
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
