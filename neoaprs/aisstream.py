"""AISStream's WebSocket messages: the subscription for the box round a circle, and what comes back.

Pure code: the text arrives from another module. A message in an unexpected form is skipped."""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .aisdecode import AisPosition, AisStatic

KM_PER_DEG = 111.195
BOX_STEP_DEG = 0.1  # the box is rounded outward to this, so a small move sends no new subscription
_SOG_NA, _COG_NA, _HEADING_NA = 102.3, 360.0, 511  # AIS "not available"
MESSAGE_TYPES = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
)
_POSITIONS = MESSAGE_TYPES[:3]
# a ship's own clock that is ahead of ours by more than this is not believed
AHEAD = timedelta(seconds=60)

Box = tuple[tuple[float, float], tuple[float, float]]  # (south, west), (north, east)


def boxes(lat: float, lon: float, radius_km: float) -> tuple[Box, ...]:
    """Return the boxes round the circle, rounded outward; two where it crosses the antimeridian."""
    down = math.floor
    reach_lat = radius_km / KM_PER_DEG
    # The circle's widest east-west reach on the sphere; a pole inside it takes every longitude.
    spread = math.sin(math.radians(reach_lat)) / max(math.cos(math.radians(lat)), 1e-9)
    reach_lon = 180.0 if abs(lat) + reach_lat >= 90.0 or spread >= 1.0 else math.degrees(math.asin(spread))
    step = BOX_STEP_DEG
    south = max(-90.0, round(down((lat - reach_lat) / step) * step, 1))
    north = min(90.0, round(math.ceil((lat + reach_lat) / step) * step, 1))
    west = round(down((lon - reach_lon) / step) * step, 1)
    east = round(math.ceil((lon + reach_lon) / step) * step, 1)
    if east - west >= 360.0:
        return (((south, -180.0), (north, 180.0)),)
    if west < -180.0:
        return (((south, west + 360.0), (north, 180.0)), ((south, -180.0), (north, east)))
    if east > 180.0:
        return (((south, west), (north, 180.0)), ((south, -180.0), (north, east - 360.0)))
    return (((south, west), (north, east)),)


def subscription(key: str, areas: tuple[Box, ...]) -> str:
    """Return the subscription message for the boxes."""
    return json.dumps(
        {
            "APIKey": key,
            "BoundingBoxes": [[[s, w], [n, e]] for (s, w), (n, e) in areas],
            "FilterMessageTypes": list(MESSAGE_TYPES),
        }
    )


@dataclass(frozen=True)
class Confirmed:
    """The server took the subscription."""


@dataclass(frozen=True)
class Refused:
    """The server answered with an error; `key` when it says the key is not valid."""

    key: bool
    words: str  # the server's own words, cut, for the log


Read = AisPosition | AisStatic | Confirmed | Refused | None


def _number(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _text(value: object) -> str:
    return value.replace("@", " ").strip() if isinstance(value, str) and value.isprintable() else ""


def _time(meta: dict[str, Any], now: datetime) -> datetime:
    """Return the report's time (`time_utc`, "2026-11-27 12:00:01.5 +0000 UTC"), else now."""
    text = meta.get("time_utc")
    try:
        at = datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return now
    return now if at > now + AHEAD else at


def _position(mmsi: int, meta: dict[str, Any], report: dict[str, Any], now: datetime) -> AisPosition | None:
    lat = _number(meta.get("latitude", report.get("Latitude")))
    lon = _number(meta.get("longitude", report.get("Longitude")))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    sog = _number(report.get("Sog"))
    cog = _number(report.get("Cog"))
    heading = _number(report.get("TrueHeading"))
    return AisPosition(
        mmsi=mmsi,
        lat=lat,
        lon=lon,
        at=_time(meta, now),
        sog_kn=None if sog is None or sog < 0 or sog >= _SOG_NA else sog,
        cog_deg=None if cog is None or not 0 <= cog < _COG_NA else cog,
        heading_deg=None if heading is None or not 0 <= heading < 360 else int(heading),
    )


def _static(mmsi: int, kind: str, body: dict[str, Any]) -> AisStatic | None:
    if kind == "ShipStaticData":
        ship_type = _number(body.get("Type"))
        return AisStatic(
            mmsi,
            _text(body.get("Name")),
            int(ship_type) if ship_type is not None and 1 <= ship_type <= 99 else None,
            _text(body.get("Destination")),
        )
    part_a, part_b = body.get("ReportA"), body.get("ReportB")
    name = _text(part_a.get("Name")) if isinstance(part_a, dict) and part_a.get("Valid") else ""
    raw = _number(part_b.get("ShipType")) if isinstance(part_b, dict) and part_b.get("Valid") else None
    ship_type = int(raw) if raw is not None and 1 <= raw <= 99 else None
    return AisStatic(mmsi, name, ship_type, "") if name or ship_type is not None else None


_KEY = re.compile(r"\b(api[ _-]?)?key\b")
_REFUSAL = ("invalid", "not valid", "unknown", "not found", "missing", "expired", "revoked", "unauthori", "wrong")
_OUTAGE = ("connection", "limit", "too many", "rate", "busy", "try again", "temporar", "unavailable", "timeout")


def refuses_key(words: str) -> bool:
    """Return whether the server's error says the key itself is not good, not a limit or an outage."""
    lower = words.lower()
    return (
        _KEY.search(lower) is not None
        and any(word in lower for word in _REFUSAL)
        and not any(word in lower for word in _OUTAGE)
    )


def read_message(text: bytes | str, now: datetime) -> Read:
    """Return what one message of the stream says, or None for anything else."""
    try:
        data = json.loads(text)
    except (ValueError, RecursionError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if "error" in data:
        words = str(data.get("error"))[:120]
        return Refused(refuses_key(words), words)
    kind = data.get("MessageType")
    if kind == "SubscriptionConfirmation":
        return Confirmed()
    meta, message = data.get("MetaData"), data.get("Message")
    if kind not in MESSAGE_TYPES or not isinstance(meta, dict) or not isinstance(message, dict):
        return None
    body = message.get(kind)
    mmsi = _number(meta.get("MMSI"))
    if not isinstance(body, dict) or mmsi is None or not 0 < mmsi < 1_000_000_000:
        return None
    if kind in _POSITIONS:
        return _position(int(mmsi), meta, body, now)
    return _static(int(mmsi), kind, body)
