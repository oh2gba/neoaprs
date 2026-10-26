"""A packet as the row of the packet table and back (the header of a third-party packet is read again from the frame, so the table holds nothing for it), and the other texts the database keeps: the stamp of a time and the JSON of what the parser made of a packet.

Pure code: the SQL is packetsql.py's and the log that uses both is packetlog.py. A time is kept as text in one fixed form, `2026-10-21T12:00:00.000000Z`, which sorts as the time does (the
table checks the form). The JSON of a decoded packet is the dataclass as an object with `type` (the word `Packet.kind` gives, "telemetry" for a telemetry report) and its fields, a time as a stamp."""
import dataclasses
import json
import typing
from datetime import UTC, datetime
from typing import Any, Literal, NamedTuple

from . import ax25
from .aprsthirdparty import header_of
from .aprstelemetry import Telemetry
from .packet import DUMMY, IS, Decoded, ItemReport, Message, ObjectReport, Other, Packet, Position, Status, Undecoded, channel_of, via_of

STAMP_FORM = "%Y-%m-%dT%H:%M:%S.%fZ"
_BY_KIND: dict[str, type] = {"position": Position, "message": Message, "object": ObjectReport, "item": ItemReport, "status": Status, "other": Other, "undecoded": Undecoded}
KINDS = tuple(_BY_KIND)                                      # the kinds of a packet (the column `kind`)
_TYPES: dict[str, type] = {**_BY_KIND, "telemetry": Telemetry}      # the `type` of the JSON of a decoded packet: a telemetry report is a packet of kind "other" and has a type of its own


class PacketRow(NamedTuple):
    """The columns of the packet table, in the order of its INSERT."""
    heard_at: str
    direction: str
    raw: bytes
    source: str
    destination: str
    path: str                       # the digipeaters, comma joined
    kind: str
    summary: str
    decoded: str                    # JSON
    error: str | None               # why a field did not decode, for kind "undecoded"
    via: str                        # the channel: rf, rf-gated or is (Packet.via)


def stamp(t: datetime) -> str:
    """The time as the database keeps it: UTC, microseconds, a Z."""
    if t.tzinfo is None:
        raise ValueError("a time must be timezone-aware UTC")
    return t.astimezone(UTC).strftime(STAMP_FORM)


def parse_stamp(text: str) -> datetime:
    return datetime.strptime(text, STAMP_FORM).replace(tzinfo=UTC)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, datetime):
        return stamp(value)
    return value


def _dataclass_in(hint: Any) -> type | None:
    """The dataclass a hint is, or the one a `X | None` holds."""
    return next((c for c in (hint, *typing.get_args(hint)) if isinstance(c, type) and dataclasses.is_dataclass(c)), None)


def _build(cls: type, data: dict[str, Any]) -> Any:
    hints = typing.get_type_hints(cls)
    values: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value, hint = data[f.name], hints[f.name]
        if value is not None and datetime in (hint, *typing.get_args(hint)):
            value = parse_stamp(value)
        elif value is not None and (nested := _dataclass_in(hint)) is not None:
            value = _build(nested, value)
        values[f.name] = value
    return cls(**values)


def encode_decoded(decoded: Decoded) -> str:
    kind = next(k for k, cls in _TYPES.items() if type(decoded) is cls)
    return json.dumps({"type": kind, **_plain(decoded)}, separators=(",", ":"), ensure_ascii=False)


def decode_decoded(text: str) -> Decoded:
    """The decoded packet from its JSON. Raises ValueError (or KeyError, TypeError) when the text is not what encode_decoded makes."""
    data = json.loads(text)
    cls = _TYPES.get(data.pop("type", None))
    if cls is None:
        raise ValueError("the JSON of a decoded packet has no known type")
    result: Decoded = _build(cls, data)
    return result


def tnc2(packet: Packet) -> str:
    """The packet as a line of TNC2 monitor text ("OH2RDG>APN391,OH2RCH-2*:!6007.47N...") with anything unprintable shown as a question mark. A packet from the internet is the line it came as."""
    try:
        line = packet.raw.decode("latin-1") if packet.via == IS else ax25.decode(packet.raw).tnc2()
    except ax25.Ax25Error:
        path = "".join("," + p for p in packet.path)
        line = f"{packet.source}>{packet.destination}{path}:{packet.info.decode('latin-1')}"
    return "".join(c if c.isprintable() else "?" for c in line)


def packet_row(packet: Packet) -> PacketRow:
    decoded = packet.decoded
    error = decoded.error if isinstance(decoded, Undecoded) else None
    return PacketRow(stamp(packet.heard_at), packet.direction, packet.raw, packet.source, packet.destination, ",".join(packet.path), packet.kind, packet.summary,
                     encode_decoded(decoded), error, packet.via)


def info_of(raw: bytes, via: str) -> bytes:
    """The information field of a kept packet: after the first colon of the line for a packet from the internet (it has no AX.25 frame), else the frame's. Raises Ax25Error for a frame that is none."""
    return raw.partition(b":")[2] if via == IS else ax25.decode(raw).info


def packet_of(row: PacketRow) -> Packet:
    """The packet from its row. Raises ValueError (or KeyError, TypeError, Ax25Error) for a row that is not one this program wrote. The channel of a packet on the radio is read from the frame again, like the header of
    a third-party packet: rf-gated exactly when the information field holds one (the column is for the statements; a row the migration marked before the header was checked is made right here)."""
    if row.direction not in ("in", "out"):
        raise ValueError(f"direction {row.direction!r}")
    via_of(row.via)
    direction: Literal["in", "out"] = "in" if row.direction == "in" else "out"
    info = info_of(bytes(row.raw), row.via)
    opened = header_of(info)                  # (the header of a third-party packet is in the information field; `decoded` holds what is inside it)
    via = channel_of(None if opened is None else opened[0], row.via == IS, row.via == DUMMY)
    return Packet(heard_at=parse_stamp(row.heard_at), direction=direction, raw=bytes(row.raw), source=row.source, destination=row.destination,
                  path=tuple(row.path.split(",")) if row.path else (), info=info, decoded=decode_decoded(row.decoded), third_party=None if opened is None else opened[0], via=via)
