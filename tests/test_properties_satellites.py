"""Properties of the satellite readers: an orbital record of CelesTrak, damaged in any field, gives an
orbit or None; the server's satellites file, damaged in any way, gives its satellites or None, never
raises; a satellite read has its own number, a name of the list's form and frequencies above 0 Hz.
"""

import csv
import io
import json
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from neoaprs.satellitelist import NAME_FORM, read_file
from neoaprs.satellites import OMM_FIELDS, orbit_of
from tests.support.files import fixture_text
from tests.support.mutation import JSON_LEAVES, json_bytes, mutated_bytes, mutated_json

RECORDS = list(csv.DictReader(io.StringIO(fixture_text("satellites/amateur.csv"))))[:6]
_TEXT_CHANGES = st.one_of(
    st.text(max_size=30),
    st.sampled_from(["", "nan", "inf", "-inf", "1e999", "0", "-1", "99999999", "0001-01-01T00:00:00+05:00"]),
    st.sampled_from(["9999-12-31T23:59:59-05:00", "2026-11-27T12:00:00Z", "2026-11-27 12:00:00.5+14:00"]),
)


@st.composite
def damaged_records(draw: st.DrawFn) -> dict[str, object]:
    record: dict[str, object] = dict(draw(st.sampled_from(RECORDS)))
    for name in draw(st.lists(st.sampled_from(OMM_FIELDS), max_size=3)):
        record[name] = draw(st.one_of(_TEXT_CHANGES, JSON_LEAVES))
    return record


@given(damaged_records())
def test_a_damaged_orbital_record_is_an_orbit_or_none(record: dict[str, object]) -> None:
    """Any value in any field of a real record gives an orbit with a mean motion of 0.5 to 20 a day, or None."""
    orbit = orbit_of(record)
    assert orbit is None or 0.5 < orbit.mean_motion < 20


def test_an_epoch_before_the_first_day_of_the_calendar_is_no_orbit() -> None:
    """An epoch that is in year 1 only in its own zone is none, not an OverflowError."""
    assert orbit_of({**RECORDS[0], "EPOCH": "0001-01-01T00:00:00+05:00"}) is None


def served() -> dict[str, Any]:
    iss = {
        "id": int(RECORDS[0]["NORAD_CAT_ID"]),
        "name": "AO-7",
        "downlink": [{"mhz": 145.975, "sure": True}, {"mhz": 29.502, "sure": False}],
        "uplink": [{"mhz": 432.15, "sure": True}],
        "mode": {"value": "afsk1200", "sure": True},
        "path": {"value": "ARISS", "sure": True},
        "elements": RECORDS[0],
    }
    return {"v": 1, "made": "2026-11-27T18:00:00Z", "elements_at": "2026-11-27T17:59:00Z", "satellites": [iss]}


@given(st.one_of(mutated_json(served(), changes=4).map(json_bytes), mutated_bytes(json_bytes(served()), changes=6)))
def test_a_damaged_satellites_file_never_raises(body: bytes) -> None:
    """Any change to a real file gives satellites of good names and frequencies, each once, or None."""
    found = read_file(body)
    if found is None:
        return
    assert len({s.id for s in found.satellites}) == len(found.satellites)
    for one in found.satellites:
        assert NAME_FORM.fullmatch(one.name)
        assert all(1_000_000 < hz < 12_000_000_000 for hz in (*one.downlinks_hz, *one.uplinks_hz))
        assert one.orbit is None or one.orbit.id == one.id


def test_the_real_file_reads_whole() -> None:
    found = read_file(json.dumps(served()).encode())
    assert found is not None and found.satellites[0].orbit is not None
