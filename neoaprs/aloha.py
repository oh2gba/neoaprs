"""The ALOHA circle: how far out the stations heard on RF would fill a 1200 baud channel.

Method of "The ALOHA Circle" (aprs.org), weights in policy.py: walking outward, each station adds
its kind's packets in 30 minutes times C (plus one per digipeater); the circle ends at 1800.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .geo import distance_km
from .policy import ALOHA_MOVING_KMH, ALOHA_PACKETS, ALOHA_WEIGHT_DIGI, ALOHA_WEIGHT_HOME, ALOHA_WEIGHT_MOBILE, ALOHA_WEIGHT_MOVING, ALOHA_WEIGHT_WEATHER, ALOHA_WINDOW_MIN
from .radiospec import RadioId
from .station import Station
from .symbols import is_mobile

Kind = Literal["moving", "mobile", "weather", "digi", "home"]
WEIGHTS: dict[Kind, int] = {"moving": ALOHA_WEIGHT_MOVING, "mobile": ALOHA_WEIGHT_MOBILE, "weather": ALOHA_WEIGHT_WEATHER, "digi": ALOHA_WEIGHT_DIGI, "home": ALOHA_WEIGHT_HOME}
# digipeater symbol, in the primary table and in the alternate one with any overlay
DIGI_CODE = "#"
WEATHER_CODE = "_"


@dataclass(frozen=True)
class Circle:
    radius_km: float
    stations: int  # stations inside the circle, including the one at its edge


def kind_of(station: Station) -> Kind:
    """Return the station's kind from its symbol and speed (a weather report means weather)."""
    code = station.symbol_code
    if code == DIGI_CODE:
        return "digi"
    if code == WEATHER_CODE or station.weather is not None:
        return "weather"
    if is_mobile(station.symbol_table, code):
        return "moving" if (station.speed_kmh or 0.0) > ALOHA_MOVING_KMH else "mobile"
    return "home"


def counted(station: Station, since: datetime, radio: RadioId | None = None) -> bool:
    """A station (not an object or item) with a position heard on RF since `since`.

    An iGate's third-party or APRS-IS packet does not show the station is on the channel.
    """
    if station.kind != "station" or station.is_me or not station.has_position or station.last_on_air_at is None or station.last_on_air_at < since:
        return False
    last = None if radio is None else on_channel_at(station, radio)
    return radio is None or (last is not None and last >= since)


def on_channel_at(station: Station, radio: RadioId) -> datetime | None:
    """Return when `radio` last heard a packet the station itself sent (not a third-party one).

    A station with no known routes uses any time heard.
    """
    routes = station.routes_on(radio)
    if routes is None:
        return station.heard_on(radio).last_at
    return max((kept[-1] for kept in routes.times.values() if kept), default=None)


def circle(position: tuple[float, float] | None, stations: list[Station], now: datetime, radio: RadioId | None = None) -> Circle | None:
    """Return the ALOHA circle around `position` for `radio` (every station of the air if None).

    None while the position is unknown or the stations heard do not fill the channel.
    """
    if position is None:
        return None
    since = now - timedelta(minutes=ALOHA_WINDOW_MIN)
    near = sorted(((distance_km(*position, s.lat, s.lon), s.call, s) for s in stations if counted(s, since, radio) and s.lat is not None and s.lon is not None), key=lambda t: (t[0], t[1]))
    total, copies = 0, 1
    for number, (km, _, station) in enumerate(near, 1):
        kind = kind_of(station)
        total += WEIGHTS[kind] * copies
        if kind == "digi":
            copies += 1
        if total >= ALOHA_PACKETS:
            return Circle(km, number) if km > 0 else None
    return None
