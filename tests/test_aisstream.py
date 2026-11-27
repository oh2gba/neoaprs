"""AISStream's messages (neoaprs/aisstream.py): the box round the map's circle, the subscription,
and what a message of the stream says."""

import json
from datetime import UTC, datetime

from neoaprs.aisdecode import AisPosition, AisStatic
from neoaprs.aisstream import MESSAGE_TYPES, Confirmed, Refused, boxes, read_message, subscription
from neoaprs.geo import distance_km
from tests.support.fakeaisstream import KEY, position, static

NOW = datetime(2026, 11, 27, 12, 0, 30, tzinfo=UTC)
AT = "2026-11-27 12:00:00"


def test_the_box_holds_the_circle_and_is_rounded_outward_to_a_tenth() -> None:
    ((south, west), (north, east)), *more = boxes(60.17, 24.94, 300)
    assert not more
    for lat, lon in ((south, 24.94), (north, 24.94), (60.17, west), (60.17, east)):
        assert distance_km(60.17, 24.94, lat, lon) >= 300
    assert all(round(edge * 10) == edge * 10 for edge in (south, north, west, east))
    assert (south, north) == (57.4, 62.9)
    assert distance_km(60.17, 24.94, 62.9, 24.94) < 310


def test_a_small_move_keeps_the_box() -> None:
    assert boxes(60.17, 24.94, 100) == boxes(60.171, 24.941, 100)


def test_a_circle_over_the_antimeridian_is_two_boxes_and_one_near_a_pole_goes_round() -> None:
    east, west = boxes(-17.0, 179.5, 300)
    assert east[1][1] == 180.0 and west[0][1] == -180.0
    assert east[0][1] < 179.5 and west[1][1] > -180.0
    assert boxes(89.5, 0.0, 300) == (((round(89.5 - 300 / 111.195 - 0.05, 1), -180.0), (90.0, 180.0)),)


def test_the_subscription_has_the_key_the_boxes_latitude_first_and_the_ship_messages() -> None:
    sent = json.loads(subscription(KEY, boxes(28.1, -15.4, 300)))
    assert sent["APIKey"] == KEY
    [[[south, west], [north, east]]] = sent["BoundingBoxes"]
    assert south < 28.1 < north and west < -15.4 < east
    assert sent["FilterMessageTypes"] == list(MESSAGE_TYPES)
    assert "PositionReport" in MESSAGE_TYPES and "ShipStaticData" in MESSAGE_TYPES


def test_a_position_report_is_a_position_with_the_ships_own_time() -> None:
    found = read_message(json.dumps(position(230111000, 60.1, 24.9, AT, sog=9.5, cog=80.2, heading=79)), NOW)
    assert found == AisPosition(230111000, 60.1, 24.9, datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC), 9.5, 80.2, 79)


def test_not_available_speed_course_and_heading_are_none() -> None:
    found = read_message(json.dumps(position(230111000, 60.1, 24.9, AT, sog=102.3, cog=360.0, heading=511)), NOW)
    assert isinstance(found, AisPosition)
    assert (found.sog_kn, found.cog_deg, found.heading_deg) == (None, None, None)


def test_a_class_b_report_is_a_position_too() -> None:
    found = read_message(json.dumps(position(230222000, 60.2, 25.0, AT, kind="StandardClassBPositionReport")), NOW)
    assert isinstance(found, AisPosition) and found.mmsi == 230222000


def test_static_data_gives_the_name_type_and_destination_without_padding() -> None:
    found = read_message(json.dumps(static(230111000, "AURA", 70, "ROSTOCK", AT)), NOW)
    assert found == AisStatic(230111000, "AURA", 70, "ROSTOCK")


def test_a_class_b_static_report_gives_its_name_or_its_type() -> None:
    message = {
        "MessageType": "StaticDataReport",
        "MetaData": {"MMSI": 230222000, "time_utc": AT},
        "Message": {
            "StaticDataReport": {"ReportA": {"Valid": True, "Name": "SEA LARK@@@"}, "ReportB": {"Valid": False}}
        },
    }
    assert read_message(json.dumps(message), NOW) == AisStatic(230222000, "SEA LARK", None, "")


def test_a_time_far_ahead_of_ours_or_unreadable_is_now() -> None:
    ahead = read_message(json.dumps(position(1, 60.1, 24.9, "2026-11-27 13:00:00")), NOW)
    broken = read_message(json.dumps(position(1, 60.1, 24.9, "yesterday")), NOW)
    assert isinstance(ahead, AisPosition) and ahead.at == NOW
    assert isinstance(broken, AisPosition) and broken.at == NOW


def test_the_confirmation_and_a_refused_key_are_told_apart_from_other_errors() -> None:
    assert read_message(b'{"MessageType": "SubscriptionConfirmation", "Message": {}}', NOW) == Confirmed()
    assert read_message(b'{"error": "Api Key Is Not Valid"}', NOW) == Refused(True, "Api Key Is Not Valid")
    assert read_message(b'{"error": "Too many connections"}', NOW) == Refused(False, "Too many connections")


def test_anything_else_is_skipped() -> None:
    for text in (b"", b"[]", b"{", b'{"MessageType": "BaseStationReport", "MetaData": {}, "Message": {}}'):
        assert read_message(text, NOW) is None
    bad = position(230111000, 91.0, 24.9, AT)
    assert read_message(json.dumps(bad), NOW) is None
    no_mmsi = position(0, 60.1, 24.9, AT)
    assert read_message(json.dumps(no_mmsi), NOW) is None
