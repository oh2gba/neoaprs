"""The ships and aircraft of the map on the wire: the topics `ships` (by MMSI) and `aircraft` (by ICAO address), and `traffic`, the state of the two feeds that the Settings tab shows under their switches
(`ais/enabled`, `adsb/enabled`, in the topic `config` like the other settings). Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`. Only received: nothing of these is ever sent on the air."""
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import Field

from neoaprs.adsb import KINDS as AIRCRAFT_KINDS, Aircraft
from neoaprs.ais import CATEGORIES, KINDS as SHIP_KINDS, Ship, category_of, eta_at
from neoaprs.clock import iso

from .wirebase import Iso, _Model

ShipKind = Literal["cargo", "tanker", "passenger", "highspeed", "fishing", "sailing", "pleasure", "tug", "towing", "pilot", "sar", "military", "law", "dredging", "diving", "tender", "antipollution",
                   "medical", "wig", "other"]
ShipCategory = Literal["cargo", "tanker", "passenger", "highspeed", "fishing", "pleasure", "special", "other"]
AircraftKind = Literal["light", "small", "jet", "heavy", "rotor", "glider", "balloon", "drone", "other"]
FeedWord = Literal["off", "waiting", "connecting", "receiving", "failing"]
assert set(ShipKind.__args__) == set(SHIP_KINDS) and set(ShipCategory.__args__) == set(CATEGORIES) and set(AircraftKind.__args__) == set(AIRCRAFT_KINDS)      # type: ignore[attr-defined]


class ShipRow(_Model):
    """A ship of the AIS feed (Digitraffic): where it is and what it said of itself. A field AIS gives as "not available" is null (or empty)."""
    mmsi: int = Field(description="the Maritime Mobile Service Identity, nine digits")
    name: str = Field(description="the name it gives, in full; empty until its voyage data has come")
    call_sign: str = Field(description="its radio call sign (`OJAA`); empty when it gives none")
    imo: int | None = Field(description="its IMO number; null when it gives none")
    ship_type: int | None = Field(description="the ship type of AIS, two digits (70 to 79 cargo, 80 to 89 tanker ...); null when it gives none")
    kind: ShipKind = Field(description="what the ship is, by its type, for the words of the page")
    category: ShipCategory = Field(description="the group of kinds whose colour the map draws it in")
    lat: float
    lon: float
    speed_kn: float | None = Field(description="the speed over ground in knots")
    course_deg: float | None = Field(description="the course over ground")
    heading_deg: int | None = Field(description="where the bow points")
    bearing_deg: float | None = Field(description="where the icon points: the heading, else the course of a ship that moves; null for a still ship without a heading (a round icon)")
    nav_status: int | None = Field(description="the navigational status of AIS (0 under way using engine, 1 at anchor, 5 moored ...); null when it is not given or not defined")
    length_m: int | None
    beam_m: int | None
    draught_m: float | None
    destination: str = Field(description="the destination as the crew typed it")
    eta: Iso | None = Field(description="the estimated time of arrival (AIS gives no year: the nearest year to now)")
    position_at: Iso = Field(description="when the position was received")
    distance_km: float = Field(ge=0)

    @classmethod
    def of(cls, ship: Ship) -> dict[str, Any]:
        fix, voyage = ship.fix, ship.voyage
        return cls.row(None, mmsi=ship.mmsi, name=voyage.name, call_sign=voyage.call_sign, imo=voyage.imo, ship_type=voyage.ship_type, kind=ship.kind, category=category_of(ship.kind),
                       lat=fix.lat, lon=fix.lon, speed_kn=fix.speed_kn, course_deg=fix.course_deg, heading_deg=fix.heading_deg, bearing_deg=ship.bearing_deg, nav_status=fix.nav_status,
                       length_m=voyage.length_m, beam_m=voyage.beam_m, draught_m=voyage.draught_m, destination=voyage.destination, eta=iso(eta_at(voyage.eta, fix.at)),
                       position_at=iso(fix.at), distance_km=round(ship.distance_km, 1))


class AircraftRow(_Model):
    """An aircraft of the ADS-B feed (adsb.fi)."""
    hex: str = Field(description="the ICAO address of its transponder, six hex digits in lower case (a `~` in front: one made up by the ground station)")
    flight: str = Field(description="the call sign it flies under (`FIN1336`); empty when it gives none")
    registration: str = Field(description="`OH-LZR`; empty when unknown")
    type_code: str = Field(description="the ICAO type designator (`A321`); empty when unknown")
    description: str = Field(description="what the type is (`AIRBUS A-321`); empty when unknown")
    category: str = Field(description="the emitter category of ADS-B (`A3`); empty when it gives none")
    kind: AircraftKind = Field(description="the icon, by the category")
    lat: float
    lon: float
    altitude_ft: int | None = Field(description="the barometric altitude in feet, else the geometric one; null on the ground and when not given")
    on_ground: bool
    speed_kn: float | None = Field(description="the ground speed in knots")
    track_deg: float | None = Field(description="where it is going (the icon points this way)")
    vertical_fpm: int | None = Field(description="the rate of climb in feet a minute, negative in a descent")
    squawk: str
    emergency: str = Field(description="the emergency it declares (`general`, `lifeguard`, `minfuel`, `nordo`, `unlawful`, `downed`); empty for none")
    position_at: Iso = Field(description="when the position was last received")
    distance_km: float = Field(ge=0)

    @classmethod
    def of(cls, one: Aircraft) -> dict[str, Any]:
        return cls.row(one, kind=one.kind, position_at=iso(one.at), distance_km=round(one.distance_km, 1))


class FeedState(_Model):
    """One feed of the map's traffic."""
    enabled: bool = Field(description="its switch as in force")
    state: FeedWord = Field(description="`off`: the switch is off; `waiting`: there is no position to ask round (`problem` says so); `connecting`: the first answer has not come; `receiving`: the latest answer "
                                        "was read; `failing`: the latest question failed (`problem` says why), and it is asked again later")
    problem: str = Field(description="why it is waiting or failing, in the server's or the system's words; empty otherwise")
    count: int = Field(ge=0, description="how many it shows now")
    radius_km: float = Field(gt=0, description="how far round our position it reads")
    updated_at: Iso | None = Field(description="when the latest answer was read; null before the first")


class TrafficState(_Model):
    """The two feeds of the map's traffic, told whole as either changes."""
    ais: FeedState = Field(description="the ships (Digitraffic's AIS, `ais/enabled`)")
    adsb: FeedState = Field(description="the aircraft (adsb.fi's ADS-B, `adsb/enabled`)")


class FeedSource(Protocol):
    """What the topic `traffic` needs of a feed (services/trafficfeed.py)."""
    @property
    def enabled(self) -> bool: ...
    @property
    def word(self) -> str: ...
    @property
    def problem(self) -> str: ...
    @property
    def updated_at(self) -> datetime | None: ...
    @property
    def radius_km(self) -> float: ...
    def __len__(self) -> int: ...


def feed_state(feed: FeedSource) -> dict[str, Any]:
    return FeedState.row(None, enabled=feed.enabled, state=feed.word, problem=feed.problem, count=len(feed), radius_km=feed.radius_km, updated_at=iso(feed.updated_at))


def traffic_state(ships: FeedSource, aircraft: FeedSource) -> dict[str, Any]:
    """The topic `traffic`."""
    return TrafficState.row(None, ais=feed_state(ships), adsb=feed_state(aircraft))
