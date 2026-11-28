"""Properties of the Bluetooth readers: SDP data elements written read back as they were, and an answer
built from its parts gives back its lists and continuation; any bytes of a device give elements or an
SdpError; a `ble://` port of any text gives the address and profile or a ValueError.
"""

import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from neoaprs.btle import PROFILES, parse_url, profile_for
from neoaprs.btsdp import (
    MAX_DEPTH,
    RFCOMM_UUID,
    SEARCH_ATTRIBUTES_ANSWER,
    SdpError,
    Uuid,
    parse_elements,
    read_answer,
    rfcomm_channels,
)
from tests.support.mutation import mutated_bytes

Element = None | int | Uuid | bytes | list["Element"]


def element_bytes(value: Element) -> bytes:
    """A data element as a device writes it: the kind and size byte, then the body."""
    if value is None:
        return b"\x00"
    if isinstance(value, Uuid):
        return bytes([3 << 3 | 1]) + value.value.to_bytes(2, "big")
    if isinstance(value, int):
        return bytes([1 << 3 | 2]) + value.to_bytes(4, "big")
    if isinstance(value, bytes):
        return bytes([4 << 3 | 5, len(value)]) + value
    body = b"".join(element_bytes(v) for v in value)
    return bytes([6 << 3 | 6]) + struct.pack(">H", len(body)) + body


ELEMENTS = st.recursive(
    st.one_of(st.none(), st.integers(0, 2**32 - 1), st.integers(0, 0xFFFF).map(Uuid), st.binary(max_size=20)),
    lambda inner: st.lists(inner, max_size=4),
    max_leaves=10,
).filter(lambda e: depth(e) <= MAX_DEPTH)


def depth(value: Element) -> int:
    return 1 + max(map(depth, value), default=0) if isinstance(value, list) else 0


def answer(lists: bytes, state: bytes, transaction: int) -> bytes:
    return (
        struct.pack(">BHHH", SEARCH_ATTRIBUTES_ANSWER, transaction, len(lists) + 3, len(lists))
        + lists
        + bytes([len(state)])
        + state
    )


@given(st.lists(ELEMENTS, max_size=4))
def test_written_elements_read_back(values: list[Element]) -> None:
    """parse_elements of the written elements gives them back in order."""
    assert parse_elements(b"".join(element_bytes(v) for v in values)) == values


@given(st.integers(1, 30))
def test_a_serial_port_record_gives_its_channel(channel: int) -> None:
    """A protocol list naming RFCOMM gives its channel."""
    record = [[[Uuid(0x0100)], [Uuid(RFCOMM_UUID), channel]]]
    assert rfcomm_channels(parse_elements(b"".join(element_bytes(v) for v in record))) == [channel]


REAL_RECORD = b"".join(element_bytes(v) for v in [[0x0004, [[Uuid(0x0100)], [Uuid(RFCOMM_UUID), 1]]]])


@given(st.one_of(st.binary(max_size=80), mutated_bytes(REAL_RECORD, changes=6)))
def test_any_bytes_of_a_device_are_elements_or_an_sdp_error(data: bytes) -> None:
    """Any bytes, a real record damaged above all, give elements and channels, or an SdpError."""
    try:
        found = parse_elements(data)
    except SdpError:
        return
    assert all(isinstance(c, int) for c in rfcomm_channels(found))


@given(st.binary(max_size=40), st.binary(max_size=16), st.integers(0, 0xFFFF))
def test_an_answer_gives_back_its_lists_and_continuation(lists: bytes, state: bytes, transaction: int) -> None:
    """read_answer of an answer built from its parts gives the parts."""
    assert read_answer(answer(lists, state, transaction), transaction) == (lists, state)


@given(st.one_of(st.binary(max_size=60), mutated_bytes(answer(REAL_RECORD, b"", 1), changes=6)))
def test_any_answer_is_its_parts_or_an_sdp_error(pdu: bytes) -> None:
    """Any bytes, a real answer damaged above all, give lists within the answer, or an SdpError."""
    try:
        lists, state = read_answer(pdu, 1)
    except SdpError:
        return
    assert len(lists) + len(state) <= len(pdu)


_HEX = "0123456789abcdefABCDEF"


@given(st.lists(st.text(alphabet=_HEX, min_size=2, max_size=2), min_size=6, max_size=6), st.sampled_from([":", "-"]))
def test_a_ble_port_gives_back_its_address(parts: list[str], dash: str) -> None:
    """ble://ADDRESS, with any profile name, gives the address in upper case with colons."""
    address = dash.join(parts)
    assert parse_url(f"ble://{address}") == (address.upper().replace("-", ":"), None)
    for profile in PROFILES:
        assert parse_url(f"ble://{address}/{profile.name}/") == (address.upper().replace("-", ":"), profile)


@given(st.one_of(st.text(max_size=60), st.text(max_size=40).map(lambda t: "ble://00:11:22:33:44:55/" + t)))
def test_any_port_is_an_address_or_a_value_error(path: str) -> None:
    """Any text as a port, a profile of any words above all, is an address and profile, or a ValueError."""
    try:
        address, profile = parse_url(path)
    except ValueError:
        return
    assert address.isascii() and address == address.upper()
    assert profile is None or profile == profile_for(profile.name if profile.name != "custom" else profile.service)


def test_a_profile_that_is_no_uuid_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        parse_url("ble://00:11:22:33:44:55/not-a-profile")
