"""A position as a Mic-E packet (neoaprs/aprsmiceout.py) read back by the parser of the other direction (neoaprs/aprsmice.py): every band of longitude the specification has its own rule for (under 10 degrees, 10 to 99,
100 to 109, 110 and over, west), the latitude's hemisphere, and the speed and course."""
from datetime import UTC, datetime

import pytest

from neoaprs.aprsmice import parse_mice
from neoaprs.aprsmiceout import mice_packet

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("lat,lon", [
    (60.17, 24.94), (60.17, 5.33), (60.17, 0.5), (51.5, -0.12), (40.7, -74.0),
    (35.68, 139.69), (-33.87, 151.21), (1.35, 103.82), (1.35, 109.9), (1.35, 100.1), (-22.9, -43.2), (64.1, -21.9),
])
def test_what_is_made_is_read_back_to_the_hundredth_of_a_minute_in_every_band_of_longitude(lat: float, lon: float) -> None:
    destination, body = mice_packet(lat, lon, "/", ">", 270, 55.0)
    read = parse_mice(destination, body[1:], NOW)
    assert read.lat == pytest.approx(lat, abs=0.5 / 6000) and read.lon == pytest.approx(lon, abs=0.5 / 6000)
    assert (read.symbol_table, read.symbol_code) == ("/", ">")


@pytest.mark.parametrize(("course", "kmh", "want_course", "want_knots"), [(0, 0.0, 0, 0), (90, 55.56, 90, 30), (359, 100.0, 359, 54), (360, 5000.0, 0, 799), (725, 18.52, 5, 10)])
def test_the_course_and_the_speed_are_read_back_north_is_written_as_360_and_read_as_0_and_the_speed_is_held_to_what_a_byte_pair_can_say(course: int, kmh: float, want_course: int, want_knots: int) -> None:
    destination, body = mice_packet(60.17, 24.94, "/", "j", course, kmh)
    read = parse_mice(destination, body[1:], NOW)
    assert read.course_deg == want_course and read.speed_kmh == pytest.approx(want_knots * 1.852, abs=0.01)


def test_the_comment_follows_the_symbol_and_the_symbol_table_may_be_an_overlay() -> None:
    destination, body = mice_packet(60.17, 24.94, "S", "O", 10, 10.0, "]hello=")
    read = parse_mice(destination, body[1:], NOW)
    assert read.symbol_table == "S" and body.endswith(b"OS]hello=") and "hello" in read.comment
