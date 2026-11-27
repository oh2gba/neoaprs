"""The orbit maths of the satellites layer (neoaprs/satellites.py) and the server's file
(neoaprs/satellitelist.py), with the elements CelesTrak gave on 27 Nov 2026 (tests/fixtures/satellites).

A pass is checked against a computation written here apart: SGP4's pure-Python model initialised by
its own OMM reader, the station turned into TEME, the topocentric frame
of Vallado's rv2razel, GMST of IAU 2006, and a scan second by second."""

import csv
import io
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sgp4 import omm
from sgp4.api import jday
from sgp4.model import Satrec as PureSatrec

from neoaprs import satellites as sat
from neoaprs.satellitelist import MAX_ELEMENTS_AGE, read_file, shown
from tests.support.files import fixture_text

HELSINKI = sat.Station(60.17, 24.94, 20.0)
NOW = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)


def rows() -> dict[int, dict[str, str]]:
    return {
        int(row["NORAD_CAT_ID"]): row for row in csv.DictReader(io.StringIO(fixture_text("satellites/amateur.csv")))
    }


def orbit(number: int = 25544) -> sat.Orbit:
    made = sat.orbit_of(rows()[number])
    assert made is not None
    return made


# ---- the independent computation


def gmst06_rad(t: datetime) -> float:
    """GMST of IAU 2006: the earth rotation angle and the precession in right ascension (arcseconds)."""
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    days = jd - 2451545.0 + fr
    era = 2 * math.pi * (0.7790572732640 + 1.00273781191135448 * days)
    c = days / 36525.0
    arcsec = 0.014506 + 4612.156534 * c + 1.3915817 * c**2 - 0.00000044 * c**3
    return (era + math.radians(arcsec / 3600)) % (2 * math.pi)


def independent_elevation(record: dict[str, str], station: sat.Station, t: datetime) -> tuple[float, float]:
    """Elevation (degrees) and range (km) of the satellite, by SGP4's pure-Python model."""
    model = PureSatrec()
    omm.initialize(model, record)
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    error, r, _ = model.sgp4(jd, fr)
    assert error == 0
    a, e2 = 6378.137, 0.00669437999014
    lat, lon = math.radians(station.lat), math.radians(station.lon)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    h = station.alt_m / 1000
    theta = gmst06_rad(t) + lon  # the station's own sidereal angle
    site = (
        (n + h) * math.cos(lat) * math.cos(theta),
        (n + h) * math.cos(lat) * math.sin(theta),
        (n * (1 - e2) + h) * math.sin(lat),
    )
    rho = [r[i] - site[i] for i in range(3)]
    # south, east, zenith
    s = math.sin(lat) * math.cos(theta) * rho[0] + math.sin(lat) * math.sin(theta) * rho[1] - math.cos(lat) * rho[2]
    e = -math.sin(theta) * rho[0] + math.cos(theta) * rho[1]
    z = math.cos(lat) * math.cos(theta) * rho[0] + math.cos(lat) * math.sin(theta) * rho[1] + math.sin(lat) * rho[2]
    distance = math.sqrt(s * s + e * e + z * z)
    return math.degrees(math.asin(z / distance)), distance


def test_a_whole_pass_of_the_iss_agrees_with_the_independent_computation_to_seconds_and_a_tenth_of_a_degree() -> None:
    record = rows()[25544]
    found = sat.passes(orbit(), HELSINKI, NOW)
    assert found, "the ISS passes over Helsinki within a day"
    first = found[0]
    seconds = int((first.set - first.rise).total_seconds()) + 240
    start = first.rise - timedelta(seconds=120)
    scan = [
        (start + timedelta(seconds=n), *independent_elevation(record, HELSINKI, start + timedelta(seconds=n)))
        for n in range(seconds)
    ]
    up = [one for one in scan if one[1] >= 0]
    top = max(scan, key=lambda one: one[1])
    assert abs((up[0][0] - first.rise).total_seconds()) <= 3
    assert abs((up[-1][0] - first.set).total_seconds()) <= 3
    assert abs((top[0] - first.max_at).total_seconds()) <= 5
    assert abs(top[1] - first.max_el_deg) <= 0.1
    # the range rate is the change of range over a second
    (_, before), (_, after) = (
        independent_elevation(record, HELSINKI, first.rise + timedelta(seconds=d)) for d in (-0.5, 0.5)
    )
    assert abs((after - before) - first.rise_rate_km_sec) <= 0.02
    for t, elevation, _ in scan[::30]:
        seen = sat.look(orbit(), HELSINKI, t)
        assert seen is not None and abs(seen.el_deg - elevation) <= 0.1


def test_the_iss_doppler_is_about_3_5_khz_on_two_metres_and_10_5_on_seventy_centimetres_and_none_at_the_top() -> None:
    under = sat.Station(45.0, 10.0)  # under the ISS's track, where the passes go high
    found = sat.passes(orbit(), under, NOW, hours=24.0)
    assert found
    vhf = max(abs(sat.downlink_shift_hz(145.825e6, one.rise_rate_km_sec)) for one in found)
    uhf = max(abs(sat.downlink_shift_hz(437.825e6, one.set_rate_km_sec)) for one in found)
    assert 3200 <= vhf <= 3600 and 9700 <= uhf <= 10800
    assert all(abs(sat.downlink_shift_hz(437.825e6, one.max_rate_km_sec)) < 150 for one in found)
    # approaching: heard above the frequency, and the uplink sent below it
    rising = found[0].rise_rate_km_sec
    assert rising < 0 and sat.downlink_shift_hz(145.825e6, rising) > 0 and sat.uplink_shift_hz(145.825e6, rising) < 0


def test_passes_lower_than_ten_degrees_are_not_listed_and_one_under_way_comes_first_with_its_rise_past() -> None:
    every = sat.passes(orbit(), HELSINKI, NOW, lowest_deg=0.0)
    listed = sat.passes(orbit(), HELSINKI, NOW)
    assert len(every) > len(listed) and all(one.max_el_deg >= 10 for one in listed)
    assert [one for one in every if one.max_el_deg >= 10] == listed
    middle = listed[0].max_at
    during = sat.passes(orbit(), HELSINKI, middle)
    assert abs((during[0].rise - listed[0].rise).total_seconds()) <= 2 and during[0].rise < middle < during[0].set


def test_the_sub_point_height_footprint_and_period_of_the_iss() -> None:
    point = sat.sub_point(orbit(), NOW)
    assert point is not None and 400 < point.alt_km < 440 and abs(point.lat) <= 51.7
    assert sat.footprint_km(420.0) == pytest.approx(2252.4, abs=1.0)
    assert sat.footprint_km(420.0, 10.0) < sat.footprint_km(420.0)
    assert orbit().period_sec / 60 == pytest.approx(92.9, abs=0.1)
    track = sat.track(orbit(), NOW, orbit().period_sec, 60.0)
    assert len(track) == 93 and max(p.lat for _, p in track) == pytest.approx(51.6, abs=0.3)


def test_an_orbit_with_a_catalogue_number_above_99999_and_a_record_that_is_none() -> None:
    assert orbit(101098).id == 101098 and sat.sub_point(orbit(101098), NOW) is not None
    broken = dict(rows()[25544], MEAN_MOTION="x")
    assert sat.orbit_of(broken) is None
    assert sat.orbit_of(dict(rows()[25544], EPOCH="yesterday")) is None
    assert sat.orbit_of({}) is None


def served(**over: Any) -> dict[str, Any]:
    iss = {
        "id": 25544,
        "name": "ISS",
        "downlink": [{"mhz": 437.825, "sure": True}, {"mhz": 145.825, "sure": False}],
        "uplink": [{"mhz": 437.825, "sure": True}],
        "mode": {"value": "afsk1200", "sure": True},
        "path": {"value": "ARISS", "sure": False},
        "elements": rows()[25544],
    }
    return {
        "v": 1,
        "made": "2026-11-27T18:00:00Z",
        "elements_at": "2026-11-27T17:59:00Z",
        "satellites": [{**iss, **over}],
    }


def test_the_file_keeps_only_what_the_list_marks_sure() -> None:
    read = read_file(json.dumps(served()).encode())
    assert read is not None and read.made == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    (iss,) = read.satellites
    assert iss.downlinks_hz == (437825000,) and iss.uplinks_hz == (437825000,)
    assert iss.mode == "afsk1200" and iss.path == "" and iss.orbit is not None
    sure = read_file(json.dumps(served(path={"value": "ARISS", "sure": True})).encode())
    assert sure is not None and sure.satellites[0].path == "ARISS"


def test_a_bad_row_is_left_out_alone_and_a_body_that_is_no_such_file_is_none() -> None:
    body = served()
    body["satellites"] += [{"id": "x"}, {"id": 1, "name": "<b>"}, {**body["satellites"][0], "id": 7}]
    read = read_file(json.dumps(body).encode())
    assert read is not None and [one.id for one in read.satellites] == [25544, 7]
    assert read.satellites[1].orbit is None, "elements of another number are not taken"
    assert read_file(b"{") is None and read_file(b'{"v": 2, "satellites": []}') is None
    odd = read_file(
        json.dumps(served(mode={"value": "fsk", "sure": True}, path={"value": "a b", "sure": True})).encode()
    )
    assert odd is not None and odd.satellites[0].mode is None and odd.satellites[0].path == ""


def test_a_satellite_whose_elements_are_older_than_fourteen_days_is_not_shown() -> None:
    read = read_file(json.dumps(served()).encode())
    assert read is not None
    (iss,) = read.satellites
    assert iss.orbit is not None
    assert shown(iss, iss.orbit.epoch + MAX_ELEMENTS_AGE) is not None
    assert shown(iss, iss.orbit.epoch + MAX_ELEMENTS_AGE + timedelta(seconds=1)) is None
