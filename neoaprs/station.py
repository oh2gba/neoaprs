"""A station as the station book keeps it: who it is, where it was heard, what it sent last and how its packets reached us (stationbook.py is the book of them)."""
from dataclasses import KW_ONLY, dataclass, field
from datetime import datetime

from .aprsextension import Extensions
from .aprslocator import Locator
from .aprstelemetry import Telemetry
from .aprsweather import Weather
from .hourcount import HourCount
from .route import Deliveries, Route

Track = list[tuple[datetime, float, float]]


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
    packets: int = 0
    last_path: tuple[str, ...] = ()
    last_via: str = ""                          # the iGate, when the latest packet came as a third-party packet (not kept in the cache: it is read again from the packets at the start)
    weather: Weather | None = None              # the latest observation of a weather station (not kept in the cache: it is read again from the weather log at the start)
    weather_at: datetime | None = None          # when it was heard
    telemetry: Telemetry | None = None          # the latest telemetry report (not kept in the cache: it is read again from the latest packets at the start)
    telemetry_at: datetime | None = None
    locator: Locator | None = None              # the Maidenhead locator of its latest status report (or Mic-E status text)
    extensions: Extensions | None = None        # PHG, RNG, DF and area data of its latest position
    device: str = ""                            # what it runs ("Kenwood TH-D74", "APRSdroid"), from the destination call or the Mic-E type code of its packets (device.py); empty when unknown (not kept in the cache: it is read again from the latest packets at the start)
    hour: HourCount = field(default_factory=HourCount, repr=False, compare=False)    # its packets of the last hour (not kept in the cache: counted from the packet log at the start and as packets come)
    sent_message: bool = False                  # it has sent a message or an ack to a station (overheard or not): it does messages (not kept in the cache: it is read again from the packet log at the start)
    position_messaging: bool | None = None      # its latest position says whether it takes messages (`=` and `@`, or Mic-E but the type code `'`); None until a position is heard (not kept in the cache either)
    track: Track = field(default_factory=list)  # (time, lat, lon), the latest TRACK_MAX positions, oldest first
    is_me: bool = False
    own: bool = False                           # an object or an item of ours, which we send (services/ownobjects.py): the settings' station is `is_me`, this is `own`; not kept in the cache, the objects of ours have a table of their own
    deliveries: Deliveries = field(default_factory=Deliveries)     # how the packets we heard from it reached us (neoaprs/route.py)

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def can_message(self) -> bool:
        """Whether a message to it makes sense. Never for an object or an item, and not for us. A station that has sent a message or an ack does messages, whatever its positions say; else its latest
        position says (`=` and `@` yes, `!` and `/` no, Mic-E yes unless its comment starts with the type code `'` of a radio without messaging); a station with neither is not hidden."""
        if self.kind != "station" or self.is_me:
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
