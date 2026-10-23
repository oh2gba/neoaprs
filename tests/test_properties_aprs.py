"""Properties of the APRS decoders: format_message then parse_message gives the message back; compress_position then parse_position keeps the place within half a metre; the parser never raises."""
import math
import re
from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from neoaprs.aprsmessage import format_message, parse_message
from neoaprs.aprsparse import parse
from neoaprs.aprsposition import compress_position, parse_position
from neoaprs.packet import Message

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
_ADDRESSEE = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126, exclude_characters=":"), min_size=1, max_size=9)
_TEXT = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126, exclude_characters="|~{"), max_size=16).filter(lambda t: not re.match(r"(ack|rej)[A-Za-z0-9]{1,5}(\}[A-Za-z0-9]{0,5})?$", t))
_ID = st.one_of(st.none(), st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=5))


def metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, a)))


@given(_ADDRESSEE, _TEXT, _ID)
def test_a_formatted_message_parses_back(addressee: str, text: str, msg_id: str | None) -> None:
    """format_message then parse_message gives back the same Message, with or without the reply-ack part of its number."""
    assert parse_message(format_message(addressee, text, msg_id)) == Message(addressee, text, msg_id)
    if msg_id is not None:
        assert parse_message(format_message(addressee, text, msg_id, "")) == Message(addressee, text, msg_id)
        assert parse_message(format_message(addressee, text, msg_id, "AB")) == Message(addressee, text, msg_id)


@given(st.floats(min_value=-90, max_value=90), st.floats(min_value=-180, max_value=180))
def test_a_compressed_position_round_trips_within_half_a_metre(lat: float, lon: float) -> None:
    """compress_position then parse_position gives a place within 0.5 m of the first."""
    p = parse_position(compress_position(lat, lon, "/", ">"), NOW)
    assert p.compressed
    assert metres_between(lat, lon, p.lat, p.lon) < 0.5


@given(st.floats(min_value=-90, max_value=90), st.floats(min_value=-180, max_value=180), st.sampled_from(["/", "\\", "0", "9", "A", "Z"]), st.integers(min_value=33, max_value=126))
def test_the_symbol_survives_compression(lat: float, lon: float, table: str, code: int) -> None:
    """The symbol table and code come back from a compressed position."""
    p = parse_position(compress_position(lat, lon, table, chr(code)), NOW)
    assert (p.symbol_table, p.symbol_code) == (table, chr(code))


@settings(max_examples=300)
@given(st.binary(max_size=80), st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", max_size=10))
def test_the_parser_never_raises(info: bytes, destination: str) -> None:
    """parse gives a Decoded for any bytes at all."""
    parse(info, "OH2XYZ", destination, NOW)


@settings(max_examples=300)
@given(st.sampled_from([b"!", b"=", b"/", b"@", b"'", b"`", b":", b";", b")", b">", b"\x1c", b"\x1d"]), st.binary(max_size=60), st.text(alphabet="PQRSTUVWXYZ0123456789", min_size=6, max_size=6))
def test_the_parser_never_raises_after_a_known_identifier(first: bytes, rest: bytes, destination: str) -> None:
    """parse gives a Decoded for any bytes after an identifier that is decoded."""
    parse(first + rest, "OH2XYZ", destination, NOW)
