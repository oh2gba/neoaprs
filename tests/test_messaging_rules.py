"""What messaging does with the messages of the specification's special cases (neoaprs/services/messaging.py, inbox.py, heard.py): a reused id with a new text, a text that only looks like an ack, messages to a
bulletin or a group, queries, telemetry definitions, the exact addressee, and the weather service's bulletins."""
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.message import MessageRecord, MessagingError
from neoaprs.packet import Packet
from neoaprs.source import Source
from neoaprs.tncmode import packet_of
from tests.test_messaging import Rig, started_rig


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await started_rig(tmp_path)


def received(rig: Rig) -> list[tuple[str, str | None]]:
    return [(m.text, m.msg_id) for m in rig.m.records() if m.state == "received"]


# ---- duplicates: sender, id and text

async def test_a_new_text_with_an_id_that_was_used_is_a_new_message_that_is_kept_acked_and_alerted(rig: Rig) -> None:
    told: list[MessageRecord] = []
    rig.m.inbox._alert = told.append
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "first", "12"))
    rig.clock.advance(60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "second", "12"))              # (the sender began its numbering again)
    await rig.settled()
    assert received(rig) == [("first", "12"), ("second", "12")] and [r.text for r in told] == ["first", "second"]
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack12"] * 2


async def test_the_same_text_with_the_same_id_is_a_repeat_whatever_reply_ack_it_carries(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "same", "12", reply=""))
    rig.clock.advance(60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "same", "12", reply="07"))     # (the retry carries another AA; the text is without it)
    await rig.settled()
    assert received(rig) == [("same", "12")] and rig.tnc.lines()[0].endswith(":ack12}") and rig.tnc.lines()[1].endswith(":ack12}07")


# ---- what is an ack

async def test_a_word_that_begins_like_an_ack_or_a_rej_and_settles_nothing_is_an_ordinary_message_without_an_id(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="oin"))                    # "rejoin"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="bar"))                    # "ackbar"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "acknowledged"))
    await rig.settled()
    assert received(rig) == [("rejoin", None), ("ackbar", None), ("acknowledged", None)]
    assert rig.tnc.sent == [], "no id: not acked"


async def test_an_ack_that_names_a_message_of_ours_is_an_ack_in_whatever_state_the_message_is(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))                     # (the plain ack as well as the reply-ack: the second settles nothing new)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="01"))
    await rig.settled()
    assert [m.state for m in rig.m.records()] == ["acked"], "no message came of the later ones, and the state stays"


async def test_an_ack_from_another_station_or_with_another_id_is_a_word_like_any_other(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2GBA", ack="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="02"))
    await rig.settled()
    assert received(rig) == [("ack01", None), ("ack02", None)] and rig.state(1).state == "sending"


def on_air(rig: Rig, source: str, info: bytes) -> Packet:
    """A packet as the radio would deliver it, the information field read by the parser."""
    frame = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse(source), (ax25.Address.parse("WIDE1-1"),), info=info)
    return packet_of("in", ax25.encode(frame), frame, rig.clock())


async def test_blanks_cr_and_lf_after_an_ack_or_a_message_number_do_not_count(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    rig.m.on_packet(on_air(rig, "OH2RDG", b":OH2GBA   :ack01  "))
    assert rig.state(1).state == "acked"
    rig.m.on_packet(on_air(rig, "OH2RDG", b":OH2GBA   :Hello{12}  "))
    rig.m.on_packet(on_air(rig, "OH2XYZ", b":OH2GBA   :Hi{7\r\n"))
    await rig.settled()
    assert received(rig) == [("Hello", "12"), ("Hi", "7")]
    assert rig.tnc.lines()[1:] == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack12}", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2XYZ   :ack7"]


async def test_a_message_whose_addressee_field_is_a_little_short_is_taken(rig: Rig) -> None:
    rig.m.on_packet(on_air(rig, "OH2RDG", b":OH2GBA:Moi{3"))
    await rig.settled()
    assert received(rig) == [("Moi", "3")] and rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack3"]


# ---- bulletins and groups

@pytest.mark.parametrize("to", ["BLN1", "BLNA", "BLN3HAMS", "ALL", "CQ", "QST", "NWS-WARNV", "SKYWRN", "CWA"])
async def test_a_message_to_a_bulletin_or_a_group_goes_out_once_without_an_id_and_is_kept_unconfirmed(rig: Rig, to: str) -> None:
    record = await rig.m.send(to.lower(), "Net tonight at 20")
    assert [f.info for f in rig.tnc.sent] == [f":{to:<9}:Net tonight at 20".encode()], "no id"
    assert (record.msg_id, record.state, record.attempts, record.attempts_max, record.to_call) == (None, "unconfirmed", 1, 1, to)
    await rig.pass_time(7200)
    assert len(rig.tnc.sent) == 1, "never retried"
    await rig.settled()
    assert [(m.state, m.attempts_max, m.msg_id) for m in await rig.log.recent()] == [("unconfirmed", 1, None)]


async def test_a_bulletin_waits_for_the_radio_like_any_message_and_is_then_sent_once(rig: Rig) -> None:
    await rig.radio(Source.State.WAITING)
    record = await rig.m.send("BLN1", "Road closed")
    assert (record.state, record.attempts) == ("sending", 0) and rig.tnc.sent == []
    await rig.radio(Source.State.CONNECTED)
    await rig.pass_time(1)
    assert [f.info for f in rig.tnc.sent] == [b":BLN1     :Road closed"] and rig.state().state == "unconfirmed"
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 1


async def test_a_bulletin_can_be_sent_again_and_goes_out_once_again(rig: Rig) -> None:
    await rig.m.send("QST", "Club news")
    again = rig.m.retry(1)
    assert (again.state, again.attempts) == ("unconfirmed", 1) and len(rig.tnc.sent) == 2


async def test_a_text_that_cannot_be_sent_is_refused_for_a_bulletin_as_for_any_message(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="printable ASCII"):
        await rig.m.send("BLN1", "Hyvää")
    assert rig.tnc.sent == [] and rig.m.records() == []


# ---- queries

@pytest.mark.parametrize("text", ["?APRSP", "?APRSS", "?APRSD", "?APRST", "?PING?", "?APRS?", "?APRSM", "?WX", "?aprsp", "?APRSH OH2XYZ"])
async def test_a_query_to_us_is_acked_when_it_carries_an_id_and_is_not_a_conversation_message(rig: Rig, text: str) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", text, "7"))                # (numbered against the specification: the ack stops the radio's retries)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", text))
    await rig.settled()
    assert [f.info for f in rig.tnc.sent] == [b":OH2RDG   :ack7"] and rig.m.records() == [] and await rig.log.recent() == [] and await rig.log.recent(overheard=True) == []


async def test_a_text_with_a_question_mark_that_is_no_query_is_a_message(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "?what is the time", "7"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Are you there?", "8"))
    await rig.settled()
    assert received(rig) == [("?what is the time", "7"), ("Are you there?", "8")] and len(rig.tnc.sent) == 2


# ---- telemetry definitions

@pytest.mark.parametrize("text", ["PARM.Battery,Btemp,ATemp", "UNIT.v/100,deg.F,deg.F", "EQNS.0,5.2,0,0,.53,-32", "BITS.10110000,N0QBF's Big Balloon"])
@pytest.mark.parametrize("to", ["OH2GBA", "OH2XYZ"])
async def test_a_definition_of_telemetry_channels_is_neither_a_message_nor_overheard_nor_acked(rig: Rig, text: str, to: str) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", to, text, "7"))
    await rig.settled()
    assert rig.tnc.sent == [] and rig.m.records() == [] and await rig.log.recent() == [] and await rig.log.recent(overheard=True) == [] and rig.board == []


# ---- weather service bulletins

@pytest.mark.parametrize("addressee", ["NWS-WARNV", "NWS-TSTWR", "SKYWRN", "CWASKY"])
async def test_a_weather_service_bulletin_goes_to_the_board_and_is_neither_overheard_nor_acked(rig: Rig, addressee: str) -> None:
    packet = rig.heard("OH2RDG", addressee, "092010z,THUNDER_STORM,AR_ASHLEY,", "S9JbA")
    rig.m.on_packet(packet)
    await rig.settled()
    assert [p for p, _ in rig.board] == [packet] and rig.tnc.sent == [] and rig.m.records() == [] and await rig.log.recent(overheard=True) == []


# ---- the exact addressee

async def test_a_message_is_ours_to_the_call_with_its_ssid_and_not_to_the_base_call_when_ours_has_an_ssid(rig: Rig) -> None:
    rig.config = replace(rig.config, station_call="OH2GBA-3")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA-3", "ours", "1"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "base", "2"))
    await rig.settled()
    assert received(rig) == [("ours", "1")] and [f.info for f in rig.tnc.sent] == [b":OH2RDG   :ack1"]


# ---- requests to QRU

async def test_a_request_to_qru_that_the_qru_server_takes_is_acked_when_it_has_an_id_and_is_neither_kept_nor_overheard(rig: Rig) -> None:
    taken: list[tuple[str, str]] = []
    rig.m.inbox._qru = lambda packet, message: taken.append((packet.sender, message.text)) is None
    rig.m.on_packet(rig.heard("OH2RDG", "QRU", "RP70", "7"))
    rig.m.on_packet(rig.heard("OH2RDG", "qru", "INFO"))
    await rig.settled()
    assert taken == [("OH2RDG", "RP70"), ("OH2RDG", "INFO")] and [f.info for f in rig.tnc.sent] == [b":OH2RDG   :ack7"]
    assert rig.m.records() == [] and await rig.log.recent() == [] and await rig.log.recent(overheard=True) == []


async def test_a_request_to_qru_that_is_not_taken_or_has_no_server_is_a_message_overheard_like_any_other(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "QRU", "INFO", "7"))
    rig.m.inbox._qru = lambda packet, message: False
    rig.m.on_packet(rig.heard("OH2ABC", "QRU", "FOOD", "8"))
    await rig.settled()
    assert [(m.from_call, m.text, m.state) for m in await rig.log.recent(overheard=True)] == [("OH2ABC", "FOOD", "overheard"), ("OH2RDG", "INFO", "overheard")] and rig.tnc.sent == []


async def test_an_ack_or_a_reject_to_qru_and_a_message_to_another_station_are_not_given_to_the_qru_server(rig: Rig) -> None:
    taken: list[str] = []
    rig.m.inbox._qru = lambda packet, message: taken.append(message.text) is None
    rig.m.on_packet(rig.heard("OH2RDG", "QRU", ack="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "QRU", rej="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "QRUX", "INFO"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2XYZ", "INFO"))
    await rig.settled()
    assert taken == []
