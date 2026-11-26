"""The datagrams of PSK Reporter's upload protocol, a subset of IPFIX (https://pskreporter.info/pskdev.html).

A datagram is the header, the record format descriptors when they are due, the receiver record and
the sender records. Pure code; docs/pskreporter.md has the rules.
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass

ENTERPRISE = 30351  # PSK Reporter's IANA enterprise number
VERSION = 10  # the IPFIX version of the header
HEADER_BYTES = 16
MAX_DATAGRAM = 1200
MAX_STRING = 254  # "a length code of no more than 254 bytes"
VARIABLE = 0xFFFF
MODE = "NEOAPRS"
AUTOMATIC = 1  # informationSource: "automatically extracted"
TEMPLATE_SET = 2
OPTIONS_SET = 3


@dataclass(frozen=True)
class Element:
    """An information element: its number, its length (VARIABLE for a string) and its enterprise."""

    number: int
    length: int
    enterprise: bool = True


SENDER_CALL = Element(1, VARIABLE)
RECEIVER_CALL = Element(2, VARIABLE)
SENDER_LOCATOR = Element(3, VARIABLE)
RECEIVER_LOCATOR = Element(4, VARIABLE)
FREQUENCY = Element(5, 4)
SNR = Element(6, 1)
SOFTWARE = Element(8, VARIABLE)
MODE_FIELD = Element(10, VARIABLE)
SOURCE = Element(11, 1)
FLOW_START = Element(150, 4, enterprise=False)


@dataclass(frozen=True)
class Template:
    id: int
    fields: tuple[Element, ...]
    options: bool = False  # an options template: the receiver's, with one scope field


# The receiver template and the first two sender templates are pskdev.html's; the page's templates with
# an SNR also carry iMD, which no modem of ours measures, so those two are our own.
RECEIVER = Template(0x9992, (RECEIVER_CALL, RECEIVER_LOCATOR, SOFTWARE), options=True)
SENDER = Template(0x9993, (SENDER_CALL, FREQUENCY, MODE_FIELD, SOURCE, FLOW_START))
SENDER_WITH_LOCATOR = Template(0x9994, (SENDER_CALL, FREQUENCY, MODE_FIELD, SOURCE, SENDER_LOCATOR, FLOW_START))
SENDER_WITH_SNR = Template(0x9995, (SENDER_CALL, FREQUENCY, SNR, MODE_FIELD, SOURCE, FLOW_START))
SENDER_WITH_BOTH = Template(0x9996, (SENDER_CALL, FREQUENCY, SNR, MODE_FIELD, SOURCE, SENDER_LOCATOR, FLOW_START))
TEMPLATES: tuple[Template, ...] = (RECEIVER, SENDER, SENDER_WITH_LOCATOR, SENDER_WITH_SNR, SENDER_WITH_BOTH)


@dataclass(frozen=True)
class Receiver:
    call: str
    locator: str
    software: str


@dataclass(frozen=True)
class Report:
    """One station heard: `heard_at` and the datagram's time are Unix seconds, `frequency_hz` the dial."""

    call: str
    frequency_hz: int
    heard_at: int
    locator: str | None = None
    snr: int | None = None
    mode: str = MODE
    source: int = AUTOMATIC


def template_for(report: Report) -> Template:
    if report.snr is None:
        return SENDER if report.locator is None else SENDER_WITH_LOCATOR
    return SENDER_WITH_SNR if report.locator is None else SENDER_WITH_BOTH


def _padded(data: bytes) -> bytes:
    return data + b"\0" * (-len(data) % 4)


def _string(text: str) -> bytes:
    """Return a string field: its length byte and its ASCII; raise ValueError for anything else."""
    data = text.encode("ascii")
    if len(data) > MAX_STRING:
        raise ValueError(f"{len(data)} bytes is longer than a field of PSK Reporter takes ({MAX_STRING})")
    return bytes([len(data)]) + data


def template_set(template: Template) -> bytes:
    """Return the record format descriptor of the template as a set of its own."""
    head = struct.pack("!HH", template.id, len(template.fields)) + (b"\0\1" if template.options else b"")
    body = head + b"".join(
        struct.pack("!HHI", 0x8000 | f.number, f.length, ENTERPRISE)
        if f.enterprise
        else struct.pack("!HH", f.number, f.length)
        for f in template.fields
    )
    kind = OPTIONS_SET if template.options else TEMPLATE_SET
    return _padded(struct.pack("!HH", kind, 4 + len(_padded(body))) + body)


def _value(element: Element, report: Report) -> bytes:
    if element == SENDER_CALL:
        return _string(report.call)
    if element == FREQUENCY:
        return struct.pack("!I", report.frequency_hz)
    if element == SNR:
        return struct.pack("!b", max(-128, min(127, report.snr or 0)))
    if element == MODE_FIELD:
        return _string(report.mode)
    if element == SOURCE:
        return bytes([report.source])
    if element == SENDER_LOCATOR:
        return _string(report.locator or "")
    return struct.pack("!I", report.heard_at)


def record(report: Report) -> bytes:
    """Return one sender record in the fields of its template; raise ValueError for a value not ASCII."""
    return b"".join(_value(element, report) for element in template_for(report).fields)


def _data_set(id: int, records: Sequence[bytes]) -> bytes:
    body = _padded(b"".join(records))
    return struct.pack("!HH", id, 4 + len(body)) + body


def receiver_set(receiver: Receiver) -> bytes:
    return _data_set(RECEIVER.id, [_string(receiver.call) + _string(receiver.locator) + _string(receiver.software)])


def datagram(
    sent_at: int,
    sequence: int,
    session: int,
    receiver: Receiver,
    reports: Sequence[Report],
    templates: Sequence[Template] = (),
) -> bytes:
    """Return one datagram: the header, `templates`, the receiver record and the sender records by template."""
    parts = [template_set(t) for t in templates]
    parts.append(receiver_set(receiver))
    for template in TEMPLATES[1:]:
        mine = [record(r) for r in reports if template_for(r) == template]
        if mine:
            parts.append(_data_set(template.id, mine))
    body = b"".join(parts)
    return struct.pack("!HHIII", VERSION, HEADER_BYTES + len(body), sent_at, sequence & 0xFFFFFFFF, session) + body


def fitting(receiver: Receiver, reports: Sequence[Report], templates: Sequence[Template] = ()) -> int:
    """Return how many of the reports, from the first, one datagram holds within MAX_DATAGRAM bytes."""
    fixed = HEADER_BYTES + sum(len(template_set(t)) for t in templates) + len(receiver_set(receiver))
    sizes: dict[Template, int] = {}
    count = 0
    for report in reports:
        template = template_for(report)
        sizes[template] = sizes.get(template, 0) + len(record(report))
        if fixed + sum(4 + size + 3 for size in sizes.values()) > MAX_DATAGRAM:
            break
        count += 1
    return count
