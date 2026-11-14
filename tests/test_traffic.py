"""The ships and aircraft of the map as values (neoaprs/ais.py, neoaprs/adsb.py): Digitraffic's `locations` and `vessels` and adsb.fi's aircraft read from captured answers (tests/fixtures/traffic), the
numbers of AIS that mean "not available", the kinds and categories by the ship type, the packed ETA, the dimensions, where an icon points, the ones near us, and the rows of the wire."""
import json
from datetime import timedelta

import pytest

from neoaprs.adsb import Aircraft, aircraft_near, feed_url, kind_of as aircraft_kind, parse_aircraft
from neoaprs.ais import Fix, Ship, Voyage, category_of, eta_at, eta_of, kind_of, parse_locations, parse_vessels, ship_mmsi, ships_near
from neoaprs.clock import utc
from neoaprs.web.trafficwire import AircraftRow, FeedState, ShipRow, TrafficState
from tests.support.files import fixture_text

NOW = utc(2026, 11, 13, 19, 10, 0)
HOME = (60.17, 24.94)


def locations() -> list[Fix]:
    return parse_locations(json.loads(fixture_text("traffic/locations.json")))


def vessels() -> dict[int, Voyage]:
    return parse_vessels(json.loads(fixture_text("traffic/vessels.json")))


def test_the_fixes_of_locations_are_read_with_the_place_the_time_and_what_the_ship_says() -> None:
    fixes = {fix.mmsi: fix for fix in locations()}
    assert sorted(fixes) == [230145760, 244335000, 244854000, 636015526]
    tug = fixes[230145760]
    assert (tug.lat, tug.lon, tug.speed_kn, tug.course_deg, tug.heading_deg, tug.nav_status) == (61.59511, 21.483535, 0.0, 145.2, 101, 5)
    assert tug.at == utc(2026, 11, 13, 19, 8, 12) + timedelta(microseconds=293000)


def test_the_voyage_data_has_the_name_the_call_the_type_the_size_the_draught_the_destination_and_the_eta() -> None:
    tug = vessels()[230145760]
    assert (tug.name, tug.call_sign, tug.imo, tug.ship_type, tug.length_m, tug.beam_m, tug.draught_m, tug.destination) == ("DUNKER", "OJSU", 8701014, 52, 31, 10, 5.0, "HARBOUR ASSISTANCE")
    assert tug.eta == (11, 9, 17, 15)


@pytest.mark.parametrize(("ship_type", "kind", "category"), [
    (70, "cargo", "cargo"), (79, "cargo", "cargo"), (80, "tanker", "tanker"), (60, "passenger", "passenger"), (40, "highspeed", "highspeed"), (30, "fishing", "fishing"),
    (36, "sailing", "pleasure"), (37, "pleasure", "pleasure"), (52, "tug", "special"), (50, "pilot", "special"), (51, "sar", "special"), (35, "military", "special"), (55, "law", "special"),
    (31, "towing", "special"), (20, "wig", "other"), (90, "other", "other"), (0, "other", "other"), (None, "other", "other"), (100, "other", "other"),
])
def test_the_kind_and_the_colour_group_of_a_ship_follow_its_type(ship_type: int | None, kind: str, category: str) -> None:
    assert (kind_of(ship_type), category_of(kind_of(ship_type))) == (kind, category)


def test_what_ais_says_is_not_available_is_none() -> None:
    feature = {"geometry": {"coordinates": [24.9, 60.1]}, "properties": {"mmsi": 230000001, "sog": 102.3, "cog": 360.0, "heading": 511, "navStat": 15, "timestampExternal": 1794596892293}}
    (fix,) = parse_locations({"features": [feature]})
    assert (fix.speed_kn, fix.course_deg, fix.heading_deg, fix.nav_status) == (None, None, None, None)
    (voyage,) = parse_vessels([{"mmsi": 230000001, "name": "NO NAME@@@@ ", "draught": 0, "eta": 0, "shipType": 0, "referencePointA": 0, "referencePointB": 10, "imo": 0}]).values()
    assert (voyage.name, voyage.draught_m, voyage.eta, voyage.ship_type, voyage.length_m, voyage.imo) == ("NO NAME", None, None, None, None, None)


def test_only_a_ship_is_a_ship_not_a_base_station_an_aid_to_navigation_or_a_place_that_is_none() -> None:
    assert [ship_mmsi(m) for m in (230145760, 111230001, 2300001, 992301234, 2300011, True, "230145760")] == [230145760, 111230001, None, None, None, None, None]
    bad = [{"geometry": {"coordinates": [200.0, 60.0]}, "properties": {"mmsi": 230000001, "timestampExternal": 1}}, {"properties": {"mmsi": 230000001}}, "junk"]
    assert parse_locations({"features": bad}) == [] and parse_locations([]) == [] and parse_vessels({}) == {}


def test_the_eta_is_unpacked_and_put_in_the_nearest_year() -> None:
    assert eta_of(740431) == (11, 9, 17, 15)
    assert eta_of((1 << 16) | (31 << 11) | (24 << 6)) is None, "hour 24 is not available"
    assert eta_of(31 << 11) is None and eta_of(None) is None
    assert eta_at((1, 2, 3, 4), utc(2026, 12, 30)) == utc(2027, 1, 2, 3, 4)
    assert eta_at((12, 30, 0, 0), utc(2027, 1, 2)) == utc(2026, 12, 30)
    assert eta_at((2, 30, 0, 0), NOW) is None


def test_the_icon_points_the_way_of_the_bow_else_of_a_moving_ships_course_else_nowhere() -> None:
    def ship(heading: int | None, course: float | None, speed: float | None) -> Ship:
        return Ship(Fix(230000001, 60.0, 25.0, NOW, speed, course, heading), Voyage(230000001), 1.0)
    assert ship(90, 120.0, 10.0).bearing_deg == 90.0
    assert ship(None, 120.0, 10.0).bearing_deg == 120.0
    assert ship(None, 120.0, 0.1).bearing_deg is None


def test_the_ships_near_us_are_the_fresh_ones_within_the_radius_with_their_voyage_data_or_an_empty_one() -> None:
    near = ships_near(locations(), vessels(), HOME, 450.0, NOW - timedelta(hours=1))
    assert sorted(near) == [230145760, 244854000, 636015526], "the one heard ten hours ago is not"
    assert near[636015526].voyage.name == "SAKURA PRINCESS" and 30 < near[636015526].distance_km < 40
    assert sorted(ships_near(locations(), {}, HOME, 100.0, NOW - timedelta(hours=1))) == [244854000, 636015526]
    assert ships_near(locations(), {}, HOME, 100.0, NOW - timedelta(hours=1))[244854000].voyage == Voyage(244854000)


def test_the_row_of_a_ship_on_the_wire() -> None:
    ship = ships_near(locations(), vessels(), HOME, 450.0, NOW - timedelta(hours=1))[230145760]
    row = ShipRow.of(ship)
    ShipRow.model_validate(row)
    assert {k: row[k] for k in ("mmsi", "name", "call_sign", "kind", "category", "bearing_deg", "nav_status", "length_m", "beam_m", "draught_m", "destination", "eta")} == {
        "mmsi": 230145760, "name": "DUNKER", "call_sign": "OJSU", "kind": "tug", "category": "special", "bearing_deg": 101.0, "nav_status": 5, "length_m": 31, "beam_m": 10, "draught_m": 5.0,
        "destination": "HARBOUR ASSISTANCE", "eta": "2026-11-09T17:15:00Z"}


def test_the_aircraft_are_read_without_the_vehicles_of_the_airport() -> None:
    found = parse_aircraft(json.loads(fixture_text("traffic/aircraft.json")), NOW)
    assert [a.hex for a in found] == ["4aca04", "4ac9ec"]
    first = found[0]
    assert (first.flight, first.registration, first.type_code, first.category, first.kind, first.altitude_ft, first.on_ground, first.speed_kn, first.track_deg) == (
        "NSZ5HA", "SE-RPD", "B738", "A3", "jet", 19200, False, 392.5, 219.0)
    assert first.at == utc(2026, 11, 13, 19, 10, 52)
    assert [aircraft_kind(c) for c in ("A1", "A5", "A7", "B1", "B2", "B6", "")] == ["light", "heavy", "rotor", "glider", "balloon", "drone", "other"]


def test_an_aircraft_on_the_ground_has_no_altitude_and_a_bad_answer_has_none() -> None:
    (one,) = parse_aircraft({"aircraft": [{"hex": "ABC123", "lat": 60.3, "lon": 24.9, "alt_baro": "ground", "track": 365.0}]}, NOW)
    assert (one.hex, one.on_ground, one.altitude_ft, one.track_deg, one.at) == ("abc123", True, None, 5.0, NOW)
    assert parse_aircraft({"aircraft": [{"hex": "x"}, 1]}, NOW) == [] and parse_aircraft([], NOW) == []


def test_the_aircraft_near_us_and_the_address_asked() -> None:
    found = parse_aircraft(json.loads(fixture_text("traffic/aircraft.json")), NOW)
    near = aircraft_near(found, (59.5, 18.0), 100.0, NOW - timedelta(minutes=1))
    assert sorted(near) == ["4ac9ec", "4aca04"] and all(0 < a.distance_km < 100 for a in near.values())
    assert aircraft_near(found, HOME, 100.0, NOW - timedelta(minutes=1)) == {}
    assert feed_url("https://opendata.adsb.fi/api/v2/", HOME, 450.0) == "https://opendata.adsb.fi/api/v2/lat/60.1700/lon/24.9400/dist/243"
    assert feed_url("https://x/", HOME, 9000.0).endswith("/dist/250")


def test_the_row_of_an_aircraft_and_the_states_on_the_wire() -> None:
    one = Aircraft("4aca04", 60.0, 25.0, NOW, flight="FIN1", category="A7", altitude_ft=1000, distance_km=12.345)
    row = AircraftRow.of(one)
    AircraftRow.model_validate(row)
    assert (row["kind"], row["position_at"], row["distance_km"]) == ("rotor", "2026-11-13T19:10:00Z", 12.3)
    state = FeedState.row(None, enabled=True, state="receiving", problem="", count=3, radius_km=450.0, updated_at=None)
    TrafficState.model_validate({"ais": state, "adsb": state})
