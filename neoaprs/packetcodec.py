"""A packet as a packet-table row and back, and the other texts the database keeps.

A time is kept as text in one fixed form (`2026-10-21T12:00:00.000000Z`) that sorts as the time
does. The JSON of a decoded packet has a `type` and the dataclass fields. Pure code.
"""
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
KINDS = tuple(_BY_KIND)  # the values of the column `kind`
# telemetry is kind "other" with a type of its own
_TYPES: dict[str, type] = {**_BY_KIND, "telemetry": Telemetry}


class PacketRow(NamedTuple):
    """The columns of the packet table, in INSERT order."""
    heard_at: str
    direction: str
    raw: bytes
    source: str
    destination: str
    path: str  # the digipeaters, comma joined
    kind: str
    summary: str
    decoded: str  # JSON
    error: str | None  # why a field did not decode, for kind "undecoded"
    via: str  # the channel: rf, rf-gated or is (Packet.via)
    # the id of the radio it came on or went out on; null for the internet
    radio: int | str | None
    snr: float | None = None
    rssi: float | None = None


def stamp(t: datetime) -> str:
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
    """Return the decoded packet as JSON. Raise ValueError for a non-finite number (not JSON)."""
    kind = next(k for k, cls in _TYPES.items() if type(decoded) is cls)
    return json.dumps({"type": kind, **_plain(decoded)}, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def decode_decoded(text: str) -> Decoded:
    """Return the decoded packet from its JSON; raise ValueError, KeyError or TypeError if bad."""
    data = json.loads(text)
    cls = _TYPES.get(data.pop("type", None))
    if cls is None:
        raise ValueError("the JSON of a decoded packet has no known type")
    result: Decoded = _build(cls, data)
    return result


def tnc2(packet: Packet) -> str:
    """Return the packet as a TNC2 monitor line ("OH2RDG>APN391,OH2RCH-2*:!6007.47N...")."""
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
                     encode_decoded(decoded), error, packet.via, packet.radio_id, packet.snr, packet.rssi)


def info_of(raw: bytes, via: str) -> bytes:
    """Return the information field of a kept packet. Raise Ax25Error for an invalid frame."""
    return raw.partition(b":")[2] if via == IS else ax25.decode(raw).info


def packet_of(row: PacketRow) -> Packet:
    """Return the packet from its row; raise ValueError, KeyError, TypeError or Ax25Error.

    The channel is re-read from the frame: rf-gated exactly when a third-party header is present.
    """
    if row.direction not in ("in", "out"):
        raise ValueError(f"direction {row.direction!r}")
    via_of(row.via)
    direction: Literal["in", "out"] = "in" if row.direction == "in" else "out"
    info = info_of(bytes(row.raw), row.via)
    opened = header_of(info)

    via = channel_of(None if opened is None else opened[0], row.via == IS, row.via == DUMMY)
    return Packet(heard_at=parse_stamp(row.heard_at), direction=direction, raw=bytes(row.raw), source=row.source, destination=row.destination,
                  path=tuple(row.path.split(",")) if row.path else (), info=info, decoded=decode_decoded(row.decoded), third_party=None if opened is None else opened[0], via=via, radio_id=None if row.radio is None else int(row.radio),
                  snr=None if row.snr is None else float(row.snr), rssi=None if row.rssi is None else float(row.rssi))
