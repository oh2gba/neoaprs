"""Properties of calls, messages, QRU lines and what the database keeps: parse_call refuses only with
CallsignError and reads back what format_call writes; a message, an ack and a reply-ack round-trip;
a QRU listing reads back what the server writes; a packet's row gives the packet back.
"""

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from neoaprs import ax25
from neoaprs.aprsisline import IsLineError, parse_is_line
from neoaprs.aprsmessage import MessageError, format_ack, line_of, parse_message, reply_ack_of
from neoaprs.aprsparse import parse
from neoaprs.callsign import (
    AX25_CALL,
    INTERNET_NAME,
    MAX_SSID,
    CallsignError,
    call_problem,
    format_call,
    normal_name,
    parse_call,
)
from neoaprs.message import MessagingError
from neoaprs.ownobject import QRU_GROUP_MAX
from neoaprs.packet import Message
from neoaprs.packetcodec import decode_decoded, encode_decoded, packet_of, packet_row, parse_stamp, stamp
from neoaprs.qrutext import ask_text, closing_of, listing_of
from neoaprs.services.answers import ANSWER_FRAMES_MAX
from neoaprs.services.qru import info_texts
from neoaprs.tncmode import packet_of as packet_of_frame
from tests.support.damaged import aprs_cases, mutated, mutated_text

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
CASES = aprs_cases()
INFOS = [c["info"].encode("latin-1") for c in CASES if c["info"]]
CALL_TEXTS = ["OH2GBA", "oh2gba-7", "OH2XYZ-15", "WINLINK", "OH2XYZ-L", " N0CALL ", "OH2GBA-16", "A-1"]
MESSAGES = [c["info"][1:].encode("latin-1") for c in CASES if c["info"][:1] == ":"] + [
    b"OH2GBA   :Hello{12}AB",
    b"OH2GBA   :ack12}",
    b"KH2Z:hi",
]
QRU = [
    "de OH2GBA:FOOD(2) FUEL(1) RP70(1) Max 5@50km",
    "de OH2GBA-1:FOOD(12)+",
    "Sent 3 FUEL Objects Max 5@300km de OH2GBA",
    "Sent 5 of 12 FOOD Objects, NEXT for more. de OH2GBA-2",
    "INFO 300",
    "NEXT",
]
BASE = st.from_regex(r"[A-Z0-9]{1,6}", fullmatch=True)
SSID = st.integers(min_value=0, max_value=MAX_SSID)
ID = st.from_regex(r"[A-Za-z0-9]{1,5}", fullmatch=True)
ADDRESSEE = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126, exclude_characters=":"), min_size=1, max_size=9
)
GROUP = st.from_regex(rf"[A-Z0-9]{{1,{QRU_GROUP_MAX}}}", fullmatch=True)


@given(st.text(max_size=12) | mutated_text(CALL_TEXTS))
def test_a_call_is_refused_with_callsign_error_only(text: str) -> None:
    """parse_call, normal_name and call_problem of any text raise nothing but CallsignError, and what
    they give is a call or an APRS-IS name in normal form."""
    try:
        base, ssid = parse_call(text)
    except CallsignError:
        pass
    else:
        assert AX25_CALL.fullmatch(base) and 0 <= ssid <= MAX_SSID
    try:
        name = normal_name(text)
    except CallsignError:
        pass
    else:
        assert INTERNET_NAME.fullmatch(name) and normal_name(name) == name
    assert isinstance(call_problem(text), str)


@given(BASE, SSID)
def test_a_formatted_call_parses_back(base: str, ssid: int) -> None:
    """parse_call of format_call gives the base and SSID back."""
    assert parse_call(format_call(base, ssid)) == (base, ssid)
    assert parse_call(format_call(base, ssid).lower()) == (base, ssid)


@given(st.binary(max_size=40) | mutated(MESSAGES))
def test_a_damaged_message_is_refused_with_message_error_only(body: bytes) -> None:
    """parse_message of any body raises nothing but MessageError, and gives an addressee of 1 to 9 characters."""
    try:
        message = parse_message(body)
    except MessageError:
        pass
    else:
        assert 1 <= len(message.addressee) <= 9
    line_of(b":" + body)
    reply_ack_of(body.decode("latin-1"))


@given(ADDRESSEE.filter(lambda a: a == a.strip()), ID, st.one_of(st.none(), st.just(""), ID))
def test_an_ack_parses_back(addressee: str, msg_id: str, reply_ack: str | None) -> None:
    """format_ack then parse_message gives the ack of the same number to the same station."""
    assert parse_message(format_ack(addressee, msg_id, reply_ack)) == Message(addressee, "", ack_id=msg_id)


@given(st.text(max_size=20) | mutated_text(QRU))
def test_qru_lines_are_read_without_raising(text: str) -> None:
    """ask_text of any text gives a request that asks the same, or MessagingError; listing_of and
    closing_of give None or what the line says."""
    try:
        asked = ask_text(text)
    except MessagingError:
        pass
    else:
        assert ask_text(asked) == asked
    listing = listing_of(text)
    assert listing is None or all(count >= 0 for _, count in listing.groups)
    closing = closing_of(text)
    assert closing is None or closing.sent >= 0


@given(
    BASE,
    st.lists(
        st.tuples(GROUP, st.integers(min_value=0, max_value=99999)), min_size=1, max_size=4, unique_by=lambda g: g[0]
    ),
    st.integers(min_value=1, max_value=20000),
)
def test_a_qru_listing_reads_back(call: str, groups: list[tuple[str, int]], km: int) -> None:
    """listing_of the texts info_texts writes gives back the groups that fit, their counts and the range."""
    texts = info_texts(call, groups, km)
    listings = [listing_of(text) for text in texts]
    assert all(listing is not None and listing.call == call for listing in listings)
    read = [group for listing in listings if listing for group in listing.groups]
    assert read == groups[: len(read)] and read
    last = listings[-1]
    assert last is not None and (last.max_objects, last.range, last.unit, last.more) == (
        ANSWER_FRAMES_MAX,
        km,
        "km",
        False,
    )


@given(st.datetimes(min_value=datetime(1970, 1, 1), timezones=st.just(UTC)))
def test_a_stamp_parses_back(at: datetime) -> None:
    """parse_stamp of stamp gives the same time to the microsecond."""
    assert parse_stamp(stamp(at)) == at


@given(mutated(INFOS), st.sampled_from(["APRS", "S32U6T", "GPS", "APDR16"]))
def test_a_decoded_packet_round_trips_through_its_json(info: bytes, destination: str) -> None:
    """decode_decoded of encode_decoded gives back what parse made of any damaged real field."""
    decoded = parse(info, "OH2XYZ", destination, NOW)
    assert decode_decoded(encode_decoded(decoded)) == decoded


@given(mutated([f"{c['source']}>{c['destination']},TCPIP*,qAC,T2FINLAND:{c['info']}".encode() for c in CASES]))
def test_an_internet_packet_round_trips_through_its_row(line: bytes) -> None:
    """packet_of of packet_row gives back an APRS-IS packet."""
    try:
        packet = parse_is_line(line, NOW)
    except IsLineError:
        return
    assert packet_of(packet_row(packet)) == packet


@given(
    st.builds(ax25.Address, BASE, SSID),
    st.builds(ax25.Address, BASE, SSID),
    mutated(INFOS),
    st.integers(min_value=1, max_value=9),
)
def test_a_radio_packet_round_trips_through_its_row(
    source: ax25.Address, destination: ax25.Address, info: bytes, radio: int
) -> None:
    """packet_of of packet_row gives back a packet heard on a radio, third-party or not."""
    frame = ax25.Frame(destination, source, (ax25.Address("WIDE1", 1, True),), info=info[: ax25.MAX_INFO])
    packet = packet_of_frame("in", ax25.encode(frame), frame, NOW, radio_id=radio)
    assert packet_of(packet_row(packet)) == packet
