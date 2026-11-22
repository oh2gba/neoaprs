"""The table of ships (neoaprs/shiptable.py): by MMSI, a position and what the ship says of itself
put together as the page's thing, and the old forgotten."""
from datetime import timedelta

from neoaprs.aisdecode import AisPosition, AisStatic
from neoaprs.clock import utc
from neoaprs.shiptable import ShipTable

NOW = utc(2026, 11, 18, 12, 0, 0)


def pos(mmsi: int = 1001, age: float = 0, sog: float | None = 10.0, cog: float | None = 90.0, heading: int | None = 88, lat: float = 60.1, lon: float = 25.0) -> AisPosition:
    return AisPosition(mmsi, lat, lon, NOW - timedelta(seconds=age), sog, cog, heading)


def test_a_ship_with_a_position_and_words_is_one_thing() -> None:
    table = ShipTable(clock=lambda: NOW)
    table.position(pos())
    table.static(AisStatic(1001, "AURA", 60, "TALLINN"))
    [thing] = table.things(NOW, 1800)
    assert (thing.id, thing.lat, thing.lon, thing.at, thing.name, thing.ship_type, thing.destination) == ("1001", 60.1, 25.0, NOW, "AURA", 60, "TALLINN")
    assert thing.speed_kmh == 10.0 * 1.852 and thing.course_deg == 90 and thing.heading_deg == 88 and thing.emergency is False and thing.altitude_m is None


def test_the_direction_is_the_heading_else_the_course_while_under_way_else_none() -> None:
    table = ShipTable(clock=lambda: NOW)
    table.position(pos(1, heading=None, sog=0.5, cog=123.4))
    table.position(pos(2, heading=None, sog=0.4, cog=123.4))
    table.position(pos(3, heading=None, sog=None, cog=123.4))
    table.position(pos(4, heading=None, sog=5.0, cog=None))
    table.position(pos(5, heading=17, sog=0.0, cog=200.0))
    by_id = {thing.id: thing for thing in table.things(NOW, 1800)}
    assert [by_id[k].heading_deg for k in "12345"] == [123, None, None, None, 17]
    assert by_id["1"].course_deg == 123 and by_id["4"].course_deg is None and by_id["3"].speed_kmh is None


def test_a_course_rounded_up_to_360_is_0() -> None:
    table = ShipTable(clock=lambda: NOW)
    table.position(pos(heading=None, cog=359.7))
    assert table.things(NOW, 1800)[0].course_deg == 0


def test_a_ship_without_a_position_is_not_a_thing_and_its_words_wait_for_it_for_a_day() -> None:
    clock = [NOW]
    table = ShipTable(clock=lambda: clock[0])
    table.static(AisStatic(1001, "AURA", 60, "X"))
    assert table.things(NOW, 1800) == []
    table.position(AisPosition(1001, 60.0, 25.0, NOW + timedelta(hours=23), None, None, None))
    assert table.things(NOW + timedelta(hours=23), 1800)[0].name == "AURA"
    table.position(AisPosition(1002, 60.0, 25.0, NOW + timedelta(hours=25), None, None, None))
    assert table.things(NOW + timedelta(hours=25), 1800)[0].id == "1002"
    table.position(AisPosition(1001, 60.0, 25.0, NOW + timedelta(hours=25), None, None, None))
    assert {t.id: t.name for t in table.things(NOW + timedelta(hours=25), 1800)} == {"1001": "", "1002": ""}


def test_the_parts_of_a_class_b_ships_words_add_up_and_a_later_message_does_not_wipe_them() -> None:
    table = ShipTable(clock=lambda: NOW)
    table.position(pos())
    table.static(AisStatic(1001, "SEA LARK", None, ""))
    table.static(AisStatic(1001, "", 37, ""))
    [thing] = table.things(NOW, 1800)
    assert (thing.name, thing.ship_type) == ("SEA LARK", 37)


def test_a_position_older_than_the_last_does_not_replace_it() -> None:
    table = ShipTable(clock=lambda: NOW)
    table.position(pos(age=10, lat=60.2))
    table.position(pos(age=100, lat=60.9))
    assert [t.lat for t in table.things(NOW, 1800)] == [60.2]


def test_a_ship_older_than_the_age_is_dropped_and_stays_dropped() -> None:
    table = ShipTable(clock=lambda: NOW)
    table.position(pos(1, age=100))
    table.position(pos(2, age=2000))
    assert [t.id for t in table.things(NOW, 1800)] == ["1"] and table.things(NOW, 50) == []
    assert table.things(NOW, 1800) == []
