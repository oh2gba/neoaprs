"""What the daemon's objects look like on the wire: the plain dicts (JSON-able) that `state` and `patch` carry, made from the station book, the packets, the messages, the message board, the station preferences, the TNC and the settings. The models of
the wire modules say what these are; the tests and NEOAPRS_VALIDATE_OUT hold them to it."""
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from neoaprs.aprstelemetry import describe
from neoaprs.aprsweather import Weather
from neoaprs.bulletin import BulletinRecord
from neoaprs.chain import INTERNET, Attempt
from neoaprs.clock import iso
from neoaprs.config import DEFAULTS, Config
from neoaprs.message import MessageRecord
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet
from neoaprs.packetcodec import encode_decoded, tnc2
from neoaprs.pref import Pref
from neoaprs.route import digipeaters, received_text, route_text, suggested_path
from neoaprs.stationbook import Station, StationBook
from neoaprs.symbols import symbol_name
from neoaprs.tnc import Tnc
from neoaprs.weatherlog import Observation

LINES_MAX = 100                     # lines of the TNC told to a page


def _routes(station: Station) -> dict[str, Any]:
    best = station.best_route
    return {
        "last_route": received_text(station.last_path, station.last_via) if station.packets else "", "heard_direct": station.deliveries.direct, "heard_gated": station.deliveries.gated,
        "heard_via": [[call, count] for call, count in station.deliveries.heard_via()], "best_route": "" if best is None else route_text(best),
        "suggested_path": None if best is None else suggested_path(best),
    }


def weather_values(weather: Weather | None) -> dict[str, Any] | None:
    if weather is None:
        return None
    return {name: getattr(weather, name) for name in ("wind_dir", "wind_kmh", "gust_kmh", "temp_c", "humidity", "pressure_hpa", "rain_1h_mm", "rain_24h_mm", "rain_today_mm", "luminosity", "snow_mm")}


def telemetry_values(book: StationBook, station: Station) -> dict[str, Any] | None:
    """The latest telemetry report of the station, scaled and named by the definitions its messages gave."""
    if station.telemetry is None:
        return None
    view = describe(station.telemetry, book.telemetry_definition(station.call))
    return {"sequence": view.sequence, "channels": [c._asdict() for c in view.channels], "bits": [b._asdict() for b in view.bits], "project": view.project, "comment": view.comment}


def weather_points(observations: list[Observation]) -> list[list[Any]]:
    """[time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity] for each observation."""
    return [[iso(at), w.temp_c, w.pressure_hpa, w.wind_kmh, w.gust_kmh, w.rain_1h_mm, w.humidity] for at, w in observations]


def station_row(book: StationBook, station: Station) -> dict[str, Any]:
    distance = None if station.is_me else book.distance_km(station)
    bearing = None if station.is_me else book.bearing_deg(station)
    return {
        "call": station.call, "kind": station.kind, "reported_by": station.reported_by, "symbol_table": station.symbol_table, "symbol_code": station.symbol_code,
        "symbol_name": symbol_name(station.symbol_table, station.symbol_code) if station.symbol_code else "unknown", "lat": station.lat, "lon": station.lon,
        "altitude_m": station.altitude_m, "course_deg": station.course_deg, "speed_kmh": station.speed_kmh, "first_heard": iso(station.first_heard), "last_heard": iso(station.last_heard),
        "last_position_at": iso(station.last_position_at), "last_status": station.last_status, "last_comment": station.last_comment, "packets": station.packets,
        "last_path": list(station.last_path), "distance_km": None if distance is None else round(distance, 2), "bearing_deg": None if bearing is None else round(bearing, 1),
        "is_me": station.is_me, "own": station.own, "can_message": station.can_message, "weather": weather_values(station.weather), "weather_at": iso(station.weather_at), "telemetry": telemetry_values(book, station),
        "telemetry_at": iso(station.telemetry_at), "locator": None if station.locator is None else asdict(station.locator),
        "extensions": None if station.extensions is None else asdict(station.extensions), "last_direct_at": iso(station.last_direct_at), **_routes(station), "track": [[iso(when), lat, lon] for when, lat, lon in station.track],
    }


def packet_row(number: int, packet: Packet) -> dict[str, Any]:
    return {
        "id": number, "heard_at": iso(packet.heard_at), "direction": packet.direction, "source": packet.source, "destination": packet.destination, "path": list(packet.path),
        "route": received_text(packet.path, packet.via) if packet.direction == "in" else "", "via": packet.via, "kind": packet.kind, "summary": packet.summary, "tnc2": tnc2(packet), "decoded": json.loads(encode_decoded(packet.decoded)),
    }


def attempt_rows(record: MessageRecord, attempts: tuple[Attempt, ...]) -> list[dict[str, Any]]:
    """The attempts of a message of ours as the page is told them; the one the ack answers is the latest sent before the ack was heard."""
    acked = next((a.number for a in reversed(attempts) if record.acked_at is not None and a.sent_at <= record.acked_at), None) if record.state == "acked" else None
    return [{"sent_at": iso(a.sent_at), "hops": [_hop_row(a, position, call) for position, call in enumerate(digipeaters(a.path), 1)],
             "internet": next((s.call for s in a.seen if s.position == INTERNET), None), "acked": a.number == acked} for a in attempts]


def _hop_row(attempt: Attempt, position: int, call: str) -> dict[str, Any]:
    radio = next((s for s in attempt.seen if s.position == position and not s.via_internet), None)
    net = next((s for s in attempt.seen if s.position == position and s.via_internet), None)
    seen = radio or net
    return {"call": call if seen is None else seen.call, "heard": radio is not None, "heard_at": None if seen is None else iso(seen.heard_at), "by_internet": net is not None}


def message_row(record: MessageRecord, attempts: tuple[Attempt, ...] = ()) -> dict[str, Any]:
    return {
        "attempts_detail": attempt_rows(record, attempts), "id": record.id, "at": iso(record.at), "direction": record.direction, "from_call": record.from_call, "to_call": record.to_call, "text": record.text, "msg_id": record.msg_id,
        "state": record.state, "attempts": record.attempts, "attempts_max": record.attempts_max, "last_attempt_at": iso(record.last_attempt_at), "acked_at": iso(record.acked_at),
        "route": record.route,
    }


def bulletin_row(record: BulletinRecord) -> dict[str, Any]:
    return {
        "sender": record.sender, "slot": record.slot, "group": record.group, "kind": record.kind, "text": record.text, "first_heard": iso(record.first_heard),
        "last_heard": iso(record.last_heard), "times_heard": record.times_heard,
    }


def own_object_row(obj: OwnObject, next_at: datetime | None) -> dict[str, Any]:
    return {
        "name": obj.name, "kind": obj.kind, "lat": obj.lat, "lon": obj.lon, "symbol_table": obj.symbol_table, "symbol_code": obj.symbol_code, "comment": obj.comment, "course_deg": obj.course_deg,
        "speed_kmh": obj.speed_kmh, "path": obj.path, "state": "live" if obj.alive else "killing", "created_at": iso(obj.created_at), "updated_at": iso(obj.updated_at), "sent": obj.sent,
        "last_sent_at": iso(obj.last_sent_at), "next_at": iso(next_at),
    }


def own_bulletin_row(bulletin: OwnBulletin, next_at: datetime | None) -> dict[str, Any]:
    return {
        "slot": bulletin.slot, "group": bulletin.group, "kind": bulletin.kind, "text": bulletin.text, "posted_at": iso(bulletin.created_at), "sent": bulletin.sent,
        "last_sent_at": iso(bulletin.last_sent_at), "next_at": iso(next_at),
    }


def pref_row(pref: Pref) -> dict[str, Any]:
    return {"path": None if pref.path is None else ",".join(pref.path), "hide_after_min": pref.hide_after_min, "rf_only": pref.rf_only}


def tnc_state(tnc: Tnc) -> dict[str, Any]:
    s = tnc.stats
    return {
        "state": tnc.state.value, "problem": tnc.problem, "last_error": tnc.last_error, "path": tnc.path, "baud": tnc.baud, "describe": tnc.describe(), "searching": tnc.searching, "silent_since": iso(tnc.silent_since),
        "stats": {"opens": s.opens, "bytes_in": s.bytes_in, "bytes_out": s.bytes_out, "frames_in": s.frames_in, "packets": s.packets, "rejected": s.rejected, "last_packet": iso(s.last_packet),
                  "keepalive_checks": s.keepalive_checks, "watchdog_probes": s.watchdog_probes, "port_reopens": s.port_reopens, "digipeated": s.digipeated},
        "last_watchdog_action": tnc.last_watchdog_action, "last_watchdog_at": iso(tnc.last_watchdog_at),
        "lines": [{"at": iso(at), "text": text} for at, text in tnc.recent_lines(LINES_MAX)],
    }


def config_values(config: Config, urls: list[str], https: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"values": config.to_data(), "defaults": DEFAULTS.to_data(), "urls": urls, "https": https or {"on": False, "port": 0, "fingerprint": "", "problem": ""}}


