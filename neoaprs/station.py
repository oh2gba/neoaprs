"""A station as the station book keeps it: identity, where and how it was heard, what it sent.

stationbook.py is the book of them.
"""

from collections.abc import Iterable
from dataclasses import KW_ONLY, dataclass, field, replace
from datetime import datetime
from typing import Any

from .aprsextension import Extensions
from .aprsfreq import Frequency
from .aprslocator import Locator
from .aprstelemetry import Telemetry
from .aprsstorm import Storm
from .aprsweather import Weather
from .geo import distance_km
from .hourcount import HourCount
from .packet import IS, Via
from .radiospec import NOT_HEARD, RadioHeard, RadioId
from .reach import Reach, RouteMark
from .route import Deliveries, Route

Track = list[tuple[datetime, float, float]]
TRACK_MAX = 50  # positions kept per station
# a new position goes on the track when the station moved more than this many metres
TRACK_MOVED_M = 10.0
TRACK_EVERY_SEC = 300.0  # or when this long has passed since the last one on it


def add_track_point(track: Track, when: datetime, lat: float, lon: float) -> None:
    """Add a position to the track if the station moved enough or enough time passed."""
    if track:
        last_time, last_lat, last_lon = track[-1]
        if (
            distance_km(last_lat, last_lon, lat, lon) * 1000.0 <= TRACK_MOVED_M
            and (when - last_time).total_seconds() < TRACK_EVERY_SEC
        ):
            return
    track.append((when, lat, lon))
    del track[:-TRACK_MAX]


@dataclass
class RadioPlace:
    """Where the latest packets that did not come from the internet put a station.

    Only a station also heard from the internet has one.
    """

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
    extensions: Extensions | None = None
    storm: Storm | None = None
    sign: str | None = None


@dataclass
class Station:
    call: str  # the call with its SSID, or the name of the object or item
    _: KW_ONLY
    first_heard: datetime
    last_heard: datetime
    kind: str = "station"  # "station", "object" or "item"
    reported_by: str = ""  # who sent the report, for an object or an item
    symbol_table: str = ""
    symbol_code: str = ""
    lat: float | None = None  # None until a position is heard
    lon: float | None = None
    altitude_m: float | None = None
    course_deg: int | None = None
    speed_kmh: float | None = None
    last_position_at: datetime | None = None
    last_status: str = ""
    last_comment: str = ""
    # packets = heard_rf + heard_rf_gated + heard_is + heard_dummy; `rf` is direct or digipeated,
    # `rf-gated` third-party via an iGate, `is` from APRS-IS, `dummy` from the Dummy radio
    packets: int = 0
    heard_rf: int = 0
    heard_rf_gated: int = 0
    heard_is: int = 0
    last_rf_at: datetime | None = None
    last_rf_gated_at: datetime | None = None
    last_is_at: datetime | None = None
    heard_dummy: int = 0
    last_dummy_at: datetime | None = None
    # what each radio heard of it; a radio that never heard it has no entry
    heard_by: dict[RadioId, RadioHeard] = field(default_factory=dict)
    snr: float | None = None
    rssi: float | None = None
    signal_at: datetime | None = None
    position_via: Via | None = None
    # path an object of ours is sent by, for a station no radio heard
    own_path: tuple[str, ...] = ()
    # the fields below are not cached: rebuilt from the packet log or weather log at start
    last_via: str = ""
    weather: Weather | None = None
    weather_at: datetime | None = None
    telemetry: Telemetry | None = None
    telemetry_at: datetime | None = None
    locator: Locator | None = None
    extensions: Extensions | None = None
    frequency: Frequency | None = None
    storm: Storm | None = None
    sign: str | None = None
    device: str = ""
    hour: HourCount = field(default_factory=HourCount, repr=False, compare=False)
    hour_is: HourCount = field(default_factory=HourCount, repr=False, compare=False)
    # where the packets not from the internet put it, once heard from the internet too
    radio: RadioPlace | None = field(default=None, repr=False, compare=False)
    sent_message: bool = False
    # whether its latest position says it takes messages; None until a position is heard
    position_messaging: bool | None = None
    track: Track = field(default_factory=list)
    is_me: bool = False
    own: bool = False
    gated: int = 0
    igate: bool = False
    # how its packets reached us on radios that may carry a path; HF has its own in `routes`
    deliveries: Deliveries = field(default_factory=Deliveries)
    routes: dict[RadioId, Deliveries] = field(default_factory=dict)
    internet_reach: Reach | None = None
    route_marks: tuple[RouteMark, ...] = ()

    def __post_init__(self) -> None:
        # its own dict (also for `dataclasses.replace`); a count of 0 means no entry
        self.heard_by = {radio: heard for radio, heard in self.heard_by.items() if heard.count > 0}

    def heard_on(self, radio: RadioId) -> RadioHeard:
        return self.heard_by.get(radio, NOT_HEARD)

    @property
    def last_radio(self) -> RadioId | None:
        """Return the radio that heard it last (lowest id on a tie); None if none did."""
        return self._latest_of(self.heard_by)

    def _latest_of(self, radios: Iterable[RadioId]) -> RadioId | None:
        found: RadioId | None = None
        latest: datetime | None = None
        for radio in sorted(radios):
            at = self.heard_by[radio].last_at
            if found is None or (at is not None and (latest is None or at > latest)):
                found, latest = radio, at
        return found

    def note_on(self, radio: RadioId, at: datetime, path: tuple[str, ...]) -> None:
        self.heard_by[radio] = RadioHeard(self.heard_on(radio).count + 1, at, path)

    def note_route(
        self,
        radio: RadioId,
        route: Route,
        count: int = 1,
        at: datetime | None = None,
        before: datetime | None = None,
        *,
        carries_path: bool = True,
    ) -> None:
        """Note `count` packets on the radio by the route; also `deliveries` if `carries_path`."""
        self.routes.setdefault(radio, Deliveries()).note(route, count, at, before)
        if carries_path:
            self.deliveries.note(route, count, at, before)

    def routes_on(self, radio: RadioId) -> Deliveries | None:
        return self.routes.get(radio)

    def seed_path(self, radio: RadioId, path: tuple[str, ...]) -> None:
        """Set the path of the latest packet the radio heard, as the database kept it."""
        if radio in self.heard_by:
            self._heard_as(radio, last_path=path)
        elif not self.heard_by:
            self.own_path = path

    def _heard_as(self, radio: RadioId, **changed: Any) -> None:
        after = replace(self.heard_on(radio), **changed)
        if after.count == 0:
            self.heard_by.pop(radio, None)
        else:
            self.heard_by[radio] = after

    @property
    def last_path(self) -> tuple[str, ...]:
        radio = self.last_radio
        return self.own_path if radio is None else self.heard_by[radio].last_path

    @last_path.setter
    def last_path(self, path: tuple[str, ...]) -> None:
        radio = self.last_radio
        if radio is None:
            self.own_path = path
        else:
            self._heard_as(radio, last_path=path)

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def last_on_air_at(self) -> datetime | None:
        """Return when a packet was last on the radio's channel (no third-party, no internet)."""
        times = [at for at in (self.last_rf_at, self.last_dummy_at) if at is not None]
        return max(times) if times else None

    @property
    def internet_only(self) -> bool:
        return self.heard_is > 0 and self.heard_rf == 0 and self.heard_rf_gated == 0 and self.heard_dummy == 0

    @property
    def can_message(self) -> bool:
        """Return whether a message to it can go out: a station, not us, not internet-only.

        A station whose position says it takes no messages can still be written to.
        """
        return self.kind == "station" and not self.is_me and not self.internet_only

    @property
    def may_not_message(self) -> bool:
        return self.kind == "station" and not self.sent_message and self.position_messaging is False

    @property
    def last_direct_at(self) -> datetime | None:
        return self.deliveries.last_direct_at

    @property
    def best_route(self) -> Route | None:
        return self.deliveries.best()

    def radio_view(self) -> "Station | None":
        """Return the station as the radio's packets alone show it; None if internet-only."""
        if self.internet_only:
            return None
        if self.heard_is == 0:
            return self
        heard = [at for at in (self.last_rf_at, self.last_rf_gated_at, self.last_dummy_at) if at is not None]
        view = replace(
            self,
            packets=self.packets - self.heard_is,
            heard_is=0,
            last_is_at=None,
            last_heard=max(heard) if heard else self.last_heard,
            hour=self.hour.without(self.hour_is),
            hour_is=HourCount(),
        )
        place = self.radio
        if place is not None:
            return replace(
                view,
                lat=place.lat,
                lon=place.lon,
                last_position_at=place.at,
                position_via=place.via,
                symbol_table=place.symbol_table,
                symbol_code=place.symbol_code,
                altitude_m=place.altitude_m,
                course_deg=place.course_deg,
                speed_kmh=place.speed_kmh,
                last_comment=place.comment,
                track=place.track,
                extensions=place.extensions,
                storm=place.storm,
                sign=place.sign,
            )
        if self.position_via == IS or self.position_via is None:
            return replace(
                view,
                lat=None,
                lon=None,
                last_position_at=None,
                position_via=None,
                altitude_m=None,
                course_deg=None,
                speed_kmh=None,
                track=[],
                symbol_table="",
                symbol_code="",
                last_comment="",
                extensions=None,
                storm=None,
                sign=None,
            )
        return view
