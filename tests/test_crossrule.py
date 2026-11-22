"""The pure rules of passing a packet between two radios (neoaprs/crossrule.py): the request and its
step, what is never passed, the slow radios and the reply paths."""
from datetime import datetime, timezone

import pytest

from neoaprs import ax25
from neoaprs.crossrule import back_path, cross, first_unused, message_id, not_to_pass, reply_path, slow_channel, spliced
from neoaprs.packet import Packet
from neoaprs.radiotypes import TYPES
from neoaprs.tncmode import packet_of
from tests.support.air import ack_info, message_info, reject_info

PAIR = ("OH2GBA", 12)
OURS = {("OH2GBA", 0), PAIR}
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
POSITION = b"!6010.20N/02456.40E-test"


def frame(path: str, source: str = "OH2XYZ", info: bytes = POSITION, destination: str = "APRS") -> ax25.Frame:
    return ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path.split(",") if p), info=info)


def packet_for(info: bytes, path: str = "OH2GBA-12", source: str = "OH2XYZ", dummy: bool = False) -> Packet:
    f = frame(path, source, info)
    return packet_of("in", ax25.encode(f), f, NOW, dummy=dummy)


def text_of(f: ax25.Frame | None) -> str | None:
    return None if f is None else f.path_text


def test_a_path_whose_first_unused_hop_is_the_pair_call_is_a_request_with_that_hop_marked_used() -> None:
    assert text_of(cross(frame("OH2GBA-12"), PAIR, OURS)) == "OH2GBA-12*"
    assert text_of(cross(frame("OH2GBA-12,WIDE2-1"), PAIR, OURS)) == "OH2GBA-12*,WIDE2-1"


def test_the_hop_is_marked_where_it_stands_after_used_hops_and_nothing_else_changes() -> None:
    f = frame("OH2RCH-2*,OH2GBA-12,WIDE2-1,OH2ABC-1")
    out = cross(f, PAIR, OURS)
    assert out is not None
    assert [str(a) for a in out.path] == ["OH2RCH-2*", "OH2GBA-12*", "WIDE2-1", "OH2ABC-1"]
    assert (out.source, out.destination, out.info, out.control, out.pid) == (f.source, f.destination, f.info, f.control, f.pid)


@pytest.mark.parametrize("path", ["WIDE1-1", "WIDE1-1,WIDE2-1", "OH2GBA", "OH2GBA-11", "OH2GBA-13", "WIDE2-1,OH2GBA-12", "OH2RCH-2*", "", "OH2GBA-12*"])
def test_any_other_first_unused_hop_or_none_is_no_request(path: str) -> None:
    assert cross(frame(path), PAIR, OURS) is None


def test_the_ssid_of_the_call_must_match_exactly() -> None:
    assert cross(frame("OH2GBA-12"), ("OH2GBA", 11), OURS) is None
    assert text_of(cross(frame("OH2GBA-11"), ("OH2GBA", 11), OURS)) == "OH2GBA-11*"


def test_a_source_that_is_one_of_our_calls_is_never_passed() -> None:
    assert cross(frame("OH2GBA-12", source="OH2GBA"), PAIR, OURS) is None
    assert cross(frame("OH2GBA-12", source="OH2GBA-12"), PAIR, OURS) is None
    assert cross(frame("OH2GBA-12", source="OH2GBA-1"), PAIR, OURS) is not None


def test_a_path_that_shows_the_pair_call_used_already_is_not_passed_again() -> None:
    assert cross(frame("OH2GBA-12*,OH2GBA-12"), PAIR, OURS) is None
    assert cross(frame("OH2GBA-12*,OH2GBA-13"), ("OH2GBA", 13), OURS) is not None


def test_a_path_with_tcpip_or_tcpxx_anywhere_is_not_passed() -> None:
    assert cross(frame("OH2GBA-12,TCPIP"), PAIR, OURS) is None
    assert cross(frame("TCPXX*,OH2GBA-12"), PAIR, OURS) is None


def test_a_frame_that_is_not_a_ui_frame_is_no_request() -> None:
    f = frame("OH2GBA-12")
    assert cross(ax25.Frame(f.destination, f.source, f.path, control=0x01, info=f.info), PAIR, OURS) is None


def test_the_first_unused_hop_is_found_wherever_it_stands() -> None:
    assert first_unused(frame("A*,B*,C,D*")) == 2
    assert first_unused(frame("A*,B*")) is None
    assert first_unused(frame("")) is None


def test_the_bytes_sent_again_are_the_heard_ones_with_only_the_path_changed() -> None:
    heard = frame("OH2GBA-12,WIDE2-1")
    raw = ax25.encode(heard)
    out = cross(heard, PAIR, OURS)
    assert out is not None
    assert spliced(raw, heard, out) == ax25.encode(out)
    assert spliced(raw, heard, out)[: 2 * ax25.ADDRESS_LEN] == raw[: 2 * ax25.ADDRESS_LEN]


def test_a_third_party_packet_is_never_passed_a_dummy_radios_too() -> None:
    info = b"}OH2XYZ>APRS,TCPIP,OH7JHF-1*::OH2ABC   :hi{12"
    assert not_to_pass(packet_for(info, source="OH7JHF-1"), {"OH2GBA"}, True)
    assert not_to_pass(packet_for(info, source="OH7JHF-1", dummy=True), {"OH2GBA"}, True)


def test_a_general_query_is_never_passed() -> None:
    assert not_to_pass(packet_for(b"?APRS?"), {"OH2GBA"}, True)
    assert not_to_pass(packet_for(b"?IGATE?"), {"OH2GBA"}, False)


def test_a_message_to_one_of_our_calls_is_never_passed_whatever_it_is() -> None:
    ours = {"OH2GBA", "OH2GBA-12"}
    assert not_to_pass(packet_for(message_info("OH2GBA", "hi", "1")), ours, True)
    assert not_to_pass(packet_for(message_info("OH2GBA-12", "hi", "1")), ours, True)
    assert not_to_pass(packet_for(ack_info("OH2GBA-12", "1")), ours, True)
    assert not_to_pass(packet_for(reject_info("OH2GBA", "1")), ours, True)
    assert not_to_pass(packet_for(message_info("OH2GBA-12", "?APRSP")), ours, True)


def test_a_message_to_another_station_and_a_position_are_passed() -> None:
    ours = {"OH2GBA", "OH2GBA-12"}
    assert not not_to_pass(packet_for(message_info("OH2ABC-9", "hi", "1")), ours, False)
    assert not not_to_pass(packet_for(ack_info("OH2ABC-9", "1")), ours, False)
    assert not not_to_pass(packet_for(POSITION), ours, False)


def test_a_directed_query_is_refused_onto_a_radio_without_paths_and_passes_onto_one_with_paths() -> None:
    query = packet_for(message_info("OH2ABC-9", "?APRSP"))
    assert not_to_pass(query, {"OH2GBA"}, False)
    assert not not_to_pass(query, {"OH2GBA"}, True)


def test_the_id_of_a_message_to_a_station_is_what_an_ack_can_answer() -> None:
    assert message_id(packet_for(message_info("OH2ABC-9", "hi", "17"))) == "17"
    assert message_id(packet_for(message_info("OH2ABC-9", "hi"))) is None
    assert message_id(packet_for(ack_info("OH2ABC-9", "17"))) is None
    assert message_id(packet_for(reject_info("OH2ABC-9", "17"))) is None
    assert message_id(packet_for(message_info("OH2ABC-9", "PARM.a,b", "17"))) is None
    assert message_id(packet_for(message_info("BLN1", "storm", "17"))) is None
    assert message_id(packet_for(message_info("CQ", "hello", "17"))) is None
    assert message_id(packet_for(POSITION)) is None


@pytest.mark.parametrize("rtype", TYPES, ids=lambda t: t.key)
def test_the_slow_channels_are_the_types_that_pause_before_a_retry(rtype) -> None:
    assert slow_channel(rtype.limits) == (rtype.kind in ("hf", "lora"))


def test_the_sound_card_and_the_fm_types_are_fast_and_mercury_is_slow() -> None:
    by_key = {t.key: t for t in TYPES}
    assert not slow_channel(by_key["kiss"].limits)
    assert not slow_channel(by_key["dummy"].limits)
    assert slow_channel(by_key["mercury"].limits)
    assert slow_channel(by_key["dummy-hf"].limits)
    assert not any(slow_channel(t.limits) for t in TYPES if t.driver == "direwolf")


@pytest.mark.parametrize("last, reply", [
    (("OH2GBA-12*",), ("OH2GBA-12",)),
    (("OH2RCH-2*", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    (("WIDE1*", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    (("OH2GBA*", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    (("OH2GBA-2*", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    (("OH2RCH-2*", "OH2GBA*", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    ((), ()),
    (("WIDE1*",), ()),
    (("OH2RCH-2*", "WIDE2-1*"), ()),
    (("OH2GBA-12*", "OH2ABC-3"), ("OH2GBA-12",)),
    (("OH2RCH-2", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    (("OH2GBA", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
    (("WIDE1", "OH2GBA-12*"), ("OH2GBA-12", "WIDE2-1")),
])
def test_the_reply_path_goes_through_the_last_used_hop_when_it_is_a_gateway(last: tuple[str, ...], reply: tuple[str, ...]) -> None:
    assert reply_path(last, {"OH2ABC", "OH2ABC-1"}) == reply


def test_after_two_pair_calls_in_turn_the_reply_names_the_last_one_and_comes_back_one_crossing() -> None:
    assert reply_path(("OH2GBA-11*", "OH2GBA-12*"), {"OH2ABC"}) == ("OH2GBA-12", "WIDE2-1"), "any used hop before the gateway's call may be a digipeater on the way, so one wide hop follows"


def test_a_last_used_hop_that_is_one_of_our_own_calls_gives_no_reply_path() -> None:
    assert reply_path(("OH2RCH-2*", "OH2ABC-1*"), {"OH2ABC", "OH2ABC-1"}) == ()


def test_the_hops_used_stay_the_call_is_marked_used_and_the_unused_are_dropped() -> None:
    path = frame("WIDE1*,OH2RCH-2*,WIDE2-1,OH2ABC-1").path
    assert [str(a) for a in back_path(path, PAIR)] == ["WIDE1*", "OH2RCH-2*", "OH2GBA-12*"]
    assert [str(a) for a in back_path(frame("WIDE1-1,WIDE2-1").path, PAIR)] == ["OH2GBA-12*"]
