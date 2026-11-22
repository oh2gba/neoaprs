"""Plain JSON-able dicts for the `state` and `patch` messages, built from the daemon's objects.

`Model.row(object, ...)` (wirebase.py) takes each wire field from the same-named attribute;
only the values that must be worked out are written here.
"""

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from neoaprs.aprstelemetry import describe
from neoaprs.aprsweather import Weather
from neoaprs.bulletin import BulletinRecord
from neoaprs.chain import AT_GATE, Attempt
from neoaprs.clock import iso
from neoaprs.config import DEFAULTS, EMAIL_RADIO, KEYS, RADIO_STATION_KEYS, STATION_KEYS, Config
from neoaprs.geo import Point
from neoaprs.gpsfix import Fix
from neoaprs.mercury import MAX_PAYLOAD, MODE
from neoaprs.direwolfmodem import DirewolfModem
from neoaprs.mercurymodem import Mercury
from neoaprs.message import MessageRecord
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownobject import OwnObject
from neoaprs.pairsetting import pair_defaults, pair_values
from neoaprs.packet import Packet
from neoaprs.packetcodec import encode_decoded, tnc2
from neoaprs.pref import Fired, Pref
from neoaprs.qrutext import Asked, Server
from neoaprs.radiotype import RadioId
from neoaprs.radiotypes import kind_fields
from neoaprs.smartbeacon import Reason, Sent
from neoaprs.route import digipeaters, heard_path, received_text, route_text, suggested_path
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.tnc import Tnc
from neoaprs.weatherlog import Observation

from .bulletinwire import BulletinRow
from .gpswire import GpsState
from .igatewire import IgateState
from .messagewire import AttemptRow, MessageRow, StationKey
from .ownwire import OwnBulletinRow, OwnObjectRow
from .packetwire import PacketRow
from .prefwire import StationAlertMsg, StationPref
from .qruwire import QruAsked, QruGroup, QruServer, QruState
from .generalwire import GeneralAsked, GeneralSent, GeneralState
from .secureside import SecureState
from .stationwire import StationRow, TelemetryValues, WeatherValues
from .tncwire import ModemState
from .wirebase import HISTORY_MAX_HOURS

LINES_MAX = 100  # recent lines of a radio's line sent to a page
# Keys of `config.values` in the form's order.
CONFIG_KEYS = tuple(
    key for key in KEYS if (key in STATION_KEYS or key == "serial/last_port") and key not in RADIO_STATION_KEYS
)


def _routes(station: Station, now: datetime) -> dict[str, Any]:
    best = station.best_route
    heard = heard_path(station.deliveries, now)
    return {
        "last_route": received_text(station.last_path, station.last_via)
        if station.heard_rf or station.heard_rf_gated
        else "",
        "heard_direct": station.deliveries.direct,
        "heard_via": [[call, count] for call, count in station.deliveries.heard_via()],
        "best_route": "" if best is None else route_text(best),
        "suggested_path": None if best is None else suggested_path(best),
        "heard_path": None if heard is None else ",".join(heard),
    }


def weather_values(weather: Weather | None) -> dict[str, Any] | None:
    return None if weather is None else WeatherValues.row(weather)


def telemetry_values(book: StationBook, station: Station) -> dict[str, Any] | None:
    """Return the latest telemetry report scaled and named by the station's definition messages."""
    if station.telemetry is None:
        return None
    return TelemetryValues.row(describe(station.telemetry, book.telemetry_definition(station.call)))


def weather_points(observations: list[Observation]) -> list[list[Any]]:
    """Return one row per observation.

    Each row is [time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity].
    """
    return [
        [iso(at), w.temp_c, w.pressure_hpa, w.wind_kmh, w.gust_kmh, w.rain_1h_mm, w.humidity] for at, w in observations
    ]


# Replay thinning (geo.py) by span: (up to this many hours, metres, seconds). A nearer or sooner
# point is dropped; a week of a busy feed stays a few hundred KB. Steps stay inside GLIDE_MAX_MIN
# of replaywire.py (a test holds them to it).
REPLAY_THINNING = ((24, 10, 30), (3 * 24, 200, 120), (HISTORY_MAX_HOURS, 300, 300))


def replay_thinning(hours: int) -> tuple[int, int]:
    """Return the (metres, seconds) thinning for a replay of `hours` hours."""
    for upto, metres, seconds in REPLAY_THINNING:
        if hours <= upto:
            return metres, seconds
    return REPLAY_THINNING[-1][1:]


def replay_tracks(tracks: Mapping[str, Sequence[Point]]) -> dict[str, list[list[Any]]]:
    """Return the replay positions by station as [time, lat, lon], oldest first, rounded to 1 m."""
    return {
        station: [[iso(at), round(lat, 5), round(lon, 5)] for at, lat, lon in points]
        for station, points in tracks.items()
    }


@dataclass(frozen=True)
class StationRadios:
    """Per-call radio facts for a station's row: choice, radio now, paths and reply paths."""

    choice: Callable[[str], RadioId | None] = lambda call: None
    now: Callable[[str], RadioId | None] = lambda call: None
    paths: Callable[[str], Mapping[RadioId, tuple[str, ...]]] = lambda call: {}
    replies: Callable[[str], Mapping[RadioId, tuple[str, ...]]] = lambda call: {}


NO_RADIOS = StationRadios()


def _radio_fields(station: Station, radios: StationRadios) -> dict[str, Any]:
    direct = [at for at in (r.last_direct_at for r in station.routes.values()) if at is not None]
    return {
        "heard": {str(id): {"count": h.count, "last_at": iso(h.last_at)} for id, h in sorted(station.heard_by.items())},
        "last_path_radio": station.last_radio,
        "last_direct_any_at": iso(max(direct)) if direct else None,
        "radio_choice": radios.choice(station.call),
        "radio_now": radios.now(station.call) if station.can_message else None,
        "paths": {str(id): ",".join(path) for id, path in sorted(radios.paths(station.call).items())},
        "replies": {str(id): ",".join(path) for id, path in sorted(radios.replies(station.call).items()) if path},
    }


def station_row(book: StationBook, station: Station, radios: StationRadios = NO_RADIOS) -> dict[str, Any]:
    distance = None if station.is_me else book.distance_km(station)
    bearing = None if station.is_me else book.bearing_deg(station)
    return StationRow.row(
        station,
        weather=weather_values(station.weather),
        telemetry=telemetry_values(book, station),
        packets_hour=station.hour.count(book.clock()),
        distance_km=None if distance is None else round(distance, 2),
        bearing_deg=None if bearing is None else round(bearing, 1),
        **_routes(station, book.clock()),
        **_radio_fields(station, radios),
    )


def packet_row(number: int, packet: Packet) -> dict[str, Any]:
    route = received_text(packet.path, packet.gate) if packet.direction == "in" and packet.on_air else ""
    return PacketRow.row(
        packet,
        id=number,
        route=route,
        tnc2=tnc2(packet),
        decoded=_wire_decoded(json.loads(encode_decoded(packet.decoded))),
    )


def _wire_decoded(decoded: dict[str, Any]) -> dict[str, Any]:
    """Return the decoded packet for the page.

    An undecoded one loses the parser's English message, keeping the code.
    """
    return {k: v for k, v in decoded.items() if k != "error"} if decoded.get("type") == "undecoded" else decoded


def attempt_rows(record: MessageRecord, attempts: tuple[Attempt, ...]) -> list[dict[str, Any]]:
    """Return the attempt rows of a message of ours.

    The acked one is the latest sent before the ack was heard.
    """
    acked = (
        next(
            (a.number for a in reversed(attempts) if record.acked_at is not None and a.sent_at <= record.acked_at), None
        )
        if record.state == "acked"
        else None
    )
    return [_attempt_row(a, a.number == acked) for a in attempts]


def _attempt_row(attempt: Attempt, acked: bool) -> dict[str, Any]:
    hops = [_hop_row(attempt, position, call) for position, call in enumerate(digipeaters(attempt.path), 1)]
    return AttemptRow.row(
        attempt, hops=hops, internet=next((s.call for s in attempt.seen if s.position == AT_GATE), None), acked=acked
    )


def _hop_row(attempt: Attempt, position: int, call: str) -> dict[str, Any]:
    radio = next((s for s in attempt.seen if s.position == position and not s.via_internet), None)
    net = next((s for s in attempt.seen if s.position == position and s.via_internet), None)
    seen = radio or net
    return {
        "call": call if seen is None else seen.call,
        "heard": radio is not None,
        "heard_at": None if seen is None else iso(seen.heard_at),
        "by_internet": net is not None,
    }


def message_row(
    record: MessageRecord, attempts: tuple[Attempt, ...] = (), queued: bool = False, radio_now: RadioId | None = None
) -> dict[str, Any]:
    """Return the page's row of a message.

    `queued` marks one waiting for another to the same station (stored as `sending`).
    """
    on_its_way = record.direction == "out" and record.state == "sending"
    return MessageRow.row(
        record,
        attempts_detail=attempt_rows(record, attempts),
        state="queued" if queued else record.state,
        radio_now=radio_now if on_its_way else None,
    )


def on_their_way(records: Iterable[MessageRecord], call: str | None = None) -> list[str]:
    """Return the keys of our messages on their way (to `call`, or any).

    Their `radio_now` follows the radio settings.
    """
    return [
        str(r.id)
        for r in records
        if r.direction == "out" and r.state == "sending" and (call is None or r.to_call == call)
    ]


def bulletin_row(record: BulletinRecord) -> dict[str, Any]:
    return BulletinRow.row(record)


def own_object_row(obj: OwnObject, next_at: datetime | None) -> dict[str, Any]:
    return OwnObjectRow.row(
        obj, state="live" if obj.alive else "killing", next_at=iso(next_at), radios=list(obj.radios)
    )


def own_bulletin_row(bulletin: OwnBulletin, next_at: datetime | None) -> dict[str, Any]:
    return OwnBulletinRow.row(
        bulletin, posted_at=iso(bulletin.created_at), next_at=iso(next_at), radios=list(bulletin.radios)
    )


def key_row(fingerprint: str, heard_at: datetime) -> dict[str, Any]:
    """Return the page's entry of a station's key."""
    return StationKey.row(None, fingerprint=fingerprint, heard_at=iso(heard_at))


def pref_row(pref: Pref) -> dict[str, Any]:
    return StationPref.row(pref, path=None if pref.path is None else ",".join(pref.path))


def station_alert_message(fired: Fired) -> dict[str, Any]:
    return StationAlertMsg.row(fired, type="station_alert")


def modem_state(tnc: Tnc) -> dict[str, Any] | None:
    """Return the state of the modem behind the line (Mercury or Direwolf).

    None if the radio type has no modem.
    """
    modem = tnc.modem
    if modem is None or tnc.profile.transport != "modem":
        return None
    if isinstance(modem, DirewolfModem):
        return ModemState.row(None, **modem.wire())
    if not isinstance(modem, Mercury):
        return None
    return ModemState.row(
        modem,
        mode=MODE,
        max_frame=MAX_PAYLOAD,
        frequencies=[{"band": f.band, "dial": f.dial} for f in modem.frequencies],
        keying=modem.keying.text,
        rx_level=None,
    )


def config_values(config: Config, urls: list[str], https: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the topic `config`: station settings in `values`, radio-related ones in `radio_values`."""
    values, defaults = config.to_data(), DEFAULTS.to_data()
    values, defaults = (
        {k: v for k, v in values.items() if k in CONFIG_KEYS or k in RADIO_STATION_KEYS},
        {k: v for k, v in defaults.items() if k in CONFIG_KEYS or k in RADIO_STATION_KEYS},
    )
    # an email radio that was removed counts as none
    values[EMAIL_RADIO] = values[EMAIL_RADIO] if config.radio(config.email_choice or 0) in config.live_radios else ""
    radio_values = (
        {key: values[key] for key in RADIO_STATION_KEYS}
        | {
            f"radio/{spec.id}/{f.key}": spec.settings.get(f.key, f.default)
            for spec in config.live_radios
            for f in kind_fields(spec.kind)
        }
        | pair_values(config.radios, config.pairs)
    )
    radio_defaults = (
        {key: defaults[key] for key in RADIO_STATION_KEYS}
        | {f"radio/{spec.id}/{f.key}": f.default for spec in config.live_radios for f in kind_fields(spec.kind)}
        | pair_defaults(config.radios)
    )
    return {
        "values": {k: v for k, v in values.items() if k not in RADIO_STATION_KEYS},
        "defaults": {k: v for k, v in defaults.items() if k not in RADIO_STATION_KEYS},
        "radio_values": radio_values,
        "radio_defaults": radio_defaults,
        "urls": urls,
        "https": https or SecureState().wire(),
    }


class IgateSource(Protocol):
    @property
    def state(self) -> str: ...
    @property
    def reason(self) -> str: ...
    @property
    def server_name(self) -> str: ...
    @property
    def gated(self) -> int: ...
    @property
    def dropped(self) -> Mapping[str, int]: ...
    @property
    def last_gated_at(self) -> datetime | None: ...


def igate_state(config: Config, igate: IgateSource) -> dict[str, Any]:
    """Return the `igate` topic value."""
    return IgateState.row(
        None,
        enabled=config.igate_enabled,
        state=igate.state,
        server=igate.server_name,
        reason=igate.reason,
        gated=igate.gated,
        dropped=dict(igate.dropped),
        last_gated_at=iso(igate.last_gated_at),
    )


class GpsSource(Protocol):
    @property
    def fix(self) -> Fix | None: ...
    @property
    def state(self) -> str: ...
    @property
    def reason(self) -> str: ...
    def current(self) -> Fix | None: ...


class MobilePlanSource(Protocol):
    @property
    def last(self) -> Sent | None: ...
    @property
    def last_reason(self) -> Reason | None: ...


class _NoPlan:
    """Plan used while no beaconing radio has SmartBeaconing: no mobile beacon sent yet."""

    last: Sent | None = None
    last_reason: Reason | None = None


NO_PLAN: MobilePlanSource = _NoPlan()


def gps_state(config: Config, gps: GpsSource, plan: MobilePlanSource, next_due: datetime | None) -> dict[str, Any]:
    """Return the `gps` topic value.

    `next_due` is shown only for a mobile station with a fresh fix.
    """
    fix, last = gps.fix, plan.last
    return GpsState.row(
        None,
        source=config.gps_source,
        state=gps.state,
        reason=gps.reason,
        lat=None if fix is None else fix.lat,
        lon=None if fix is None else fix.lon,
        altitude_m=None if fix is None else fix.altitude_m,
        speed_kmh=None if fix is None else fix.speed_kmh,
        course_deg=None if fix is None else fix.course_deg,
        satellites=None if fix is None else fix.satellites,
        fix_at=None if fix is None else iso(fix.at),
        mobile=config.mobile,
        next_beacon_at=iso(next_due) if config.mobile and gps.current() is not None else None,
        last_beacon_reason=plan.last_reason or "" if last is not None else "",
        last_beacon_at=None if last is None else iso(last.at),
    )


class QruSource(Protocol):
    @property
    def asked(self) -> Asked | None: ...
    def servers(self) -> list[Server]: ...


class AskedAround(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def query(self) -> str: ...
    @property
    def at(self) -> datetime: ...
    @property
    def path(self) -> tuple[str, ...] | None: ...
    @property
    def until(self) -> datetime: ...
    @property
    def new(self) -> tuple[str, ...]: ...
    @property
    def radios(self) -> tuple[RadioId, ...]: ...


class AskedOnRadio(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def radio(self) -> RadioId: ...
    @property
    def at(self) -> datetime: ...


def general_state(asked: Sequence[AskedAround], by_radio: Sequence[AskedOnRadio] = ()) -> dict[str, Any]:
    """Return the `general` topic value; `by_radio` has when each kind last went on each radio."""
    return GeneralState.row(
        None, asked=[GeneralAsked.row(a) for a in asked], by_radio=[GeneralSent.row(a) for a in by_radio]
    )


def qru_state(qru: QruSource) -> dict[str, Any]:
    """Return the `qru` topic value."""
    asked = qru.asked
    servers = [
        QruServer.row(
            s,
            groups=[QruGroup.row(None, name=name, count=count) for name, count in s.groups],
            sent_at=iso(s.sent_at),
            received=list(s.received),
            settles_at=iso(s.settles_at),
        )
        for s in qru.servers()
    ]
    return QruState.row(
        None,
        asked=None if asked is None else QruAsked.row(asked, radios=list(getattr(asked, "radios", ()))),
        servers=servers,
    )
