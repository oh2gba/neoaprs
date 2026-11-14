"""The aircraft of the open ADS-B feed of adsb.fi (`https://opendata.adsb.fi/api/v2/lat/LAT/lon/LON/dist/NM`, the JSON of readsb: `now` and a list `aircraft`), as values. Pure code: services/adsb.py asks for the
JSON and keeps the aircraft; nothing here is ever sent anywhere, the aircraft are only drawn on the map.

An aircraft is named by the ICAO address of its transponder (`hex`, six hex digits; a `~` in front is one that has none, made up by the ground station). The emitter category of ADS-B (A1 light ... A7
rotorcraft, B1 glider ...) is a `kind` that decides the icon; the surface vehicles and obstacles of an airport (C1 to C7) are left out, they are no aircraft."""
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from .geo import distance_km

NM_KM = 1.852
MAX_DIST_NM = 250                        # the most the feed answers for
KINDS = ("light", "small", "jet", "heavy", "rotor", "glider", "balloon", "drone", "other")
_KIND = {"A1": "light", "A2": "small", "A3": "jet", "A4": "jet", "A5": "heavy", "A6": "jet", "A7": "rotor", "B1": "glider", "B2": "balloon", "B4": "light", "B6": "drone"}
EMERGENCIES = frozenset({"general", "lifeguard", "minfuel", "nordo", "unlawful", "downed"})


def kind_of(category: str) -> str:
    """The icon of an aircraft, by its emitter category; `other` for one that gives none."""
    return _KIND.get(category, "other")


@dataclass(frozen=True, slots=True)
class Aircraft:
    """An aircraft as the map shows it."""
    hex: str                             # the ICAO address, lower case
    lat: float
    lon: float
    at: datetime                         # when its position was last received
    flight: str = ""                     # the call sign it flies under (FIN1336)
    registration: str = ""               # OH-LZR
    type_code: str = ""                  # A321
    description: str = ""                # AIRBUS A-321
    category: str = ""                   # A3
    altitude_ft: int | None = None       # the barometric altitude, else the geometric one; None on the ground and when not given
    on_ground: bool = False
    speed_kn: float | None = None        # the ground speed
    track_deg: float | None = None       # where it is going, else where it points
    vertical_fpm: int | None = None      # the rate of climb (negative: descent)
    squawk: str = ""
    emergency: str = ""                  # one of EMERGENCIES, else empty
    distance_km: float = 0.0

    @property
    def kind(self) -> str:
        return kind_of(self.category)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _whole(value: Any) -> int | None:
    number = _number(value)
    return round(number) if number is not None else None


def _text(value: Any, limit: int = 40) -> str:
    return "".join(c for c in value if c.isprintable()).strip()[:limit] if isinstance(value, str) else ""


def _altitude(item: dict[str, Any]) -> tuple[int | None, bool]:
    baro = item.get("alt_baro")
    if baro == "ground":
        return None, True
    altitude = _whole(baro)
    return (altitude if altitude is not None else _whole(item.get("alt_geom"))), False


def _aircraft(item: Any, now: datetime) -> Aircraft | None:
    if not isinstance(item, dict):
        return None
    address, category = _text(item.get("hex")).lower(), _text(item.get("category"))
    lat, lon, seen = _number(item.get("lat")), _number(item.get("lon")), _number(item.get("seen_pos"))
    if not address or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or category.startswith("C"):
        return None
    altitude, ground = _altitude(item)
    track = _number(item.get("track"))
    track = track if track is not None else _number(item.get("true_heading"))
    vertical = _whole(item.get("baro_rate"))
    emergency = _text(item.get("emergency"))
    return Aircraft(address, lat, lon, now - timedelta(seconds=max(seen or 0.0, 0.0)), _text(item.get("flight")), _text(item.get("r")), _text(item.get("t")), _text(item.get("desc")), category,
                    altitude, ground, _number(item.get("gs")), track % 360.0 if track is not None else None, vertical if vertical is not None else _whole(item.get("geom_rate")),
                    _text(item.get("squawk"), 4), emergency if emergency in EMERGENCIES else "")


def parse_aircraft(data: Any, received_at: datetime) -> list[Aircraft]:
    """The aircraft of an answer, each with where it was last received (`now` of the answer, else `received_at`, less how long ago the position was heard); one that gives no place, or is a vehicle of the
    airport, is left out."""
    if not isinstance(data, dict) or not isinstance(data.get("aircraft"), list):
        return []
    stamp = _number(data.get("now"))
    now = datetime.fromtimestamp(stamp, UTC) if stamp is not None and stamp > 0 else received_at
    return [one for one in (_aircraft(item, now) for item in data["aircraft"]) if one is not None]


def aircraft_near(found: list[Aircraft], centre: tuple[float, float], radius_km: float, newer_than: datetime) -> dict[str, Aircraft]:
    """The aircraft within `radius_km` of `centre` heard after `newer_than`, with how far each is, by the ICAO address."""
    near: dict[str, Aircraft] = {}
    for one in found:
        if one.at <= newer_than:
            continue
        km = distance_km(centre[0], centre[1], one.lat, one.lon)
        if km <= radius_km:
            near[one.hex] = replace(one, distance_km=km)
    return near


def feed_url(base: str, centre: tuple[float, float], radius_km: float) -> str:
    """The address of the aircraft within `radius_km` of `centre` (in whole nautical miles, at most MAX_DIST_NM)."""
    miles = max(1, min(MAX_DIST_NM, round(radius_km / NM_KM)))
    return f"{base.rstrip('/')}/lat/{centre[0]:.4f}/lon/{centre[1]:.4f}/dist/{miles}"
