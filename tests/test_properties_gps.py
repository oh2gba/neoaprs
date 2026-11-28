"""Properties of the GPS readers: an RMC sentence made from a place gives back that place within a metre;
any line, real sentences damaged with or without a fresh checksum above all, and any gpsd report never
raise; a fix is on the earth with a speed of 0 or more, a course under 360 and nothing that is NaN.
"""

import math
from datetime import timedelta
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from neoaprs.clock import utc
from neoaprs.gpsfix import Fix, GpsdFixes, NmeaFixes, fix_from_gpsd, satellites_of_sky
from tests.support.gps import gga, nmea, rmc, sky, tpv
from tests.support.mutation import mutated_json, mutated_text

NOW = utc(2026, 10, 25, 12, 35, 19)
REAL_SENTENCES = [
    "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A",
    "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47",
    rmc(-33.8688, -151.2093, 5.0, 359.6).strip(),
    rmc(60.0, 24.0, valid=False).strip(),
    gga(60.43, 24.145, 12.0, 11).strip(),
    gga(0.0, 0.0, quality=0).strip(),
    "$GPGSV,3,1,12,01,40,083,46,02,17,308,41,12,07,344,39,14,22,228,45*75",
]


def in_domain(fix: Fix | None) -> None:
    if fix is None:
        return
    assert -90 <= fix.lat <= 90 and -180 <= fix.lon <= 180
    assert fix.speed_kmh is None or (math.isfinite(fix.speed_kmh) and fix.speed_kmh >= 0)
    assert fix.course_deg is None or 0 <= fix.course_deg < 360
    assert fix.altitude_m is None or math.isfinite(fix.altitude_m)
    assert fix.satellites is None or fix.satellites >= 0


def rechecked(line: str) -> str:
    """The damaged sentence with a checksum that is right for what is left of it."""
    body = line.split("*")[0].removeprefix("$")
    return nmea(body).strip()


@given(st.floats(-89.9, 89.9), st.floats(-179.9, 179.9), st.floats(0, 999), st.floats(0, 359.4))
def test_an_rmc_sentence_gives_back_its_place_speed_and_course(
    lat: float, lon: float, knots: float, course: float
) -> None:
    """A sentence made from a place, speed and course gives them back: the place within a metre."""
    fix = NmeaFixes().feed(rmc(lat, lon, knots, course), NOW)
    assert fix is not None
    assert abs(fix.lat - lat) < 1e-5 and abs(fix.lon - lon) < 1e-5
    assert fix.course_deg == round(round(course, 1)) % 360
    assert fix.speed_kmh is not None and abs(fix.speed_kmh - round(knots, 1) * 1.852) < 1e-6


@given(
    st.lists(
        st.one_of(
            st.sampled_from(REAL_SENTENCES).flatmap(mutated_text),
            st.sampled_from(REAL_SENTENCES).flatmap(mutated_text).map(rechecked),
            st.text(max_size=80),
        ),
        max_size=6,
    )
)
def test_any_nmea_line_never_raises_and_a_fix_is_in_its_domain(lines: list[str]) -> None:
    """A stream of any lines, damaged real sentences above all, gives fixes on the earth or None."""
    fixes = NmeaFixes()
    for n, line in enumerate(lines):
        in_domain(fixes.feed(line, NOW + timedelta(seconds=n)))
        in_domain(fixes.fix)


@given(st.binary(max_size=80))
def test_any_bytes_from_the_receiver_never_raise(line: bytes) -> None:
    """Bytes that are no text at all are read without raising."""
    in_domain(NmeaFixes().feed(b"$GPRMC," + line, NOW))


REAL_REPORTS: list[dict[str, Any]] = [
    tpv(60.17, 24.94),
    {"class": "TPV", "mode": 3, "lat": 60.0, "lon": 24.0, "altHAE": 52.0, "altMSL": 31.0, "speed": 3.2, "track": 359.7},
    sky(7),
    {"class": "SKY", "satellites": [{"PRN": 1, "used": True}, {"PRN": 2, "used": False}]},
]


@given(st.lists(st.sampled_from(REAL_REPORTS).flatmap(mutated_json), max_size=5))
def test_any_gpsd_report_never_raises_and_a_fix_is_in_its_domain(reports: list[object]) -> None:
    """Damaged TPV and SKY reports give fixes on the earth or None, and a count of satellites of 0 or more."""
    fixes = GpsdFixes()
    for report in reports:
        if not isinstance(report, dict):
            continue
        in_domain(fixes.feed(report, NOW))
        in_domain(fix_from_gpsd(report, NOW))
        used = satellites_of_sky(report)
        assert used is None or used >= 0
