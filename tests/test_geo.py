import math

import pytest

from neoaprs.geo import bearing_deg, distance_km

HELSINKI = (60.17, 24.94)
TALLINN = (59.44, 24.75)


def test_helsinki_to_tallinn() -> None:
    assert distance_km(*HELSINKI, *TALLINN) == pytest.approx(82, abs=1.5)
    assert bearing_deg(*HELSINKI, *TALLINN) == pytest.approx(188, abs=1)
    assert bearing_deg(*TALLINN, *HELSINKI) == pytest.approx(8, abs=1)


def test_distance_is_symmetric_and_zero_on_the_spot() -> None:
    assert distance_km(*HELSINKI, *TALLINN) == pytest.approx(distance_km(*TALLINN, *HELSINKI))
    assert distance_km(*HELSINKI, *HELSINKI) == 0.0


def test_a_degree_of_latitude_and_a_quarter_of_the_earth() -> None:
    assert distance_km(0, 0, 1, 0) == pytest.approx(111.195, abs=0.01)
    assert distance_km(0, 0, 0, 90) == pytest.approx(math.pi / 2 * 6371.0088)
    assert distance_km(0, 0, 0, 180) == pytest.approx(math.pi * 6371.0088)


def test_the_short_way_over_the_date_line() -> None:
    assert distance_km(0, 179.5, 0, -179.5) == pytest.approx(distance_km(0, 0, 0, 1))
    assert bearing_deg(0, 179.5, 0, -179.5) == pytest.approx(90)


@pytest.mark.parametrize("to, expected", [((1, 0), 0), ((0, 1), 90), ((-1, 0), 180), ((0, -1), 270)])
def test_the_compass_points(to: tuple[float, float], expected: float) -> None:
    assert bearing_deg(0, 0, *to) == pytest.approx(expected)


def test_bearing_stays_in_range() -> None:
    assert bearing_deg(10, 10, 10, 10) == 0.0
    for lat in range(-80, 81, 40):
        for lon in range(-170, 171, 40):
            assert 0.0 <= bearing_deg(lat, lon, 12.5, -3.5) < 360.0
