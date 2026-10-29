"""Raw NMEA sentences: the position, course, speed, altitude and time of GGA, GLL, RMC and WPL, and what is not a position."""
from datetime import UTC, datetime
from functools import reduce

import pytest

from neoaprs.aprsnmea import NmeaError, parse_nmea

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def sentence(body: str) -> bytes:
    return f"${body}*{reduce(lambda a, c: a ^ ord(c), body, 0):02X}".encode()


def parse(info: bytes | str, destination: str = "APRS", source: str = "OH2XYZ") -> object:
    return parse_nmea(info if isinstance(info, bytes) else info.encode(), source, destination, NOW)


def test_the_specs_gga() -> None:
    p = parse_nmea(b"$GPGGA,102705,5157.9762,N,00029.3256,W,1,04,2.0,75.7,M,47.6,M,,*62", "OH2XYZ", "GPSPR", NOW)
    assert p is not None
    assert (p.lat, p.lon, p.altitude_m, p.symbol_table, p.symbol_code) == (pytest.approx(51.96627, abs=1e-5), pytest.approx(-0.48876, abs=1e-5), 75.7, "/", "R")
    assert p.timestamp == datetime(2026, 10, 21, 10, 27, 5, tzinfo=UTC)


def test_the_specs_rmc_has_the_date() -> None:
    p = parse_nmea(b"$GPRMC,063909,A,3349.4302,N,11700.3721,W,43.022,89.3,291099,13.6,E*52", "OH2XYZ", "APRS", NOW)
    assert p is not None and p.timestamp == datetime(1999, 10, 29, 6, 39, 9, tzinfo=UTC)
    assert (p.course_deg, p.speed_kmh) == (89, pytest.approx(43.022 * 1.852))


def test_the_specs_gll_time_is_the_latest_that_is_not_in_the_future() -> None:
    p = parse_nmea(b"$GPGLL,2554.459,N,08020.187,W,154027.281,A", "OH2XYZ-9", "APRS", NOW)
    assert p is not None and p.timestamp == datetime(2026, 10, 20, 15, 40, 27, tzinfo=UTC) and (p.symbol_table, p.symbol_code) == ("/", ">")
    assert (p.lat, p.lon) == (pytest.approx(25.90765, abs=1e-5), pytest.approx(-80.33645, abs=1e-5))


def test_the_waypoint_is_a_position_with_its_name() -> None:
    p = parse(sentence("GPWPL,4917.16,N,12310.64,W,003"))
    assert p is not None and (p.lat, p.lon, p.comment) == (pytest.approx(49.28600, abs=1e-5), pytest.approx(-123.17733, abs=1e-5), "003")     # type: ignore[attr-defined]


@pytest.mark.parametrize("talker", ["GP", "GN", "GL", "GA", "BD"])
def test_any_talker(talker: str) -> None:
    assert parse(sentence(f"{talker}GLL,6010.2000,N,02456.4000,E,120000,A")) is not None


def test_a_south_east_position_and_a_course_of_360() -> None:
    p = parse(sentence("GPRMC,120000,A,3345.0000,S,15112.5000,E,10.0,360,211026,,"))
    assert p is not None and (p.lat, p.lon, p.course_deg) == (pytest.approx(-33.75), pytest.approx(151.2083, abs=1e-4), 0)       # type: ignore[attr-defined]


@pytest.mark.parametrize("info", [
    b"$GPVTG,318.7,T,,M,35.1,N,65.0,K*69", b"$GPZDA,120000,21,10,2026,,", b"$GPRMC,063909,V,3349.4302,N,11700.3721,W,0,0,291099,,", b"$GPGGA,102705,5157.9762,N,00029.3256,W,0,04,2.0,75.7,M,,,,",
    b"$GPGGA,102705", b"$ULTW0031003702CE0069", b"hello", b"$gpgga,1", b"$GPRMC,063909,A",
])
def test_a_sentence_without_a_position_gives_none(info: bytes) -> None:
    try:
        assert parse_nmea(info, "A", "B", NOW) is None
    except NmeaError:
        pass                                                           # (a sentence that is cut short is damaged, not merely empty)


def test_a_wrong_checksum_is_refused_and_a_missing_one_is_not_needed() -> None:
    with pytest.raises(NmeaError, match="checksum"):
        parse(b"$GPGLL,6010.2000,N,02456.4000,E,120000,A*00")
    assert parse(b"$GPGLL,6010.2000,N,02456.4000,E,120000,A") is not None
    assert parse(b"$GPGLL,6010.2000,N,02456.4000,E,120000,A\r\n") is not None


@pytest.mark.parametrize("body", ["GPGLL,9154.4590,N,08020.1870,W,154027,A", "GPGLL,2554.4590,X,08020.1870,W,154027,A", "GPGLL,2554.459,N,08020.187", "GPGLL,2554.459,N,18020.1870,W,154027,A",
                                  "GPGLL,2575.0000,N,08020.1870,W,154027,A", "GPGLL,255.4,N,08020.1870,W,154027,A"])
def test_a_damaged_coordinate_is_an_error(body: str) -> None:
    with pytest.raises(NmeaError):
        parse(sentence(body))


def test_a_date_that_is_none_is_an_error() -> None:
    with pytest.raises(NmeaError, match="date"):
        parse(sentence("GPRMC,120000,A,6010.2000,N,02456.4000,E,0,0,311126,,"))
    with pytest.raises(NmeaError):
        parse(sentence("GPGLL,6010.2000,N,02456.4000,E,256000,A"))


@pytest.mark.parametrize("speed, course", [("022.4", "inf"), ("1e999", "084.4"), ("nan", "084.4"), ("022.4", "-inf"), ("022.4", "nan"), ("abc", "084.4"), ("1e308", "084.4")])
def test_a_speed_or_course_that_is_not_a_finite_number_is_an_error(speed: str, course: str) -> None:
    with pytest.raises(NmeaError):
        parse(f"$GPRMC,123519,A,4807.038,N,01131.000,E,{speed},{course},230394,003.1,W".encode())


def test_an_empty_speed_and_course_are_no_motion() -> None:
    p = parse(sentence("GPRMC,123519,A,4807.038,N,01131.000,E,,,230394,003.1,W"))
    assert p is not None and (p.course_deg, p.speed_kmh) == (None, None)       # type: ignore[attr-defined]


def test_an_altitude_that_is_not_a_number_is_an_error() -> None:
    with pytest.raises(NmeaError):
        parse(sentence("GPGGA,102705,5157.9762,N,00029.3256,W,1,04,2.0,inf,M,47.6,M,,"))


def test_a_long_run_of_blanks_inside_a_sentence_is_not_a_position() -> None:
    assert parse(b"$GPRMC," + b" " * 50000 + b"x") is None            # (the match is linear in the length; one that tried every end of the blanks took seconds)
