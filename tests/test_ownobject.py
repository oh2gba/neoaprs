"""An object or an item of ours (neoaprs/ownobject.py): the information field byte for byte as the specification's chapter 11 shows it, read back by our own parser, a killed one, and what is refused."""
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from neoaprs import ax25
from neoaprs.aprsparse import parse
from neoaprs.geo import distance_km
from neoaprs.ownobject import OwnError, OwnObject, info_of, make_object
from neoaprs.packet import ItemReport, ObjectReport

NOW = datetime(2026, 10, 9, 23, 45, 17, tzinfo=UTC)
LAT, LON = 49 + 3.5 / 60, -(72 + 1.75 / 60)              # 4903.50N 07201.75W, the position of the specification's examples


def made(name: str = "LEADER", kind: str = "object", **values: object) -> OwnObject:
    defaults: dict[str, object] = {"lat": LAT, "lon": LON, "symbol_table": "/", "symbol_code": ">"}
    return make_object(NOW, name, kind, **{**defaults, **values})                      # type: ignore[arg-type]


def test_the_object_of_the_specification_is_sent_as_it_shows_it() -> None:
    """`;LEADERVVV*092345z4903.50N/07201.75W>088/036`, the V standing for a blank, at 2345 hours zulu on the 9th, heading 88 degrees at 36 knots (an object's example, chapter 11)."""
    assert info_of(made(course_deg=88, speed_kmh=36 * 1.852), NOW) == b";LEADER   *092345z4903.50N/07201.75W>088/036"


def test_the_item_of_the_specification_is_sent_as_it_shows_it() -> None:
    """`)BRENDA!4903.50N\\07201.75W@088/036` (an item's example, chapter 11): no time stamp, the name as long as it is, `!` after it."""
    assert info_of(made("BRENDA", "item", symbol_table="\\", symbol_code="@", course_deg=88, speed_kmh=36 * 1.852), NOW) == b")BRENDA!4903.50N\\07201.75W@088/036"


def test_a_killed_object_and_a_killed_item_are_the_same_packet_with_an_underscore_for_the_star_and_the_bang() -> None:
    assert info_of(made(course_deg=88, speed_kmh=36 * 1.852).killed(NOW), NOW) == b";LEADER   _092345z4903.50N/07201.75W>088/036"
    assert info_of(made("BRENDA", "item", symbol_table="\\", symbol_code="@").killed(NOW), NOW) == b")BRENDA_4903.50N\\07201.75W@"


def test_the_name_is_padded_to_nine_characters_and_the_time_stamp_is_that_of_the_moment_it_is_sent() -> None:
    obj = made("A")
    assert info_of(obj, NOW) == b";A        *092345z4903.50N/07201.75W>"
    assert info_of(obj, datetime(2026, 11, 2, 7, 5, 59, tzinfo=UTC)) == b";A        *020705z4903.50N/07201.75W>"


def test_the_comment_follows_the_position_or_the_course_and_speed() -> None:
    assert info_of(made(comment="Rescue 1"), NOW).endswith(b">Rescue 1")
    assert info_of(made(comment="Rescue 1", course_deg=90, speed_kmh=0.0), NOW).endswith(b">090/000Rescue 1")
    assert info_of(made(course_deg=0, speed_kmh=18.52), NOW).endswith(b">360/010"), "north is 360: 000 says there is no course"
    assert info_of(made(speed_kmh=18.52), NOW).endswith(b">000/010")
    assert info_of(made(course_deg=270), NOW).endswith(b">270/000")


@pytest.mark.parametrize("lat, lon, text", [(60.17, 24.94, b"6010.20N/02456.40E"), (-33.8688, 151.2093, b"3352.13S/15112.56E"), (0.0, 0.0, b"0000.00N/00000.00E"), (90.0, -180.0, b"9000.00N/18000.00W")])
def test_the_position_is_the_uncompressed_form_rounded_to_the_hundredth_of_a_minute(lat: float, lon: float, text: bytes) -> None:
    assert info_of(made("X", lat=lat, lon=lon, symbol_code="E"), NOW)[len(b";X        *092345z"):][:18] == text


def test_our_own_parser_reads_an_object_back_with_everything_it_said() -> None:
    obj = made(comment="Rescue 1", course_deg=88, speed_kmh=36 * 1.852)
    report = parse(info_of(obj, NOW), "OH2GBA", "APZNEO", NOW)
    assert isinstance(report, ObjectReport) and report.alive and report.name == "LEADER"
    position = report.position
    assert distance_km(position.lat, position.lon, LAT, LON) * 1000 < 10
    assert (position.symbol_table, position.symbol_code, position.comment, position.course_deg) == ("/", ">", "Rescue 1", 88)
    assert position.speed_kmh == pytest.approx(36 * 1.852) and report.timestamp == datetime(2026, 10, 9, 23, 45, tzinfo=UTC) and not position.compressed


def test_our_own_parser_reads_an_item_and_a_killed_object_back() -> None:
    item = parse(info_of(made("BRENDA", "item", symbol_table="\\", symbol_code="@", comment="Hurricane"), NOW), "OH2GBA", "APZNEO", NOW)
    assert isinstance(item, ItemReport) and item.alive and item.name == "BRENDA" and item.position.comment == "Hurricane"
    dead = parse(info_of(made(comment="gone").killed(NOW), NOW), "OH2GBA", "APZNEO", NOW)
    assert isinstance(dead, ObjectReport) and not dead.alive and dead.name == "LEADER"
    dead_item = parse(info_of(made("BRENDA", "item").killed(NOW), NOW), "OH2GBA", "APZNEO", NOW)
    assert isinstance(dead_item, ItemReport) and not dead_item.alive


def test_the_packet_is_one_ax25_frame_that_goes_over_the_air_and_comes_back() -> None:
    frame = ax25.Frame(ax25.Address.parse("APZNEO"), ax25.Address.parse("OH2GBA"), (ax25.Address.parse("WIDE1-1"),), info=info_of(made(comment="x" * 36, course_deg=88, speed_kmh=60), NOW))
    assert ax25.decode(ax25.encode(frame)) == frame and len(frame.info) <= ax25.MAX_INFO


@pytest.mark.parametrize("name, kind", [("", "object"), ("TENCHARSXX", "object"), ("AB", "item"), (" LEADER", "object"), ("LEADER ", "object"), ("BAD!NAME", "object"), ("BAD_NAME", "item"), ("A|B", "object"),
                                       ("A~B", "object"), ("Ä", "object"), ("tab\t", "object"), ("X", "marker")])
def test_a_name_that_cannot_be_sent_is_refused(name: str, kind: str) -> None:
    with pytest.raises(OwnError):
        made(name, kind)


@pytest.mark.parametrize("name, kind", [("A", "object"), ("123456789", "object"), ("ABC", "item"), ("Rescue-1", "object"), ("a b", "item"), ("Mixed Cs", "object"), ("OH2GBA-7", "item")])
def test_a_name_of_the_right_length_without_the_forbidden_characters_is_taken_with_its_case(name: str, kind: str) -> None:
    assert made(name, kind).name == name


@pytest.mark.parametrize("values", [{"lat": 90.1}, {"lat": -91.0}, {"lon": 180.5}, {"lon": -181.0}, {"symbol_table": "!"}, {"symbol_table": "//"}, {"symbol_code": " "}, {"symbol_code": ""}, {"course_deg": 360}, {"course_deg": -1},
                                    {"speed_kmh": -1.0}, {"speed_kmh": 1851.0}, {"comment": "x" * 44}, {"comment": "x" * 37, "course_deg": 1}, {"comment": "x" * 37, "speed_kmh": 1.0}, {"comment": "a|b"}, {"comment": "åäö"},
                                    {"path": ",".join(["WIDE1-1"] * 9)}, {"path": "WIDE1-1,BAD CALL"}])
def test_values_that_make_no_packet_are_refused(values: dict[str, object]) -> None:
    with pytest.raises(OwnError):
        made(**values)


def test_the_comment_may_be_43_characters_or_36_behind_the_course_and_speed() -> None:
    assert len(made(comment="x" * 43).comment) == 43 and len(made(comment="x" * 36, course_deg=1).comment) == 36
    assert len(info_of(made(comment="x" * 36, course_deg=1, speed_kmh=1800.0), NOW)) < ax25.MAX_INFO


def test_the_path_is_written_the_way_a_frame_carries_it_and_empty_means_the_beacons() -> None:
    assert made(path="wide1-1, wide2-1").path == "WIDE1-1,WIDE2-1" and made(path="wide1-1").path_calls == ("WIDE1-1",)
    assert made(path=None).path is None and made(path="  ").path is None and made().path_calls is None


def test_direct_is_said_with_the_word_and_is_a_path_of_no_digipeaters_not_the_beacons() -> None:
    assert made(path="direct").path == "DIRECT" and made(path="DIRECT").path_calls == ()
    with pytest.raises(OwnError) as e:
        made(path="DIRECT,WIDE1-1")
    assert e.value.code == "path.direct_alone"


def test_a_changed_object_keeps_when_it_was_made_and_last_sent_and_starts_its_count_again() -> None:
    sent = replace(made(comment="one"), sent=4, last_sent_at=NOW)
    later = datetime(2026, 10, 9, 23, 55, tzinfo=UTC)
    changed = make_object(later, "LEADER", "object", LAT, LON, "/", ">", "two", before=sent)
    assert (changed.created_at, changed.updated_at, changed.last_sent_at, changed.sent, changed.comment) == (NOW, later, NOW, 0, "two")
    assert sent.same_content(made(comment="one")) and not sent.same_content(changed)


def test_a_qru_group_is_upper_case_letters_and_digits_and_none_by_default() -> None:
    assert made().qru_group == "" and not made().on_request
    assert made(qru_group=" rp70 ").qru_group == "RP70" and made(qru_group="LIFEBOAT", on_request=True).on_request


@pytest.mark.parametrize("group", ["LIFEBOATS", "R P", "RP-70", "ÅÄÖ", "INFO", "next"])
def test_a_qru_group_that_is_too_long_has_another_character_or_is_a_word_qru_takes_for_something_else_is_refused(group: str) -> None:
    with pytest.raises(OwnError) as e:
        made(qru_group=group)
    assert e.value.code == "object.qru_group" and e.value.params["max"] == 8


def test_a_changed_object_that_becomes_on_request_is_a_different_object() -> None:
    assert not made(qru_group="FOOD").same_content(made(qru_group="FOOD", on_request=True)) and not made().same_content(made(qru_group="FOOD"))
