"""Properties of KISS framing: encoded bytes come back as the same frame whatever the chunking of the stream, and garbage before a frame never costs the frame."""
from hypothesis import given
from hypothesis import strategies as st

from neoaprs.kiss import FEND, KissDecoder, KissFrame, encode

payloads = st.binary(max_size=1000)             # a frame is at most 1024 bytes with its command byte, before escaping


def cut(data: bytes, points: list[int]) -> list[bytes]:
    """`data` split at the given positions (any order, repeats and positions beyond the end allowed)."""
    marks = sorted({min(p, len(data)) for p in points} | {0, len(data)})
    return [data[a:b] for a, b in zip(marks, marks[1:])]


@given(payloads, st.integers(0, 15), st.integers(0, 15), st.lists(st.integers(0, 2200), max_size=40))
def test_any_split_of_an_encoded_frame_yields_that_one_frame(payload: bytes, port: int, command: int, points: list[int]) -> None:
    decoder = KissDecoder()
    frames: list[KissFrame] = []
    for chunk in cut(encode(payload, port, command), points):
        frames += decoder.feed(chunk)
    assert frames == [KissFrame(port, command, payload)]
    assert decoder.dropped == 0


@given(st.lists(payloads, max_size=6), st.lists(st.integers(0, 4000), max_size=30))
def test_a_stream_of_frames_comes_out_in_order_whatever_the_chunking(items: list[bytes], points: list[int]) -> None:
    decoder = KissDecoder()
    stream = b"".join(encode(p) for p in items)
    frames: list[KissFrame] = []
    for chunk in cut(stream, points):
        frames += decoder.feed(chunk)
    assert [f.payload for f in frames] == items


@given(st.binary(max_size=200).map(lambda b: b.replace(bytes([FEND]), b"")), payloads)
def test_bytes_before_the_first_fend_are_forgotten(garbage: bytes, payload: bytes) -> None:
    assert KissDecoder().feed(garbage + encode(payload)) == [KissFrame(0, 0, payload)]


@given(st.binary(max_size=3000))
def test_any_bytes_decode_without_error_and_every_frame_fits_the_limit(data: bytes) -> None:
    decoder = KissDecoder()
    for frame in decoder.feed(data):
        assert len(frame.payload) < 1024 and 0 <= frame.port <= 15 and 0 <= frame.command <= 15
