"""What the program knows of the map's layers of traffic (aircraft and ships): the one shape of a thing on them, the sources a station is offered, what a request to a service on the internet carries,
how often each is asked, how old a thing may be, and how many are kept. Plain values and rules, no I/O: the services, the readers and the wire take their numbers from here, and scripts/gen-protocol.py gives the
page those it needs (LIMITS.layers, AIRCRAFT_SOURCES, SHIP_SOURCES of ui/src/protocol/lists.ts).

Nothing of a layer is a station: a thing lives in the memory of the layers' service by its id, and never reaches the station book, the database, the packets, the statistics, the replay, the iGate or a radio."""
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
LAYERS: tuple[Layer, ...] = ("aircraft", "ships")             # in the order the topic `map` tells them
AIRCRAFT_SOURCES: tuple[Source, ...] = ("none", "adsbfi", "adsblol", "radarcape", "receiver")
SHIP_SOURCES: tuple[Source, ...] = ("none", "fintraffic", "receiver")
SOURCES: dict[Layer, tuple[Source, ...]] = {"aircraft": AIRCRAFT_SOURCES, "ships": SHIP_SOURCES}
SERVICES: frozenset[Source] = frozenset({"adsbfi", "adsblol", "fintraffic"})     # a source on the internet
OWN_RECEIVERS: frozenset[Source] = frozenset({"radarcape", "receiver"})         # a receiver of the operator's own: a Radarcape, or readsb's file as a receiver of the operator's own serves it (aircraft); an AIS receiver (ships)

FINTRAFFIC_BOX = (57.7, 65.8, 16.5, 32.5)                      # the waters Fintraffic's feed covers: south, north, west, east, in degrees
ADSBFI_URL = "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}"
ADSBLOL_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
FINTRAFFIC_LOCATIONS = "https://meri.digitraffic.fi/api/ais/v1/locations"
FINTRAFFIC_VESSELS = "https://meri.digitraffic.fi/api/ais/v1/vessels"
FINTRAFFIC_HEADERS = {"Digitraffic-User": "NeoAPRS"}
AREA_MARGIN_KM = 8                                             # what a request asks beyond the circle, so that a thing at its edge is not lost to the rounding of our position
MAX_NM = 250                                                   # the most either aircraft service answers for

EVERY_SEC: dict[Feed, int] = {"adsbfi": 30, "adsblol": 60, "aircraft_receiver": 5, "fintraffic_locations": 60, "fintraffic_vessels": 900}     # how often each feed is asked, at most
BACKOFF_MAX_SEC = 900                                          # the longest wait after failures in a row
STOP_CODES = frozenset({400, 401, 403, 404})                   # a service that answers one of these is not asked again until the daemon starts again
TELL_EVERY_SEC = 5                                             # the AIS receiver's table is told to the pages at most this often
AGE_CHECK_SEC = 60                                             # how often the tables are looked at for things that grew too old
AIS_RETRY_SEC = (5, 300)                                       # a lost or refused AIS connection is opened again after the first, doubling up to the second

AIRCRAFT_RECEIVER_AGE_SEC = 60                                 # how old a thing may be before it is dropped: an aircraft from the own receiver,
AIRCRAFT_SERVICE_AGE_SEC = 90                                  # an aircraft from a service,
SHIPS_AGE_SEC = 1800                                           # a ship from any source
MAX_AGE_SEC = {"aircraft_receiver": AIRCRAFT_RECEIVER_AGE_SEC, "aircraft_service": AIRCRAFT_SERVICE_AGE_SEC, "ships": SHIPS_AGE_SEC}     # the three by name; max_age_sec picks one

LIMIT = 300                                                    # a service's answer is cut to the nearest this many (an emergency is kept beyond them)
RECEIVER_BOUND = 2000                                          # an own receiver is cut by nothing but this guard against a broken feed: beyond it the newest positions are kept
MAX_PACKED = 4 * 1024 * 1024                                   # the largest answer as it travels
MAX_UNPACKED = 16 * 1024 * 1024                                # and unpacked
AIS_LINE_MAX = 1024                                            # the longest AIS line read, in bytes
AIS_LINES_PER_SEC = 200                                        # the most AIS lines read a second; the rest are passed over

AIRCRAFT_PLACES = ("/tar1090/data/aircraft.json", "/data/aircraft.json", "/skyaware/data/aircraft.json", "/dump1090/data/aircraft.json")     # where a receiver keeps readsb's JSON
AIRCRAFT_PORTS = (80, 8080)
AIRCRAFT_HOST = "127.0.0.1"                                    # the own aircraft receiver while its address is empty: this computer
RADARCAPE_PLACE = "/aircraftlist.json?knownposonly=1"          # a Radarcape's own list of the aircraft whose position it knows (a Radarcape with no address is not looked for: it is a device of its own)
AIS_PORT = 10110
AIS_HOST = "127.0.0.1"                                         # the own AIS receiver while its address is empty, on AIS_PORT


@dataclass(frozen=True)
class Thing:
    """The one shape of an aircraft or a ship."""
    id: str                         # aircraft: readsb's `hex` as given, lower case (it may begin with "~"); ship: the MMSI as text
    lat: float
    lon: float
    at: datetime                    # the time of its position (UTC)
    heading_deg: int | None         # 0..359, where the mark points; None: no direction, drawn as a diamond
    speed_kmh: float | None
    name: str = ""                  # aircraft: the flight, trimmed; ship: its name, trimmed; "" when none
    emergency: bool = False         # aircraft only
    altitude_m: int | None = None   # aircraft only
    registration: str = ""          # aircraft only ("OH-LZA")
    type: str = ""                  # aircraft only: readsb's `desc`, else `t`; a Radarcape's `typ`; else ""
    category: str = ""              # aircraft only: the emitter category as given, upper case ("A3"); "" when none
    designator: str = ""            # aircraft only: the ICAO type designator, upper case ("A321"); "" when none
    ship_type: int | None = None    # ships only: the AIS type of ship and cargo, 1..99; None when not known or 0
    course_deg: int | None = None   # ships only: course over ground, 0..359
    destination: str = ""           # a ship's destination as it gave it; an aircraft's: the ICAO code of the airport it is going to, upper case ("" when not told)
    origin: str = ""                # aircraft only: the ICAO code of the airport it left, upper case ("" when not told)
    vertical_ms: float | None = None  # aircraft only: metres a second, above zero while it climbs, one decimal; None when not told


@dataclass(frozen=True)
class ReceiverState:
    """The own receiver's state, for its line in Settings."""
    state: Literal["looking", "receiving", "no_answer"]
    things: int                     # what it gave with a position at its last answer (aircraft), or the ships held now (AIS)
    heard_at: datetime | None       # its last answer in the expected form (AIS: the last sentence decoded)


@dataclass(frozen=True)
class LayerState:
    """What the topic `map` says of one layer."""
    layer: Layer
    source: Source                  # in force (in_force)
    offered: tuple[Source, ...]     # what the Settings list holds, "none" first
    receiver: ReceiverState | None  # while `source` is an own receiver (OWN_RECEIVERS); else None


@dataclass(frozen=True)
class LayerTable:
    """What the message `layer_things` carries: the whole table of a layer."""
    layer: Layer
    source: Source
    away: bool                      # the last question failed or was not in the expected form, the connection is down, or there is no position to ask for
    things: tuple[Thing, ...]


def reaches_box(position: tuple[float, float] | None, radius_km: int, box: tuple[float, float, float, float] = FINTRAFFIC_BOX) -> bool:
    """Whether the circle of `radius_km` round the position reaches the box (south, north, west, east): the distance to the box's nearest point is at most the radius. No position reaches nothing."""
    if position is None:
        return False
    lat, lon = position
    south, north, west, east = box
    return distance_km(lat, lon, min(max(lat, south), north), min(max(lon, west), east)) <= radius_km


def offered(layer: Layer, position: tuple[float, float] | None, radius_km: int) -> tuple[Source, ...]:
    """The sources the station is offered for the layer, "none" first: every aircraft source; for ships Fintraffic only where the circle reaches its waters."""
    if layer == "aircraft":
        return AIRCRAFT_SOURCES
    return tuple(source for source in SHIP_SOURCES if source != "fintraffic" or reaches_box(position, radius_km))


def in_force(layer: Layer, chosen: str, offered: Iterable[Source]) -> Source:
    """The source that counts: the one chosen while it is offered, else "none" (a stored source the station is not offered now stays stored)."""
    none: Source = "none"
    return next((source for source in offered if source == chosen and source in SOURCES[layer]), none)


def _tenth(value: float) -> str:
    return f"{round(value, 1) + 0.0:.1f}"          # (+ 0.0 turns a -0.0 into 0.0)


def request_point(lat: float, lon: float) -> tuple[str, str]:
    """Our position as a request to a service carries it: each to one decimal ("60.2", "24.7"), never "-0.0"."""
    return _tenth(lat), _tenth(lon)


def request_nm(radius_km: int) -> int:
    """The radius a request asks for, in whole nautical miles: the circle and AREA_MARGIN_KM, at most MAX_NM."""
    return min(MAX_NM, ceil((radius_km + AREA_MARGIN_KM) / NAUTICAL_MILE_KM))


def service_url(source: Source, lat: float, lon: float, radius_km: int) -> str:
    """The address of an aircraft service's question for the circle round the position (adsbfi, adsblol); ValueError for any other source."""
    pattern = {"adsbfi": ADSBFI_URL, "adsblol": ADSBLOL_URL}.get(source)
    if pattern is None:
        raise ValueError(f"{source} is not an aircraft service")
    at_lat, at_lon = request_point(lat, lon)
    return pattern.format(lat=at_lat, lon=at_lon, nm=request_nm(radius_km))


def max_age_sec(layer: Layer, source: Source) -> int:
    """How old a thing of the layer from the source may be before it is dropped."""
    if layer == "ships":
        return MAX_AGE_SEC["ships"]
    return MAX_AGE_SEC["aircraft_receiver" if source in OWN_RECEIVERS else "aircraft_service"]


def backoff_sec(every_sec: float, failures: int) -> float:
    """The wait before the next question after `failures` failures in a row (1 or more): the feed's interval doubled for each, at most BACKOFF_MAX_SEC."""
    return float(min(every_sec * (1 << max(failures, 0)), BACKOFF_MAX_SEC))


def _km(thing: Thing, centre: tuple[float, float]) -> float:
    return distance_km(centre[0], centre[1], thing.lat, thing.lon)


def within(things: Iterable[Thing], centre: tuple[float, float], radius_km: float) -> list[Thing]:
    """The things at most `radius_km` from the centre, in their order."""
    return [thing for thing in things if _km(thing, centre) <= radius_km]


def nearest(things: Iterable[Thing], centre: tuple[float, float], limit: int = LIMIT) -> list[Thing]:
    """The `limit` things nearest the centre, nearest first, and after them every emergency beyond the limit."""
    ranked = sorted(things, key=lambda thing: _km(thing, centre))
    return ranked[:limit] + [thing for thing in ranked[limit:] if thing.emergency]


def newest(things: Iterable[Thing], bound: int = RECEIVER_BOUND) -> list[Thing]:
    """At most `bound` things, the newest positions; all of them, in their order, while there are no more (the own receivers' guard: no cut by distance)."""
    listed = list(things)
    if len(listed) <= bound:
        return listed
    kept = {id(thing) for thing in heapq.nlargest(bound, listed, key=lambda thing: thing.at)}          # (a heap, not a sort of them all: other threads run between its steps)
    return [thing for thing in listed if id(thing) in kept]
