"""What the daemon's objects look like on the wire: the plain dicts (JSON-able) that `state` and `patch` carry, made from the station book, the packets, the messages, the message board,
the station preferences, the TNC and the settings. The models of the wire modules say what these are, and `Model.row(object, ...)` (neoaprs/web/wirebase.py) takes each field of the model
from the attribute of the object that has its name: what is written here is only what the object does not have as it is, the values that are worked out (a distance, the next time a thing
is sent, the route as text)."""
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from neoaprs.aprstelemetry import describe
from neoaprs.aprsweather import Weather
from neoaprs.bulletin import BulletinRecord
from neoaprs.chain import INTERNET, Attempt
from neoaprs.clock import iso
from neoaprs.config import DEFAULTS, Config
from neoaprs.geo import thinned
from neoaprs.gpsfix import Fix
from neoaprs.message import MessageRecord
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet
from neoaprs.packetcodec import encode_decoded, tnc2
from neoaprs.pref import Pref
from neoaprs.qrutext import Asked, Server
from neoaprs.smartbeacon import Reason, Sent
from neoaprs.route import digipeaters, heard_path, received_text, route_text, suggested_path
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.symbols import symbol_name
from neoaprs.tnc import Tnc
from neoaprs.weatherlog import Observation

from .bulletinwire import BulletinRow
from .gpswire import GpsState
from .igatewire import IgateState
from .messagewire import AttemptRow, MessageRow
from .ownwire import OwnBulletinRow, OwnObjectRow
from .packetwire import PacketRow
from .prefwire import StationPref
from .qruwire import QruAsked, QruGroup, QruServer, QruState
from .generalwire import GeneralAsked, GeneralState
from .stationwire import StationRow, TelemetryValues, WeatherValues
from .tncwire import TncState, TncStats

LINES_MAX = 100                     # lines of the TNC told to a page


def _routes(station: Station, now: datetime) -> dict[str, Any]:
    best = station.best_route
    heard = heard_path(station.deliveries, now)
    return {
        "last_route": received_text(station.last_path, station.last_via) if station.heard_rf or station.heard_rf_gated else "", "heard_direct": station.deliveries.direct,
        "heard_via": [[call, count] for call, count in station.deliveries.heard_via()], "best_route": "" if best is None else route_text(best),
        "suggested_path": None if best is None else suggested_path(best), "heard_path": None if heard is None else ",".join(heard),
    }


def weather_values(weather: Weather | None) -> dict[str, Any] | None:
    return None if weather is None else WeatherValues.row(weather)


def telemetry_values(book: StationBook, station: Station) -> dict[str, Any] | None:
    """The latest telemetry report of the station, scaled and named by the definitions its messages gave."""
    if station.telemetry is None:
        return None
    return TelemetryValues.row(describe(station.telemetry, book.telemetry_definition(station.call)))


def weather_points(observations: list[Observation]) -> list[list[Any]]:
    """[time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity] for each observation."""
    return [[iso(at), w.temp_c, w.pressure_hpa, w.wind_kmh, w.gust_kmh, w.rain_1h_mm, w.humidity] for at, w in observations]


REPLAY_METRES = 10                  # a point of a replay this near the one before it adds nothing that shows
REPLAY_SECONDS = 30                 # nor one this soon after it (a station heard by two digipeaters, or one that beacons fast)


def replay_tracks(found: list[tuple[str, datetime, float, float]]) -> dict[str, list[list[Any]]]:
    """The positions of the replay by station, [time, lat, lon] the oldest first, each station's thinned (neoaprs/geo.py) and to 5 decimals (about a metre)."""
    tracks: dict[str, list[tuple[datetime, float, float]]] = {}
    for station, at, lat, lon in found:
        tracks.setdefault(station, []).append((at, lat, lon))
    return {station: [[iso(at), round(lat, 5), round(lon, 5)] for at, lat, lon in thinned(points, REPLAY_METRES, REPLAY_SECONDS)] for station, points in tracks.items()}


def station_row(book: StationBook, station: Station) -> dict[str, Any]:
    distance = None if station.is_me else book.distance_km(station)
    bearing = None if station.is_me else book.bearing_deg(station)
    return StationRow.row(
        station, symbol_name=symbol_name(station.symbol_table, station.symbol_code) if station.symbol_code else "unknown", weather=weather_values(station.weather),
        telemetry=telemetry_values(book, station), packets_hour=station.hour.count(book.clock()), distance_km=None if distance is None else round(distance, 2), bearing_deg=None if bearing is None else round(bearing, 1), **_routes(station, book.clock()),
    )


def packet_row(number: int, packet: Packet) -> dict[str, Any]:
    route = received_text(packet.path, packet.gate) if packet.direction == "in" and packet.on_air else ""
    return PacketRow.row(packet, id=number, route=route, tnc2=tnc2(packet), decoded=json.loads(encode_decoded(packet.decoded)))


def attempt_rows(record: MessageRecord, attempts: tuple[Attempt, ...]) -> list[dict[str, Any]]:
    """The attempts of a message of ours as the page is told them; the one the ack answers is the latest sent before the ack was heard."""
    acked = next((a.number for a in reversed(attempts) if record.acked_at is not None and a.sent_at <= record.acked_at), None) if record.state == "acked" else None
    return [_attempt_row(a, a.number == acked) for a in attempts]


def _attempt_row(attempt: Attempt, acked: bool) -> dict[str, Any]:
    hops = [_hop_row(attempt, position, call) for position, call in enumerate(digipeaters(attempt.path), 1)]
    return AttemptRow.row(attempt, hops=hops, internet=next((s.call for s in attempt.seen if s.position == INTERNET), None), acked=acked)


def _hop_row(attempt: Attempt, position: int, call: str) -> dict[str, Any]:
    radio = next((s for s in attempt.seen if s.position == position and not s.via_internet), None)
    net = next((s for s in attempt.seen if s.position == position and s.via_internet), None)
    seen = radio or net
    return {"call": call if seen is None else seen.call, "heard": radio is not None, "heard_at": None if seen is None else iso(seen.heard_at), "by_internet": net is not None}


def message_row(record: MessageRecord, attempts: tuple[Attempt, ...] = (), queued: bool = False) -> dict[str, Any]:
    """The page's row of a message; `queued` (services/messaging.py, Messaging.queued) for one of ours that waits for another to the same station, which the database keeps as `sending`."""
    return MessageRow.row(record, attempts_detail=attempt_rows(record, attempts), state="queued" if queued else record.state)


def bulletin_row(record: BulletinRecord) -> dict[str, Any]:
    return BulletinRow.row(record)


def own_object_row(obj: OwnObject, next_at: datetime | None) -> dict[str, Any]:
    return OwnObjectRow.row(obj, state="live" if obj.alive else "killing", next_at=iso(next_at))


def own_bulletin_row(bulletin: OwnBulletin, next_at: datetime | None) -> dict[str, Any]:
    return OwnBulletinRow.row(bulletin, posted_at=iso(bulletin.created_at), next_at=iso(next_at))


def pref_row(pref: Pref) -> dict[str, Any]:
    return StationPref.row(pref, path=None if pref.path is None else ",".join(pref.path))


def tnc_state(tnc: Tnc) -> dict[str, Any]:
    lines = [{"at": iso(at), "text": text} for at, text in tnc.recent_lines(LINES_MAX)]
    return TncState.row(tnc, state=tnc.state.value, describe=tnc.describe(), dummy=tnc.is_dummy, stats=TncStats.row(tnc.stats), lines=lines)


def config_values(config: Config, urls: list[str], https: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"values": config.to_data(), "defaults": DEFAULTS.to_data(), "urls": urls, "https": https or {"on": False, "port": 0, "fingerprint": "", "problem": ""}}


class IgateSource(Protocol):
    """What the `igate` topic needs of the iGate service."""
    @property
    def state(self) -> str: ...
    @property
    def problem(self) -> str: ...
    @property
    def server_name(self) -> str: ...
    @property
    def gated(self) -> int: ...
    @property
    def dropped(self) -> Mapping[str, int]: ...
    @property
    def last_gated_at(self) -> datetime | None: ...


def igate_state(config: Config, igate: IgateSource) -> dict[str, Any]:
    """The `igate` topic: whether the iGate is connected and what it has gated and not gated."""
    return IgateState.row(None, enabled=config.igate_enabled, state=igate.state, server=igate.server_name, problem=igate.problem, gated=igate.gated, dropped=dict(igate.dropped),
                          last_gated_at=iso(igate.last_gated_at))


class GpsSource(Protocol):
    """What the `gps` topic needs of the GPS service."""
    @property
    def fix(self) -> Fix | None: ...
    @property
    def state(self) -> str: ...
    @property
    def problem(self) -> str: ...
    def current(self) -> Fix | None: ...


class MobilePlanSource(Protocol):
    """What the `gps` topic needs of the beacon's memory of its mobile beacons."""
    @property
    def last(self) -> Sent | None: ...
    @property
    def last_reason(self) -> Reason | None: ...


def gps_state(config: Config, gps: GpsSource, plan: MobilePlanSource, next_due: datetime | None) -> dict[str, Any]:
    """The `gps` topic: the latest fix and its state, and the moving station's beacon. `next_due` is the beacon's time of the next beacon, told only for a mobile station with a fresh fix."""
    fix, last = gps.fix, plan.last
    return GpsState.row(
        None, source=config.gps_source, state=gps.state, problem=gps.problem, lat=None if fix is None else fix.lat, lon=None if fix is None else fix.lon,
        altitude_m=None if fix is None else fix.altitude_m, speed_kmh=None if fix is None else fix.speed_kmh, course_deg=None if fix is None else fix.course_deg,
        satellites=None if fix is None else fix.satellites, fix_at=None if fix is None else iso(fix.at), mobile=config.mobile,
        next_beacon_at=iso(next_due) if config.mobile and gps.current() is not None else None,
        last_beacon_reason=plan.last_reason or "" if last is not None else "", last_beacon_at=None if last is None else iso(last.at))


class QruSource(Protocol):
    """What the `qru` topic needs of the QRU client (neoaprs/services/qruask.py)."""
    @property
    def asked(self) -> Asked | None: ...
    def servers(self) -> list[Server]: ...


class AskedAround(Protocol):
    """What the `general` topic needs of a general query sent (GeneralAsked of neoaprs/services/generalask.py)."""
    @property
    def kind(self) -> str: ...
    @property
    def query(self) -> str: ...
    @property
    def at(self) -> datetime: ...
    @property
    def path(self) -> tuple[str, ...]: ...
    @property
    def until(self) -> datetime: ...
    @property
    def new(self) -> tuple[str, ...]: ...


def general_state(asked: Sequence[AskedAround]) -> dict[str, Any]:
    """The `general` topic: the last general query of each kind and the stations heard after it."""
    return GeneralState.row(None, asked=[GeneralAsked.row(a) for a in asked])


def qru_state(qru: QruSource) -> dict[str, Any]:
    """The `qru` topic: the last request and the servers that answered it."""
    asked = qru.asked
    servers = [QruServer.row(s, groups=[QruGroup.row(None, name=name, count=count) for name, count in s.groups], sent_at=iso(s.sent_at), received=list(s.received), settles_at=iso(s.settles_at)) for s in qru.servers()]
    return QruState.row(None, asked=None if asked is None else QruAsked.row(asked), servers=servers)
