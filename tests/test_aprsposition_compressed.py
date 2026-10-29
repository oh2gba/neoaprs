"""The compressed position a moving station sends (neoaprs/aprsposition.py `compressed_position`, `altitude_text`, `compressed_comment`), against the specification's worked example, the decoder of the same module, and
the layout of chapter 9: 13 bytes `/YYYYXXXX$csT`."""
import pytest

from neoaprs.aprsposition import COMPRESSED_COMMENT_MAX, altitude_text, compressed_comment, compressed_position, parse_position
from neoaprs.clock import utc
from neoaprs.units import FOOT_M, KNOT_KMH

NOW = utc(2026, 10, 25, 12, 0, 0)


def decoded(info: bytes):                                                  # type: ignore[no-untyped-def]
    return parse_position(info, NOW)


def test_the_specifications_example_comes_out_with_the_same_course_speed_and_type_bytes() -> None:
    """49 30' N, 72 45' W, 36.2 knots, 88 degrees, an RMC fix compressed by software: `/5L!!<*e7>7P[`. The specification truncates the longitude's last character, `7`; this rounds to the nearest, which is `8`
    (half a metre further east)."""
    made = compressed_position(49.5, -72.75, "/", ">", 88, 36.2 * KNOT_KMH)
    assert made == b"/5L!!<*e8>7P["
    assert made[:5] == b"/5L!!" and made[9:] == b">7P[" and len(made) == 13
    assert decoded(b"/5L!!<*e7>7P[").lon == pytest.approx(decoded(made).lon, abs=1 / 190463 + 1e-9), "one step of the last character: half a metre"


def test_a_known_fix_gives_exactly_these_bytes() -> None:
    assert compressed_position(60.43, 24.145, "/", ">", 270, 54.0) == b"//w5#TW?M>eM["
    assert compressed_position(60.17, 24.94, "/", "-") == b"/0(1DTiYG- sT"


def test_a_position_with_no_course_or_no_speed_is_the_blank_form_the_specification_shows() -> None:
    """`=/5L!!<*e7> sTComment`: a space in c says there is no course, speed, radio range or altitude; `sT` are fillers."""
    assert compressed_position(49.5, -72.75, "/", ">")[9:] == b"> sT"
    assert compressed_position(49.5, -72.75, "/", ">", course_deg=88)[9:] == b"> sT"
    assert compressed_position(49.5, -72.75, "/", ">", speed_kmh=10.0)[9:] == b"> sT"
    p = decoded(compressed_position(49.5, -72.75, "/", ">") + b"x")
    assert (p.course_deg, p.speed_kmh, p.altitude_m, p.comment) == (None, None, None, "x")


@pytest.mark.parametrize(("lat", "lon"), [(60.17, 24.94), (60.43, 24.145), (-33.8688, 151.2093), (0.0, 0.0), (89.9999, 179.9999), (-89.9999, -179.9999), (90.0, -180.0), (-90.0, 180.0), (0.00001, -0.00001), (51.5007, -0.1246)])
def test_the_position_reads_back_within_the_precision_the_specification_gives(lat: float, lon: float) -> None:
    p = decoded(compressed_position(lat, lon, "/", ">", 90, 10.0))
    assert p.compressed and (p.lat, p.lon) == (pytest.approx(lat, abs=0.5 / 380926 + 1e-9), pytest.approx(lon, abs=0.5 / 190463 + 1e-9))
    assert abs(p.lat - lat) * 111195 < 0.2 and p.symbol_code == ">", "a fifth of a metre"


@pytest.mark.parametrize(("course", "speed_kmh"), [(0, 5.0), (1, 5.0), (2, 5.0), (88, 67.0), (90, 100.0), (179, 20.0), (270, 54.0), (358, 120.0), (359, 120.0), (45, 0.2)])
def test_the_course_and_speed_read_back_within_four_degrees_and_a_few_percent(course: int, speed_kmh: float) -> None:
    p = decoded(compressed_position(60.0, 24.0, "/", ">", course, speed_kmh))
    assert p.course_deg is not None and p.speed_kmh is not None
    assert min((p.course_deg - course) % 360, (course - p.course_deg) % 360) <= 2
    assert p.speed_kmh == pytest.approx(speed_kmh, rel=0.04, abs=0.25 * KNOT_KMH)


def test_a_speed_of_nothing_with_a_course_is_course_and_no_speed() -> None:
    made = compressed_position(60.0, 24.0, "/", ">", 90, 0.0)
    assert made[10:12] == bytes((33 + 22, 33)), "c is 90/4 and s is 0"
    p = decoded(made)
    assert (p.course_deg, p.speed_kmh) == (88, 0.0), "90 degrees is 22.5 steps of 4: 88"


def test_a_course_due_north_with_a_speed_is_read_as_north_not_as_no_course() -> None:
    p = decoded(compressed_position(60.0, 24.0, "/", ">", 0, 30.0))
    assert p.course_deg == 0 and p.speed_kmh == pytest.approx(30.0, rel=0.04)
    assert decoded(b"/5L!!<*e7>!!A").course_deg is None, "c and s both 0 is still no data"


def test_the_speed_is_held_to_what_the_byte_holds() -> None:
    made = compressed_position(60.0, 24.0, "/", ">", 90, 5000.0)
    assert made[11] == 33 + 90
    assert decoded(made).speed_kmh == pytest.approx((1.08 ** 90 - 1) * KNOT_KMH)


def test_the_type_byte_says_a_current_fix_from_an_rmc_sentence_compressed_by_software() -> None:
    t = compressed_position(60.0, 24.0, "/", ">", 90, 10.0)[12] - 33
    assert (t >> 5) & 1 == 1 and (t >> 3) & 3 == 0b11 and t & 7 == 0b010 and t == 58 and chr(t + 33) == "["


@pytest.mark.parametrize(("table", "written"), [("/", "/"), ("\\", "\\"), ("A", "A"), ("Z", "Z"), ("0", "a"), ("5", "f"), ("9", "j")])
def test_a_digit_overlay_is_written_a_to_j(table: str, written: str) -> None:
    made = compressed_position(60.0, 24.0, table, ">", 90, 10.0)
    assert made[:1].decode() == written and decoded(made).symbol_table == table


@pytest.mark.parametrize("args", [
    (91.0, 0.0, "/", ">"), (-90.5, 0.0, "/", ">"), (0.0, 180.5, "/", ">"), (0.0, -181.0, "/", ">"), (float("nan"), 0.0, "/", ">"),
    (60.0, 24.0, "", ">"), (60.0, 24.0, "ab", ">"), (60.0, 24.0, "!", ">"), (60.0, 24.0, "/", ""), (60.0, 24.0, "/", ">>"), (60.0, 24.0, "/", " ")])
def test_a_position_or_a_symbol_that_is_not_one_is_refused(args: tuple[float, float, str, str]) -> None:
    with pytest.raises(ValueError):
        compressed_position(*args)


def test_the_bytes_are_all_base_91_characters_except_the_symbols() -> None:
    for lat, lon in [(90.0, -180.0), (-90.0, 180.0), (0.0, 0.0)]:
        made = compressed_position(lat, lon, "/", ">", 359, 300.0)
        assert all(33 <= b <= 123 for b in made[1:9] + made[10:13])


# ---- the altitude and the comment

@pytest.mark.parametrize(("metres", "text"), [(0.0, "/A=000000"), (31.4, "/A=000103"), (1234 * FOOT_M, "/A=001234"), (8848.0, "/A=029029"), (-3.0, "/A=-00010"), (-100000.0, "/A=-99999"), (1e9, "/A=999999")])
def test_the_altitude_is_six_digits_of_feet_with_a_sign_below_sea_level(metres: float, text: str) -> None:
    assert altitude_text(metres) == text
    assert parse_position(b"/5L!!<*e7> sT" + text.encode(), NOW).altitude_m is not None


def test_the_comment_of_a_compressed_position_is_the_altitude_and_then_the_stations_comment() -> None:
    assert compressed_comment(31.4, "NeoAPRS") == "/A=000103NeoAPRS"
    assert compressed_comment(None, "NeoAPRS") == "NeoAPRS"
    assert compressed_comment(None, "") == "" and compressed_comment(100.0, "") == "/A=000328"


def test_a_long_comment_is_cut_to_the_forty_characters_a_compressed_report_may_have_altitude_included() -> None:
    long = "x" * 43
    assert COMPRESSED_COMMENT_MAX == 40
    assert compressed_comment(None, long) == "x" * 40
    with_altitude = compressed_comment(31.4, long)
    assert with_altitude == "/A=000103" + "x" * 31 and len(with_altitude) == 40


def test_the_altitude_and_the_comment_read_back() -> None:
    p = decoded(compressed_position(60.43, 24.145, "/", ">", 270, 54.0) + compressed_comment(31.4, "NeoAPRS mobile").encode())
    assert p.altitude_m == pytest.approx(31.4, abs=FOOT_M) and p.comment == "NeoAPRS mobile" and p.compressed


@pytest.mark.parametrize("cs", [b"!\x01", b"\x10!", b"\x1f\x1f", b"!\x7f", b"\x7f!", b"|!", b"~!", b"!~", b"!\xff", b"\xff\xff"])
def test_cs_bytes_that_are_not_base_91_digits_are_no_course_and_speed(cs: bytes) -> None:
    p = decoded(b"/5L!!<*e7>" + cs + b"[")
    assert (p.course_deg, p.speed_kmh, p.altitude_m, p.extensions) == (None, None, None, None)


@pytest.mark.parametrize("cs", [b"!\x01", b"\x10!", b"!\x7f", b"\x7f!"])
def test_cs_bytes_that_are_not_base_91_digits_are_no_altitude_and_no_wind_either(cs: bytes) -> None:
    assert decoded(b"/5L!!<*e7>" + cs + b"\x35").altitude_m is None            # (T = 0x35: a GGA fix, cs is an altitude)
    assert decoded(b"/5L!!<*e7_" + cs + b"[").weather is None


def test_the_cs_digits_at_the_ends_of_their_range_are_read() -> None:
    p = decoded(b"/5L!!<*e7>z![")                       # c = 89 (the last course step): 356 degrees; s = 0
    assert (p.course_deg, p.speed_kmh) == (356, 0.0)
    q = decoded(b"/5L!!<*e7>!{[")                       # c = 0, s = 90: north at the greatest speed that cs can hold
    assert q.course_deg == 0 and q.speed_kmh == pytest.approx((1.08 ** 90 - 1) * KNOT_KMH)
