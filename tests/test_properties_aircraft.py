"""Properties of the aircraft readers: readsb's item-by-item JSON reader gives what json.loads gives; readsb's
and a Radarcape's answers, real ones damaged above all, never raise; an aircraft is on the earth, its
heading and course under 360, its speed, height and climb within their ranges, its time a day old at most.
"""

import json
import math
from datetime import datetime, timedelta
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from neoaprs import radarcape, readsb
from neoaprs.layerthing import Thing
from tests.support.mutation import JSON_VALUES, json_bytes, mutated_bytes, mutated_json
from tests.test_radarcape import AT as RADARCAPE_AT
from tests.test_radarcape import row
from tests.test_readsb import AT, NOW, flying


def in_domain(things: list[Thing] | None, at: datetime) -> None:
    for thing in things or []:
        assert thing.id and -90 <= thing.lat <= 90 and -180 <= thing.lon <= 180
        assert thing.heading_deg is None or 0 <= thing.heading_deg < 360
        assert thing.course_deg is None or 0 <= thing.course_deg < 360
        assert thing.speed_kmh is None or readsb.SPEED_KMH_RANGE[0] <= thing.speed_kmh <= readsb.SPEED_KMH_RANGE[1]
        assert thing.altitude_m is None or -1000 <= thing.altitude_m <= 40000
        assert thing.vertical_ms is None or (math.isfinite(thing.vertical_ms) and abs(thing.vertical_ms) <= 150)
        assert at - timedelta(seconds=readsb.SEEN_MAX_SEC) < thing.at <= at
        assert len(thing.name) <= readsb.TEXT_MAX and thing.name.isprintable()
    if things is not None:
        assert len({t.id for t in things}) == len(things)


@given(JSON_VALUES)
def test_the_item_by_item_reader_gives_what_json_gives(value: Any) -> None:
    """For any JSON value, loads gives what json.loads gives (NaN aside, which is never equal to itself)."""
    for body in (json_bytes(value), json_bytes({"now": NOW, "aircraft": value})):
        assert json.dumps(readsb.loads(body)) == json.dumps(json.loads(body))


REAL_RECEIVER = {"now": NOW, "messages": 123456, "aircraft": [flying(), flying(hex="461f2b", lat=-33.9, lon=151.2)]}
REAL_SERVICE = {"ac": [flying()], "msg": "No error", "now": int(NOW * 1000), "total": 1, "ctime": 0, "ptime": 0}


@given(
    st.sampled_from([REAL_RECEIVER, REAL_SERVICE]).flatmap(lambda seed: mutated_json(seed, changes=4)), st.booleans()
)
def test_a_damaged_readsb_answer_never_raises(answer: Any, own_clock: bool) -> None:
    """Any change to a real answer gives aircraft in their domain, or None."""
    found = readsb.read_aircraft(json_bytes(answer), AT if own_clock else None)
    if own_clock:
        in_domain(found, AT)
    else:
        for thing in found or []:
            assert -90 <= thing.lat <= 90 and -180 <= thing.lon <= 180


@given(st.one_of(st.binary(max_size=120), mutated_bytes(json_bytes(REAL_RECEIVER), changes=6)))
def test_any_bytes_as_a_readsb_answer_never_raise(body: bytes) -> None:
    """Any bytes, a real answer with bytes damaged above all, give aircraft in their domain, or None."""
    in_domain(readsb.read_aircraft(body, AT), AT)


REAL_RADARCAPE = [row(), row(hex="461f2b", lat=-33.9, lon=151.2, lla=None, uti=1794812300)]


@given(mutated_json(REAL_RADARCAPE, changes=4))
def test_a_damaged_radarcape_answer_never_raises(answer: Any) -> None:
    """Any change to a real list gives aircraft in their domain with four-letter airports, or None."""
    found = radarcape.read_aircraft(json_bytes(answer), RADARCAPE_AT)
    in_domain(found, RADARCAPE_AT)
    for thing in found or []:
        assert thing.origin == "" or len(thing.origin) == 4
        assert thing.destination == "" or len(thing.destination) == 4


@given(st.one_of(st.binary(max_size=120), mutated_bytes(json_bytes(REAL_RADARCAPE), changes=6)))
def test_any_bytes_as_a_radarcape_answer_never_raise(body: bytes) -> None:
    """Any bytes give aircraft in their domain, or None."""
    in_domain(radarcape.read_aircraft(body, RADARCAPE_AT), RADARCAPE_AT)
