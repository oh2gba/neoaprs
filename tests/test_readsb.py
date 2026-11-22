"""readsb's JSON read into the layer's aircraft (neoaprs/readsb.py) on made-up answers in the form
of an own receiver's `aircraft.json` and the services' answers, and the places an own receiver's
file is tried.
"""
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from neoaprs.readsb import loads, number, read_aircraft, receiver_urls

NOW = 1794812336.0
AT = datetime.fromtimestamp(NOW, UTC)


def flying(**extra: Any) -> dict[str, Any]:
    """An airliner north-east of Espoo as readsb says it."""
    return {"hex": "461F2A", "type": "adsb_icao", "flight": "FIN7AB  ", "r": "OH-LZA", "t": "A321", "desc": "AIRBUS A-321", "alt_baro": 8000, "alt_geom": 7650, "gs": 227.0, "track": 224.6,
            "true_heading": 230.0, "mag_heading": 220.0, "squawk": "2563", "emergency": "none", "category": "A3", "lat": 60.3172, "lon": 24.9633, "seen_pos": 1.5, "seen": 0.4, "rssi": -12.0, **extra}


def receiver_file(*aircraft: dict[str, Any], now: float = NOW) -> bytes:
    return json.dumps({"now": now, "messages": 123456, "aircraft": list(aircraft)}).encode()


def service_answer(*aircraft: dict[str, Any], now: float = NOW) -> bytes:
    return json.dumps({"ac": list(aircraft), "msg": "No error", "now": int(now * 1000), "total": len(aircraft), "ctime": int(now * 1000), "ptime": 0}).encode()


def test_an_aircraft_of_a_receivers_file_is_read_with_its_place_height_speed_heading_and_names() -> None:
    (plane,) = read_aircraft(receiver_file(flying())) or []
    assert (plane.id, plane.lat, plane.lon) == ("461f2a", 60.3172, 24.9633)
    assert plane.at == AT - timedelta(seconds=1.5), "the time of its position: seen_pos before the answer's now"
    assert (plane.altitude_m, plane.speed_kmh, plane.heading_deg) == (2438, 420.4, 225), "feet to metres, knots to km/h, the track rounded"
    assert (plane.name, plane.registration, plane.type, plane.emergency) == ("FIN7AB", "OH-LZA", "AIRBUS A-321", False)
    assert (plane.ship_type, plane.course_deg, plane.destination) == (None, None, "")


def test_the_services_answer_has_its_list_as_ac_and_now_in_milliseconds() -> None:
    (plane,) = read_aircraft(service_answer(flying())) or []
    assert plane.id == "461f2a" and plane.at == AT - timedelta(seconds=1.5)


def test_the_time_of_a_position_is_counted_from_the_daemons_clock_when_it_is_given() -> None:
    mine = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    (plane,) = read_aircraft(receiver_file(flying(), now=1000.0), mine) or []
    assert plane.at == mine - timedelta(seconds=1.5), "a receiver whose clock is wrong does not age its aircraft away"


def test_one_on_the_ground_a_vehicle_an_obstacle_and_one_without_a_position_are_left_out() -> None:
    body = receiver_file(flying(hex="aaaaaa", alt_baro="ground"), flying(hex="bbbbbb", category="C1"), flying(hex="cccccc", category="C3"), flying(hex="dddddd", lat=None),
                         {k: v for k, v in flying(hex="eeeeee").items() if k != "lon"}, flying(hex="ffffff", lat=95.0), flying(hex="111111"))
    assert [plane.id for plane in read_aircraft(body) or []] == ["111111"]


@pytest.mark.parametrize(("extra", "emergency"), [({"emergency": "general"}, True), ({"emergency": "lifeguard"}, True), ({"squawk": "7700"}, True), ({"squawk": "7600"}, True),
                                                   ({"squawk": "7500", "emergency": "none"}, True), ({"squawk": "7000"}, False), ({}, False)])
def test_an_emergency_is_one_it_declares_or_a_squawk_of_7500_7600_or_7700(extra: dict[str, Any], emergency: bool) -> None:
    (plane,) = read_aircraft(receiver_file(flying(**extra))) or []
    assert plane.emergency is emergency


@pytest.mark.parametrize("huge", [1e308, 10 ** 400, 1e7], ids=["1e308", "10e400", "1e7"])
def test_a_height_or_a_speed_too_large_to_be_one_is_none_and_the_aircraft_stays(huge: float) -> None:
    body = json.dumps({"now": 1794812336, "aircraft": [{"hex": "aaaaaa", "lat": 60.3, "lon": 24.9, "alt_baro": huge, "alt_geom": huge, "gs": huge}]}).encode()
    (plane,) = read_aircraft(body) or []
    assert (plane.altitude_m, plane.speed_kmh) == (None, None)


def test_a_number_too_large_for_a_float_is_none() -> None:
    assert number(10 ** 400) is None and number(-(10 ** 400)) is None and number(12) == 12.0


def test_the_heading_is_the_track_else_the_true_heading_else_the_magnetic_one_else_none() -> None:
    def heading(**extra: Any) -> int | None:
        base = {k: v for k, v in flying().items() if k not in ("track", "true_heading", "mag_heading")}
        (plane,) = read_aircraft(receiver_file({**base, **extra})) or []
        return plane.heading_deg

    assert (heading(track=359.7), heading(true_heading=12.2), heading(mag_heading=90.0), heading()) == (0, 12, 90, None)


def test_what_is_not_there_is_empty_or_none_and_a_flight_without_a_name_keeps_its_registration() -> None:
    (plane,) = read_aircraft(receiver_file({"hex": "~2f0c1a", "lat": 60.2, "lon": 24.7})) or []
    assert (plane.id, plane.name, plane.registration, plane.type, plane.altitude_m, plane.speed_kmh, plane.heading_deg, plane.at) == ("~2f0c1a", "", "", "", None, None, None, AT)
    (other,) = read_aircraft(receiver_file(flying(flight=None, desc=None, alt_baro=None))) or []
    assert (other.name, other.registration, other.type, other.altitude_m) == ("", "OH-LZA", "A321", 2332), "the type `t` without `desc`, the height from alt_geom without alt_baro"


def test_one_hex_twice_is_one_aircraft_at_its_newest_position() -> None:
    body = receiver_file(flying(seen_pos=9.0, lat=60.0), flying(seen_pos=0.5, lat=60.1))
    (plane,) = read_aircraft(body) or []
    assert plane.lat == 60.1


@pytest.mark.parametrize("body", [b"", b"not json", b"\xff\xfe", b"[]", b'"aircraft"', b'{"aircraft": []}', b'{"now": 1, "aircraft": {}}', b'{"now": "soon", "aircraft": []}', b'{"now": true, "ac": []}',
                                  b"<html><body>tar1090</body></html>", b'{"now": 1e400, "aircraft": []}', b"[" * 100000], ids=lambda body: f"{len(body)} bytes" if isinstance(body, bytes) and len(body) > 80 else None)
def test_anything_that_is_not_readsbs_json_is_none(body: bytes) -> None:
    assert read_aircraft(body) is None


@pytest.mark.parametrize("seen_pos", [1e20, 1e12, 6e10, 86400.0])
def test_a_position_a_day_old_or_beyond_the_calendar_costs_that_one_aircraft_and_nothing_more(seen_pos: float) -> None:
    body = receiver_file(flying(hex="aaaaaa", seen_pos=seen_pos), flying(hex="bbbbbb"))
    assert [plane.id for plane in read_aircraft(body) or []] == ["bbbbbb"]
    assert [plane.id for plane in read_aircraft(body, datetime(1, 1, 2, tzinfo=UTC)) or []] == ["bbbbbb"]


@pytest.mark.parametrize("body", [b'{}', b' { "now" : 1.5 , "aircraft" : [ 1 , {"hex": [2, {"x": []}]} ] , "ac": [] } ', b'{"aircraft": [], "aircraft": [3]}', b'\xef\xbb\xbf{"ac": [1]}', b"[1, 2]",
                                  b'{"a": NaN, "b": "\\u00e4"}'])
def test_the_answer_read_item_by_item_is_what_json_reads(body: bytes) -> None:
    assert loads(body) == json.loads(body)


@pytest.mark.parametrize("body", [b'{"ac": [1,]}', b'{"now": 1,}', b'{"now" 1}', b'{1: 2}', b'{"ac": [1] x', b'{"ac": [1', b'{"ac": [1]} {}', b'{"ac": [' + b"[" * 100000 + b"]"], ids=lambda body: f"{len(body)} bytes" if isinstance(body, bytes) and len(body) > 80 else None)
def test_an_answer_that_is_not_json_is_still_none_when_read_item_by_item(body: bytes) -> None:
    assert read_aircraft(body) is None


def test_an_empty_sky_is_an_empty_list_and_a_list_of_things_that_are_not_aircraft_is_too() -> None:
    assert read_aircraft(receiver_file()) == []
    assert read_aircraft(json.dumps({"now": NOW, "aircraft": [1, "x", None, {"lat": 60, "lon": 24}]}).encode()) == []


def test_the_kind_of_an_aircraft_is_its_emitter_category_and_its_type_designator_upper_cased_and_empty_when_none() -> None:
    (plane,) = read_aircraft(receiver_file(flying(category="a7", t="ec35", desc="EUROCOPTER EC-135"))) or []
    assert (plane.category, plane.designator, plane.type) == ("A7", "EC35", "EUROCOPTER EC-135")
    (bare,) = read_aircraft(receiver_file({k: v for k, v in flying().items() if k not in ("category", "t", "desc")})) or []
    assert (bare.category, bare.designator, bare.type) == ("", "", "")


def test_a_top_level_list_is_read_item_by_item_as_json_reads_it() -> None:
    body = b' [ {"a": [1, 2]}, 3, "x" , [] ] '
    assert loads(body) == json.loads(body) and loads(b"[]") == []
    for broken in (b"[1, 2", b"[1 2]", b"[1] [2]"):
        with pytest.raises((ValueError, StopIteration)):
            loads(broken)


def test_a_name_from_the_feed_is_trimmed_cut_and_has_no_control_characters() -> None:
    (plane,) = read_aircraft(receiver_file(flying(flight="  FIN\x007AB\n ", r="X" * 200))) or []
    assert plane.name == "FIN7AB" and len(plane.registration) == 64


# ---- where an own receiver's file is tried

PLACES = ["/tar1090/data/aircraft.json", "/data/aircraft.json", "/skyaware/data/aircraft.json", "/dump1090/data/aircraft.json"]


def test_an_empty_address_is_this_computer_on_port_80_and_then_8080() -> None:
    assert receiver_urls("") == [f"http://127.0.0.1{place}" for place in PLACES] + [f"http://127.0.0.1:8080{place}" for place in PLACES]


def test_a_bare_host_has_the_known_places_tried_on_80_then_8080_and_a_port_given_only_on_that_port() -> None:
    assert receiver_urls("pi.local") == [f"http://pi.local{place}" for place in PLACES] + [f"http://pi.local:8080{place}" for place in PLACES]
    assert receiver_urls("192.168.1.20:8504") == [f"http://192.168.1.20:8504{place}" for place in PLACES]
    assert receiver_urls("[fe80::1]:8080")[0] == "http://[fe80::1]:8080/tar1090/data/aircraft.json"
    assert receiver_urls("[fe80::1]")[4] == "http://[fe80::1]:8080/tar1090/data/aircraft.json"


def test_a_zone_of_an_ipv6_address_is_written_as_an_address_writes_it() -> None:
    assert receiver_urls("[fe80::1%eth0]:8080")[0] == "http://[fe80::1%25eth0]:8080/tar1090/data/aircraft.json"


def test_a_whole_address_is_used_as_typed() -> None:
    assert receiver_urls("HTTP://pi.local/my/aircraft.json") == ["HTTP://pi.local/my/aircraft.json"]
    assert receiver_urls("http://pi.local:8080/my/aircraft.json") == ["http://pi.local:8080/my/aircraft.json"]
    assert receiver_urls("https://adsb.example.org/tar1090/data/aircraft.json") == ["https://adsb.example.org/tar1090/data/aircraft.json"]


@pytest.mark.parametrize(("extra", "metres"), [({"baro_rate": 700}, 3.6), ({"baro_rate": -2112}, -10.7), ({"baro_rate": 0}, 0.0), ({"geom_rate": 1800}, 9.1), ({"baro_rate": 700, "geom_rate": -600}, 3.6),
                                                ({"baro_rate": None, "geom_rate": -600}, -3.0), ({"baro_rate": None}, None), ({"baro_rate": "700"}, None), ({"baro_rate": 30000}, None), ({"geom_rate": -30000}, None), ({}, None)],
                         ids=["climbing", "descending", "level", "geom only", "baro first", "geom where baro is null", "null", "a string", "too fast up", "too fast down", "missing"])
def test_the_vertical_rate_of_a_receivers_file_is_the_barometric_one_else_the_geometric_one_in_metres_a_second(extra: dict[str, Any], metres: float | None) -> None:
    (plane,) = read_aircraft(receiver_file(flying(**extra))) or []
    assert plane.vertical_ms == metres
