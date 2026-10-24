"""The dispatcher: every case of tests/fixtures/aprs/cases.json (spec examples, radio captures and malformed fields), and what the dispatcher promises besides."""
import json
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from neoaprs.aprsparse import parse
from neoaprs.aprsthirdparty import parse_packet
from neoaprs.clock import iso
from neoaprs.packet import Other, Packet, Position, Undecoded
from tests.support.files import FIXTURES

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
CASES = json.loads((FIXTURES / "aprs" / "cases.json").read_text(encoding="utf-8"))


def _kind(decoded: Any) -> str:
    return Packet(NOW, "in", b"", "A", "B", (), b"", decoded).kind


def _check(actual: Any, expected: dict[str, Any], where: str) -> None:
    """Every key of `expected` holds for `actual` (a dataclass); floats within a millimetre-ish tolerance, datetimes as ISO text."""
    assert is_dataclass(actual), where
    names = {f.name for f in fields(actual)}
    for key, want in expected.items():
        if key == "kind":
            assert _kind(actual) == want, where
        elif key == "class":
            assert type(actual).__name__ == want, where
        elif key == "other_kind":
            assert isinstance(actual, Other) and actual.kind == want, where
        elif key == "error_contains":
            assert isinstance(actual, Undecoded) and want in actual.error, f"{where}: {getattr(actual, 'error', actual)!r} lacks {want!r}"
        else:
            assert key in names, f"{where}: no field {key}"
            value = getattr(actual, key)
            if isinstance(want, dict) and is_dataclass(value):
                _check(value, want, f"{where}.{key}")
            elif isinstance(want, float):
                assert value == pytest.approx(want, abs=1e-3), f"{where}.{key}"
            elif isinstance(value, datetime):
                assert iso(value) == want, f"{where}.{key}"
            else:
                assert value == want, f"{where}.{key}"


def test_there_are_enough_cases() -> None:
    assert len(CASES) >= 40
    assert len({c["name"] for c in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_a_case(case: dict[str, Any]) -> None:
    decoded, third = parse_packet(case["info"].encode("latin-1"), case["source"], case["destination"], NOW)
    _check(decoded, case["expected"], case["name"])
    want = case.get("third_party")
    assert (None if third is None else {"source": third.source, "destination": third.destination, "path": list(third.path)}) == want, case["name"]


def test_the_text_of_an_undecoded_field_is_the_field_as_latin_1() -> None:
    d = parse(b"!4903.50X/07201.75W-\xe4", "A", "B", NOW)
    assert isinstance(d, Undecoded)
    assert d.text == "!4903.50X/07201.75W-\xe4"


def test_an_other_keeps_the_whole_field_with_its_identifier() -> None:
    assert parse(b"T#005,199", "A", "B", NOW) == Other("telemetry", "T#005,199")


@pytest.mark.parametrize("first", range(256))
def test_no_first_byte_makes_the_parser_raise(first: int) -> None:
    for tail in (b"", b"x", b"\x00" * 3, b"49", b"4903.50N/07201.75W", b"\xff" * 30, b"abcdefghi:ack1"):
        parse(bytes([first]) + tail, "A", "VPQP20", NOW)


def test_an_exception_from_inside_is_undecoded_not_raised() -> None:
    d = parse(b"@000000z4903.50N/07201.75W-", "A", "B", NOW)          # day 0
    assert isinstance(d, Undecoded)


def test_messaging_follows_the_identifier() -> None:
    results = {chr(i): parse(i.to_bytes(1) + b"4903.50N/07201.75W-", "A", "B", NOW) for i in b"!=/@"}
    assert {k: isinstance(v, Position) and v.messaging for k, v in results.items()} == {"!": False, "=": True, "/": False, "@": True}


LAT, LON = 49 + 3.50 / 60, -(72 + 1.75 / 60)          # 4903.50N/07201.75W


@pytest.mark.parametrize(("info", "destination"), [
    (b"!4903.50N/07201.75W-Comment !W12!", "APRS"),
    (b"@092345z4903.50N/07201.75W_220/004g005t077!W12!wRSW", "APRS"),
    (b";LEADER   *092345z4903.50N/07201.75W>088/036!W12!Comment", "APRS"),
    (b")AID #2!4903.50N/07201.75WA!W12!Comment", "APRS"),
])
def test_dao_makes_a_position_an_object_and_an_item_finer_and_leaves_the_comment(info: bytes, destination: str) -> None:
    decoded = parse(info, "OH2XYZ", destination, NOW)
    position = decoded if isinstance(decoded, Position) else decoded.position          # type: ignore[union-attr]
    assert (position.lat, position.lon) == (pytest.approx(LAT + 0.001 / 60, abs=1e-9), pytest.approx(LON - 0.002 / 60, abs=1e-9))
    assert "!W12!" not in position.comment and "!W12!" not in str(position.weather)


def test_dao_in_a_mic_e_comment_before_the_radios_type_code() -> None:
    position = parse(b'`(_fn"Oj/]"4T}Hi!w5L!=', "OH2XYZ", "S32UVT", NOW)
    assert isinstance(position, Position) and position.comment == "Mic-E: Returning - Hi"
    assert (position.lat, position.lon) == (pytest.approx(33 + (25.64 + 20 * 1.1 / 10000) / 60, abs=1e-9), pytest.approx(-(112 + (7.74 + 43 * 1.1 / 10000) / 60), abs=1e-9))


def test_dao_is_taken_out_of_a_compressed_or_an_ambiguous_position_without_moving_it() -> None:
    plain, with_dao = parse(b"=/5L!!<*e7>7P[", "X", "APRS", NOW), parse(b"=/5L!!<*e7>7P[!W12!", "X", "APRS", NOW)
    assert isinstance(plain, Position) and isinstance(with_dao, Position) and (with_dao.lat, with_dao.lon, with_dao.comment) == (plain.lat, plain.lon, "")
    vague, vague_dao = parse(b"!4903.5 N/07201.7 W-", "X", "APRS", NOW), parse(b"!4903.5 N/07201.7 W-!W12!", "X", "APRS", NOW)
    assert isinstance(vague, Position) and isinstance(vague_dao, Position) and vague_dao.ambiguity == 1 and (vague_dao.lat, vague_dao.lon, vague_dao.comment) == (vague.lat, vague.lon, "")
