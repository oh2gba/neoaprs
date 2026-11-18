"""Fintraffic's ship feed read (neoaprs/digitraffic.py): the positions of /locations and the words of /vessels, in the form the service gives them; anything else is None."""
import json

from neoaprs.clock import from_unix
from neoaprs.digitraffic import read_locations, read_vessels


def feature(mmsi: int = 230123000, lon: float = 24.94, lat: float = 60.17, **props: object) -> dict[str, object]:
    return {"mmsi": mmsi, "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"mmsi": mmsi, "sog": 9.3, "cog": 94.0, "navStat": 0, "heading": 94, "timestampExternal": 1794758058247, **props}}


def collection(*features: object) -> bytes:
    return json.dumps({"type": "FeatureCollection", "dataUpdatedTime": "2026-11-16T06:58:13Z", "features": list(features)}).encode()


def test_the_locations_of_a_collection_are_read_with_place_speed_course_heading_and_time() -> None:
    [found] = read_locations(collection(feature())) or []
    assert (found.mmsi, found.lat, found.lon, found.sog_kn, found.cog_deg, found.heading_deg) == (230123000, 60.17, 24.94, 9.3, 94.0, 94)
    assert found.at == from_unix(1794758058.247)


def test_what_a_ship_says_is_not_available_is_none() -> None:
    [found] = read_locations(collection(feature(sog=102.3, cog=360.0, heading=511))) or []
    assert (found.sog_kn, found.cog_deg, found.heading_deg) == (None, None, None)
    [found] = read_locations(collection(feature(sog=None, cog=None, heading=None))) or []
    assert (found.sog_kn, found.cog_deg, found.heading_deg) == (None, None, None)


def test_a_ship_that_is_not_complete_is_passed_over_and_the_rest_are_read() -> None:
    broken = [feature(lat=91.0), feature(lon=181.0), {"type": "Feature"}, 7, feature(timestampExternal=None), {**feature(), "geometry": {"coordinates": [24.0]}}, feature(mmsi=230999000)]
    found = read_locations(collection(*broken))
    assert found is not None and [p.mmsi for p in found] == [230999000]


def test_a_number_that_is_not_finite_or_too_large_for_a_float_passes_the_ship_over() -> None:
    nan, huge = float("nan"), 10**400
    broken = [feature(lon=nan), feature(lat=nan), feature(lon=huge), feature(timestampExternal=huge), feature(timestampExternal=nan), feature(mmsi=-5), feature(mmsi=10**10)]
    good = feature(mmsi=230999000, sog=nan, cog=huge)
    found = read_locations(json.dumps({"features": [*broken, good]}))
    assert found is not None and [p.mmsi for p in found] == [230999000]
    assert found[0].sog_kn is None and found[0].cog_deg is None


def test_a_reader_gives_none_for_an_answer_not_in_its_form() -> None:
    for body in (b"", b"not json", b"[]", b'{"features": 3}', b'{"type": "FeatureCollection"}', b"null"):
        assert read_locations(body) is None
    for body in (b"", b"not json", b"{}", b'{"features": []}', b"null", b"3"):
        assert read_vessels(body) is None


def test_the_vessels_are_read_with_name_kind_and_destination() -> None:
    body = json.dumps([{"callSign": "3E2300", "destination": "DZAAE", "mmsi": 352002374, "name": "LADY JAMILA", "shipType": 70},
                       {"destination": "", "mmsi": 265587000, "name": "RESCUE MATHILDA@@", "shipType": 0}, {"name": "no mmsi"}, 4]).encode()
    found = read_vessels(body)
    assert found is not None
    assert [(s.mmsi, s.name, s.ship_type, s.destination) for s in found] == [(352002374, "LADY JAMILA", 70, "DZAAE"), (265587000, "RESCUE MATHILDA", None, "")]
