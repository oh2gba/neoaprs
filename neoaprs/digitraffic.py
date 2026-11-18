"""Fintraffic's open ship feed (digitraffic.fi, marine AIS) as the program reads it: the positions of every ship (`/locations`, GeoJSON) and what each says of itself (`/vessels`, a list). Pure code: the
answer arrives as bytes from another module. An answer that is not in the expected form is None (the caller counts it as a failure); a single ship that is not complete is passed over."""
import json
import math
from typing import Any

from .aisdecode import AisPosition, AisStatic
from .clock import from_unix

_SOG_NA, _COG_NA, _HEADING_NA = 102.3, 360, 511           # AIS's "not available" for speed, course and heading


def _json(body: bytes | str) -> Any:
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        return None


def _number(value: object) -> float | None:
    """A JSON number (not a boolean) as a finite float, else None (NaN, infinity and an integer too large for a float are not numbers here)."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _position(feature: object) -> AisPosition | None:
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(props, dict) or not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    mmsi = props.get("mmsi", feature.get("mmsi"))
    stamp = _number(props.get("timestampExternal"))
    if not isinstance(coordinates, list) or len(coordinates) < 2 or not isinstance(mmsi, int) or isinstance(mmsi, bool) or not 0 < mmsi <= 999999999 or stamp is None:
        return None
    lon, lat = _number(coordinates[0]), _number(coordinates[1])
    if lon is None or lat is None or abs(lon) > 180 or abs(lat) > 90:
        return None
    sog, cog, heading = _number(props.get("sog")), _number(props.get("cog")), _number(props.get("heading"))
    try:
        at = from_unix(stamp / 1000)
    except (OverflowError, ValueError):
        return None
    return AisPosition(
        mmsi=mmsi, lat=lat, lon=lon, at=at,
        sog_kn=None if sog is None or sog < 0 or sog >= _SOG_NA else sog,
        cog_deg=None if cog is None or not 0 <= cog < _COG_NA else cog,
        heading_deg=None if heading is None or not 0 <= heading < 360 or heading == _HEADING_NA else int(heading),
    )


def read_locations(body: bytes | str) -> list[AisPosition] | None:
    """The ships of `/locations` that have a position and a time; None when the answer is not a GeoJSON collection of features."""
    data = _json(body)
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return None
    return [found for feature in features if (found := _position(feature)) is not None]


def _static(entry: object) -> AisStatic | None:
    if not isinstance(entry, dict):
        return None
    mmsi, name, kind, destination = entry.get("mmsi"), entry.get("name"), entry.get("shipType"), entry.get("destination")
    if not isinstance(mmsi, int) or isinstance(mmsi, bool) or not 0 < mmsi <= 999999999:
        return None
    return AisStatic(
        mmsi=mmsi,
        name=name.rstrip("@ ").strip() if isinstance(name, str) else "",
        ship_type=kind if isinstance(kind, int) and not isinstance(kind, bool) and 1 <= kind <= 99 else None,
        destination=destination.rstrip("@ ").strip() if isinstance(destination, str) else "",
    )


def read_vessels(body: bytes | str) -> list[AisStatic] | None:
    """What the ships of `/vessels` say of themselves; None when the answer is not a list."""
    data = _json(body)
    if not isinstance(data, list):
        return None
    return [found for entry in data if (found := _static(entry)) is not None]
