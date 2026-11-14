"""The ships of the AIS feed of Fintraffic's Digitraffic (`https://meri.digitraffic.fi/api/ais/v1`), as values: the positions of `locations` (GeoJSON, one feature for each vessel) and the voyage data of `vessels` (name,
call sign, type, dimensions, draught, destination and ETA), joined by the MMSI. Pure code: services/ais.py asks for the JSON and keeps the ships; nothing here is ever sent anywhere, the ships are only drawn on the map.

The numbers of AIS that mean "not available" are none here: a heading of 511, a course of 360, a speed of 102.3 knots, a draught of 0 and an ETA without a month or a day. The ship type of AIS (a number of two
digits) is a `kind` the page has words for and a `category` that decides the colour of the ship on the map."""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .geo import distance_km

NO_HEADING = 511
NO_COURSE = 360.0
NO_SPEED_KN = 102.3
MOVING_KN = 0.5                          # a ship slower than this is still: its icon points the way the bow does, or nowhere when no heading is known

CATEGORIES = ("cargo", "tanker", "passenger", "highspeed", "fishing", "pleasure", "special", "other")
KINDS = ("cargo", "tanker", "passenger", "highspeed", "fishing", "sailing", "pleasure", "tug", "towing", "pilot", "sar", "military", "law", "dredging", "diving", "tender", "antipollution",
         "medical", "wig", "other")
_SPECIAL = {31: "towing", 32: "towing", 33: "dredging", 34: "diving", 35: "military", 36: "sailing", 37: "pleasure", 50: "pilot", 51: "sar", 52: "tug", 53: "tender", 54: "antipollution",
            55: "law", 58: "medical"}
_DECADES = {2: "wig", 4: "highspeed", 6: "passenger", 7: "cargo", 8: "tanker"}
_CATEGORY = {"sailing": "pleasure", "pleasure": "pleasure", "fishing": "fishing", "highspeed": "highspeed", "passenger": "passenger", "cargo": "cargo", "tanker": "tanker", "other": "other", "wig": "other"}
NAV_STATUSES = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 14})       # the navigational statuses the page has words for (9, 10 and 13 are reserved, 15 is "not defined")


def kind_of(ship_type: int | None) -> str:
    """What the ship is, by the ship type of AIS: `cargo` for 70 to 79, `tug` for 52 and so on; `other` for a type that says nothing (0, a reserved one, or none)."""
    if ship_type is None or not 20 <= ship_type <= 99:
        return "other"
    if ship_type == 30:
        return "fishing"
    return _SPECIAL.get(ship_type) or _DECADES.get(ship_type // 10, "other")


def category_of(kind: str) -> str:
    """The group of kinds a ship is drawn in the colour of: the tugs, pilots, rescue and the like are `special`."""
    return _CATEGORY.get(kind, "special")


@dataclass(frozen=True, slots=True)
class Fix:
    """Where a ship is, from `locations`."""
    mmsi: int
    lat: float
    lon: float
    at: datetime
    speed_kn: float | None = None
    course_deg: float | None = None
    heading_deg: int | None = None
    nav_status: int | None = None


@dataclass(frozen=True, slots=True)
class Voyage:
    """What a ship says of itself, from `vessels`."""
    mmsi: int
    name: str = ""
    call_sign: str = ""
    imo: int | None = None
    ship_type: int | None = None
    length_m: int | None = None
    beam_m: int | None = None
    draught_m: float | None = None
    destination: str = ""
    eta: tuple[int, int, int, int] | None = None          # (month, day, hour, minute) as AIS gives it: no year, UTC


@dataclass(frozen=True, slots=True)
class Ship:
    """A ship as the map shows it: its fix, its voyage data (empty until `vessels` has named it) and how far it is from us."""
    fix: Fix
    voyage: Voyage
    distance_km: float

    @property
    def mmsi(self) -> int:
        return self.fix.mmsi

    @property
    def kind(self) -> str:
        return kind_of(self.voyage.ship_type)

    @property
    def bearing_deg(self) -> float | None:
        """Where the icon points: the heading (the bow), else the course of a ship that moves; None for a still ship with no heading."""
        if self.fix.heading_deg is not None:
            return float(self.fix.heading_deg)
        moving = self.fix.speed_kn is not None and self.fix.speed_kn >= MOVING_KN
        return self.fix.course_deg if moving else None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _whole(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _text(value: Any) -> str:
    """A text of AIS without the padding (`@` and spaces at the end) and the control characters."""
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value if c.isprintable()).replace("@", " ").strip()


def ship_mmsi(value: Any) -> int | None:
    """The MMSI of a ship: nine digits of a maritime identification of a country (2 to 7 first), or of a search and rescue aircraft (111); a base station, an aid to navigation or a craft that is none is no ship."""
    mmsi = _whole(value)
    if mmsi is None or not 100_000_000 <= mmsi <= 999_999_999:
        return None
    first = mmsi // 100_000_000
    return mmsi if 2 <= first <= 7 or mmsi // 1_000_000 == 111 else None


def _fix(feature: Any) -> Fix | None:
    if not isinstance(feature, dict):
        return None
    props, geometry = feature.get("properties"), feature.get("geometry")
    if not isinstance(props, dict) or not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    mmsi = ship_mmsi(props.get("mmsi", feature.get("mmsi")))
    millis = _number(props.get("timestampExternal"))
    if mmsi is None or millis is None or not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    lon, lat = _number(coordinates[0]), _number(coordinates[1])
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    speed, course, heading, status = _number(props.get("sog")), _number(props.get("cog")), _whole(props.get("heading")), _whole(props.get("navStat"))
    return Fix(mmsi, lat, lon, datetime.fromtimestamp(millis / 1000.0, UTC),
               speed if speed is not None and 0 <= speed < NO_SPEED_KN else None,
               course if course is not None and 0 <= course < NO_COURSE else None,
               heading if heading is not None and 0 <= heading < 360 else None,
               status if status in NAV_STATUSES else None)


def parse_locations(data: Any) -> list[Fix]:
    """The fixes of a `locations` answer (a FeatureCollection); a feature that is not a ship's or says no place is left out."""
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return []
    return [fix for fix in map(_fix, features) if fix is not None]


def eta_of(value: Any) -> tuple[int, int, int, int] | None:
    """The ETA of AIS, packed in one number (the month in bits 16 to 19, the day in 11 to 15, the hour in 6 to 10, the minute in 0 to 5), as (month, day, hour, minute); None when the month or the day is
    not given, or a value is out of its range (hour 24 and minute 60 are "not available")."""
    packed = _whole(value)
    if packed is None or packed <= 0:
        return None
    month, day, hour, minute = (packed >> 16) & 0xF, (packed >> 11) & 0x1F, (packed >> 6) & 0x1F, packed & 0x3F
    if not (1 <= month <= 12 and 1 <= day <= 31) or hour > 23 or minute > 59:
        return None
    return month, day, hour, minute


def eta_at(eta: tuple[int, int, int, int] | None, now: datetime) -> datetime | None:
    """The ETA as a time: in the year that puts it nearest to `now` (an ETA of January seen in December is next year's), None for a day that the year does not have."""
    if eta is None:
        return None
    month, day, hour, minute = eta
    best: datetime | None = None
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            when = datetime(year, month, day, hour, minute, tzinfo=UTC)
        except ValueError:
            continue
        if best is None or abs((when - now).total_seconds()) < abs((best - now).total_seconds()):
            best = when
    return best


def _size(a: Any, b: Any) -> int | None:
    """A length or a beam from the two distances to the reference point of the GPS; None when either is not given."""
    first, second = _whole(a), _whole(b)
    return first + second if first and second and first > 0 and second > 0 else None


def _voyage(item: Any) -> Voyage | None:
    if not isinstance(item, dict) or (mmsi := ship_mmsi(item.get("mmsi"))) is None:
        return None
    imo, ship_type, draught = _whole(item.get("imo")), _whole(item.get("shipType")), _number(item.get("draught"))
    return Voyage(mmsi, _text(item.get("name")), _text(item.get("callSign")), imo if imo is not None and imo > 0 else None, ship_type if ship_type is not None and ship_type > 0 else None,
                  _size(item.get("referencePointA"), item.get("referencePointB")), _size(item.get("referencePointC"), item.get("referencePointD")),
                  draught / 10.0 if draught is not None and draught > 0 else None, _text(item.get("destination")), eta_of(item.get("eta")))


def parse_vessels(data: Any) -> dict[int, Voyage]:
    """The voyage data of a `vessels` answer (a list) by MMSI; an entry that is not a ship's is left out."""
    if not isinstance(data, list):
        return {}
    return {voyage.mmsi: voyage for voyage in map(_voyage, data) if voyage is not None}


def ships_near(fixes: list[Fix], voyages: dict[int, Voyage], centre: tuple[float, float], radius_km: float, newer_than: datetime) -> dict[int, Ship]:
    """The ships of the fixes within `radius_km` of `centre` whose fix is newer than `newer_than`, each with its voyage data (an empty one when `vessels` has not named it yet)."""
    ships: dict[int, Ship] = {}
    for fix in fixes:
        if fix.at <= newer_than:
            continue
        km = distance_km(centre[0], centre[1], fix.lat, fix.lon)
        if km <= radius_km:
            ships[fix.mmsi] = Ship(fix, voyages.get(fix.mmsi) or Voyage(fix.mmsi), km)
    return ships
