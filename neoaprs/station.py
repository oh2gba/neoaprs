"""A station as the station book keeps it: who it is, where it was heard, what it sent last and how its packets reached us (stationbook.py is the book of them)."""
from collections.abc import Iterable
from dataclasses import KW_ONLY, dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .aprsextension import Extensions
from .aprsfreq import Frequency
from .aprslocator import Locator
from .aprstelemetry import Telemetry
from .aprsstorm import Storm
from .aprsweather import Weather
from .geo import distance_km
from .hourcount import HourCount
from .packet import IS, Via
from .radiospec import FM_ID, HF_ID, NOT_HEARD, RadioHeard, RadioId
from .reach import Reach, RouteMark
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
    extensions: Extensions | None = None
    storm: Storm | None = None
    sign: str | None = None


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
    heard_by: dict[RadioId, RadioHeard] = field(default_factory=dict)      # what each radio heard of it (rule 3.3), by the radio's id: how many of the packets of the air (rf, rf-gated and dummy alike) came on it, when the latest did and by which digipeaters; a radio that never heard it has no entry
    snr: float | None = None                    # the last reading of its signal (neoaprs/reading.py): the SNR in dB and the RSSI in dBm of the latest packet heard direct from it that had one (not by a digipeater,
    rssi: float | None = None                   # not as a third-party packet: those are another station's signal), each None when that packet's radio gave none
    signal_at: datetime | None = None           # when that packet was heard; None until one was
    position_via: Via | None = None             # the channel of the packet that gave the position (the latest one wins); None without a position and for our own station
    own_path: tuple[str, ...] = ()              # the digipeaters of a station that no radio heard: those an object of ours is sent by (the path of a packet that was heard is its radio's, in `heard_by`)
    latest_path: tuple[str, ...] | None = field(default=None, repr=False, compare=False)   # the digipeaters of the packet noted last in this run whatever its time (a clock that stepped back, a tie), and after a restart the path of the latest route the database kept for a station radio 2 heard last (its packets are no route): what `last_path` says while it is set, as before the radios were by id; not kept in the cache (R2 deletes it with the HF exception)
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
    message_radio: str = ""                     # the radio the operator chose for messages to it while both are on (`fm`, `hf`), "" for the daemon's choice (radios.py); kept in the state row MESSAGE_RADIOS, not in the cache
    position_messaging: bool | None = None      # its latest position says whether it takes messages (`=` and `@`, or Mic-E but the type code `'`); None until a position is heard (not kept in the cache either)
    track: Track = field(default_factory=list)  # (time, lat, lon), the latest TRACK_MAX positions, oldest first
    is_me: bool = False
    own: bool = False                           # an object or an item of ours, which we send (services/ownobjects.py): the settings' station is `is_me`, this is `own`; not kept in the cache, the objects of ours have a table of their own
    gated: int = 0                              # how many third-party packets it put on the air that we heard (it is an iGate): counted from the packets heard in this run and the latest the database kept, and only while it is in the book; not the same as `deliveries.gated`, the packets of this station that a gate put on the air
    igate: bool = False                         # a capabilities packet of its own said `IGATE` (not kept in the cache: it is read again from the latest packets at the start)
    deliveries: Deliveries = field(default_factory=Deliveries)     # how the packets we heard from it reached us (neoaprs/route.py)
    internet_reach: Reach | None = None         # how its latest internet packet got there: heard by an iGate, or sent from an app (neoaprs/reach.py; not kept in the cache: it is read again from the latest packets at the start)
    route_marks: tuple[RouteMark, ...] = ()     # the route of its latest packet and the one before it that came another way, any channel, newest first, for the map (not kept in the cache either)

    def heard_on(self, radio: RadioId) -> RadioHeard:
        """What the radio heard of it; nothing (a count of 0) for a radio that never heard it."""
        return self.heard_by.get(radio, NOT_HEARD)

    @property
    def last_radio(self) -> RadioId | None:
        """The radio that heard it last: the one with the latest time, the lowest id among equals (radio 1 on a tie; an entry without a time is before any time); None when no radio heard it."""
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
        """A packet of it came on the radio at `at` by the digipeaters `path`: one more for that radio, which heard it last now, and its path is the station's latest."""
        self.heard_by[radio] = RadioHeard(self.heard_on(radio).count + 1, at, path)
        self.latest_path = path

    def seed_route_path(self, path: tuple[str, ...]) -> None:
        """The path of the latest route the database kept of it (the routes leave out the packets of radio 2, the HF radio of today): the path of the latest packet of the radio that heard it last; while
        radio 2 heard it last, the path of the latest of the other radios, and what `last_path` says until the next packet, as before the radios were by id."""
        if self.last_radio != HF_ID:
            self.last_path = path
            return
        other = self._latest_of(radio for radio in self.heard_by if radio != HF_ID)
        if other is not None:
            self._heard_as(other, last_path=path)
        self.latest_path = path

    def _heard_as(self, radio: RadioId, **changed: Any) -> None:
        """What the radio heard of it as `changed` says; a radio with a count of 0 heard nothing and has no entry (the time or the path of such a radio is dropped with it)."""
        after = replace(self.heard_on(radio), **changed)
        if after.count == 0:
            self.heard_by.pop(radio, None)
        else:
            self.heard_by[radio] = after

    # ---- the old names, until W3: the counts and times of radio 1 (`fm`) and radio 2 (`hf`), and the one path of the latest packet, as views of `heard_by` that are read, set and taken by the constructor
    if TYPE_CHECKING:                           # (what a type checker is told of them; in the running program they are the properties below, no fields)
        heard_fm: int = 0
        heard_hf: int = 0
        last_fm_at: datetime | None = None
        last_hf_at: datetime | None = None
        last_path: tuple[str, ...] = ()
    else:
        heard_fm = property(lambda self: self.heard_on(FM_ID).count, lambda self, count: self._heard_as(FM_ID, count=count))
        heard_hf = property(lambda self: self.heard_on(HF_ID).count, lambda self, count: self._heard_as(HF_ID, count=count))
        last_fm_at = property(lambda self: self.heard_on(FM_ID).last_at, lambda self, at: self._heard_as(FM_ID, last_at=at))
        last_hf_at = property(lambda self: self.heard_on(HF_ID).last_at, lambda self, at: self._heard_as(HF_ID, last_at=at))

        @property
        def last_path(self) -> tuple[str, ...]:
            """The digipeaters of the latest packet heard on a radio (an `is` packet came by no route): those of the packet noted last in this run (`latest_path`), else those of the radio that heard it
            last; of a station no radio heard, `own_path`."""
            if self.latest_path is not None:
                return self.latest_path
            radio = self.last_radio
            return self.own_path if radio is None else self.heard_by[radio].last_path

        @last_path.setter
        def last_path(self, path: tuple[str, ...]) -> None:
            self.latest_path = None
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
        """When a packet of the station was last on the radio's channel, the Dummy radio's too (not a third-party packet, not one from the internet); None when none was."""
        times = [at for at in (self.last_rf_at, self.last_dummy_at) if at is not None]
        return max(times) if times else None

    @property
    def internet_only(self) -> bool:
        """Known from APRS-IS alone: packets were received over the internet and none was ever heard on the radio, not even as a third-party packet. Nothing that means "on the air near us" counts it."""
        return self.heard_is > 0 and self.heard_rf == 0 and self.heard_rf_gated == 0 and self.heard_dummy == 0

    @property
    def can_message(self) -> bool:
        """Whether a message to it can go out: never to an object or an item, not to us, and not to a station known only from the internet (this program sends nothing but by radio). A station whose position
        says it takes no messages can still be written to (the operator knows better than the position: John, 4 Nov 2026); `may_not_message` says so beside the conversation."""
        return self.kind == "station" and not self.is_me and not self.internet_only

    @property
    def may_not_message(self) -> bool:
        """Its latest position says it takes no messages (`!` and `/`, or Mic-E with the type code `'` of a radio without messaging) and it has never sent a message or an ack: a message may not be read there.
        A station that has sent one does messages, whatever its position says."""
        return self.kind == "station" and not self.sent_message and self.position_messaging is False

    @property
    def last_direct_at(self) -> datetime | None:
        """When a packet of the station was last heard direct, from the packets counted (this run's and the latest the database kept); None for a station never heard direct."""
        return self.deliveries.last_direct_at

    @property
    def best_route(self) -> Route | None:
        """The route most of its packets came by (direct included); None until a packet is counted."""
        return self.deliveries.best()

    def radio_view(self) -> "Station | None":
        """The station as it is without the internet: None for one known only from there; for one heard both ways the copy a book that was given only the radio's packets would hold (no packets, times, hour or position
        from the internet, and what a position says besides where it is: the symbol, the comment, the extensions, the storm data and the sign); a station never heard from the internet is itself. The status, the weather,
        the telemetry, the frequency, the locator and the like are whatever the latest packet of any channel said."""
        if self.internet_only:
            return None
        if self.heard_is == 0:
            return self
        heard = [at for at in (self.last_rf_at, self.last_rf_gated_at, self.last_dummy_at) if at is not None]
        view = replace(self, packets=self.packets - self.heard_is, heard_is=0, last_is_at=None, last_heard=max(heard) if heard else self.last_heard, hour=self.hour.without(self.hour_is), hour_is=HourCount())
        place = self.radio
        if place is not None:
            return replace(view, lat=place.lat, lon=place.lon, last_position_at=place.at, position_via=place.via, symbol_table=place.symbol_table, symbol_code=place.symbol_code,
                           altitude_m=place.altitude_m, course_deg=place.course_deg, speed_kmh=place.speed_kmh, last_comment=place.comment, track=place.track, extensions=place.extensions, storm=place.storm, sign=place.sign)
        if self.position_via == IS or self.position_via is None:
            return replace(view, lat=None, lon=None, last_position_at=None, position_via=None, altitude_m=None, course_deg=None, speed_kmh=None, track=[],
                           symbol_table="", symbol_code="", last_comment="", extensions=None, storm=None, sign=None)
        return view


OLD_NAMES = ("heard_fm", "heard_hf", "last_fm_at", "last_hf_at", "last_path")       # in the order they are set: the counts and the times, then the path, which goes with the radio that heard last
_made = Station.__init__


def _init(self: Station, *args: Any, **values: Any) -> None:
    """The constructor still takes the old names beside `heard_by` (`dataclasses.replace` too, which goes through it): each is set through its view, over a `heard_by` that is the new station's own dict."""
    old = [(name, values.pop(name)) for name in OLD_NAMES if name in values]
    values["heard_by"] = {radio: heard for radio, heard in (values.get("heard_by") or {}).items() if heard.count > 0}     # (a radio with a count of 0 heard nothing: no entry)
    _made(self, *args, **values)
    for name, value in old:
        setattr(self, name, value)


Station.__init__ = _init                        # type: ignore[method-assign]
