"""The rules of a message that need no I/O (neoaprs/message.py): the addressee, the text allowed,
and when the next attempt is due.
"""

from dataclasses import fields, replace
from datetime import timedelta

import pytest

from neoaprs.aprsmessage import MessageError
from neoaprs.callsign import CallsignError
from neoaprs.clock import utc
from neoaprs.coded import CodedError
from neoaprs.message import (
    EMAIL_ATTEMPTS,
    FINAL_WAIT_SEC,
    MSG_IDS,
    STATION_ATTEMPTS,
    MessageRecord,
    addressed_to,
    attempts_for,
    check_text,
    due_at,
    is_query,
    is_telemetry_definition,
    next_msg_id,
    normal_call,
    normal_path,
    path_choice,
    query_text,
    request_path,
    retry_pause,
    same_call,
    schedule_sec,
    wait_after,
    is_internet_service,
)

from neoaprs.radiotype import FM_ID, HF_ID
from tests.support.english import page_english

T0 = utc(2026, 10, 21, 12, 0, 0)


def sending(attempts: int = 0, last: object = None) -> MessageRecord:
    return MessageRecord(1, T0, "out", "OH2GBA", "OH2RDG", "hi", "7", "sending", attempts, last)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "addressee, ours, expected",
    [
        ("OH2GBA", "OH2GBA", True),
        ("oh2gba", "OH2GBA", True),
        ("OH2GBA-0", "OH2GBA", True),
        ("OH2GBA", "OH2GBA-0", True),
        ("OH2GBA-7", "OH2GBA-7", True),
        ("OH2GBA", "OH2GBA-7", False),
        ("OH2GBA-7", "OH2GBA", False),
        ("OH2GBA-9", "OH2GBA-7", False),
        ("OH2GBB", "OH2GBA", False),
        ("BLN1", "OH2GBA", False),
        ("NOT A CALL", "OH2GBA", False),
        ("", "OH2GBA", False),
    ],
)
def test_a_message_is_for_our_call_with_its_ssid_exactly_and_not_for_our_base_call(
    addressee: str, ours: str, expected: bool
) -> None:
    assert addressed_to(addressee, ours) is expected


def test_the_same_call_ignores_case_and_a_zero_ssid_and_nothing_else() -> None:
    assert (
        same_call("oh2gba", "OH2GBA-0")
        and not same_call("OH2GBA", "OH2GBA-1")
        and not same_call("OH2GBA", "garbage garbage")
    )


def test_a_call_is_written_in_upper_case_without_a_zero_ssid() -> None:
    assert normal_call(" oh2rdg-7 ") == "OH2RDG-7" and normal_call("oh2rdg-0") == "OH2RDG"
    for bad in ("", "TOOLONGCALL", "OH2RDG-16", "OH2 RDG", "ÅÄÖ"):
        with pytest.raises(CallsignError):
            normal_call(bad)


@pytest.mark.parametrize(
    "text, reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("x" * 68, "68 characters"),
        ("a|b", "|"),
        ("a~b", "~"),
        ("a{b", "{"),
        ("a\nb", "control"),
        ("a\x00b", "control"),
        ("\ud800", "not printable ASCII"),
        ("Hyvää päivää", "äö|ä|ä ö|not printable ASCII"),
        ("café", "é"),
        ("a\u200bb", "printable ASCII"),
    ],
)
def test_the_text_of_a_message_is_checked_and_the_reason_is_named(text: str, reason: str) -> None:
    with pytest.raises(MessageError, match=reason):
        check_text(text)


@pytest.mark.parametrize("text", ["x", "hello world", "x" * 67, "ack is fine inside a text, ack1", "73 de OH2GBA!"])
def test_a_text_that_fits_is_taken(text: str) -> None:
    check_text(text)


def test_a_message_is_given_4_attempts_and_one_to_the_email_gateway_2() -> None:
    assert (STATION_ATTEMPTS, EMAIL_ATTEMPTS) == (4, 2)
    assert [attempts_for(to) for to in ("OH2RDG", "OH2RDG-7", "EMAIL-2", "EMAIL-1", "EMAIL-22")] == [4, 4, 2, 4, 4]
    assert schedule_sec(STATION_ATTEMPTS) == (0, 32, 64, 128) and schedule_sec(EMAIL_ATTEMPTS) == (0, 32)
    assert [wait_after(n).total_seconds() for n in range(1, 5)] == [32, 32, 64, FINAL_WAIT_SEC], (
        "no retry exactly at the edge of the digipeaters' 30 s duplicate window"
    )
    assert sum(wait_after(n).total_seconds() for n in range(1, 4)) == 128


def test_the_schedule_of_a_message_an_older_version_gave_more_attempts_goes_on_to_960_seconds() -> None:
    assert schedule_sec(6) == (0, 32, 64, 128, 256, 512) and schedule_sec(10)[-1] == 3904
    assert [wait_after(n, 6).total_seconds() for n in range(1, 7)] == [32, 32, 64, 128, 256, FINAL_WAIT_SEC]


def test_the_schedule_follows_the_number_of_attempts_doubles_and_no_wait_is_over_960_seconds() -> None:
    assert schedule_sec(1) == (0,) and schedule_sec(3) == (0, 32, 64)
    assert schedule_sec(10) == (0, 32, 64, 128, 256, 512, 1024, 1984, 2944, 3904)
    assert [wait_after(n, 10).total_seconds() for n in range(1, 11)] == [
        32,
        32,
        64,
        128,
        256,
        512,
        960,
        960,
        960,
        FINAL_WAIT_SEC,
    ]
    assert [wait_after(n, 3).total_seconds() for n in range(1, 4)] == [32, 32, FINAL_WAIT_SEC], (
        "the last attempt of any number is waited for the same time"
    )
    assert wait_after(1, 1).total_seconds() == FINAL_WAIT_SEC


def test_a_message_is_due_when_it_was_made_until_it_has_been_sent_and_then_a_wait_after_the_latest_attempt() -> None:
    assert due_at(sending()) == T0
    assert due_at(sending(1, T0)) == T0 + timedelta(seconds=32)
    assert due_at(sending(3, T0 + timedelta(seconds=64))) == T0 + timedelta(seconds=128)
    assert due_at(sending(6, T0 + timedelta(seconds=480))) == T0 + timedelta(seconds=480 + FINAL_WAIT_SEC)
    assert due_at(replace(sending(3, T0 + timedelta(seconds=60)), attempts_max=3)) == T0 + timedelta(
        seconds=60 + FINAL_WAIT_SEC
    ), "a message of 3 attempts waits for the answer after its third"
    for state in ("acked", "rejected", "failed", "cancelled", "received"):
        assert due_at(MessageRecord(1, T0, "out", "A", "B", "x", "1", state)) is None  # type: ignore[arg-type]


def test_the_other_station_of_a_conversation_is_the_sender_of_a_message_that_came_in_and_the_addressee_of_one_we_sent() -> (
    None
):
    assert MessageRecord(1, T0, "in", "OH2RDG", "OH2GBA", "x", None, "received").peer == "OH2RDG"
    assert sending().peer == "OH2RDG"


def test_a_message_that_came_in_keeps_the_id_of_its_radio() -> None:
    assert "radio_id" in {f.name for f in fields(MessageRecord)}
    came = [
        MessageRecord(1, T0, "in", "OH2RDG", "OH2GBA", "x", None, "received", radio_id=radio_id)
        for radio_id in (None, FM_ID, HF_ID, 3)
    ]
    assert [m.radio_id for m in came] == [None, 1, 2, 3], "any radio by its id"
    assert sending().radio_id is None, "one of ours: its attempts say"
    assert (
        replace(came[1], radio_id=HF_ID).radio_id == HF_ID
        and replace(came[1], radio_id=3).radio_id == 3
        and replace(came[2], state="overheard").radio_id == HF_ID
    )


def test_the_ids_we_give_are_every_two_character_id_once_in_the_order_01_to_99_a0_to_zz_0a_to_9z_and_00() -> None:
    assert len(MSG_IDS) == len(set(MSG_IDS)) == 1296 and all(
        len(i) == 2 and i.isalnum() and i == i.upper() for i in MSG_IDS
    )
    assert (
        MSG_IDS[:3] == ("01", "02", "03")
        and MSG_IDS[98:102] == ("99", "A0", "A1", "A2")
        and MSG_IDS[99 + 935] == "ZZ"
        and MSG_IDS[1035:1037] == ("0A", "0B")
        and MSG_IDS[-2:] == ("9Z", "00")
    )


def test_the_next_id_follows_the_last_skips_the_busy_ones_and_goes_round() -> None:
    assert (
        next_msg_id(None, set()) == "01"
        and next_msg_id("07", set()) == "08"
        and next_msg_id("99", set()) == "A0"
        and next_msg_id("00", set()) == "01"
    )
    assert next_msg_id("12345", set()) == "01", "an id of an older program is none of ours: the sequence begins"
    assert next_msg_id("07", {"08", "09"}) == "10"
    assert next_msg_id("07", set(MSG_IDS) - {"05"}) == "05", "all the way round"
    assert next_msg_id("07", set(MSG_IDS)) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("?APRSP", True),
        ("?APRSS", True),
        ("?APRSD", True),
        ("?APRST", True),
        ("?PING?", True),
        ("?APRS?", True),
        ("?APRSM", True),
        ("?APRSH OH2XYZ", True),
        ("?APRSO", True),
        ("?WX", True),
        ("?WX?", True),
        ("?IGATE?", True),
        ("?aprsp", True),
        (" ?APRSP ", True),
        ("?APRS?V34.02,-117.15,0200", True),
        ("?", False),
        ("?what", False),
        ("?APRSPX", False),
        ("APRSP", False),
        ("What?", False),
        ("hello ?APRSP", False),
        ("", False),
    ],
)
def test_a_text_is_a_query_when_it_begins_with_a_question_mark_and_a_query_of_the_specification(
    text: str, expected: bool
) -> None:
    assert is_query(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("PARM.Battery,Btemp", True),
        ("UNIT.v/100,deg.F", True),
        ("EQNS.0,5.2,0", True),
        ("BITS.10110000,Balloon", True),
        ("PARM", False),
        ("parm.x", False),
        ("the PARM. list", False),
        ("", False),
    ],
)
def test_a_definition_of_telemetry_channels_begins_with_parm_unit_eqns_or_bits_and_a_dot(
    text: str, expected: bool
) -> None:
    assert is_telemetry_definition(text) is expected


# ---- the reasons a text, a path or a query is refused, as the page shows them


@pytest.mark.parametrize(
    "text, code, params",
    [
        ("", "message.empty", {}),
        (" ", "message.empty", {}),
        ("x" * 68, "message.too_long", {"length": 68, "max": 67}),
        ("a\tb", "message.control", {}),
    ],
)
def test_a_refused_text_has_the_code_and_values_the_page_says_it_with(text: str, code: str, params: dict) -> None:
    with pytest.raises(MessageError) as refused:
        check_text(text)
    assert (refused.value.code, refused.value.params) == (code, params)
    assert str(refused.value) == page_english(refused.value)


def test_a_text_with_characters_a_message_cannot_carry_names_each_of_them_once_in_their_order() -> None:
    with pytest.raises(MessageError) as refused:
        check_text("a~b|c~")
    assert (refused.value.code, refused.value.params) == ("message.forbidden", {"chars": "| ~"})
    assert str(refused.value) == "the text has | ~, which a message cannot carry (| ~ { are not allowed)"


@pytest.mark.parametrize(
    "text, chars, said",
    [
        ("Hyvää päivää", "ä", "ä"),
        ("café ok ö é", "éö", "éö"),
        ("a\u200bb", "", "a character"),
    ],
)
def test_a_text_that_is_not_printable_ascii_names_its_printable_characters_once_or_says_a_character(
    text: str, chars: str, said: str
) -> None:
    with pytest.raises(MessageError) as refused:
        check_text(text)
    assert (refused.value.code, refused.value.params) == ("message.not_ascii", {"chars": chars})
    assert str(refused.value) == (
        f"the text has {said} that is not printable ASCII: a message carries printable ASCII only"
    )


def test_a_path_is_its_calls_in_upper_case_with_the_empty_pieces_left_out() -> None:
    assert normal_path(" wide1-1, ,WIDE2-2,oh2rch-0,") == ("WIDE1-1", "WIDE2-2", "OH2RCH")
    assert normal_path(",".join(["WIDE2-2"] * 8)) == ("WIDE2-2",) * 8


@pytest.mark.parametrize(
    "text, code, params",
    [
        ("WIDE1-1,direct", "path.direct_alone", {"word": "DIRECT"}),
        (",".join(["WIDE2-2"] * 9), "path.too_long", {"count": 9, "max": 8}),
    ],
)
def test_a_path_with_direct_among_its_calls_or_more_than_eight_is_refused(text: str, code: str, params: dict) -> None:
    with pytest.raises(CodedError) as refused:
        normal_path(text)
    assert (refused.value.code, refused.value.params) == (code, params)
    assert str(refused.value) == page_english(refused.value)


def test_an_empty_path_is_the_automatic_one_direct_alone_is_none_and_any_other_its_calls() -> None:
    assert path_choice("") is None and path_choice("   ") is None
    assert path_choice("direct") == () and path_choice(" DIRECT ") == ()
    assert path_choice("wide1-1") == ("WIDE1-1",)


def test_the_path_of_a_request_is_the_typed_one_or_the_automatic_one_and_rf_only_adds_rfonly_last() -> None:
    auto = ("WIDE1-1", "WIDE2-1")
    assert request_path(None, auto, False) == auto and request_path("  ", auto, False) == auto
    assert request_path("oh2rch", auto, False) == ("OH2RCH",)
    assert request_path("direct", auto, False) == ()
    assert request_path(None, auto, True) == (*auto, "RFONLY")
    assert request_path("direct", auto, True) == ("RFONLY",)
    assert request_path("WIDE1-1,NOGATE", auto, True) == ("WIDE1-1", "NOGATE"), "NOGATE keeps it off already"
    assert request_path(",".join(["WIDE2-2"] * 7), auto, True) == ("WIDE2-2",) * 7 + ("RFONLY",)


def test_a_path_of_eight_with_rf_only_is_refused_with_its_count() -> None:
    with pytest.raises(CodedError) as refused:
        request_path(",".join(["WIDE2-2"] * 8), (), True)
    assert (refused.value.code, refused.value.params) == ("path.too_long_rf_only", {"count": 8, "max": 8})
    assert str(refused.value) == (
        "path too long for Radio only: 8 digipeaters and RFONLY make more than the 8 a path may have"
    )


def test_a_query_is_sent_trimmed_and_in_upper_case() -> None:
    assert query_text("  ?aprsp ") == "?APRSP" and query_text("?x") == "?X"


@pytest.mark.parametrize("text", ["?", " ? ", "", "APRSP?", "x?y"])
def test_a_query_that_does_not_begin_with_a_question_mark_and_say_something_after_it_is_refused(text: str) -> None:
    with pytest.raises(MessageError) as refused:
        query_text(text)
    assert refused.value.code == "query.form" and str(refused.value) == page_english(refused.value)


def test_a_query_is_held_to_the_rules_of_a_text() -> None:
    with pytest.raises(MessageError) as refused:
        query_text("?APRS|")
    assert refused.value.code == "message.forbidden"


# ---- the pause before a retry


def test_a_retry_pause_is_none_without_jitter_before_the_first_attempt_and_after_the_last() -> None:
    assert retry_pause(sending(1, T0), 0) == timedelta(0)
    assert retry_pause(sending(1, T0), -5) == timedelta(0)
    assert retry_pause(sending(0), 20) == timedelta(0)
    assert retry_pause(sending(STATION_ATTEMPTS, T0), 20) == timedelta(0)
    assert retry_pause(sending(STATION_ATTEMPTS + 1, T0), 20) == timedelta(0)


def test_a_retry_pause_is_the_same_for_the_same_attempt_and_spreads_over_the_jitter_for_others() -> None:
    def pause(to: str, number: int, attempts: int, jitter: int = 20) -> float:
        record = replace(sending(attempts, T0), to_call=to, id=number)
        return retry_pause(record, jitter).total_seconds()

    assert pause("OH2RDG", 1, 1) == pause("OH2RDG", 1, 1)
    pauses = [pause(f"OH2R{n % 10}", n, 1 + n % 3) for n in range(300)]
    assert all(0 <= p <= 20 for p in pauses)
    assert min(pauses) < 1 and max(pauses) > 19, "the whole span from no pause to the jitter is used"
    assert pause("OH2RDG", 1, 1) != pause("OH2RDG", 1, 2) != pause("OH2RDG", 2, 2) != pause("OH2RDX", 2, 2)
    assert pause("OH2RDG", 1, STATION_ATTEMPTS - 1) > 0
    assert max(pause(f"OH2R{n}", n, 1, 3) for n in range(100)) <= 3
    assert 0 < max(pause(f"OH2R{n}", n, 1, 1) for n in range(10)) <= 1, "a jitter of one second is one"


def test_a_message_counted_as_sent_with_no_time_of_its_attempt_is_due_when_it_was_made() -> None:
    assert due_at(replace(sending(2, T0), last_attempt_at=None)) == T0
    assert due_at(replace(sending(0), last_attempt_at=T0 + timedelta(seconds=5))) == T0


def test_the_internet_services_are_known_by_their_exact_calls_whatever_the_case_and_blanks() -> None:
    assert [is_internet_service(c) for c in ("ANSRVR", " ota ", "EMAIL-2", "email-2")] == [True] * 4
    assert [is_internet_service(c) for c in ("ANSRVR-1", "OTA1", "EMAIL", "OH2GBA", "")] == [False] * 5
