"""The satellites file of the project's server: the list of satellites, each with its orbital elements.

A value the list does not mark sure is dropped here, so nothing unconfirmed reaches the page; a
satellite whose elements are older than MAX_ELEMENTS_AGE is not shown."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .satellites import Orbit, orbit_of

SATELLITES_URL = "https://neo.oh2gba.eu/api/v1/satellites.php"
FILE_NAME = "satellites.json"
MAX_BYTES = 262144
MAX_SATELLITES = 60
MAX_ELEMENTS_AGE = timedelta(days=14)
MAX_ELEMENTS_AHEAD = timedelta(days=2)  # an epoch later than this is a broken record
NAME_FORM = re.compile(r"[0-9A-Za-z .()-]{1,24}")
PATH_FORM = re.compile(r"[A-Z0-9]{1,6}(-[0-9]{1,2})?(,[A-Z0-9]{1,6}(-[0-9]{1,2})?){0,7}")
Mode = Literal["afsk1200", "gmsk9600"]
MODES: tuple[Mode, ...] = ("afsk1200", "gmsk9600")


@dataclass(frozen=True)
class Satellite:
    id: int
    name: str
    downlinks_hz: tuple[int, ...]
    uplinks_hz: tuple[int, ...]
    mode: Mode | None
    path: str
    orbit: Orbit | None


@dataclass(frozen=True)
class SatelliteFile:
    made: datetime | None
    elements_at: datetime | None
    satellites: tuple[Satellite, ...]


def _time(value: object) -> datetime | None:
    try:
        when = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return when if when is not None and when.tzinfo is not None else None


def _sure_hz(value: object) -> tuple[int, ...]:
    found: list[int] = []
    for one in value if isinstance(value, list) else []:
        mhz = one.get("mhz") if isinstance(one, dict) else None
        if one.get("sure") is True and isinstance(mhz, int | float) and 1 < mhz < 12000:
            hz = round(mhz * 1e6)
            if hz not in found:
                found.append(hz)
    return tuple(found)


def _sure_text(value: object) -> str:
    return (
        value["value"]
        if isinstance(value, dict) and value.get("sure") is True and isinstance(value.get("value"), str)
        else ""
    )


def _satellite(row: Mapping[str, object]) -> Satellite | None:
    number, name = row.get("id"), row.get("name")
    if type(number) is not int or not isinstance(name, str) or NAME_FORM.fullmatch(name) is None:
        return None
    mode, path = _sure_text(row.get("mode")), _sure_text(row.get("path"))
    elements = row.get("elements")
    orbit = orbit_of(elements) if isinstance(elements, dict) else None
    return Satellite(
        number,
        name,
        _sure_hz(row.get("downlink")),
        _sure_hz(row.get("uplink")),
        next((one for one in MODES if one == mode), None),
        path if PATH_FORM.fullmatch(path) else "",
        orbit if orbit is not None and orbit.id == number else None,
    )


def read_file(body: bytes) -> SatelliteFile | None:
    """Return the file's satellites (a bad row is left out alone); None if the body is not such a file."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1 or not isinstance(data.get("satellites"), list):
        return None
    rows = [_satellite(row) for row in data["satellites"][:MAX_SATELLITES] if isinstance(row, dict)]
    found: dict[int, Satellite] = {}
    for one in rows:
        if one is not None and one.id not in found:
            found[one.id] = one
    return SatelliteFile(_time(data.get("made")), _time(data.get("elements_at")), tuple(found.values()))


def shown(satellite: Satellite, now: datetime) -> Orbit | None:
    """Return the satellite's orbit while its elements are fresh enough to be drawn, else None."""
    orbit = satellite.orbit
    if orbit is None or not -MAX_ELEMENTS_AHEAD <= now - orbit.epoch <= MAX_ELEMENTS_AGE:
        return None
    return orbit
