"""Properties of the sked board reader: a board written as the daemon keeps it reads back the same; any
board, real ones damaged above all, and any text as the kept ids never raise; a sked read is of a usable
call, a dial of the page's form, a plain note, and lasts at most a day.
"""

import json
from datetime import timedelta
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from neoaprs.skeds import (
    MAX_LENGTH,
    MAX_NOTE,
    Board,
    Sked,
    board_text,
    kept_board,
    kept_ids,
    parse_board,
    past_of,
    plain_note,
)
from neoaprs.versions import is_dial
from tests.support.mutation import json_bytes, mutated_bytes, mutated_json
from tests.test_skeds import NOW, row

_SKED = st.builds(
    Sked,
    id=st.text(alphabet="0123456789abcdef", min_size=12, max_size=12),
    call=st.sampled_from(["OH2XYZ", "OH2ABC-7", "W1AW", "DL9SAU-15", "SM5ABC"]),
    start=st.integers(-60, 60 * 24 * 30).map(lambda m: NOW + timedelta(minutes=m)),
    end=st.just(NOW),
    dial=st.sampled_from(["7.0541 MHz USB", "14.1070 MHz USB", "3.5850 MHz LSB"]),
    note=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=MAX_NOTE).map(str.strip),
)


@st.composite
def boards(draw: st.DrawFn) -> Board:
    skeds = {}
    for sked in draw(st.lists(_SKED, max_size=8)):
        length = timedelta(minutes=draw(st.integers(1, 24 * 60)))
        end = max(sked.start + length, NOW + timedelta(minutes=1))
        if end - sked.start <= MAX_LENGTH:
            skeds[sked.id] = Sked(sked.id, sked.call, sked.start, end, sked.dial, sked.note)
    return Board(draw(st.booleans()), tuple(sorted(skeds.values(), key=lambda s: (s.start, s.id))))


def in_domain(skeds: tuple[Sked, ...]) -> None:
    assert len({s.id for s in skeds}) == len(skeds)
    for sked in skeds:
        assert sked.call and is_dial(sked.dial) and plain_note(sked.note)
        assert sked.start < sked.end <= sked.start + MAX_LENGTH


@given(boards())
def test_a_kept_board_reads_back_the_same(board: Board) -> None:
    """board_text then kept_board gives the same board and the time it was fetched."""
    assert kept_board(board_text(board, NOW), NOW) == (board, NOW)


REAL_BOARD: dict[str, Any] = {
    "v": 1,
    "closed": False,
    "skeds": [row(), row("aaaaaaaaaaaa", "OH2ABC-7", 1.0, 3.0, "14.1070 MHz USB", "FT8 first")],
}
REAL_PAST: dict[str, Any] = {"v": 1, "past": [row(start=-30.0), row("bbbbbbbbbbbb", start=-5.0, end=-4.0)]}


@given(mutated_json(REAL_BOARD, changes=4))
def test_a_damaged_board_never_raises(board: Any) -> None:
    """Any change to a real board gives a board of good skeds, or None."""
    found = parse_board(json_bytes(board), NOW)
    if found is not None:
        in_domain(found.skeds)


@given(mutated_json(REAL_PAST, changes=4))
def test_damaged_past_tests_never_raise(past: Any) -> None:
    """Any change to a real list of past tests gives good skeds, or None."""
    found = past_of(past, NOW)
    if found is not None:
        in_domain(found)


@given(st.one_of(st.binary(max_size=80), mutated_bytes(json_bytes(REAL_BOARD), changes=6)))
def test_any_bytes_as_a_board_never_raise(body: bytes) -> None:
    """Any bytes, a real board damaged above all, give a board or None."""
    parse_board(body, NOW)


@given(st.one_of(st.none(), st.text(max_size=40), mutated_json(["aaaaaaaaaaaa", "7f3a9c21d4e0"]).map(json.dumps)))
def test_any_kept_ids_are_ids(text: str | None) -> None:
    """Any text as the kept ids gives a list of ids of the board's form."""
    assert all(len(i) == 12 for i in kept_ids(text))


def test_a_sked_at_the_end_of_the_calendar_is_dropped_alone() -> None:
    """A row in the last day of year 9999 is dropped, not an OverflowError."""
    late = {**row(), "from": "9999-12-31T00:00:00Z", "to": "9999-12-31T01:00:00Z"}
    found = parse_board(json.dumps({**REAL_BOARD, "skeds": [late, row()]}), NOW)
    assert found is not None and [s.id for s in found.skeds] == [row()["id"]]
    past_of({"v": 1, "past": [late]}, NOW)
