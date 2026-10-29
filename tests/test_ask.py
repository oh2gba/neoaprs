"""The directed queries the page can send (`Asking.ask`, the command `query`): the text of each kind on the air as a message without an id, sent once and never again, the rate limit of one query of a kind to a station in
60 seconds, the refusals (a call that is none, ourselves, the interlock, a silent radio, a station that is unknown or takes no messages), the row kept in the conversation, and the command over the socket. Everything goes
through a stub Tnc or the fake radio of an `Env`: nothing is transmitted on a real radio."""
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.coded import CodedError
from neoaprs.message import QUERIES, QUERY_EVERY_SEC, MessagingError
from neoaprs.source import Source
from neoaprs.web.messagewire import MessageRow
from tests.support.air import on_air
from tests.support.env import Env
from tests.support.wsclient import WsClient
from tests.test_messaging import Rig, started_rig
from tests.test_web import with_page


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await started_rig(tmp_path)


# ---- the service

@pytest.mark.parametrize(("kind", "text"), [("position", "?APRSP"), ("status", "?APRSS"), ("heard", "?APRSD"), ("trace", "?APRST")])
async def test_each_kind_goes_out_as_its_query_text_in_a_message_without_an_id(rig: Rig, kind: str, text: str) -> None:
    record = await rig.m.asking.ask("oh2rdg", kind)
    assert QUERIES[kind] == text
    assert rig.tnc.lines() == [f"OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :{text}"], "no {id}: nobody acks a query"
    assert (record.direction, record.to_call, record.text, record.msg_id, record.state, record.attempts, record.attempts_max) == ("out", "OH2RDG", text, None, "unconfirmed", 1, 1)


async def test_the_query_goes_by_the_path_of_the_station_and_with_its_ssid(rig: Rig) -> None:
    await rig.prefs.set_path("OH2RDG-7", "OH2RCH-2")
    await rig.m.asking.ask("OH2RDG-7", "status")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,OH2RCH-2::OH2RDG-7 :?APRSS"]


async def test_a_query_is_sent_once_and_never_again_whatever_time_passes(rig: Rig) -> None:
    await rig.m.asking.ask("OH2RDG", "position")
    await rig.pass_time(7200)
    assert len(rig.tnc.sent) == 1
    assert rig.state().state == "unconfirmed"


async def test_the_query_is_kept_as_a_message_of_the_conversation_with_the_station(rig: Rig) -> None:
    await rig.m.asking.ask("OH2RDG", "heard")
    await rig.settled()
    [kept] = await rig.log.recent()
    assert (kept.peer, kept.text, kept.msg_id, kept.state, kept.attempts_max) == ("OH2RDG", "?APRSD", None, "unconfirmed", 1)


async def test_the_same_query_to_the_same_station_within_a_minute_is_refused_and_nothing_is_sent_or_kept(rig: Rig) -> None:
    await rig.m.asking.ask("OH2RDG", "status")
    await rig.pass_time(QUERY_EVERY_SEC - 11)
    with pytest.raises(MessagingError) as refused:
        await rig.m.asking.ask("oh2rdg", "status")
    assert (refused.value.code, refused.value.params) == ("query.too_soon", {"call": "OH2RDG", "seconds": 11})
    assert len(rig.tnc.sent) == 1 and len(rig.m.records()) == 1


async def test_another_kind_another_station_or_another_ssid_is_not_held_back_and_the_same_query_goes_again_after_the_minute(rig: Rig) -> None:
    await rig.m.asking.ask("OH2RDG", "status")
    await rig.m.asking.ask("OH2RDG", "position")
    await rig.m.asking.ask("OH2RCH", "status")
    await rig.m.asking.ask("OH2RDG-7", "status")
    assert len(rig.tnc.sent) == 4
    await rig.pass_time(QUERY_EVERY_SEC)
    await rig.m.asking.ask("OH2RDG", "status")
    assert len(rig.tnc.sent) == 5


async def test_a_refusal_for_any_other_reason_does_not_use_up_the_minute(rig: Rig) -> None:
    rig.config = replace(rig.config, station_call="")
    with pytest.raises(MessagingError, match="set your call first"):
        await rig.m.asking.ask("OH2RDG", "status")
    rig.config = replace(rig.config, station_call="OH2GBA")
    await rig.m.asking.ask("OH2RDG", "status")
    assert len(rig.tnc.sent) == 1


@pytest.mark.parametrize("call", ["", "OH2 RDG", "TOOLONGCALL"])
async def test_a_call_that_is_none_is_refused(rig: Rig, call: str) -> None:
    with pytest.raises(MessagingError):
        await rig.m.asking.ask(call, "status")
    assert rig.tnc.sent == [] and rig.m.records() == []


async def test_our_own_call_is_not_asked(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="own call"):
        await rig.m.asking.ask("OH2GBA", "status")
    assert rig.tnc.sent == []


async def test_the_interlock_holds_a_query_back_like_any_frame(rig: Rig) -> None:
    for call in ("", "N0CALL"):
        rig.config = replace(rig.config, station_call=call)
        with pytest.raises(MessagingError, match="set your call first"):
            await rig.m.asking.ask("OH2RDG", "position")
    assert rig.tnc.sent == [] and rig.m.records() == []


async def test_a_silent_radio_refuses_a_query(rig: Rig) -> None:
    await rig.radio(Source.State.SILENT)
    with pytest.raises(MessagingError):
        await rig.m.asking.ask("OH2RDG", "status")
    assert rig.tnc.sent == [] and rig.m.records() == []


async def test_a_query_waits_for_the_radio_like_any_message_and_is_then_sent_once(rig: Rig) -> None:
    await rig.radio(Source.State.WAITING)
    record = await rig.m.asking.ask("OH2RDG", "status")
    assert (record.state, record.attempts) == ("sending", 0) and rig.tnc.sent == []
    await rig.radio(Source.State.CONNECTED)
    await rig.pass_time(1)
    assert [f.info for f in rig.tnc.sent] == [b":OH2RDG   :?APRSS"] and rig.state().state == "unconfirmed"
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 1


async def test_queries_written_together_go_out_one_after_the_other(tmp_path: Path) -> None:
    r = await started_rig(tmp_path, spacing_sec=5.0)
    first = await r.m.asking.ask("OH2RDG", "status")
    second = await r.m.asking.ask("OH2RDG", "position")
    assert first.state == "unconfirmed" and second.state == "sending" and len(r.tnc.sent) == 1, "the pacing holds the second back"
    await r.pass_time(6)
    assert [f.info for f in r.tnc.sent] == [b":OH2RDG   :?APRSS", b":OH2RDG   :?APRSP"]


async def test_a_message_of_ours_that_looks_like_a_query_but_has_an_id_is_an_ordinary_message(rig: Rig) -> None:
    record = await rig.m.send("OH2RDG", "?APRSS")
    assert record.msg_id == "01" and record.attempts_max == 4


def test_the_kinds_are_the_queries_of_the_specification() -> None:
    assert QUERIES == {"position": "?APRSP", "status": "?APRSS", "heard": "?APRSD", "trace": "?APRST", "weather": "?WX?"}


async def test_weather_goes_out_as_wx_to_the_station_without_an_id(rig: Rig) -> None:
    record = await rig.m.asking.ask("OH2MUI", "weather")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2MUI   :?WX?"]
    assert (record.text, record.msg_id, record.attempts_max) == ("?WX?", None, 1)


async def test_a_custom_query_goes_out_trimmed_and_upper_cased_without_an_id(rig: Rig) -> None:
    record = await rig.m.asking.ask("OH2RDG", "custom", "  ?aprsh oh2gba-15 ")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :?APRSH OH2GBA-15"]
    assert (record.text, record.msg_id, record.state) == ("?APRSH OH2GBA-15", None, "unconfirmed")


@pytest.mark.parametrize(("text", "code"), [("APRSH", "query.form"), ("?", "query.form"), ("?" + "A" * 67, "message.too_long"), ("?APRS{1", "message.forbidden"), ("?APRSÄ", "message.not_ascii")])
async def test_a_custom_query_that_is_no_query_is_refused_and_nothing_is_sent(rig: Rig, text: str, code: str) -> None:
    with pytest.raises(MessagingError) as refused:
        await rig.m.asking.ask("OH2RDG", "custom", text)
    assert isinstance(refused.value.__context__, CodedError) and refused.value.__context__.code == code
    assert rig.tnc.sent == [] and rig.m.records() == []


async def test_the_same_custom_query_within_a_minute_is_refused_and_another_text_is_not(rig: Rig) -> None:
    await rig.m.asking.ask("OH2RDG", "custom", "?APRSO")
    await rig.m.asking.ask("OH2RDG", "custom", "?APRSM")
    with pytest.raises(MessagingError) as refused:
        await rig.m.asking.ask("OH2RDG", "custom", "?aprso")
    assert refused.value.code == "query.too_soon" and len(rig.tnc.sent) == 2


# ---- the command over the socket

def on_the_air(page: WsClient) -> list[dict[str, object]]:
    """The packets of ours the page was told of."""
    return [p for p in page.topics["packets"].values() if p["direction"] == "out"]


async def hear_station(e: Env, page: WsClient, call: str, info: bytes) -> None:
    e.feed(on_air(call, info))
    await page.until(lambda: call in page.topics["stations"])


async def test_query_sends_the_query_as_a_message_without_an_id_and_the_row_is_told_to_every_page(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await hear_station(e, page, "OH2RDG-7", b"=6010.00N/02456.00E>x")
    await page.send({"cmd": "query", "call": "oh2rdg-7", "kind": "status"})
    await page.until(lambda: any(r["attempts"] == 1 for r in page.topics["messages"].values()))
    [packet] = on_the_air(page)
    assert packet["kind"] == "message" and packet["tnc2"] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :?APRSS"
    [row] = page.topics["messages"].values()
    message = MessageRow.model_validate(row)
    assert (message.direction, message.to_call, message.text, message.msg_id, message.state, message.attempts, message.attempts_max) == ("out", "OH2RDG-7", "?APRSS", None, "unconfirmed", 1, 1)
    await other.until(lambda: other.topics["messages"] == page.topics["messages"] and len(other.topics["messages"]) == 1)
    assert page.of("error") == []


async def test_query_twice_within_a_minute_is_an_error_with_a_code_and_the_second_goes_nowhere(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await hear_station(e, page, "OH2RDG", b"=6010.00N/02456.00E>x")
    await page.send({"cmd": "query", "call": "OH2RDG", "kind": "position"})
    await page.until(lambda: any(r["attempts"] == 1 for r in page.topics["messages"].values()))
    await page.send({"cmd": "query", "call": "OH2RDG", "kind": "position"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"], error["params"]) == ("query", "query.too_soon", {"call": "OH2RDG", "seconds": 60})
    assert error["text"].startswith("query: OH2RDG was asked the same")
    await page.quiet(0.2)
    assert len(page.topics["messages"]) == 1 and len(on_the_air(page)) == 1


async def test_query_to_a_station_that_is_not_in_the_book_is_refused(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "query", "call": "OH2XYZ", "kind": "status"})
    error = await page.expect("error")
    assert (error["code"], error["params"]) == ("station.unknown", {"call": "OH2XYZ"})
    await page.quiet(0.2)
    assert page.topics["messages"] == {} and page.topics["packets"] == {}


async def test_query_to_a_station_that_takes_no_messages_is_refused(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await hear_station(e, page, "OH2PLN", b"!6010.00N/02456.00E>x")                       # (a position with no messaging)
    assert page.topics["stations"]["OH2PLN"]["can_message"] is False
    await page.send({"cmd": "query", "call": "OH2PLN", "kind": "status"})
    error = await page.expect("error")
    assert (error["code"], error["params"]) == ("query.not_capable", {"call": "OH2PLN"})
    await page.quiet(0.2)
    assert page.topics["messages"] == {} and on_the_air(page) == []


async def test_query_to_ourselves_or_to_an_object_is_refused(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await hear_station(e, page, "OH2OBJ", b";LEADER   *092345z6010.00N/02456.00E>x")
    await page.until(lambda: "LEADER" in page.topics["stations"])
    for call in ("LEADER", "OH2GBA"):
        await page.send({"cmd": "query", "call": call, "kind": "position"})
        assert (await page.expect("error"))["code"] in ("query.not_capable", "station.unknown")
    assert page.topics["messages"] == {}


async def test_query_with_a_custom_text_sends_it_and_one_that_is_no_query_is_an_error(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await hear_station(e, page, "OH2RDG", b"=6010.00N/02456.00E>x")
    await page.send({"cmd": "query", "call": "OH2RDG", "kind": "custom", "text": "APRSH"})
    assert (await page.expect("error"))["code"] == "invalid"
    await page.send({"cmd": "query", "call": "OH2RDG", "kind": "custom", "text": "?ping?"})
    await page.until(lambda: any(r["attempts"] == 1 for r in page.topics["messages"].values()))
    [packet] = on_the_air(page)
    assert packet["tnc2"] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :?PING?"


async def test_query_with_a_kind_that_is_none_is_not_a_command(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "query", "call": "OH2RDG", "kind": "everything"})
    await page.expect("error")
    assert page.topics["messages"] == {}


async def test_query_is_refused_by_the_interlock_while_the_call_is_not_set(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await hear_station(e, page, "OH2RDG", b"=6010.00N/02456.00E>x")
    assert await e.ctl.save_config(replace(e.ctl.config, station_call=""))
    await page.send({"cmd": "query", "call": "OH2RDG", "kind": "status"})
    assert (await page.expect("error"))["text"] == "query: set your call first"
    await page.quiet(0.2)
    assert page.topics["messages"] == {} and on_the_air(page) == []
