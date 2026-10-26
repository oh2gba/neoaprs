"""A station as the station book keeps it: who it is, where it was heard, what it sent last and how its packets reached us (stationbook.py is the book of them)."""
from dataclasses import KW_ONLY, dataclass, field, replace
from datetime import datetime

from .aprsextension import Extensions
from .aprsfreq import Frequency
from .aprslocator import Locator
from .aprstelemetry import Telemetry
from .aprsstorm import Storm
from .aprsweather import Weather
from .geo import distance_km
from .hourcount import HourCount
from .packet import IS, Via
from .route import Deliveries, Route

Track = list[tuple[datetime, float, float]]
TRACK_MAX = 50                      # positions kept per station
TRACK_MOVED_M = 10.0                # a new position goes on the track when the station moved more than this ...
TRACK_EVERY_SEC = 300.0             # ... or when this long has passed since the last one on it


def add_track_point(track: Track, when: datetime, lat: float, lon: float) -> None:
    """A position joins the track when the station moved more than TRACK_MOVED_M or TRACK_EVERY_SEC passed since the last one on it; the track keeps the latest TRACK_MAX."""
    if track:
        last_time, last_lat, last_lon = track[-1]
        if distance_km(last_lat, last_lon, lat, lon) * 1000.0 <= TRACK_MOVED_M and (when - last_time).total_seconds() < TRACK_EVERY_SEC:
            return
    track.append((when, lat, lon))
    del track[:-TRACK_MAX]


@dataclass
class RadioPlace:
    """Where a station was put by the latest packets that did not come from the internet, with the track of those: what its row shows while the internet stations are hidden. Only a station that has been heard
    from the internet too has one (for any other the station's own place is the radio's)."""
    lat: float
    lon: float
    at: datetime
    via: Via
    symbol_table: str = ""
    symbol_code: str = ""
    altitude_m: float | None = None
    course_deg: int | None = None
    speed_kmh: float | None = None
    comment: str = ""
    track: Track = field(default_factory=list)


@dataclass
class Station:
    call: str                                   # the call with its SSID, or the name of the object or item
    _: KW_ONLY
    first_heard: datetime
    last_heard: datetime
    kind: str = "station"                       # "station", "object" or "item"
    reported_by: str = ""                       # who sent the report, for an object or an item
    symbol_table: str = ""
    symbol_code: str = ""
    lat: float | None = None                    # None until a position is heard
    lon: float | None = None
    altitude_m: float | None = None
    course_deg: int | None = None
    speed_kmh: float | None = None
    last_position_at: datetime | None = None
    last_status: str = ""
    last_comment: str = ""
    packets: int = 0                            # all its packets, whatever the channel: heard_rf + heard_rf_gated + heard_is + heard_dummy
    heard_rf: int = 0                           # how many of them were heard on the radio, direct or by digipeaters (Packet.via `rf`)
    heard_rf_gated: int = 0                     # ... as third-party packets that an iGate put on the air (`rf-gated`)
    heard_is: int = 0                           # ... received from APRS-IS over the internet (`is`)
    last_rf_at: datetime | None = None          # when the latest of each kind was heard
    last_rf_gated_at: datetime | None = None
    last_is_at: datetime | None = None
    heard_dummy: int = 0                        # ... made up by the Dummy radio (`dummy`; they count as the air for everything but the internet)
    last_dummy_at: datetime | None = None
    position_via: Via | None = None             # the channel of the packet that gave the position (the latest one wins); None without a position and for our own station
    last_path: tuple[str, ...] = ()             # the digipeaters of the latest packet heard on the radio (an `is` packet came by no route)
    last_via: str = ""                          # the iGate, when the latest packet came as a third-party packet (not kept in the cache: it is read again from the packets at the start)
    weather: Weather | None = None              # the latest observation of a weather station (not kept in the cache: it is read again from the weather log at the start)
    weather_at: datetime | None = None          # when it was heard
    telemetry: Telemetry | None = None          # the latest telemetry report (not kept in the cache: it is read again from the latest packets at the start)
    telemetry_at: datetime | None = None
    locator: Locator | None = None              # the Maidenhead locator of its latest status report (or Mic-E status text)
    extensions: Extensions | None = None        # PHG, RNG, DF and area data of its latest position
    frequency: Frequency | None = None          # the voice frequency it gave last, in the comment of a position or an object, or in a status text (a position without one leaves it; an object or an item that says none has none); not kept in the cache: read again from the latest packets at the start
    storm: Storm | None = None                  # the storm data of its latest position (a storm object); not kept in the cache either
    sign: str | None = None                     # what the signpost it is says, from the comment of its latest position (`55`); not kept in the cache either
    device: str = ""                            # what it runs ("Kenwood TH-D74", "APRSdroid"), from the destination call or the Mic-E type code of its packets (device.py); empty when unknown (not kept in the cache: it is read again from the latest packets at the start)
    hour: HourCount = field(default_factory=HourCount, repr=False, compare=False)    # its packets of the last hour (not kept in the cache: counted from the packet log at the start and as packets come)
    hour_is: HourCount = field(default_factory=HourCount, repr=False, compare=False)    # ... those of them that came from the internet
    radio: RadioPlace | None = field(default=None, repr=False, compare=False)    # where the packets that were not from the internet put it, once it has been heard from the internet too (not kept in the cache: read again from the packets at the start)
    sent_message: bool = False                  # it has sent a message or an ack to a station (overheard or not): it does messages (not kept in the cache: it is read again from the packet log at the start)
    position_messaging: bool | None = None      # its latest position says whether it takes messages (`=` and `@`, or Mic-E but the type code `'`); None until a position is heard (not kept in the cache either)
    track: Track = field(default_factory=list)  # (time, lat, lon), the latest TRACK_MAX positions, oldest first
    is_me: bool = False
    own: bool = False                           # an object or an item of ours, which we send (services/ownobjects.py): the settings' station is `is_me`, this is `own`; not kept in the cache, the objects of ours have a table of their own
    gated: int = 0                              # how many third-party packets it put on the air that we heard (it is an iGate): counted from the packets heard in this run and the latest the database kept, and only while it is in the book; not the same as `deliveries.gated`, the packets of this station that a gate put on the air
    igate: bool = False                         # a capabilities packet of its own said `IGATE` (not kept in the cache: it is read again from the latest packets at the start)
    deliveries: Deliveries = field(default_factory=Deliveries)     # how the packets we heard from it reached us (neoaprs/route.py)

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def last_on_air_at(self) -> datetime | None:
        """When a packet of the station was last on the radio's channel, the Dummy radio's too (not a third-party packet, not one from the internet); None when none was."""
        times = [at for at in (self.last_rf_at, self.last_dummy_at) if at is not None]
        return max(times) if times else None

    @property
    def internet_only(self) -> bool:
        """Known from APRS-IS alone: packets were received over the internet and none was ever heard on the radio, not even as a third-party packet. Nothing that means "on the air near us" counts it."""
        return self.heard_is > 0 and self.heard_rf == 0 and self.heard_rf_gated == 0 and self.heard_dummy == 0

    @property
    def can_message(self) -> bool:
        """Whether a message to it makes sense. Never for an object or an item, not for us, and not for a station known only from the internet (this program sends nothing but by radio). A station that has sent a message or an ack does messages, whatever its positions say; else its latest
        position says (`=` and `@` yes, `!` and `/` no, Mic-E yes unless its comment starts with the type code `'` of a radio without messaging); a station with neither is not hidden."""
        if self.kind != "station" or self.is_me or self.internet_only:
            return False
        return self.sent_message or self.position_messaging is not False

    @property
    def last_direct_at(self) -> datetime | None:
        """When a packet of the station was last heard direct, from the packets counted (this run's and the latest the database kept); None for a station never heard direct."""
        return self.deliveries.last_direct_at

    @property
    def best_route(self) -> Route | None:
        """The route most of its packets came by (direct included); None until a packet is counted."""
        return self.deliveries.best()

    def radio_view(self) -> "Station | None":
        """The station as it is without the internet: None for one known only from there; for one heard both ways a copy that has only the radio's side (no packets, times, hour or position from the internet);
        a station never heard from the internet is itself. The status, the weather, the telemetry and the like are whatever the latest packet of any channel said."""
        if self.internet_only:
            return None
        if self.heard_is == 0:
            return self
        heard = [at for at in (self.last_rf_at, self.last_rf_gated_at, self.last_dummy_at) if at is not None]
        view = replace(self, packets=self.packets - self.heard_is, heard_is=0, last_is_at=None, last_heard=max(heard) if heard else self.last_heard, hour=self.hour.without(self.hour_is), hour_is=HourCount())
        place = self.radio
        if place is not None:
            return replace(view, lat=place.lat, lon=place.lon, last_position_at=place.at, position_via=place.via, symbol_table=place.symbol_table, symbol_code=place.symbol_code,
                           altitude_m=place.altitude_m, course_deg=place.course_deg, speed_kmh=place.speed_kmh, last_comment=place.comment, track=place.track)
        if self.position_via == IS or self.position_via is None:
            return replace(view, lat=None, lon=None, last_position_at=None, position_via=None, altitude_m=None, course_deg=None, speed_kmh=None, track=[])
        return view
