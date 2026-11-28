"""Properties of the ship readers: an AIS message made into sentences decodes back to its values; the AIS
decoder, AISStream's messages and Fintraffic's answers never raise on damaged input; what they return is
a place on the earth, a speed of 0 or more, a course and a heading under 360, never NaN.
"""

import json
import math

from hypothesis import given
from hypothesis import strategies as st

from neoaprs.aisdecode import AisDecoder, AisPosition, AisStatic
from neoaprs.aisstream import Confirmed, Refused, read_message
from neoaprs.clock import utc
from neoaprs.digitraffic import read_locations, read_vessels
from tests.support import aissentences as ais
from tests.support.fakeaisstream import position, static
from tests.support.mutation import json_bytes, mutated_json, mutated_text
from tests.test_digitraffic import collection, feature

AT = utc(2026, 11, 27, 12, 0, 30)
REAL_LINES = [
    "!AIVDM,1,1,,A,13u?etPv2;0n:dDPwUM1U1Cb069D,0*24",
    *ais.sentences(ais.static_a(352002374, "Lady Jamila", 70, "Helsinki")),
    *ais.sentences(ais.class_b(230999000, -33.8568, -151.2153, 5.0, 0.0, 0, 18)),
    *ais.sentences(ais.static_b(230555000, 0, name="Sea Lark")),
    *ais.sentences(ais.static_b(230555000, 1, ship_type=36)),
]
_MMSI = st.integers(1, 999_999_999)
_LAT = st.integers(-90 * 600000, 90 * 600000).map(lambda n: n / 600000)
_LON = st.integers(-180 * 600000, 180 * 600000).map(lambda n: n / 600000)
_SOG = st.integers(0, 1022).map(lambda n: n / 10)
_COG = st.integers(0, 3599).map(lambda n: n / 10)
_HEADING = st.integers(0, 359)
_NAME = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", max_size=20).map(str.strip)


def in_domain(found: object) -> None:
    if isinstance(found, AisPosition):
        assert -90 <= found.lat <= 90 and -180 <= found.lon <= 180
        assert isinstance(found.mmsi, int) and 0 <= found.mmsi < 2**30
        assert found.sog_kn is None or (math.isfinite(found.sog_kn) and 0 <= found.sog_kn < 102.3)
        assert found.cog_deg is None or 0 <= found.cog_deg < 360
        assert found.heading_deg is None or 0 <= found.heading_deg < 360
    elif isinstance(found, AisStatic):
        assert found.ship_type is None or 1 <= found.ship_type <= 99
        assert isinstance(found.name, str) and isinstance(found.destination, str)
    else:
        assert found is None or isinstance(found, Confirmed | Refused)


@given(_MMSI, _LAT, _LON, _SOG, _COG, _HEADING, st.sampled_from([1, 2, 3, 18, 19]))
def test_a_position_made_into_a_sentence_decodes_back(
    mmsi: int, lat: float, lon: float, sog: float, cog: float, heading: int, kind: int
) -> None:
    """A position report of any type made into sentences gives back its MMSI, place, speed, course and heading."""
    make = ais.class_a if kind < 18 else ais.class_b
    found = AisDecoder().feed(ais.sentences(make(mmsi, lat, lon, sog, cog, heading, kind))[0], AT)
    assert isinstance(found, AisPosition)
    assert (found.mmsi, found.sog_kn, found.cog_deg, found.heading_deg) == (mmsi, sog, cog, heading)
    assert abs(found.lat - lat) < 1e-9 and abs(found.lon - lon) < 1e-9


@given(_MMSI, _NAME, st.integers(1, 99), _NAME, st.integers(8, 72))
def test_a_static_message_in_parts_decodes_back(mmsi: int, name: str, kind: int, destination: str, per: int) -> None:
    """A type 5 message cut into any number of parts gives back its name, ship type and destination."""
    decoder = AisDecoder()
    found = [decoder.feed(line, AT) for line in ais.sentences(ais.static_a(mmsi, name, kind, destination), per)]
    assert found[-1] == AisStatic(mmsi, name, kind, destination)
    assert all(f is None for f in found[:-1])


@given(st.lists(st.one_of(st.sampled_from(REAL_LINES).flatmap(mutated_text), st.text(max_size=90)), max_size=8))
def test_the_ais_decoder_never_raises_on_damaged_sentences(lines: list[str]) -> None:
    """Any lines, real sentences damaged above all, give a position, a ship's words or None, each in its domain."""
    decoder = AisDecoder()
    for line in lines:
        in_domain(decoder.feed(line, AT))


@given(st.text(alphabet="0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVW`abcdefghijklmnopqrstuvw", min_size=1, max_size=60))
def test_any_payload_with_a_right_checksum_decodes_within_the_domain(payload: str) -> None:
    """A sentence of any armoured payload and fill, its checksum right, never raises and stays in the domain."""
    for fill in (0, 5):
        in_domain(AisDecoder().feed(ais.sentence(payload, fill), AT))


REAL_STREAM = [
    position(230111000, 60.1, 24.9, "2026-11-27 12:00:00", sog=9.5, cog=80.2, heading=79),
    position(230111000, 60.1, 24.9, "2026-11-27 12:00:00", kind="StandardClassBPositionReport"),
    static(230111000, "SEA LARK", 36, "HELSINKI", "2026-11-27 12:00:00"),
    {"MessageType": "SubscriptionConfirmation"},
    {"error": "Api Key Is Not Valid"},
]


@given(st.sampled_from(REAL_STREAM).flatmap(mutated_json))
def test_a_damaged_aisstream_message_never_raises(message: object) -> None:
    """Any change to a real message of the stream gives a position, a ship's words, an answer or None, in its domain."""
    in_domain(read_message(json_bytes(message), AT))


@given(st.binary(max_size=80))
def test_aisstream_bytes_never_raise(body: bytes) -> None:
    """Any bytes at all are read without raising."""
    in_domain(read_message(body, AT))


def test_a_latitude_too_large_for_a_float_is_no_position() -> None:
    """An integer beyond a float's range for the place is no position, not an OverflowError."""
    body = json.dumps(position(230111000, 60.1, 24.9, "2026-11-27 12:00:00")).replace("60.1", "1" + "0" * 400)
    assert read_message(body, AT) is None


REAL_LOCATIONS = json.loads(collection(feature(), feature(230999000, -151.2, -33.8)))
REAL_VESSELS = [
    {"callSign": "3E2300", "destination": "DZAAE", "mmsi": 352002374, "name": "LADY JAMILA", "shipType": 70},
    {"destination": "", "mmsi": 265587000, "name": "RESCUE MATHILDA@@", "shipType": 0},
]


@given(mutated_json(REAL_LOCATIONS, changes=4))
def test_damaged_locations_never_raise(answer: object) -> None:
    """Any change to a real /locations answer gives a list of positions in their domain, or None."""
    found = read_locations(json_bytes(answer))
    for one in found or []:
        in_domain(one)


@given(mutated_json(REAL_VESSELS, changes=4))
def test_damaged_vessels_never_raise(answer: object) -> None:
    """Any change to a real /vessels answer gives a list of ships' words in their domain, or None."""
    found = read_vessels(json_bytes(answer))
    for one in found or []:
        in_domain(one)
