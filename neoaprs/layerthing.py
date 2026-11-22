"""Map traffic layers (aircraft and ships): a thing's shape, sources, polling rules, limits.

Plain values and rules, no I/O. A thing is never a station and never reaches the station book.
"""

import heapq
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Literal

from .geo import distance_km
from .units import NAUTICAL_MILE_KM

Layer = Literal["aircraft", "ships"]
Source = Literal["none", "adsbfi", "adsblol", "fintraffic", "radarcape", "receiver"]
Feed = Literal["adsbfi", "adsblol", "aircraft_receiver", "fintraffic_locations", "fintraffic_vessels"]
LAYERS: tuple[Layer, ...] = ("aircraft", "ships")
AIRCRAFT_SOURCES: tuple[Source, ...] = ("none", "adsbfi", "adsblol", "radarcape", "receiver")
SHIP_SOURCES: tuple[Source, ...] = ("none", "fintraffic", "receiver")
SOURCES: dict[Layer, tuple[Source, ...]] = {"aircraft": AIRCRAFT_SOURCES, "ships": SHIP_SOURCES}
SERVICES: frozenset[Source] = frozenset({"adsbfi", "adsblol", "fintraffic"})
OWN_RECEIVERS: frozenset[Source] = frozenset({"radarcape", "receiver"})

# Fintraffic coverage: south, north, west, east (degrees)
FINTRAFFIC_BOX = (57.7, 65.8, 16.5, 32.5)
ADSBFI_URL = "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}"
ADSBLOL_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
FINTRAFFIC_LOCATIONS = "https://meri.digitraffic.fi/api/ais/v1/locations"
FINTRAFFIC_VESSELS = "https://meri.digitraffic.fi/api/ais/v1/vessels"
FINTRAFFIC_HEADERS = {"Digitraffic-User": "NeoAPRS"}
# a request reaches this far beyond the circle so rounding does not lose a thing at the edge
AREA_MARGIN_KM = 8
MAX_NM = 250  # the most either aircraft service answers for

EVERY_SEC: dict[Feed, int] = {
    "adsbfi": 30,
    "adsblol": 60,
    "aircraft_receiver": 5,
    "fintraffic_locations": 60,
    "fintraffic_vessels": 900,
}
BACKOFF_MAX_SEC = 900  # the longest wait after failures in a row
# a service answering one of these is not asked again until restart
STOP_CODES = frozenset({400, 401, 403, 404})
TELL_EVERY_SEC = 5
AGE_CHECK_SEC = 60
AIS_RETRY_SEC = (5, 300)

AIRCRAFT_RECEIVER_AGE_SEC = 60
AIRCRAFT_SERVICE_AGE_SEC = 90
SHIPS_AGE_SEC = 1800
MAX_AGE_SEC = {
    "aircraft_receiver": AIRCRAFT_RECEIVER_AGE_SEC,
    "aircraft_service": AIRCRAFT_SERVICE_AGE_SEC,
    "ships": SHIPS_AGE_SEC,
}

# a service's answer keeps the nearest LIMIT things plus emergencies
LIMIT = 300
RECEIVER_BOUND = 2000
MAX_PACKED = 4 * 1024 * 1024
MAX_UNPACKED = 16 * 1024 * 1024
AIS_LINE_MAX = 1024  # bytes
AIS_LINES_PER_SEC = 200

AIRCRAFT_PLACES = (
    "/tar1090/data/aircraft.json",
    "/data/aircraft.json",
    "/skyaware/data/aircraft.json",
    "/dump1090/data/aircraft.json",
)
AIRCRAFT_PORTS = (80, 8080)
AIRCRAFT_HOST = "127.0.0.1"
RADARCAPE_PLACE = "/aircraftlist.json?knownposonly=1"
AIS_PORT = 10110
AIS_HOST = "127.0.0.1"


@dataclass(frozen=True)
class Thing:
    """The one shape of an aircraft or a ship."""

    # aircraft: readsb's `hex`, lower case; ship: the MMSI as text
    id: str
    lat: float
    lon: float
    at: datetime  # UTC
    heading_deg: int | None  # 0..359
    speed_kmh: float | None
    name: str = ""  # aircraft: the flight; ship: its name
    # aircraft only, except ship_type, course_deg and destination
    emergency: bool = False
    altitude_m: int | None = None
    registration: str = ""
    type: str = ""
    category: str = ""  # emitter category ("A3")
    designator: str = ""  # ICAO type designator ("A321")
    ship_type: int | None = None  # AIS type 1..99
    course_deg: int | None = None
    destination: str = ""
    origin: str = ""
    vertical_ms: float | None = None


@dataclass(frozen=True)
class ReceiverState:
    state: Literal["looking", "receiving", "no_answer"]
    things: int
    heard_at: datetime | None


@dataclass(frozen=True)
class LayerState:
    layer: Layer
    source: Source
    offered: tuple[Source, ...]
    receiver: ReceiverState | None


@dataclass(frozen=True)
class LayerTable:
    layer: Layer
    source: Source
    away: bool
    things: tuple[Thing, ...]


def reaches_box(
    position: tuple[float, float] | None, radius_km: int, box: tuple[float, float, float, float] = FINTRAFFIC_BOX
) -> bool:
    """Return whether the circle round the position reaches the box."""
    if position is None:
        return False
    lat, lon = position
    south, north, west, east = box
    return distance_km(lat, lon, min(max(lat, south), north), min(max(lon, west), east)) <= radius_km


def offered(layer: Layer, position: tuple[float, float] | None, radius_km: int) -> tuple[Source, ...]:
    """Return the sources offered, "none" first; Fintraffic only within its waters."""
    if layer == "aircraft":
        return AIRCRAFT_SOURCES
    return tuple(source for source in SHIP_SOURCES if source != "fintraffic" or reaches_box(position, radius_km))


def in_force(layer: Layer, chosen: str, offered: Iterable[Source]) -> Source:
    """Return the chosen source while offered, else "none"."""
    none: Source = "none"
    return next((source for source in offered if source == chosen and source in SOURCES[layer]), none)


def _tenth(value: float) -> str:
    return f"{round(value, 1) + 0.0:.1f}"  # + 0.0 turns a -0.0 into 0.0


def request_point(lat: float, lon: float) -> tuple[str, str]:
    """Return one decimal each, never "-0.0"."""
    return _tenth(lat), _tenth(lon)


def request_nm(radius_km: int) -> int:
    return min(MAX_NM, ceil((radius_km + AREA_MARGIN_KM) / NAUTICAL_MILE_KM))


def service_url(source: Source, lat: float, lon: float, radius_km: int) -> str:
    """Return an aircraft service's request URL; raise ValueError for other sources."""
    pattern = {"adsbfi": ADSBFI_URL, "adsblol": ADSBLOL_URL}.get(source)
    if pattern is None:
        raise ValueError(f"{source} is not an aircraft service")
    at_lat, at_lon = request_point(lat, lon)
    return pattern.format(lat=at_lat, lon=at_lon, nm=request_nm(radius_km))


def max_age_sec(layer: Layer, source: Source) -> int:
    if layer == "ships":
        return MAX_AGE_SEC["ships"]
    return MAX_AGE_SEC["aircraft_receiver" if source in OWN_RECEIVERS else "aircraft_service"]


def backoff_sec(every_sec: float, failures: int) -> float:
    """Return the interval doubled per failure, at most BACKOFF_MAX_SEC."""
    return float(min(every_sec * (1 << max(failures, 0)), BACKOFF_MAX_SEC))


def _km(thing: Thing, centre: tuple[float, float]) -> float:
    return distance_km(centre[0], centre[1], thing.lat, thing.lon)


def within(things: Iterable[Thing], centre: tuple[float, float], radius_km: float) -> list[Thing]:
    return [thing for thing in things if _km(thing, centre) <= radius_km]


def nearest(things: Iterable[Thing], centre: tuple[float, float], limit: int = LIMIT) -> list[Thing]:
    """Return the `limit` nearest things, nearest first, then the emergencies beyond."""
    ranked = sorted(things, key=lambda thing: _km(thing, centre))
    return ranked[:limit] + [thing for thing in ranked[limit:] if thing.emergency]


def newest(things: Iterable[Thing], bound: int = RECEIVER_BOUND) -> list[Thing]:
    """Return at most `bound` things, the newest positions; no cut by distance."""
    listed = list(things)
    if len(listed) <= bound:
        return listed
    # a heap, not a full sort: other threads run between its steps
    kept = {id(thing) for thing in heapq.nlargest(bound, listed, key=lambda thing: thing.at)}

    return [thing for thing in listed if id(thing) in kept]
