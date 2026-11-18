"""A Radarcape's list of aircraft read into the layer's things (neoaprs/radarcape.py), on made-up answers in the form of a Radarcape's `aircraftlist.json` (work/par/r6/radarcape, read for the form only), and
the address it is asked at."""
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from neoaprs.radarcape import radarcape_url, read_aircraft

NOW = 1794812336
AT = datetime.fromtimestamp(NOW, UTC)


def row(**extra: Any) -> dict[str, Any]:
    """An airliner north-east of Espoo as a Radarcape says it."""
    return {"uti": NOW, "ns": 397346020, "hex": "461F2A", "fli": "FIN7AB  ", "src": "A", "ava": "AM", "lat": 60.3172, "lon": 24.9633, "alt": 8000, "gda": "A", "spd": 227, "trk": 224.6, "vrt": 0,
            "cat": "a3", "org": "ESSA", "dst": "EFHK", "opr": "FIN", "typ": "a321", "reg": "OH-LZA", "dis": 172.8, "dbm": -94, "cou": "Finl", "squ": "2563", "tru": 238, "lla": 2, "alr": 0, **extra}


def answer(*rows: dict[str, Any]) -> bytes:
    return json.dumps(list(rows)).encode()


def read(*rows: dict[str, Any]) -> list[Any]:
    return read_aircraft(answer(*rows), AT) or []


def test_an_aircraft_is_read_with_its_place_height_speed_heading_names_and_kind() -> None:
    (plane,) = read(row())
    assert (plane.id, plane.lat, plane.lon, plane.at) == ("461f2a", 60.3172, 24.9633, AT - timedelta(seconds=2))
    assert (plane.altitude_m, plane.speed_kmh, plane.heading_deg) == (2438, 420.4, 225), "feet to metres, knots to km/h, the track rounded"
    assert (plane.name, plane.registration, plane.emergency) == ("FIN7AB", "OH-LZA", False)
    assert (plane.type, plane.designator, plane.category) == ("A321", "A321", "A3"), "the type designator is the card's type too; both upper-cased"
    assert (plane.ship_type, plane.course_deg, plane.destination) == (None, None, "")


def test_without_the_age_of_its_position_the_time_of_its_last_message_gives_the_time_and_never_one_after_the_answer() -> None:
    (plane,) = read(row(lla=None, uti=NOW - 7))
    assert plane.at == AT - timedelta(seconds=7)
    (ahead,) = read(row(lla=None, uti=NOW + 30))
    assert ahead.at == AT, "a Radarcape whose clock is ahead does not put a position in the future"
    (unknown,) = read({k: v for k, v in row(lla=None).items() if k != "uti"})
    assert unknown.at == AT, "neither: the time of the answer"


@pytest.mark.parametrize(("extra", "why"), [({"lla": 86400}, "lla"), ({"lla": None, "uti": NOW - 86400}, "uti")], ids=["lla", "uti"])
def test_a_position_a_day_old_or_older_is_passed_over(extra: dict[str, Any], why: str) -> None:
    assert [plane.id for plane in read(row(**extra), row(hex="111111"))] == ["111111"], why


def test_one_on_the_ground_a_vehicle_an_obstacle_and_one_without_a_position_are_left_out() -> None:
    rows = (row(hex="aaaaaa", gda="G"), row(hex="aaaaab", gda="g"), row(hex="bbbbbb", cat="C1"), row(hex="cccccc", cat="c3"), row(hex="dddddd", lat=None), {k: v for k, v in row(hex="eeeeee").items() if k != "lon"},
            row(hex="ffffff", lat=95.0), row(hex="", lat=60.0), row(hex="111111"), row(hex="222222", gda="a"), row(hex="333333", gda=None))
    assert [plane.id for plane in read(*rows)] == ["111111", "222222", "333333"], "in the air (A, a) or not said"


@pytest.mark.parametrize(("extra", "emergency"), [({"alr": 3}, True), ({"squ": "7700"}, True), ({"squ": "7600"}, True), ({"squ": "7500", "alr": 0}, True), ({"squ": 7700}, True), ({"alr": 1}, False),
                                                   ({"alr": 2}, False), ({"squ": "7000"}, False), ({"squ": None, "alr": None}, False)],
                         ids=["alr3", "7700", "7600", "7500", "7700num", "alr1", "alr2", "7000", "none"])
def test_an_emergency_is_a_permanent_alert_or_a_squawk_of_7500_7600_or_7700(extra: dict[str, Any], emergency: bool) -> None:
    (plane,) = read(row(**extra))
    assert plane.emergency is emergency


@pytest.mark.parametrize("bad", [None, "fast", float("nan"), True, [1], {"a": 1}], ids=["null", "text", "nan", "bool", "list", "object"])
def test_a_number_that_is_null_a_string_or_not_a_number_is_none_and_the_row_stays(bad: Any) -> None:
    body = json.dumps([row(alt=bad, spd=bad, trk=bad, lla=bad, alr=bad)], allow_nan=True).encode()
    (plane,) = read_aircraft(body, AT) or []
    assert (plane.altitude_m, plane.speed_kmh, plane.heading_deg, plane.emergency) == (None, None, None, False)
    assert plane.at == AT, "no age of the position: the time of the last message (here the answer's own)"


@pytest.mark.parametrize("huge", [1e308, 10 ** 400, 1e7], ids=["1e308", "10e400", "1e7"])
def test_a_height_or_a_speed_too_large_to_be_one_is_none_and_the_row_stays(huge: float) -> None:
    (plane,) = read(row(alt=huge, spd=huge))
    assert (plane.altitude_m, plane.speed_kmh, plane.heading_deg) == (None, None, 225)


def test_a_missing_flight_type_category_and_registration_are_empty() -> None:
    (plane,) = read({k: v for k, v in row(fli=None, cat=None).items() if k not in ("typ", "reg")})
    assert (plane.name, plane.type, plane.designator, plane.category, plane.registration) == ("", "", "", "", "")


def test_a_negative_speed_is_none_and_a_track_of_360_is_north() -> None:
    (plane,) = read(row(spd=-5, trk=359.6))
    assert (plane.speed_kmh, plane.heading_deg) == (None, 0)


def test_a_row_that_cannot_be_read_never_loses_the_others() -> None:
    rows = [row(hex="aaaaaa", uti=1e300, lla=None), "a line", 7, None, row(hex="bbbbbb", lat=10 ** 400), row(hex="111111")]
    assert [plane.id for plane in read(*rows)] == ["111111"]


def test_one_aircraft_twice_is_kept_once_with_its_newest_position() -> None:
    planes = read(row(lla=9, lat=60.0), row(lla=1, lat=60.1), row(lla=5, lat=60.2))
    assert [(plane.id, plane.lat) for plane in planes] == [("461f2a", 60.1)]


@pytest.mark.parametrize("body", [b"", b"not json", b'{"now": 1, "aircraft": []}', b'"text"', b"[1, 2, 3]", b'[["461f2a"]]', b"[{}] x", b"[{"],
                         ids=["empty", "text", "readsb", "string", "numbers", "lists", "after", "cut"])
def test_anything_that_is_not_a_json_array_of_objects_is_none(body: bytes) -> None:
    assert read_aircraft(body, AT) is None


def test_an_empty_list_is_no_aircraft() -> None:
    assert read_aircraft(b"[]", AT) == [] and read_aircraft(b" [ ] \n", AT) == []


def test_an_answer_of_a_megabyte_is_read_whole() -> None:
    rows = [row(hex=f"{n:06x}", lat=59 + n / 10000, fli=f"T{n:05d}") for n in range(4000)]
    body = answer(*rows)
    assert len(body) > 1_000_000
    started = time.monotonic()
    planes = read_aircraft(body, AT) or []
    assert len(planes) == 4000 and planes[-1].name == "T03999"
    assert time.monotonic() - started < 30.0, "(a loose bound: a small machine reads it in well under a second)"


@pytest.mark.parametrize(("address", "url"), [("192.168.1.160", "http://192.168.1.160/aircraftlist.json?knownposonly=1"), ("radarcape.local:8080", "http://radarcape.local:8080/aircraftlist.json?knownposonly=1"),
                                              ("cape:80", "http://cape/aircraftlist.json?knownposonly=1"), ("[fe80::1]", "http://[fe80::1]/aircraftlist.json?knownposonly=1"),
                                              ("[fe80::1]:81", "http://[fe80::1]:81/aircraftlist.json?knownposonly=1"), ("https://cape.example/list.json?a=1", "https://cape.example/list.json?a=1"),
                                              ("http://192.168.1.160", "http://192.168.1.160/aircraftlist.json?knownposonly=1"), ("HTTP://cape:8080/", "http://cape:8080/aircraftlist.json?knownposonly=1"),
                                              (" 192.168.1.160 ", "http://192.168.1.160/aircraftlist.json?knownposonly=1"), ("", None), ("  ", None)],
                         ids=["ip", "port", "port80", "ipv6", "ipv6port", "whole", "noplace", "upper", "blanks", "empty", "blank"])
def test_a_radarcape_is_asked_at_its_one_place_and_one_with_no_address_is_not_looked_for(address: str, url: str | None) -> None:
    assert radarcape_url(address) == url
