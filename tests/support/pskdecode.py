"""PSK Reporter's side of a datagram, as its collector reads one: the header, the record format
descriptors (kept from one datagram to the next, as the server caches them) and the records."""

import struct
from dataclasses import dataclass, field
from typing import Any

from neoaprs import pskreport

# the elements by (enterprise, number), as names of the records read back
NAMES = {
    (True, 1): "senderCallsign",
    (True, 2): "receiverCallsign",
    (True, 3): "senderLocator",
    (True, 4): "receiverLocator",
    (True, 5): "frequency",
    (True, 6): "sNR",
    (True, 7): "iMD",
    (True, 8): "decodingSoftware",
    (True, 9): "antennaInformation",
    (True, 10): "mode",
    (True, 11): "informationSource",
    (False, 150): "flowStartSeconds",
}
SIGNED = {"sNR", "iMD"}


@dataclass
class Datagram:
    length: int
    sent_at: int
    sequence: int
    session: int
    templates: list[int] = field(default_factory=list)  # the ids of the descriptors it carried
    receivers: list[dict[str, Any]] = field(default_factory=list)
    senders: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Collector:
    """Reads datagrams of one sender; raises ValueError for one it cannot read."""

    templates: dict[int, list[tuple[str, int]]] = field(default_factory=dict)

    def read(self, data: bytes) -> Datagram:
        version, length, sent_at, sequence, session = struct.unpack_from("!HHIII", data)
        if version != pskreport.VERSION or length != len(data):
            raise ValueError(f"header: version {version}, length {length} of {len(data)} bytes")
        out = Datagram(length, sent_at, sequence, session)
        at = pskreport.HEADER_BYTES
        while at < len(data):
            kind, size = struct.unpack_from("!HH", data, at)
            if size < 4 or at + size > len(data):
                raise ValueError(f"a set of {size} bytes at {at}")
            body = data[at + 4 : at + size]
            if kind in (pskreport.TEMPLATE_SET, pskreport.OPTIONS_SET):
                out.templates.append(self._template(kind, body))
            elif kind in self.templates:
                (out.receivers if kind == pskreport.RECEIVER.id else out.senders).extend(self._records(kind, body))
            else:
                raise ValueError(f"a set of the template {kind:#06x}, which was never described")
            at += size
        return out

    def _template(self, kind: int, body: bytes) -> int:
        id, count = struct.unpack_from("!HH", body)
        at = 6 if kind == pskreport.OPTIONS_SET else 4
        fields: list[tuple[str, int]] = []
        for _ in range(count):
            number, length = struct.unpack_from("!HH", body, at)
            enterprise = bool(number & 0x8000)
            if enterprise and struct.unpack_from("!I", body, at + 4)[0] != pskreport.ENTERPRISE:
                raise ValueError("another enterprise's element")
            at += 8 if enterprise else 4
            fields.append((NAMES[(enterprise, number & 0x7FFF)], length))
        if any(body[at:]):
            raise ValueError("the padding of a descriptor is not zero")
        self.templates[id] = fields
        return int(id)

    def _records(self, id: int, body: bytes) -> list[dict[str, Any]]:
        fields, at = self.templates[id], 0
        records: list[dict[str, Any]] = []
        while any(body[at:]):  # (the rest is the padding)
            one: dict[str, Any] = {}
            for name, length in fields:
                if length == pskreport.VARIABLE:
                    size = body[at]
                    one[name] = body[at + 1 : at + 1 + size].decode("ascii")
                    at += 1 + size
                else:
                    one[name] = int.from_bytes(body[at : at + length], "big", signed=name in SIGNED)
                    at += length
            records.append(one)
        return records
