"""The ALOHA circle of WB4APR: how far from our station the stations heard on RF would fill the channel, so that a packet sent for a station beyond it is a packet that cannot be received reliably.

The method is that of Bob Bruninga's text "The ALOHA Circle" (aprs.org, 7 November 2011), with the numbers in neoaprs/policy.py. Every station heard on RF lately gets the packets it is taken to send in 30 minutes by its kind
(a mobile station in motion 15, any other mobile 7, a weather station 6, a digipeater 3, any other 2). The stations are walked from the nearest to the farthest, each adding its packets times C to a total, where C starts at 1
and rises by one after each digipeater (everything farther away is repeated once more). The circle ends at the station where the total reaches 1800, the packets a 1200 baud channel carries in 30 minutes. If the stations heard
never reach that, the channel is not full and there is no circle.

Pure code: the stations are those of the station book, and the kinds are told by their symbols."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .geo import distance_km
from .policy import ALOHA_MOVING_KMH, ALOHA_PACKETS, ALOHA_WEIGHT_DIGI, ALOHA_WEIGHT_HOME, ALOHA_WEIGHT_MOBILE, ALOHA_WEIGHT_MOVING, ALOHA_WEIGHT_WEATHER, ALOHA_WINDOW_MIN
from .station import Station
from .symbols import is_mobile

Kind = Literal["moving", "mobile", "weather", "digi", "home"]
WEIGHTS: dict[Kind, int] = {"moving": ALOHA_WEIGHT_MOVING, "mobile": ALOHA_WEIGHT_MOBILE, "weather": ALOHA_WEIGHT_WEATHER, "digi": ALOHA_WEIGHT_DIGI, "home": ALOHA_WEIGHT_HOME}
DIGI_CODE = "#"                                 # the symbol of a digipeater, in the primary table and in the alternate one with any overlay
WEATHER_CODE = "_"


@dataclass(frozen=True)
class Circle:
    radius_km: float
    stations: int                               # how many stations are inside it (the one at its edge included)


def kind_of(station: Station) -> Kind:
    """What the station is taken to be, by its symbol (a weather report makes a weather station whatever the symbol) and its speed."""
    code = station.symbol_code
    if code == DIGI_CODE:
        return "digi"
    if code == WEATHER_CODE or station.weather is not None:
        return "weather"
    if is_mobile(station.symbol_table, code):
        return "moving" if (station.speed_kmh or 0.0) > ALOHA_MOVING_KMH else "mobile"
    return "home"


def counted(station: Station, since: datetime) -> bool:
    """A station of the air, not an object or an item, with a position, heard on RF since `since`. One whose latest packet an iGate put on the air from the internet is not on the channel from where it is."""
    return station.kind == "station" and not station.is_me and station.has_position and station.last_heard >= since and not station.last_via


def circle(position: tuple[float, float] | None, stations: list[Station], now: datetime) -> Circle | None:
    """The ALOHA circle round `position`, or None while the position is not known or the stations heard do not fill the channel."""
    if position is None:
        return None
    since = now - timedelta(minutes=ALOHA_WINDOW_MIN)
    near = sorted(((distance_km(*position, s.lat, s.lon), s.call, s) for s in stations if counted(s, since) and s.lat is not None and s.lon is not None), key=lambda t: (t[0], t[1]))
    total, copies = 0, 1
    for number, (km, _, station) in enumerate(near, 1):
        kind = kind_of(station)
        total += WEIGHTS[kind] * copies
        if kind == "digi":
            copies += 1
        if total >= ALOHA_PACKETS:
            return Circle(km, number) if km > 0 else None
    return None
