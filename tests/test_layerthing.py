"""What the program knows of the map's layers of traffic (neoaprs/layerthing.py): the sources a station is offered, the one that counts, what a request to a service carries, and how the things are cut;
and the wire's names of the layers and sources (neoaprs/web/layerwire.py) are the same."""
from datetime import timedelta
from typing import get_args

import pytest

from neoaprs.clock import utc
from neoaprs.geo import distance_km
from neoaprs.layerthing import (AIRCRAFT_SOURCES, FINTRAFFIC_BOX, LAYERS, LIMIT, MAX_AGE_SEC, SERVICES, SHIP_SOURCES, Layer, Source, Thing, backoff_sec, in_force, max_age_sec, nearest, newest, offered, reaches_box,
                                request_nm, request_point, service_url, within)
from neoaprs.web.layerwire import LayerName, SourceName

HELSINKI, FRANKFURT, ESPOO = (60.17, 24.94), (50.11, 8.68), (60.2231, 24.7152)
AT = utc(2026, 11, 18, 12, 0, 0)


def thing(id: str, lat: float, lon: float, **extra: object) -> Thing:
    return Thing(id=id, lat=lat, lon=lon, at=extra.pop("at", AT), heading_deg=None, speed_kmh=None, **extra)  # type: ignore[arg-type]


def test_the_wire_names_the_layers_and_the_sources_as_the_program_does() -> None:
    assert get_args(LayerName) == get_args(Layer) == LAYERS
    assert get_args(SourceName) == get_args(Source)
    assert set(AIRCRAFT_SOURCES) | set(SHIP_SOURCES) == set(get_args(Source)) and AIRCRAFT_SOURCES[0] == SHIP_SOURCES[0] == "none"
    assert SERVICES == {"adsbfi", "adsblol", "fintraffic"}


def test_fintraffic_is_offered_at_helsinki_and_not_at_frankfurt_and_every_aircraft_source_everywhere() -> None:
    assert offered("ships", HELSINKI, 150) == ("none", "fintraffic", "receiver")
    assert offered("ships", FRANKFURT, 300) == ("none", "receiver")
    assert offered("ships", None, 300) == ("none", "receiver"), "without a position no Fintraffic"
    for where in (HELSINKI, FRANKFURT, None):
        assert offered("aircraft", where, 10) == ("none", "adsbfi", "adsblol", "receiver")


def test_the_box_is_reached_when_its_nearest_point_is_within_the_radius() -> None:
    south, north, west, east = FINTRAFFIC_BOX
    assert reaches_box((61.0, 25.0), 10), "inside the box"
    below = (south - 1.0, 25.0)                                 # due south of the box: its nearest point is on the southern edge, straight north
    edge_km = distance_km(*below, south, 25.0)
    assert reaches_box(below, int(edge_km) + 1) and not reaches_box(below, int(edge_km) - 1)
    corner = (north + 0.5, east + 0.5)                          # beyond the north-east corner: the corner is the nearest point
    corner_km = distance_km(*corner, north, east)
    assert reaches_box(corner, int(corner_km) + 1) and not reaches_box(corner, int(corner_km) - 1)
    assert not reaches_box(None, 300)


def test_the_source_in_force_is_the_one_chosen_while_it_is_offered_and_else_none() -> None:
    assert in_force("ships", "fintraffic", offered("ships", HELSINKI, 150)) == "fintraffic"
    assert in_force("ships", "fintraffic", offered("ships", FRANKFURT, 300)) == "none", "a source not offered counts as none"
    assert in_force("aircraft", "receiver", AIRCRAFT_SOURCES) == "receiver"
    assert in_force("aircraft", "fintraffic", AIRCRAFT_SOURCES) == "none" and in_force("aircraft", "", AIRCRAFT_SOURCES) == "none"


def test_a_request_carries_the_position_to_one_decimal_and_the_radius_with_its_margin_in_nautical_miles() -> None:
    assert request_point(60.2231, 24.7152) == ("60.2", "24.7")
    assert request_point(-0.04, 0.04) == ("0.0", "0.0"), "never -0.0"
    assert request_point(-33.87, -151.21) == ("-33.9", "-151.2")
    assert (request_nm(150), request_nm(300), request_nm(10000)) == (86, 167, 250)
    assert service_url("adsbfi", *ESPOO, 150) == "https://opendata.adsb.fi/api/v3/lat/60.2/lon/24.7/dist/86"
    assert service_url("adsblol", *ESPOO, 300) == "https://api.adsb.lol/v2/lat/60.2/lon/24.7/dist/167"
    with pytest.raises(ValueError):
        service_url("fintraffic", *ESPOO, 150)


def test_the_things_are_cut_to_the_circle_and_to_the_nearest_with_every_emergency_kept() -> None:
    near = [thing(f"n{i}", ESPOO[0] + i * 0.001, ESPOO[1]) for i in range(LIMIT)]
    far = thing("far", ESPOO[0] + 1.0, ESPOO[1])
    far_emergency = thing("sos", ESPOO[0] + 1.5, ESPOO[1], emergency=True)
    kept = nearest([far, far_emergency, *reversed(near)], ESPOO)
    assert [t.id for t in kept] == [*(t.id for t in near), "sos"], "the 300 nearest, nearest first, and the emergency beyond them"
    assert [t.id for t in within([far, near[0], far_emergency], ESPOO, 150)] == ["far", "n0"]
    assert [t.id for t in within([far, near[0]], ESPOO, 50)] == ["n0"]


def test_an_own_receivers_things_are_kept_but_for_the_oldest_beyond_the_guard() -> None:
    things = [thing(str(i), 0.0, float(i % 180), at=AT + timedelta(seconds=i)) for i in range(5)]
    assert newest(things, 10) == things
    assert [t.id for t in newest(things, 3)] == ["2", "3", "4"]


def test_how_old_a_thing_may_be_and_how_long_a_failing_feed_waits() -> None:
    assert (max_age_sec("aircraft", "receiver"), max_age_sec("aircraft", "adsbfi"), max_age_sec("aircraft", "adsblol"), max_age_sec("ships", "fintraffic"), max_age_sec("ships", "receiver")) == (60, 90, 90, 1800, 1800)
    assert MAX_AGE_SEC == {"aircraft_receiver": 60, "aircraft_service": 90, "ships": 1800}
    assert [backoff_sec(30, n) for n in (1, 2, 3, 4, 5, 6)] == [60, 120, 240, 480, 900, 900]
