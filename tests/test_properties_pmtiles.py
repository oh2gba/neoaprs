"""Properties of the PMTiles readers: a header, a directory (plain or gzip) and a tile id each read back
what was written; any bytes as a header, a directory or a packed directory, and any range a server
answers, give the value or a FormatError (a CutError for the server), never anything else.
"""

import zlib
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from neoaprs import pmtilesformat as fmt
from neoaprs.pmtilesrange import CutError, Halt, HttpSource
from tests.support.mutation import mutated_bytes

U64 = st.integers(0, 2**64 - 1)
U8 = st.integers(0, 255)
I32 = st.integers(-(2**31), 2**31 - 1)


@st.composite
def headers(draw: st.DrawFn) -> fmt.Header:
    low = draw(st.integers(0, fmt.MAX_ZOOM))
    return fmt.Header(
        *(draw(U64) for _ in range(11)),
        clustered=draw(st.booleans()),
        internal_compression=draw(st.sampled_from([fmt.NONE, fmt.GZIP])),
        tile_compression=draw(U8),
        tile_type=draw(U8),
        min_zoom=low,
        max_zoom=draw(st.integers(low, fmt.MAX_ZOOM)),
        bounds_e7=(draw(I32), draw(I32), draw(I32), draw(I32)),
        center_zoom=draw(U8),
        center_e7=(draw(I32), draw(I32)),
    )


@st.composite
def entries(draw: st.DrawFn) -> fmt.Entries:
    found, tile_id, run = fmt.Entries(), 0, 0
    for _ in range(draw(st.integers(0, 12))):
        tile_id += draw(st.integers(max(1, run) if len(found) else 0, max(1, run) + 1000))
        run = draw(st.integers(0, 50))
        found.add(tile_id, run, draw(st.integers(1, 2**32 - 1)), draw(st.integers(0, 2**40)))
    return found


def rows(found: fmt.Entries) -> list[tuple[int, int, int, int]]:
    return list(found)


@given(headers())
def test_a_header_reads_back_what_was_written(header: fmt.Header) -> None:
    """header_bytes then parse_header gives the same header."""
    data = fmt.header_bytes(header)
    assert len(data) == fmt.HEADER_LENGTH
    assert fmt.parse_header(data) == header


@given(st.one_of(st.binary(max_size=200), headers().map(fmt.header_bytes).flatmap(mutated_bytes)))
def test_any_bytes_as_a_header_are_a_header_or_a_format_error(data: bytes) -> None:
    """Any bytes, a real header damaged above all, give a header with possible zooms, or a FormatError."""
    try:
        header = fmt.parse_header(data)
    except fmt.FormatError:
        return
    assert header.min_zoom <= header.max_zoom <= fmt.MAX_ZOOM
    for size in (0, 16384, 2**64):
        try:
            fmt.check_sections(header, size)
        except fmt.FormatError:
            pass


@given(entries(), st.sampled_from([fmt.NONE, fmt.GZIP]))
def test_a_directory_reads_back_its_entries(found: fmt.Entries, compression: int) -> None:
    """encode, unpack and decode give the same entries, plain or gzip."""
    data = fmt.encode(found, 0, len(found), compression)
    assert rows(fmt.decode(fmt.unpack(data, compression, fmt.MAX_LEAF))) == rows(found)


@given(
    st.one_of(
        st.binary(max_size=120), entries().map(lambda e: fmt.encode(e, 0, len(e), fmt.NONE)).flatmap(mutated_bytes)
    )
)
def test_any_bytes_as_a_directory_are_entries_in_order_or_a_format_error(data: bytes) -> None:
    """Any bytes, a real directory damaged above all, give entries in order within 64 bits, or a FormatError."""
    try:
        found = fmt.decode(data)
    except fmt.FormatError:
        return
    ids = list(found.tile_ids)
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    assert all(0 <= value < 2**64 for row in found for value in row)


@given(
    st.one_of(
        st.binary(max_size=120), entries().map(lambda e: fmt.encode(e, 0, len(e), fmt.GZIP)).flatmap(mutated_bytes)
    )
)
def test_any_bytes_as_a_packed_directory_unpack_within_the_limit_or_are_a_format_error(data: bytes) -> None:
    """Any bytes, a real gzip directory damaged above all, unpack to at most the limit, or give a FormatError."""
    try:
        assert len(fmt.unpack(data, fmt.GZIP, 4096)) <= 4096
    except fmt.FormatError:
        pass


def test_a_directory_that_unpacks_beyond_its_limit_is_a_format_error() -> None:
    with pytest.raises(fmt.FormatError):
        fmt.unpack(zlib.compress(bytes(10_000), wbits=31), fmt.GZIP, 4096)


@given(
    st.integers(0, fmt.MAX_ZOOM).flatmap(
        lambda z: st.tuples(st.just(z), st.integers(0, 2**z - 1), st.integers(0, 2**z - 1))
    )
)
def test_a_tile_id_gives_back_its_tile(zxy: tuple[int, int, int]) -> None:
    """id_to_zxy of zxy_to_id is the tile itself."""
    assert fmt.id_to_zxy(fmt.zxy_to_id(*zxy)) == zxy


class Answer:
    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.status, self.headers = status, headers


@given(
    st.sampled_from([206, 200, 416]),
    st.one_of(
        st.text(max_size=60),
        st.just("bytes 0-126/5000").flatmap(lambda t: mutated_bytes(t.encode()).map(lambda b: b.decode("latin-1"))),
    ),
    st.one_of(st.none(), st.text(max_size=8), st.just("127")),
)
def test_any_answer_of_a_map_server_is_the_range_or_a_cut_error(status: int, said: str, length: str | None) -> None:
    """Any status, Content-Range and Content-Length give the size of the archive or a CutError."""
    source = HttpSource("https://example.invalid/map.pmtiles", Halt())
    answer: Any = Answer(status, {"Content-Range": said} | ({} if length is None else {"Content-Length": length}))
    try:
        source._check(answer, 0, 127)
    except CutError:
        return
    assert source.size >= 0 and status == 206


def test_a_header_with_impossible_zooms_is_a_format_error() -> None:
    sizes = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    data = bytearray(fmt.header_bytes(fmt.Header(*sizes, False, fmt.GZIP, 1, 1, 0, 14, (0, 0, 0, 0), 0, (0, 0))))
    data[100], data[101] = 5, 4
    with pytest.raises(fmt.FormatError):
        fmt.parse_header(bytes(data))
