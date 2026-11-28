"""Properties of the LoRa board readers: text lines and KISS frames sent in turn come back apart, the same
whichever way the stream is cut; any bytes never raise; the board's list of heard packets is entries with
finite readings or a ListError, for any answer, damaged real ones above all.
"""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from neoaprs import kiss
from neoaprs.loraboard import KissText
from neoaprs.loralist import Heard, ListError, parse
from tests.support.mutation import mutated_bytes, mutated_json

_LINE = st.binary(max_size=40).map(lambda b: bytes(c for c in b if c >= 0x20 and c != kiss.FEND) + b"\r\n")
_FRAME = st.tuples(st.integers(0, 15), st.binary(min_size=1, max_size=60))
_PIECE = st.one_of(_LINE.map(lambda line: ("text", line)), _FRAME.map(lambda f: ("frame", f)))


def stream(pieces: list[tuple[str, object]]) -> bytes:
    return b"".join(p if kind == "text" else kiss.encode(p[1], 0, p[0]) for kind, p in pieces)  # type: ignore[index, misc]


def split(data: bytes, cuts: list[int]) -> tuple[list[kiss.KissFrame], bytes]:
    reader, frames, text = KissText(), [], b""
    at = 0
    for cut in [*sorted(c % (len(data) + 1) for c in cuts), len(data)]:
        for item in reader.feed(data[at:cut]):
            if isinstance(item, kiss.KissFrame):
                frames.append(item)
            else:
                text += item
        at = max(at, cut)
    return frames, text


@given(st.lists(_PIECE, max_size=8), st.lists(st.integers(0, 10_000), max_size=6))
def test_text_and_frames_in_turn_come_back_apart_however_the_stream_is_cut(
    pieces: list[tuple[str, object]], cuts: list[int]
) -> None:
    """Lines and KISS frames of port 0 give back each frame and all the text, read whole or in any pieces."""
    frames, text = split(stream(pieces), cuts)
    assert [(f.command, f.payload) for f in frames] == [p for kind, p in pieces if kind == "frame"]
    assert text == b"".join(p for kind, p in pieces if kind == "text")  # type: ignore[misc]


@given(st.binary(max_size=200), st.lists(st.integers(0, 10_000), max_size=4))
def test_any_bytes_from_the_board_never_raise(data: bytes, cuts: list[int]) -> None:
    """Any bytes are frames and text; the text is never longer than what came."""
    frames, text = split(data, cuts)
    assert len(text) <= len(data)
    assert all(0 <= f.command <= 15 and len(f.payload) <= kiss.MAX_FRAME for f in frames)


REAL_LIST = [
    {
        "rxDate": "2026-11-15",
        "rxTime": "12:00:01",
        "packet": "OH2XYZ-7>APLRG1,WIDE1-1:!6010.00N/02450.00E#",
        "RSSI": -97,
        "SNR": 6.25,
    },
    {"rxDate": "2026-11-15", "rxTime": "12:00:09", "packet": "OH2ABC>APLRT1:>hello", "RSSI": -120.5, "SNR": -12},
]


def answer(entries: object) -> bytes:
    return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + json.dumps(entries).encode()


def heard_or_refused(body: bytes) -> list[Heard] | None:
    try:
        return parse(body)
    except ListError:
        return None


def test_the_real_list_is_read_whole() -> None:
    assert [h.key for h in parse(answer(REAL_LIST))] == [e["packet"] for e in REAL_LIST]


@given(mutated_json(REAL_LIST, changes=4))
def test_a_damaged_list_gives_entries_with_finite_readings_or_a_list_error(entries: object) -> None:
    """Any change to a real list gives entries whose SNR and RSSI are finite, or a ListError."""
    for one in heard_or_refused(answer(entries)) or []:
        assert isinstance(one.key, str)
        assert one.reading.snr is not None and abs(one.reading.snr) < float("inf")
        assert one.reading.rssi is not None and abs(one.reading.rssi) < float("inf")


@given(st.one_of(st.binary(max_size=120), mutated_bytes(answer(REAL_LIST), changes=6)))
def test_any_answer_gives_entries_or_a_list_error(body: bytes) -> None:
    """Any bytes, a damaged real answer above all, give entries or a ListError, never anything else."""
    heard_or_refused(body)


def test_an_answer_that_is_not_a_list_is_a_list_error() -> None:
    with pytest.raises(ListError):
        parse(answer({"packet": "A>B:x"}))
