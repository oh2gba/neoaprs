"""Positions: the timestamp resolution, the coordinates, the extensions and the compressed form."""
from datetime import UTC, datetime, timedelta, timezone

import pytest

from neoaprs.aprsposition import PositionError, degrees, motion, parse_position, resolve_mdhm, resolve_timestamp

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
BODY = b"4903.50N/07201.75W-"


def compress_position(lat: float, lon: float, symbol_table: str, symbol_code: str) -> bytes:
    """A compressed position without course, speed or altitude, to feed the parser: symbol table, latitude, longitude, symbol code, "  " (no cs) and the type byte "#"."""
    y = min(max(round((90 - lat) * 380926), 0), 91 ** 4 - 1)
    x = min(max(round((180 + lon) * 190463), 0), 91 ** 4 - 1)
    table_byte = chr(ord(symbol_table) - ord("0") + ord("a")) if symbol_table.isdigit() else symbol_table      # overlays 0-9 are written a-j
    return (table_byte + _base91_text(y) + _base91_text(x) + symbol_code + "  #").encode("ascii")


def _base91_text(v: int) -> str:
    return "".join(chr(33 + v // 91 ** i % 91) for i in (3, 2, 1, 0))


def at(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[arg-type]


@pytest.mark.parametrize(("raw", "now", "want"), [
    (b"211200z", NOW, at(2026, 10, 21, 12)),
    (b"211204z", NOW, at(2026, 10, 21, 12, 4)),                       # four minutes ahead is allowed
    (b"211259z", NOW, at(2026, 10, 21, 12, 59)),                      # so is an hour: a station's clock is often fast
    (b"211301z", NOW, at(2026, 9, 21, 13, 1)),                        # more than an hour is not: it is last month
    (b"092345z", NOW, at(2026, 10, 9, 23, 45)),
    (b"302345z", NOW, at(2026, 9, 30, 23, 45)),                       # a day that has not come this month
    (b"312345z", NOW, at(2026, 8, 31, 23, 45)),                       # September has no 31st
    (b"290000z", at(2026, 3, 1), at(2026, 1, 29)),                     # 2026 has no 29 February: the 29th before it is January's
    (b"010001z", at(2026, 10, 31, 23, 58), at(2026, 11, 1, 0, 1)),   # three minutes ahead across the month's end
    (b"280000z", at(2026, 1, 2), at(2025, 12, 28)),
    (b"092345/", NOW, at(2026, 10, 9, 23, 45)),
    (b"115900h", NOW, at(2026, 10, 21, 11, 59)),
    (b"120300h", NOW, at(2026, 10, 21, 12, 3)),
    (b"120600h", NOW, at(2026, 10, 21, 12, 6)),
    (b"130100h", NOW, at(2026, 10, 20, 13, 1)),                       # more than an hour ahead: yesterday
    (b"235959h", at(2026, 10, 21, 0, 1), at(2026, 10, 20, 23, 59, 59)),
])
def test_timestamps(raw: bytes, now: datetime, want: datetime) -> None:
    assert resolve_timestamp(raw, now) == want


@pytest.mark.parametrize("raw", [b"092345x", b"09234z", b"09a345z", b"002345z", b"322345z", b"092445z", b"092360z", b"246000h", b"126100h", b"120060h", b"", b"0923455z"])
def test_bad_timestamps(raw: bytes) -> None:
    with pytest.raises(PositionError):
        resolve_timestamp(raw, NOW)


def test_the_timestamp_is_resolved_against_a_clock_in_another_zone() -> None:
    helsinki = NOW.astimezone(timezone(timedelta(hours=3)))
    assert resolve_timestamp(b"211159z", helsinki) == at(2026, 10, 21, 11, 59)


def test_plain_uncompressed() -> None:
    p = parse_position(BODY + b"Test", NOW)
    assert (p.lat, p.lon, p.symbol_table, p.symbol_code, p.comment) == (pytest.approx(49 + 3.5 / 60), pytest.approx(-(72 + 1.75 / 60)), "/", "-", "Test")
    assert (p.timestamp, p.messaging, p.compressed, p.ambiguity) == (None, False, False, 0)


def test_hemispheres() -> None:
    p = parse_position(b"3345.00S/15112.50E>", NOW)
    assert (p.lat, p.lon) == (pytest.approx(-33.75), pytest.approx(151 + 12.5 / 60))
    p = parse_position(b"0000.00N/00000.00E>", NOW)
    assert (p.lat, p.lon) == (0.0, 0.0)
    p = parse_position(b"9000.00S/18000.00W>", NOW)
    assert (p.lat, p.lon) == (-90.0, -180.0)


def test_messaging_is_the_callers_word() -> None:
    assert parse_position(BODY, NOW, messaging=True).messaging is True
    assert parse_position(b"092345z" + BODY, NOW, messaging=True).timestamp == at(2026, 10, 9, 23, 45)


@pytest.mark.parametrize(("lat", "lon", "n", "want_lat", "want_lon"), [
    (b"4903.50N", b"07201.75W", 0, 49 + 3.5 / 60, -(72 + 1.75 / 60)),
    (b"4903.5 N", b"07201.7 W", 1, 49 + 3.55 / 60, -(72 + 1.75 / 60)),
    (b"4903.  N", b"07201.  W", 2, 49 + 3.5 / 60, -(72 + 1.5 / 60)),
    (b"490 .  N", b"0720 .  W", 3, 49 + 5 / 60, -(72 + 5 / 60)),
    (b"49  .  N", b"072  .  W", 4, 49.5, -72.5),
])
def test_ambiguity_is_counted_and_centred(lat: bytes, lon: bytes, n: int, want_lat: float, want_lon: float) -> None:
    p = parse_position(lat + b"/" + lon + b"-", NOW)
    assert (p.ambiguity, p.lat, p.lon) == (n, pytest.approx(want_lat), pytest.approx(want_lon))


@pytest.mark.parametrize("lat", [b"49 3.50N", b"4 03.50N", b"4903. 0N", b"4903.5xN"])
def test_blanks_must_be_trailing(lat: bytes) -> None:
    with pytest.raises(PositionError):
        parse_position(lat + b"/07201.75W-", NOW)


@pytest.mark.parametrize("body", [b"", b"4903.50N/07201.75W", b"4903.50N/0720", b"4903.50X/07201.75W-", b"4903.50N/07201.75X-", b"9103.50N/07201.75W-", b"4960.00N/07201.75W-",
                                  b"4903.50N/18101.75W-", b"4903.50N#07201.75W-", b"4903x50N/07201.75W-", b"4903.50N/07201.75W\x01", b"092345z", b"/5L!!<*e7>"])
def test_bad_bodies(body: bytes) -> None:
    with pytest.raises(PositionError):
        parse_position(body, NOW)


def test_course_and_speed_in_knots_become_kmh() -> None:
    p = parse_position(BODY[:-1] + b">088/036Hello", NOW)
    assert (p.course_deg, p.speed_kmh, p.comment) == (88, pytest.approx(36 * 1.852), "Hello")


def test_course_edge_cases() -> None:
    assert motion(360, 5) == (0, pytest.approx(9.26))
    assert motion(0, 5) == (None, pytest.approx(9.26))
    assert motion(90, 0) == (90, 0.0)
    assert motion(0, 0) == (None, None)
    p = parse_position(BODY + b"000/000x", NOW)
    assert (p.course_deg, p.speed_kmh, p.comment) == (None, None, "x")
    p = parse_position(BODY + b"361/010x", NOW)                         # not a course: stays text
    assert (p.course_deg, p.comment) == (None, "361/010x")


@pytest.mark.parametrize("extension, course, speed, comment", [
    (".../...", None, None, ""), (".../...Hi", None, None, "Hi"), ("   /   ", None, None, ""), ("   /   Hi", None, None, "Hi"), ("088/...", 88, None, ""), (".../036", None, pytest.approx(36 * 1.852), ""),
    ("088/036", 88, pytest.approx(36 * 1.852), ""), ("..../...", None, None, "..../...")])
def test_the_extension_that_says_course_and_speed_are_not_known_is_taken_off_the_comment(extension: str, course: int | None, speed: float | None, comment: str) -> None:
    p = parse_position(BODY + extension.encode(), NOW)
    assert (p.course_deg, p.speed_kmh, p.comment) == (course, speed, comment)


def test_the_unknown_course_and_speed_leave_a_df_bearing_after_them_to_be_read() -> None:
    p = parse_position(b"4903.50N/07201.75W\\.../.../270/729", NOW)
    assert p.extensions is not None and p.extensions.df_bearing is not None and p.extensions.df_bearing.bearing_deg == 270


def test_course_and_speed_only_at_the_start_of_the_comment() -> None:
    p = parse_position(BODY + b"Hi 088/036", NOW)
    assert (p.course_deg, p.comment) == (None, "Hi 088/036")


def test_altitude_anywhere_in_the_comment() -> None:
    assert parse_position(BODY + b"/A=012345", NOW).altitude_m == pytest.approx(12345 * 0.3048)
    p = parse_position(BODY + b"before /A=000100 after", NOW)
    assert (p.altitude_m, p.comment) == (pytest.approx(30.48), "before  after")
    assert parse_position(BODY + b"/A=-00100", NOW).altitude_m == pytest.approx(-30.48)
    assert parse_position(BODY + b"/A=12", NOW).altitude_m is None


def test_course_speed_phg_and_altitude_together() -> None:
    p = parse_position(BODY + b"090/036PHG5132 /A=000500", NOW)
    assert (p.course_deg, p.comment, p.altitude_m) == (90, "PHG5132", pytest.approx(152.4))


def test_a_comment_loses_its_surrounding_whitespace_and_keeps_utf_8() -> None:
    assert parse_position(BODY + "  Hyvää \r\n".encode(), NOW).comment == "Hyvää"


def test_the_spec_compressed_example() -> None:
    p = parse_position(b"/5L!!<*e7>7P[", NOW)
    assert p.compressed and (p.symbol_table, p.symbol_code) == ("/", ">")
    assert (p.lat, p.lon) == (pytest.approx(49.5), pytest.approx(-72.75, abs=1e-5))
    assert (p.course_deg, p.speed_kmh) == (88, pytest.approx((1.08 ** 47 - 1) * 1.852))


def test_compressed_altitude_and_no_cs() -> None:
    assert parse_position(b"/5L!!<*e7OS]S", NOW).altitude_m == pytest.approx(1.002 ** 4610 * 0.3048)
    p = parse_position(b"/5L!!<*e7> sTx", NOW)
    assert (p.course_deg, p.speed_kmh, p.altitude_m, p.comment) == (None, None, None, "x")


def test_compressed_range_and_weather_cs_are_not_motion() -> None:
    p = parse_position(b"/5L!!<*e7>{PA", NOW)                           # "{" in c: radio range
    assert (p.course_deg, p.speed_kmh, p.altitude_m) == (None, None, None)
    p = parse_position(b"/5L!!<*e7_7P[", NOW)                           # a weather station: wind, not motion
    assert (p.course_deg, p.speed_kmh) == (None, None)


def test_the_cs_bytes_of_a_compressed_weather_position_are_the_wind() -> None:
    """The spec's 7P: 88 degrees and 36.2 (miles per hour); the fields after the 13 bytes are the rest of the weather, and the wind of the fields does not replace the cs."""
    p = parse_position(b"/5L!!<*e7_7P[g005t077r000", NOW)
    assert p.weather is not None
    assert (p.weather.wind_dir, p.weather.wind_kmh, p.weather.gust_kmh, p.weather.temp_c) == (88, pytest.approx(58.3, abs=0.05), pytest.approx(8.0, abs=0.05), 25.0)
    alone = parse_position(b"/5L!!<*e7_7P[", NOW).weather
    assert alone is not None and (alone.wind_dir, alone.temp_c) == (88, None)
    calm = parse_position(b"/5L!!<*e7_!![", NOW).weather
    assert calm is not None and (calm.wind_dir, calm.wind_kmh) == (0, 0.0)
    assert parse_position(b"/5L!!<*e7_ sT", NOW).weather is None         # a space: no wind
    assert parse_position(b"/5L!!<*e7_{?!", NOW).weather is None         # "{": a range, not a wind


def test_compressed_stationary_has_no_motion() -> None:
    p = parse_position(b"/5L!!<*e7>!!A", NOW)
    assert (p.course_deg, p.speed_kmh) == (None, None)


def test_compressed_corners() -> None:
    assert (parse_position(b"/!!!!!!!!>  A", NOW).lat, parse_position(b"/!!!!!!!!>  A", NOW).lon) == (90.0, -180.0)
    with pytest.raises(PositionError):                                  # the largest base-91 number is beyond the south pole
        parse_position(b"/{{{{{{{{>  A", NOW)


def test_a_digit_overlay_in_a_compressed_position_is_written_a_to_j() -> None:
    assert parse_position(b"j5L!!<*e7>  A", NOW).symbol_table == "9"
    assert parse_position(b"S5L!!<*e7>  A", NOW).symbol_table == "S"


def test_degrees_helper() -> None:
    assert degrees(49, 350) == pytest.approx(49 + 3.5 / 60)
    assert degrees(49, 350, 4) == 49.5
    assert degrees(49, 0, 3) == pytest.approx(49 + 5 / 60)


def test_an_overlay_digit_is_written_as_a_letter_and_read_back() -> None:
    assert compress_position(0.0, 0.0, "5", "#")[0:1] == b"f"
    assert parse_position(compress_position(0.0, 0.0, "5", "#"), NOW).symbol_table == "5"


def test_the_time_111111z_of_a_permanent_object_is_no_time() -> None:
    p = parse_position(b"111111z4903.50N/07201.75W>x", NOW)
    assert (p.timestamp, p.timestamp_local, p.comment) == (None, False, "x")


def test_a_timestamp_that_is_none_leaves_the_position_without_a_time() -> None:
    p = parse_position(b"322345z4903.50N/07201.75W>x", NOW)             # the 32nd
    assert (p.timestamp, p.timestamp_local, p.lat, p.comment) == (None, False, pytest.approx(49.058333), "x")
    p = parse_position(b"092460/4903.50N/07201.75W>x", NOW)             # the 60th minute, local: no time, and not local either
    assert (p.timestamp, p.timestamp_local, p.comment) == (None, False, "x")


def test_a_local_timestamp_is_kept_as_sent_and_flagged() -> None:
    local, zulu = parse_position(b"092345/4903.50N/07201.75W>x", NOW), parse_position(b"092345z4903.50N/07201.75W>x", NOW)
    assert (local.timestamp, local.timestamp_local) == (zulu.timestamp, True) and not zulu.timestamp_local
    assert parse_position(b"4903.50N/07201.75W>x", NOW).timestamp_local is False


def test_the_mdhm_timestamp_of_a_weather_report() -> None:
    assert resolve_mdhm("10090556", NOW) == datetime(2026, 10, 9, 5, 56, tzinfo=UTC)
    assert resolve_mdhm("12312359", NOW) == datetime(2025, 12, 31, 23, 59, tzinfo=UTC)                  # not in the future
    assert resolve_mdhm("02291200", NOW) == datetime(2024, 2, 29, 12, 0, tzinfo=UTC)                    # the last leap day
    for bad in ("1009055", "100905560", "13090556", "ab090556", "10320556", "10092456"):
        with pytest.raises(PositionError):
            resolve_mdhm(bad, NOW)


def test_compress_position_corners_round_trip() -> None:
    for lat, lon in [(90.0, -180.0), (-90.0, 180.0), (0.0, 0.0), (60.17, 24.94), (-90.0, -180.0)]:
        p = parse_position(compress_position(lat, lon, "/", "-"), NOW)
        assert (p.lat, p.lon) == (pytest.approx(lat, abs=1e-5), pytest.approx(lon, abs=1e-5))
