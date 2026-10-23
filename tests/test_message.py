"""The rules of a message that need no I/O (neoaprs/message.py): who a message is addressed to, what text may be sent, and when the next attempt of a message is due."""
from dataclasses import replace
from datetime import timedelta

import pytest

from neoaprs.aprsmessage import MessageError
from neoaprs.callsign import CallsignError
from neoaprs.clock import utc
from neoaprs.message import (EMAIL_ATTEMPTS, FINAL_WAIT_SEC, MAX_ATTEMPTS, MSG_IDS, STATION_ATTEMPTS, MessageRecord, addressed_to, attempts_for, check_text, due_at, is_query, is_telemetry_definition, next_msg_id, normal_call,
                            same_call, schedule_sec, wait_after)

T0 = utc(2026, 10, 21, 12, 0, 0)


def sending(attempts: int = 0, last: object = None) -> MessageRecord:
    return MessageRecord(1, T0, "out", "OH2GBA", "OH2RDG", "hi", "7", "sending", attempts, last)  # type: ignore[arg-type]


@pytest.mark.parametrize("addressee, ours, expected", [
    ("OH2GBA", "OH2GBA", True), ("oh2gba", "OH2GBA", True), ("OH2GBA-0", "OH2GBA", True), ("OH2GBA", "OH2GBA-0", True), ("OH2GBA-7", "OH2GBA-7", True),
    ("OH2GBA", "OH2GBA-7", False), ("OH2GBA-7", "OH2GBA", False), ("OH2GBA-9", "OH2GBA-7", False), ("OH2GBB", "OH2GBA", False), ("BLN1", "OH2GBA", False),
    ("NOT A CALL", "OH2GBA", False), ("", "OH2GBA", False)])
def test_a_message_is_for_our_call_with_its_ssid_exactly_and_not_for_our_base_call(addressee: str, ours: str, expected: bool) -> None:
    assert addressed_to(addressee, ours) is expected


def test_the_same_call_ignores_case_and_a_zero_ssid_and_nothing_else() -> None:
    assert same_call("oh2gba", "OH2GBA-0") and not same_call("OH2GBA", "OH2GBA-1") and not same_call("OH2GBA", "garbage garbage")


def test_a_call_is_written_in_upper_case_without_a_zero_ssid() -> None:
    assert normal_call(" oh2rdg-7 ") == "OH2RDG-7" and normal_call("oh2rdg-0") == "OH2RDG"
    for bad in ("", "TOOLONGCALL", "OH2RDG-16", "OH2 RDG", "ÅÄÖ"):
        with pytest.raises(CallsignError):
            normal_call(bad)


@pytest.mark.parametrize("text, reason", [("", "empty"), ("   ", "empty"), ("x" * 68, "68 characters"), ("a|b", "|"), ("a~b", "~"), ("a{b", "{"), ("a\nb", "control"),
                                          ("a\x00b", "control"), ("\ud800", "not printable ASCII"), ("Hyvää päivää", "äö|ä|ä ö|not printable ASCII"), ("café", "é"), ("a\u200bb", "printable ASCII")])
def test_the_text_of_a_message_is_checked_and_the_reason_is_named(text: str, reason: str) -> None:
    with pytest.raises(MessageError, match=reason):
        check_text(text)


@pytest.mark.parametrize("text", ["x", "hello world", "x" * 67, "ack is fine inside a text, ack1", "73 de OH2GBA!"])
def test_a_text_that_fits_is_taken(text: str) -> None:
    check_text(text)


def test_a_message_is_given_4_attempts_and_one_to_the_email_gateway_2() -> None:
    assert (STATION_ATTEMPTS, EMAIL_ATTEMPTS) == (4, 2)
    assert [attempts_for(to) for to in ("OH2RDG", "OH2RDG-7", "EMAIL-2", "EMAIL-1", "EMAIL-22")] == [4, 4, 2, 4, 4]
    assert schedule_sec(STATION_ATTEMPTS) == (0, 30, 60, 120) and schedule_sec(EMAIL_ATTEMPTS) == (0, 30)
    assert [wait_after(n).total_seconds() for n in range(1, 5)] == [30, 30, 60, FINAL_WAIT_SEC]
    assert sum(wait_after(n).total_seconds() for n in range(1, 4)) == 120


def test_the_schedule_of_a_message_an_older_version_gave_more_attempts_goes_on_to_960_seconds() -> None:
    assert schedule_sec(6) == (0, 30, 60, 120, 240, 480) and schedule_sec(10)[-1] == 3840
    assert [wait_after(n, 6).total_seconds() for n in range(1, 7)] == [30, 30, 60, 120, 240, FINAL_WAIT_SEC]


def test_the_schedule_follows_the_number_of_attempts_doubles_and_no_wait_is_over_960_seconds() -> None:
    assert schedule_sec(1) == (0,) and schedule_sec(3) == (0, 30, 60)
    assert schedule_sec(MAX_ATTEMPTS) == (0, 30, 60, 120, 240, 480, 960, 1920, 2880, 3840) and MAX_ATTEMPTS == 10
    assert [wait_after(n, 10).total_seconds() for n in range(1, 11)] == [30, 30, 60, 120, 240, 480, 960, 960, 960, FINAL_WAIT_SEC]
    assert [wait_after(n, 3).total_seconds() for n in range(1, 4)] == [30, 30, FINAL_WAIT_SEC], "the last attempt of any number is waited for the same time"
    assert wait_after(1, 1).total_seconds() == FINAL_WAIT_SEC


def test_a_message_is_due_when_it_was_made_until_it_has_been_sent_and_then_a_wait_after_the_latest_attempt() -> None:
    assert due_at(sending()) == T0
    assert due_at(sending(1, T0)) == T0 + timedelta(seconds=30)
    assert due_at(sending(3, T0 + timedelta(seconds=60))) == T0 + timedelta(seconds=120)
    assert due_at(sending(6, T0 + timedelta(seconds=480))) == T0 + timedelta(seconds=480 + FINAL_WAIT_SEC)
    assert due_at(replace(sending(3, T0 + timedelta(seconds=60)), attempts_max=3)) == T0 + timedelta(seconds=60 + FINAL_WAIT_SEC), "a message of 3 attempts waits for the answer after its third"
    for state in ("acked", "rejected", "failed", "cancelled", "received"):
        assert due_at(MessageRecord(1, T0, "out", "A", "B", "x", "1", state)) is None  # type: ignore[arg-type]


def test_the_other_station_of_a_conversation_is_the_sender_of_a_message_that_came_in_and_the_addressee_of_one_we_sent() -> None:
    assert MessageRecord(1, T0, "in", "OH2RDG", "OH2GBA", "x", None, "received").peer == "OH2RDG"
    assert sending().peer == "OH2RDG"


def test_the_ids_we_give_are_every_two_character_id_once_in_the_order_01_to_99_a0_to_zz_0a_to_9z_and_00() -> None:
    assert len(MSG_IDS) == len(set(MSG_IDS)) == 1296 and all(len(i) == 2 and i.isalnum() and i == i.upper() for i in MSG_IDS)
    assert MSG_IDS[:3] == ("01", "02", "03") and MSG_IDS[98:102] == ("99", "A0", "A1", "A2") and MSG_IDS[99 + 935] == "ZZ" and MSG_IDS[1035:1037] == ("0A", "0B") and MSG_IDS[-2:] == ("9Z", "00")


def test_the_next_id_follows_the_last_skips_the_busy_ones_and_goes_round() -> None:
    assert next_msg_id(None, set()) == "01" and next_msg_id("07", set()) == "08" and next_msg_id("99", set()) == "A0" and next_msg_id("00", set()) == "01"
    assert next_msg_id("12345", set()) == "01", "an id of an older program is none of ours: the sequence begins"
    assert next_msg_id("07", {"08", "09"}) == "10"
    assert next_msg_id("07", set(MSG_IDS) - {"05"}) == "05", "all the way round"
    assert next_msg_id("07", set(MSG_IDS)) is None


@pytest.mark.parametrize("text, expected", [
    ("?APRSP", True), ("?APRSS", True), ("?APRSD", True), ("?APRST", True), ("?PING?", True), ("?APRS?", True), ("?APRSM", True), ("?APRSH OH2XYZ", True), ("?APRSO", True), ("?WX", True), ("?WX?", True),
    ("?IGATE?", True), ("?aprsp", True), (" ?APRSP ", True), ("?APRS?V34.02,-117.15,0200", True),
    ("?", False), ("?what", False), ("?APRSPX", False), ("APRSP", False), ("What?", False), ("hello ?APRSP", False), ("", False)])
def test_a_text_is_a_query_when_it_begins_with_a_question_mark_and_a_query_of_the_specification(text: str, expected: bool) -> None:
    assert is_query(text) is expected


@pytest.mark.parametrize("text, expected", [("PARM.Battery,Btemp", True), ("UNIT.v/100,deg.F", True), ("EQNS.0,5.2,0", True), ("BITS.10110000,Balloon", True),
                                            ("PARM", False), ("parm.x", False), ("the PARM. list", False), ("", False)])
def test_a_definition_of_telemetry_channels_begins_with_parm_unit_eqns_or_bits_and_a_dot(text: str, expected: bool) -> None:
    assert is_telemetry_definition(text) is expected
