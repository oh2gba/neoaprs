"""Mic-E: the destination digits and bits, the longitude rules, speed and course, symbol, altitude,
the comment and the radios' type codes."""

import re
from datetime import UTC, datetime

import pytest

from neoaprs.aprsmice import MicEError, MicType, mice_type, parse_mice

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
WORKED = b'(_fn"Oj/'  # 112 07.74 W, 20 knots, 251 degrees, a jeep


def test_the_worked_example() -> None:
    p = parse_mice("S32UVT", WORKED, NOW)
    assert (p.lat, p.lon) == (pytest.approx(33 + 25.64 / 60), pytest.approx(-(112 + 7.74 / 60)))
    assert (p.course_deg, p.speed_kmh) == (251, pytest.approx(20 * 1.852))
    assert (p.symbol_table, p.symbol_code, p.timestamp, p.altitude_m) == ("/", "j", None, None)
    assert p.comment == "Mic-E: Returning"


def test_the_message_comes_from_the_first_three_characters() -> None:
    def name(dest: str) -> str:
        return parse_mice(dest, WORKED, NOW).comment

    assert name("PPPUVT") == ""  # standard 111: Off Duty is the default and not shown
    assert name("PP3UVT") == "Mic-E: En Route"
    assert name("P3PUVT") == "Mic-E: In Service"
    assert name("P33UVT") == "Mic-E: Returning"
    assert name("3PPUVT") == "Mic-E: Committed"
    assert name("3P3UVT") == "Mic-E: Special"
    assert name("33PUVT") == "Mic-E: Priority"
    assert name("333UVT") == "Mic-E: Emergency"
    assert name("AAAUVT") == "Mic-E: Custom 0"
    assert name("AA3UVT") == "Mic-E: Custom 1"
    assert name("33AUVT") == "Mic-E: Custom 6"
    assert name("PAPUVT") == ""  # standard and custom mixed: no message


def test_the_destination_may_carry_an_ssid() -> None:
    assert parse_mice("S32UVT-7", WORKED, NOW) == parse_mice("S32UVT", WORKED, NOW)


@pytest.mark.parametrize(
    ("dest", "north", "west", "offset"),
    [
        ("S32UVT", True, True, True),
        ("S325VT", False, True, True),
        ("S32U6T", True, True, False),
        ("S32UV4", True, False, True),
    ],
)
def test_north_south_west_east_and_the_longitude_offset(dest: str, north: bool, west: bool, offset: bool) -> None:
    p = parse_mice(dest, WORKED, NOW)
    assert (p.lat > 0, p.lon < 0) == (north, west)
    assert abs(p.lon) == pytest.approx(112 + 7.74 / 60 if offset else 12 + 7.74 / 60)


@pytest.mark.parametrize(
    ("offset", "d", "degrees"),
    [
        (False, 0, 0),
        (False, 12, 12),
        (False, 99, 99),
        (True, 0, 100),
        (True, 12, 112),
        (True, 79, 179),
        (True, 80, 100),
        (True, 89, 109),
        (True, 90, 0),
        (True, 99, 9),
    ],
)
def test_longitude_degrees_and_the_offset(offset: bool, d: int, degrees: int) -> None:
    dest = "VPQPVT" if offset else "VPQP6T"
    p = parse_mice(dest, bytes([d + 28]) + b"4D" + WORKED[3:], NOW)
    assert p.lon == pytest.approx(-(degrees + (24 + 0.40) / 60))


def test_longitude_minutes_wrap_at_60() -> None:
    p = parse_mice("S32UVT", b"(" + bytes([28 + 60 + 7]) + b"f" + WORKED[3:], NOW)
    assert abs(p.lon) == pytest.approx(112 + (7 + 0.74) / 60)


def test_speed_and_course_rules() -> None:
    def sc(sp: int, dc: int, se: int) -> tuple[int | None, float | None]:
        p = parse_mice("S32UVT", WORKED[:3] + bytes([sp + 28, dc + 28, se + 28]) + WORKED[6:], NOW)
        return p.course_deg, p.speed_kmh

    assert sc(2, 2, 51) == (251, pytest.approx(20 * 1.852))
    # 800 and over: minus 800, 400 and over: minus 400
    assert sc(82, 6, 51) == (251, pytest.approx(20 * 1.852))
    assert sc(0, 0, 0) == (None, None)
    assert sc(0, 5, 0) == (100, pytest.approx(0.0))  # 500 - 400
    assert sc(5, 0, 0) == (None, pytest.approx(50 * 1.852))
    assert sc(1, 0, 36) == (36, pytest.approx(10 * 1.852))
    assert sc(0, 3, 60)[0] == 0  # 360 is north
    assert sc(80, 0, 0) == (None, None)


def test_a_course_over_360_is_refused() -> None:
    with pytest.raises(MicEError, match="course"):
        parse_mice("S32UVT", WORKED[:3] + bytes([28, 28 + 3, 28 + 62]) + WORKED[6:], NOW)


def test_latitude_ambiguity_from_trailing_blanks() -> None:
    p = parse_mice("S32UVZ", WORKED, NOW)  # last digit blank, west
    assert (p.lat, p.lon) == (pytest.approx(33 + 25.65 / 60), pytest.approx(-(112 + 7.75 / 60)))
    p = parse_mice("S3LZZZ", WORKED, NOW)  # four blanks: the degree's centre, north
    assert (p.lat, p.lon) == (pytest.approx(33.5), pytest.approx(-(112 + 30 / 60)))
    # (the page shows the circle of ambiguity, so the count is told)
    assert (
        p.ambiguity == 4
        and parse_mice("S32UVZ", WORKED, NOW).ambiguity == 1
        and parse_mice("S32UVT", WORKED, NOW).ambiguity == 0
    )


@pytest.mark.parametrize("dest", ["S3LUVT", "L32UVT", "S32U!T", "S32UV", "", "s32uvt", "S32KVT", "S32UVK", "S32UV?"])
def test_bad_destinations(dest: str) -> None:
    with pytest.raises(MicEError):
        parse_mice(dest, WORKED, NOW)


@pytest.mark.parametrize(
    "body", [b"", WORKED[:7], b"\x1b" + WORKED[1:], WORKED[:3] + b"\x1b" + WORKED[4:], WORKED[:6] + b"j?"]
)
def test_bad_bodies(body: bytes) -> None:
    with pytest.raises(MicEError):
        parse_mice("S32UVT", body, NOW)


def test_the_latitude_must_exist() -> None:
    with pytest.raises(MicEError, match="latitude"):
        parse_mice("YYPPPP", WORKED, NOW)  # 99 degrees


def test_kenwood_and_yaesu_type_codes_are_dropped() -> None:
    def comment(rest: bytes) -> str:
        return parse_mice("PPPUVT", WORKED + rest, NOW).comment

    assert comment(b">Hello") == "Hello"  # TH-D7
    assert comment(b">Hello=") == "Hello"  # TH-D72
    assert comment(b">Hello^") == "Hello"  # TH-D74
    assert comment(b"]Hello") == "Hello"  # TM-D700
    assert comment(b"]Hello=") == "Hello"  # TM-D710
    assert comment(b"`Hello_ ") == "Hello"  # VX-8
    assert comment(b"`Hello_#") == "Hello"  # VX-8G
    assert comment(b"'Hello") == "Hello"
    assert comment(b"Hello=") == "Hello="  # an equals sign with no type code before it is text
    assert comment(b"Hello\r") == "Hello"
    assert comment(b"") == ""
    assert comment(b">") == ""


@pytest.mark.parametrize(
    ("rest", "text"),
    [
        (b">Hello&", "Hello"),  # TH-D75
        (b"]Hello^", "Hello^"),  # (^ is a handheld's: a mobile's text keeps it)
        (b"`Hello_%", "Hello"),
        (b"`Hello_0", "Hello"),
        (b"`Hello_)", "Hello"),  # FTM-400DR, FT3D, FTM-100D
        # Anytone D878UV, TinyTrak3 and 4 (non-messaging trackers)
        (b"`Hello(8", "Hello"),
        (b"'Hello|3", "Hello"),
        (b"'Hello|4", "Hello"),
        (b"`Hello[1", "Hello"),
        (b"`Hello^v", "Hello"),
        (b"'Hello X", "Hello"),
        (b"`Hello:2", "Hello"),
        (b"`Hello*9", "Hello"),
        (b"`Hello!w5L![1", "Hello"),  # the DAO comes before the type code
        (b"`Hello_9", "Hello_9"),
        (b"`Hi ab", "Hi ab"),  # a suffix that is not in aprs-deviceid's table is text
    ],
)
def test_the_type_codes_of_aprs_deviceid_are_dropped(rest: bytes, text: str) -> None:
    assert parse_mice("PPPUVT", WORKED + rest, NOW).comment == text


def test_old_hex_telemetry_is_dropped() -> None:
    def comment(rest: bytes) -> str:
        return parse_mice("PPPUVT", WORKED + rest, NOW).comment

    assert comment(b"`0A1BHi") == "Hi"  # the backtick flag: two values, two hex digits each
    assert comment(b"'0A1B2C3D4EHi") == "Hi"  # the apostrophe flag: five values
    assert comment(b"\x1d\x01\x02\x03\x04\x05Hi") == "Hi"  # 0x1d: five binary values
    # four hex digits after an apostrophe are not telemetry: only the type code goes
    assert comment(b"'0A1BHi") == "0A1BHi"
    assert comment(b"`0A1") == "0A1"  # too short to be telemetry: only the type code goes
    # a Yaesu whose text starts with four hex-looking characters: the type code wins over the
    # obsolete telemetry
    assert comment(b"`1296 MHz on request_3") == "1296 MHz on request"
    assert comment(b"`CAFE_3") == "CAFE"
    assert comment(b"'2024 trip|3") == "2024 trip"
    assert comment(b"`0A1BHi") == "Hi"  # (no known suffix: the telemetry reading stands)


def test_altitude() -> None:
    def alt(rest: bytes) -> tuple[float | None, str]:
        p = parse_mice("PPPUVT", WORKED + rest, NOW)
        return p.altitude_m, p.comment

    assert alt(b'>"4{}Hi') == (100.0, "Hi")  # 10100 - 10000
    assert alt(b'"4{}') == (100.0, "")
    assert alt(b"]!!!}=") == (-10000.0, "")
    assert alt(b">Hi}") == (None, "Hi}")  # (two characters are not an altitude)
    # only at the start: three characters and a brace inside the text are text
    assert alt(b'>Hello "4{} bye') == (None, 'Hello "4{} bye')
    assert alt(b">see you QRT}") == (None, "see you QRT}")
    assert alt(b'>Hello"4{}') == (None, 'Hello"4{}')  # not glued to a word
    assert alt(b'>Hello "4{}x') == (None, 'Hello "4{}x')  # nor followed by one
    assert alt(b">abc}x") == (
        pytest.approx(((ord("a") - 33) * 91 * 91 + (ord("b") - 33) * 91 + ord("c") - 33) - 10000.0),
        "x",
    )


def test_the_symbol_table_and_overlay() -> None:
    p = parse_mice("PPPUVT", WORKED[:6] + b"jD", NOW)
    assert (p.symbol_table, p.symbol_code) == ("D", "j")
    with pytest.raises(MicEError):
        parse_mice("PPPUVT", WORKED[:6] + b"j?", NOW)


def test_custom_digits_and_the_blank_k_carry_the_custom_message() -> None:
    p = parse_mice("JA0PPP", WORKED, NOW)  # J and A are the digits 9 and 0 with the custom bit
    assert (p.lat, p.comment) == (pytest.approx(90.0), "Mic-E: Custom 1")
    p = parse_mice("A3KZZZ", WORKED, NOW)  # K: a blank with the custom bit
    assert (p.lat, p.ambiguity, p.comment) == (pytest.approx(3.5), 4, "Mic-E: Custom 2")


def test_the_blanks_l_and_z_carry_their_message_and_north_bits() -> None:
    assert parse_mice("S3LZZZ", WORKED, NOW).comment == "Mic-E: Returning"  # L: bit 0
    assert parse_mice("S3ZZZZ", WORKED, NOW).comment == "Mic-E: In Service"  # Z: bit 1
    assert parse_mice("S32LZZ", WORKED, NOW).lat < 0  # L in the fourth place: south


def test_the_digit_nine_and_the_last_minute() -> None:
    p = parse_mice("455999", WORKED, NOW)
    assert (p.lat, p.comment) == (pytest.approx(-(45 + 59.99 / 60)), "Mic-E: Emergency")


def test_the_latitude_stops_at_90() -> None:
    assert parse_mice("900099", WORKED, NOW).lat == -90.0


@pytest.mark.parametrize(
    ("dest", "error"),
    [
        ("S32AVT", "bad character 'A' in the destination"),  # A to K only in the first three
        ("S32KZZ", "bad character 'K' in the destination"),
        ("S32U!T", "bad character '!' in the destination"),
        ("5ZZZZZ", "blank digits inside the latitude"),  # four blanks at most
        ("9100PP", "latitude out of range"),
        ("4560PP", "latitude out of range"),
        ("S32UV", "destination shorter than six characters"),
        ("S32UV-7", "destination shorter than six characters"),
    ],
)
def test_what_is_wrong_with_a_destination_is_said(dest: str, error: str) -> None:
    with pytest.raises(MicEError, match=f"^{re.escape(error)}$"):
        parse_mice(dest, WORKED, NOW)


def test_only_six_destination_characters_count() -> None:
    assert parse_mice("S32UVT!", WORKED, NOW) == parse_mice("S32UVT", WORKED, NOW)


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (WORKED[:7], "body shorter than eight bytes"),
        (b"\x1b" + WORKED[1:], "longitude out of range"),
        (bytes([128]) + WORKED[1:], "longitude out of range"),  # 200 degrees with the offset
        (WORKED[:1] + bytes([148]) + WORKED[2:], "longitude out of range"),  # 60 minutes after the wrap
        (WORKED[:2] + bytes([128]) + WORKED[3:], "longitude out of range"),  # 100 hundredths
        (WORKED[:4] + b"\x1b" + WORKED[5:], "bad speed or course"),
        (WORKED[:5] + b"\x1b" + WORKED[6:], "bad speed or course"),
        (WORKED[:3] + bytes([28, 28 + 3, 28 + 61]) + WORKED[6:], "course out of range"),
        (WORKED[:6] + b" /", "bad symbol"),
        (WORKED[:6] + b"\x7f/", "bad symbol"),
        (WORKED[:6] + b"j?", "bad symbol"),
    ],
)
def test_what_is_wrong_with_a_body_is_said(body: bytes, error: str) -> None:
    with pytest.raises(MicEError, match=f"^{re.escape(error)}$"):
        parse_mice("S32UVT", body, NOW)


def test_a_course_of_400_is_none() -> None:
    p = parse_mice("S32UVT", WORKED[:3] + bytes([28 + 1, 28 + 4, 28]) + WORKED[6:], NOW)
    assert (p.course_deg, p.speed_kmh) == (None, pytest.approx(10 * 1.852))


def test_the_symbol_codes_at_the_ends_of_the_range() -> None:
    assert parse_mice("S32UVT", WORKED[:6] + b"!/", NOW).symbol_code == "!"
    assert parse_mice("S32UVT", WORKED[:6] + b"~/", NOW).symbol_code == "~"


def test_the_message_comes_before_the_comment() -> None:
    assert parse_mice("S32UVT", WORKED + b">Hello", NOW).comment == "Mic-E: Returning - Hello"


def test_the_dao_refines_only_a_place_without_blanks() -> None:
    p = parse_mice("S32UVT", WORKED + b">Hi!W59!", NOW)
    assert (p.lat, p.lon) == (pytest.approx(33 + 25.645 / 60), pytest.approx(-(112 + 7.749 / 60)))
    p = parse_mice("S32UVZ", WORKED + b">Hi!W59!", NOW)
    assert (p.lat, p.lon) == (pytest.approx(33 + 25.65 / 60), pytest.approx(-(112 + 7.75 / 60)))


def test_the_locator_telemetry_and_frequency_of_the_comment() -> None:
    p = parse_mice("PPPUVT", WORKED + b">KP20le/- 146.520MHz Hi|!!!!|", NOW)
    assert p.locator is not None and (p.locator.grid, p.locator.symbol_code) == ("KP20le", "-")
    assert p.frequency is not None and p.frequency.mhz == pytest.approx(146.52)
    assert p.telemetry is not None and (p.telemetry.sequence, p.telemetry.analog) == (0, [0.0])
    assert p.comment == "Hi"


def test_text_after_a_line_end_and_trailing_letters() -> None:
    def comment(rest: bytes) -> str:
        return parse_mice("PPPUVT", WORKED + rest, NOW).comment

    assert comment(b"`Hello_ \r\n") == "Hello"
    assert comment(b">Box X") == "Box X"
    assert comment(b"`0A1B") == ""  # telemetry and nothing after it
    assert comment(b"`G0A1Hi") == "G0A1Hi"
    assert comment(b"'0A1B2C3D4E") == ""
    assert comment(b"'G0A1B2C3D4Hi") == "G0A1B2C3D4Hi"
    assert comment(b"\x1d\x01\x02\x03\x04\x05") == ""


@pytest.mark.parametrize(
    ("rest", "split"),
    [
        (b"`Hello_ ", MicType(b"`", b"_ ", b"Hello")),
        (b"`0A1BHi", MicType(b"", b"", b"Hi")),
        (b"'0A1B2C3D4EHi", MicType(b"", b"", b"Hi")),
        (b"\x1d\x01\x02\x03\x04\x05Hi", MicType(b"", b"", b"Hi")),
        (b"Hello", MicType(b"", b"", b"Hello")),
        (b">Hello=", MicType(b">", b"=", b"Hello")),
        (b"]Hello", MicType(b"]", b"", b"Hello")),
    ],
)
def test_the_type_code_and_suffix_that_name_the_radio(rest: bytes, split: MicType) -> None:
    assert mice_type(rest) == split
