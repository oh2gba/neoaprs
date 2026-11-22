"""A jetvision Radarcape's aircraft list, `aircraftlist.json` (asked with `knownposonly=1`).

Read into the layer's things as readsb.py reads readsb's file; fields follow wiki.jetvision.de.
Ground traffic and rows without a recent position are left out. No I/O.
"""

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from .clock import from_unix
from .layerthing import RADARCAPE_PLACE, Thing
from .readsb import (
    ALTITUDE_M_RANGE,
    EMERGENCY_SQUAWKS,
    SEEN_MAX_SEC,
    SPEED_KMH_RANGE,
    converted,
    host_port,
    is_whole_address,
    loads,
    number,
    text_of,
    vertical_ms,
)
from .units import FOOT_M, KNOT_KMH

AIRPORT_CODE_LENGTH = 4
PERMANENT_ALERT = 3  # `alr`: a squawk of 7500, 7600 or 7700


def _airport(value: Any) -> str:
    """Return an airport's ICAO code in upper case (four ASCII letters or digits); else none."""
    code = value.strip() if isinstance(value, str) else ""
    return code.upper() if len(code) == AIRPORT_CODE_LENGTH and code.isascii() and code.isalnum() else ""


def _squawk(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:04d}"
    return text_of(value)


def _at(row: dict[str, Any], received_at: datetime) -> datetime | None:
    """Return the time of the position (`lla` or `uti`, else the answer's); None when a day old."""
    age = number(row.get("lla"))
    if age is None and (sent := number(row.get("uti"))) is not None:
        age = (received_at - from_unix(sent)).total_seconds()
    age = max(age or 0.0, 0.0)
    return None if age >= SEEN_MAX_SEC else received_at - timedelta(seconds=age)


def _thing(row: Any, received_at: datetime) -> Thing | None:
    """Return one aircraft of the list, or None for one that is not shown."""
    if not isinstance(row, dict) or not (id := text_of(row.get("hex")).lower()):
        return None
    lat, lon = number(row.get("lat")), number(row.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    category = text_of(row.get("cat")).upper()
    if text_of(row.get("gda")).upper() == "G" or category.startswith("C"):
        return None
    at = _at(row, received_at)
    if at is None:
        return None
    metres, speed, track = (
        converted(row.get("alt"), FOOT_M, ALTITUDE_M_RANGE),
        converted(row.get("spd"), KNOT_KMH, SPEED_KMH_RANGE),
        number(row.get("trk")),
    )
    designator = text_of(row.get("typ")).upper()
    return Thing(
        id=id,
        lat=lat,
        lon=lon,
        at=at,
        heading_deg=None if track is None else int(round(track)) % 360,
        speed_kmh=None if speed is None else round(speed, 1),
        name=text_of(row.get("fli")),
        emergency=number(row.get("alr")) == PERMANENT_ALERT or _squawk(row.get("squ")) in EMERGENCY_SQUAWKS,
        altitude_m=None if metres is None else int(round(metres)),
        vertical_ms=vertical_ms(row.get("vrt")),
        registration=text_of(row.get("reg")),
        type=designator,
        category=category,
        designator=designator,
        destination=_airport(row.get("dst")),
        origin=_airport(row.get("org")),
    )


def read_aircraft(body: bytes, received_at: datetime) -> list[Thing] | None:
    """Return the shown aircraft, one per `hex` (newest); None if not a JSON array of objects."""
    try:
        listed = loads(body)
    except (ValueError, RecursionError, StopIteration):
        return None
    if not isinstance(listed, list) or (listed and not any(isinstance(row, dict) for row in listed)):
        return None
    kept: dict[str, Thing] = {}
    for row in listed:
        try:
            thing = _thing(row, received_at)
        except (OverflowError, ValueError):  # a number or time out of range: that row is skipped
            continue
        if thing is not None and (thing.id not in kept or kept[thing.id].at < thing.at):
            kept[thing.id] = thing
    return list(kept.values())


def radarcape_url(address: str) -> str | None:
    """Return where the list is asked: a whole address as typed, or host[:port] plus the place."""

    value = address.strip()
    if not value:
        return None
    if is_whole_address(value):
        whole = urlsplit(value)
        return (
            value
            if whole.path not in ("", "/") or whole.query or whole.fragment
            else f"{whole.scheme.lower()}://{whole.netloc}{RADARCAPE_PLACE}"
        )
    host, port = host_port(value)
    return f"http://{host}{'' if port in (None, 80) else f':{port}'}{RADARCAPE_PLACE}"
