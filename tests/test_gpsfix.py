"""A GPS fix from what a receiver says (neoaprs/gpsfix.py): NMEA sentences with their checksums, a stream of them, and gpsd's TPV and SKY reports."""
from datetime import datetime

import pytest

from neoaprs.clock import utc
from neoaprs.gpsfix import Fix, GpsdFixes, NmeaFixes, fix_from_gpsd, satellites_of_sky
from tests.support.gps import gga, nmea, rmc, sky, tpv

NOW = utc(2026, 10, 25, 12, 35, 19)
KNOT_KMH = 1.852


def fix_from_nmea(line: str | bytes, now: datetime) -> Fix | None:
    """The fix of one sentence on its own."""
    return NmeaFixes().feed(line, now)


# ---- one NMEA sentence --------------------------------------------------------------------------------------------------------------------------------

def test_the_rmc_sentence_of_the_nmea_documentation_gives_position_speed_and_course() -> None:
    fix = fix_from_nmea("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n", NOW)
    assert fix == Fix(pytest.approx(48.1173), pytest.approx(11.516667), NOW, pytest.approx(22.4 * KNOT_KMH), 84, None, None)       # type: ignore[arg-type]


def test_the_gga_sentence_of_the_nmea_documentation_gives_position_altitude_and_satellites() -> None:
    fix = fix_from_nmea(b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47", NOW)
    assert fix == Fix(pytest.approx(48.1173), pytest.approx(11.516667), NOW, None, None, 545.4, 8)       # type: ignore[arg-type]


def test_the_position_is_south_and_west_with_the_signs() -> None:
    fix = fix_from_nmea(rmc(-33.8688, -151.2093, 5.0, 359.6), NOW)
    assert fix is not None and (fix.lat, fix.lon) == (pytest.approx(-33.8688, abs=1e-5), pytest.approx(-151.2093, abs=1e-5)) and fix.course_deg == 0, "359.6 degrees is north"


def test_the_fix_is_stamped_with_the_time_it_was_read_not_the_receivers() -> None:
    fix = fix_from_nmea(rmc(60.43, 24.145, 1.0, 10.0, time="010101", date="010100"), NOW)
    assert fix is not None and fix.at == NOW, "a receiver that has just started may not know the date"


@pytest.mark.parametrize("line", [
    "$GPGSV,3,1,12,01,40,083,46,02,17,308,41,12,07,344,39,14,22,228,45*75", "$GPVTG,084.4,T,081.3,M,022.4,N,041.5,K*43", "$GPGSA,A,3,04,05,,09,12,,,24,,,,,2.5,1.3,2.1*39",
    "", "garbage", "$GPRMC", "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*00"])
def test_other_sentences_and_damaged_ones_give_no_fix(line: str) -> None:
    assert fix_from_nmea(line, NOW) is None


@pytest.mark.parametrize("line", [rmc(0, 0, valid=False), gga(0, 0, quality=0)])
def test_a_sentence_that_says_there_is_no_fix_gives_none(line: str) -> None:
    assert fix_from_nmea(line, NOW) is None


def test_the_talker_may_be_any() -> None:
    for talker in ("GN", "GL", "GA", "BD"):
        body = rmc(60.43, 24.145, 2.0, 90.0).strip().split("*")[0][1:].replace("GP", talker, 1)
        fix = fix_from_nmea(nmea(body), NOW)
        assert fix is not None and fix.course_deg == 90


# ---- a stream ---------------------------------------------------------------------------------------------------------------------------------------------

def test_a_stream_puts_the_latest_gga_into_the_fix_of_the_rmc() -> None:
    stream = NmeaFixes()
    assert stream.feed(gga(60.43, 24.145, altitude=31.4, satellites=9), NOW) is not None, "a GGA alone is a fix, with no speed"
    fix = stream.feed(rmc(60.43, 24.145, 27.0, 270.0), NOW)
    assert fix is not None and (fix.speed_kmh, fix.course_deg, fix.altitude_m, fix.satellites) == (pytest.approx(27.0 * KNOT_KMH), 270, 31.4, 9)
    assert stream.fix == fix


def test_a_receiver_that_sends_both_gives_one_fix_a_second_from_the_rmc() -> None:
    stream = NmeaFixes()
    fixes = [stream.feed(line, NOW) for line in (rmc(60.43, 24.145, 27.0, 270.0), gga(60.43, 24.145), rmc(60.4301, 24.146, 27.0, 270.0), gga(60.4301, 24.146))]
    assert [f is not None for f in fixes] == [True, False, True, False]
    assert fixes[2] is not None and fixes[2].altitude_m == 31.4 and fixes[2].satellites == 9


def test_an_old_gga_is_not_put_into_a_later_fix() -> None:
    stream = NmeaFixes()
    stream.feed(gga(60.43, 24.145), NOW)
    fix = stream.feed(rmc(60.43, 24.145, 1.0, 10.0), NOW.replace(second=40))
    assert fix is not None and (fix.altitude_m, fix.satellites) == (None, None)


def test_a_sentence_without_a_fix_clears_the_fix_and_the_next_one_with_a_fix_brings_it_back() -> None:
    stream = NmeaFixes()
    assert stream.feed(rmc(60.43, 24.145, 1.0, 10.0), NOW) is not None and stream.fix is not None
    assert stream.feed(rmc(0, 0, valid=False), NOW) is None
    assert stream.fix is None and stream.said_none
    assert stream.feed("$GPGSV,3,1,12*00", NOW) is None and not stream.said_none
    assert stream.feed(rmc(60.44, 24.146, 1.0, 10.0), NOW) is not None and stream.fix is not None


def test_a_gga_without_a_fix_clears_the_altitude_too() -> None:
    stream = NmeaFixes()
    stream.feed(gga(60.43, 24.145), NOW)
    stream.feed(gga(0, 0, quality=0), NOW)
    fix = stream.feed(rmc(60.43, 24.145, 1.0, 10.0), NOW)
    assert fix is not None and fix.altitude_m is None


def test_a_damaged_sentence_is_counted_and_changes_nothing() -> None:
    stream = NmeaFixes()
    good = stream.feed(rmc(60.43, 24.145, 1.0, 10.0), NOW)
    assert stream.feed("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6B", NOW) is None
    assert stream.damaged == 1 and stream.fix == good and not stream.said_none


@pytest.mark.parametrize("line", [
    "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W",            # the end of the line was lost
    "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*",
    "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6",           # and one digit of the checksum with it
    "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"])
def test_a_sentence_with_no_checksum_or_a_cut_one_is_damaged_and_changes_nothing(line: str) -> None:
    stream = NmeaFixes()
    good = stream.feed(rmc(60.43, 24.145, 1.0, 10.0), NOW)
    assert stream.feed(line, NOW) is None
    assert stream.damaged == 1 and stream.fix == good and not stream.said_none


@pytest.mark.parametrize("error", [ValueError("not a number"), OverflowError("cannot convert float infinity to integer")])
def test_a_sentence_the_parser_cannot_make_sense_of_is_damaged_and_never_raised(error: Exception, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr("neoaprs.gpsfix.parse_nmea", refuse)
    stream = NmeaFixes()
    assert stream.feed(rmc(60.43, 24.145, 1.0, 10.0), NOW) is None
    assert stream.damaged == 1 and stream.fix is None


def test_a_stationary_receiver_with_no_course_has_a_speed_and_no_course() -> None:
    fix = fix_from_nmea(rmc(60.43, 24.145, 0.0, None), NOW)
    assert fix is not None and (fix.speed_kmh, fix.course_deg) == (0.0, None)


# ---- gpsd ---------------------------------------------------------------------------------------------------------------------------------------------

def test_a_tpv_report_gives_the_fix_in_kilometres_per_hour_and_whole_degrees() -> None:
    fix = fix_from_gpsd(tpv(60.43, 24.145, speed=15.0, track=269.6, alt=31.4), NOW, satellites=9)
    assert fix == Fix(60.43, 24.145, NOW, pytest.approx(54.0), 270, 31.4, 9)       # type: ignore[arg-type]


def test_a_tpv_report_of_2d_has_no_altitude_and_one_without_speed_or_track_has_none() -> None:
    fix = fix_from_gpsd({"class": "TPV", "mode": 2, "lat": 60.0, "lon": 24.0}, NOW)
    assert fix == Fix(60.0, 24.0, NOW, None, None, None, None)


def test_the_altitude_is_above_sea_level_when_gpsd_says_so() -> None:
    both = {"class": "TPV", "mode": 3, "lat": 60.0, "lon": 24.0, "altHAE": 52.0, "altMSL": 31.0}
    assert fix_from_gpsd(both, NOW).altitude_m == 31.0                              # type: ignore[union-attr]
    assert fix_from_gpsd({**both, "alt": 30.0}, NOW).altitude_m == 31.0             # type: ignore[union-attr]
    assert fix_from_gpsd({"class": "TPV", "mode": 3, "lat": 60.0, "lon": 24.0, "alt": 30.0, "altHAE": 52.0}, NOW).altitude_m == 30.0       # type: ignore[union-attr]
    assert fix_from_gpsd({"class": "TPV", "mode": 3, "lat": 60.0, "lon": 24.0, "altHAE": 52.0}, NOW).altitude_m == 52.0                  # type: ignore[union-attr]


@pytest.mark.parametrize("report", [
    {"class": "TPV", "mode": 1}, {"class": "TPV", "mode": 0, "lat": 60.0, "lon": 24.0}, {"class": "TPV", "mode": 3}, {"class": "TPV", "mode": 3, "lat": 91.0, "lon": 24.0},
    {"class": "TPV", "mode": 3, "lat": 60.0, "lon": "x"}, {"class": "TPV", "mode": 3, "lat": float("nan"), "lon": 24.0}, {"class": "TPV", "mode": True, "lat": 60.0, "lon": 24.0},
    {"class": "SKY", "mode": 3, "lat": 60.0, "lon": 24.0}, {"mode": 3, "lat": 60.0, "lon": 24.0}, {"class": "VERSION", "release": "3.25"}])
def test_a_report_that_is_no_fix_gives_none(report: dict[str, object]) -> None:
    assert fix_from_gpsd(report, NOW) is None


def test_a_sky_report_counts_the_satellites_used() -> None:
    assert satellites_of_sky(sky(used=7, seen=12)) == 7
    assert satellites_of_sky({"class": "SKY", "satellites": [{"PRN": 1, "used": True}, {"PRN": 2, "used": False}, {"PRN": 3, "used": True}]}) == 2
    assert satellites_of_sky({"class": "SKY", "uSat": 0}) == 0
    assert satellites_of_sky({"class": "SKY"}) is None


def test_the_stream_of_gpsd_reports_puts_the_satellites_of_the_sky_into_the_fix() -> None:
    stream = GpsdFixes()
    assert stream.feed({"class": "VERSION"}, NOW) is None
    first = stream.feed(tpv(60.43, 24.145), NOW)
    assert first is not None and first.satellites is None
    assert stream.feed(sky(used=8), NOW) is None
    second = stream.feed(tpv(60.43, 24.146), NOW)
    assert second is not None and second.satellites == 8
    assert stream.feed(tpv(None, None, mode=1), NOW) is None and stream.fix is None and stream.said_none
    assert stream.feed(sky(used=9), NOW) is None and not stream.said_none
