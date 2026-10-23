"""Properties of AX.25: decode(encode(frame)) is the frame for every valid frame; no bytes make decode fail with anything but Ax25Error; an address survives its text."""
from hypothesis import given, strategies as st

from neoaprs.ax25 import Address, Ax25Error, Frame, decode, encode

CALL_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
calls = st.text(alphabet=CALL_CHARS, min_size=1, max_size=6)
ssids = st.integers(0, 15)
plain_addresses = st.builds(Address, calls, ssids)
digipeaters = st.builds(Address, calls, ssids, st.booleans())


@st.composite
def frames(draw: st.DrawFn) -> Frame:
    control = draw(st.one_of(st.just(0x03), st.integers(0, 255)))
    is_ui = control & 0xEF == 0x03
    return Frame(
        draw(plain_addresses), draw(plain_addresses), tuple(draw(st.lists(digipeaters, max_size=8))),
        control, draw(st.integers(0, 255)) if is_ui else 0xF0, draw(st.binary(max_size=300)),
    )


@given(frames())
def test_decode_of_encode_is_the_frame(frame: Frame) -> None:
    assert decode(encode(frame)) == frame


@given(frames())
def test_encode_of_decode_of_encode_is_the_same_bytes(frame: Frame) -> None:
    data = encode(frame)
    assert encode(decode(data)) == data


@given(st.binary(max_size=200))
def test_decode_either_gives_a_frame_or_raises_ax25_error(data: bytes) -> None:
    try:
        frame = decode(data)
    except Ax25Error:
        return
    assert decode(encode(frame)) == frame


@given(st.builds(Address, calls, ssids, st.booleans()))
def test_an_address_survives_its_text(address: Address) -> None:
    assert Address.parse(str(address)) == address
