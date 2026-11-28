"""Properties of Mic-E: mice_packet then parse_mice gives back the place within half a hundredth of a
minute, the speed within half a knot, the course, the symbol and the message; parse_mice refuses any
damaged destination or body with MicEError only, and what it returns is a place on the Earth.
"""

import math
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from neoaprs.aprsmice import MicEError, parse_mice
from neoaprs.aprsmiceout import MAX_LON_HUNDREDTHS, OFF_DUTY, mice_packet
from neoaprs.aprsparse import parse
from neoaprs.aprsposition import HUNDREDTHS_PER_DEGREE
from neoaprs.packet import Position, Undecoded
from neoaprs.units import KNOT_KMH
from tests.support.damaged import aprs_cases, mutated, mutated_text

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
# the resolution of the format: a hundredth of a minute, rounded
HALF_HUNDREDTH = 0.5 / HUNDREDTHS_PER_DEGREE + 1e-9
STANDARD = ("Emergency", "Priority", "Special", "Committed", "Returning", "In Service", "En Route", "Off Duty")
TABLES = "/\\0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CASES = [c for c in aprs_cases() if c["info"][:1] in ("`", "'")]
DESTINATIONS = [c["destination"] for c in CASES] + ["S32U6T", "T4SP0W-1", "PPPPPP", "LLLLLL", "0000ZZ"]
BODIES = [c["info"][1:].encode("latin-1") for c in CASES] + [b'(_fn"Oj/', b'(_fl"Oj/]"4-}=']


def assert_on_earth(p: Position) -> None:
    assert -90 <= p.lat <= 90 and -180 <= p.lon <= 180
    assert p.speed_kmh is None or (math.isfinite(p.speed_kmh) and p.speed_kmh >= 0)
    assert p.course_deg is None or 0 <= p.course_deg < 360
    assert p.altitude_m is None or math.isfinite(p.altitude_m)
    assert 0 <= p.ambiguity <= 4


@given(
    st.floats(min_value=-90, max_value=90),
    st.floats(min_value=-180, max_value=180),
    st.integers(min_value=0, max_value=359),
    st.floats(min_value=0, max_value=799 * KNOT_KMH),
    st.tuples(*[st.integers(min_value=0, max_value=1)] * 3),
    st.sampled_from(TABLES),
    st.integers(min_value=33, max_value=126),
)
def test_a_mice_packet_parses_back_within_its_resolution(
    lat: float, lon: float, course: int, speed: float, message: tuple[int, int, int], table: str, code: int
) -> None:
    """parse_mice of mice_packet gives the place, course, speed, symbol and message that went in."""
    destination, info = mice_packet(lat, lon, table, chr(code), course, speed, message=message)
    p = parse_mice(destination, info[1:], NOW)
    assert abs(p.lat - lat) <= HALF_HUNDREDTH
    largest = MAX_LON_HUNDREDTHS / HUNDREDTHS_PER_DEGREE
    assert abs(p.lon - math.copysign(min(abs(lon), largest), lon)) <= HALF_HUNDREDTH
    assert p.course_deg == course
    assert p.speed_kmh is not None and abs(p.speed_kmh - speed) <= KNOT_KMH / 2 + 1e-9
    assert (p.symbol_table, p.symbol_code) == (table, chr(code))
    name = STANDARD[message[0] * 4 + message[1] * 2 + message[2]]
    assert p.comment == ("" if message == OFF_DUTY else f"Mic-E: {name}")
    assert_on_earth(p)


@given(st.sampled_from(DESTINATIONS) | mutated_text(DESTINATIONS), mutated(BODIES))
def test_a_damaged_mice_packet_is_refused_with_mice_error_or_is_on_earth(destination: str, body: bytes) -> None:
    """parse_mice of a damaged real packet raises nothing but MicEError and returns a place on the Earth."""
    try:
        p = parse_mice(destination, body, NOW)
    except MicEError:
        return
    assert_on_earth(p)


@given(st.text(max_size=12), st.binary(max_size=40))
def test_parse_mice_refuses_anything_with_mice_error_only(destination: str, body: bytes) -> None:
    """parse_mice of any destination and body raises nothing but MicEError."""
    try:
        assert_on_earth(parse_mice(destination, body, NOW))
    except MicEError:
        pass


@given(st.sampled_from(DESTINATIONS), mutated(BODIES))
def test_the_parser_never_raises_on_a_damaged_mice_packet(destination: str, body: bytes) -> None:
    """parse of a damaged Mic-E field gives a Decoded; a position in it is on the Earth."""
    decoded = parse(b"`" + body, "OH2XYZ", destination, NOW)
    if isinstance(decoded, Position):
        assert_on_earth(decoded)


def test_a_kelvin_sign_in_a_mice_comment_is_text() -> None:
    """A Kelvin sign, which folds to K, names no microwave band: the comment stays text."""
    decoded = parse(b'`(_fn"Oj/\xe2\x84\xaa12.345MHz', "OH2XYZ", "S32U6T", NOW)
    assert not isinstance(decoded, Undecoded)
    assert isinstance(decoded, Position) and decoded.frequency is None
