"""Asking QRU for local info (neoaprs/services/qruask.py, the words in neoaprs/qrutext.py, the command `qru_ask` and the topic `qru`): the request on the air (to QRU, no id, RFONLY, once, not kept), the refusals, the
servers that answer and what is made of their lists and closing lines, and the whole through the daemon and the socket, on a stub Tnc or the fake radio of an `Env`."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import dummyline
from neoaprs.aprsmessage import format_message
from neoaprs.message import MessagingError
from neoaprs.packet import GATEABLE, Message, Packet, ThirdParty, Via
from neoaprs.qrutext import ASK_KM_MAX, Closing, Listing, ask_text, closing_of, listing_of
from neoaprs.services.qruask import ASK_EVERY_SEC, CONTINUE_SEC, KEEP_FOR, QruAsk
from neoaprs.source import Source
from tests.support.air import message_info, on_air
from tests.support.env import idle_for, quick_start, remember_stop, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.rig import ServiceRig
from tests.test_web import with_page


# ---- the words

@pytest.mark.parametrize("text, expected", [("info", "INFO"), ("Next", "NEXT"), ("rp70", "RP70"), (" rp70   150 ", "RP70 150"), ("INFO 1", "INFO 1"), (f"POST {ASK_KM_MAX}", f"POST {ASK_KM_MAX}")])
def test_a_request_is_info_next_or_a_group_with_a_distance(text: str, expected: str) -> None:
    assert ask_text(text) == expected


@pytest.mark.parametrize("text", ["", "RP-70", "LIFEBOATS", "INFO 0", f"INFO {ASK_KM_MAX + 1}", "INFO 5 5", "INFO km", "?INFO", "A B 5"])
def test_a_text_that_is_no_request_is_refused(text: str) -> None:
    with pytest.raises(MessagingError):
        ask_text(text)


def test_a_list_of_groups_is_read_with_its_limit_and_range_and_the_plus_of_a_list_that_goes_on() -> None:
    assert listing_of("de DF8LS-10:RP70(10) RP2M(3) Max 5@50km") == Listing("DF8LS-10", (("RP70", 10), ("RP2M", 3)), False, 5, 50, "km")
    assert listing_of("de DF8LS-10:RP70(10) RP2M(3)+") == Listing("DF8LS-10", (("RP70", 10), ("RP2M", 3)), True, None, None, "")
    assert listing_of("de W1AW:FOOD(1) Max 5@30mi") == Listing("W1AW", (("FOOD", 1),), False, 5, 30, "mi")


@pytest.mark.parametrize("text", ["", "hello", "de DF8LS-10:", "de DF8LS-10:RP70 Max 5@50km", "Sent 5 RP70 Objects Max 5@50km de DF8LS-10", "see de OH2ABC:FOOD(1)"])
def test_a_text_that_is_no_list_of_groups_is_none(text: str) -> None:
    assert listing_of(text) is None


def test_the_closing_lines_of_a_server_are_read() -> None:
    assert closing_of("Sent 5 RP70 Objects Max 5@50km de DF8LS-10") == Closing("DF8LS-10", "RP70", 5)
    assert closing_of("Sent 5 of 12 FOOD Objects, NEXT for more. de OH2GBA") == Closing("OH2GBA", "FOOD", 5)
    assert closing_of("Sent 5 of 12 FOOD Objects") is None and closing_of("de DF8LS-10:RP70(1)") is None


# ---- the service

class Rig(ServiceRig):
    def __init__(self, **changes: object) -> None:
        super().__init__(**changes)
        self.paths: dict[str, tuple[str, ...]] = {}
        self.qru = QruAsk(self.tnc, lambda: self.config, lambda call: self.paths.get(call, self.config.beacon_path_calls), self.clock)
        remember_stop(self.qru.stop)
        self.told = 0
        self.qru.changed.connect(self.tell)

    def tell(self) -> None:
        self.told += 1

    def hear(self, source: str, text: str, to: str = "OH2GBA", via: Via = "rf", msg_id: str | None = None) -> None:
        info = b":" + format_message(to, text, msg_id, None if msg_id is None else "")
        third = ThirdParty(source, "APRS") if via == "rf-gated" else None
        packet = Packet(self.clock(), "in", b"", "OH2GATE" if third else source, "APRS", ("OH2RCH-2*",), info, Message(to, text, msg_id), third, via)
        self.qru.on_packet(packet)


async def test_a_request_is_one_message_to_qru_without_an_id_by_the_path_of_messages_and_rfonly() -> None:
    rig = Rig()
    rig.qru.ask("info")
    assert rig.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY::QRU      :INFO"], "a broadcast: no {id}, RF only"
    assert rig.qru.asked is not None and (rig.qru.asked.text, rig.qru.asked.at) == ("INFO", rig.clock()) and rig.told == 1
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 1, "once, and never again"


async def test_a_request_goes_by_the_path_set_for_qru_with_rfonly_after_it() -> None:
    rig = Rig()
    rig.paths["QRU"] = ("OH2RCH-2",)
    rig.qru.ask("rp70 150")
    assert rig.lines() == ["OH2GBA>APZNEO,OH2RCH-2,RFONLY::QRU      :RP70 150"]


async def test_a_path_that_rfonly_makes_too_long_sends_nothing() -> None:
    rig = Rig()
    rig.paths["QRU"] = tuple(f"A{n}" for n in range(8))
    with pytest.raises(MessagingError, match="path too long"):
        rig.qru.ask("INFO")
    assert rig.tnc.sent == [] and rig.qru.asked is None


async def test_nothing_is_asked_in_rx_only_without_a_call_or_with_the_radio_away() -> None:
    rig = Rig(station_transmit=False)
    with pytest.raises(MessagingError) as refused:
        rig.qru.ask("INFO")
    assert (refused.value.code, str(refused.value)) == ("transmit.off", "RX only: nothing is sent")
    rig.set(station_transmit=True, station_call="")
    with pytest.raises(MessagingError):
        rig.qru.ask("INFO")
    rig.set(station_call="OH2GBA")
    rig.tnc.state = Source.State.WAITING
    with pytest.raises(MessagingError):
        rig.qru.ask("INFO")
    rig.tnc.state = Source.State.CONNECTED
    rig.tnc.takes = False
    with pytest.raises(MessagingError, match="would not take"):
        rig.qru.ask("INFO")
    assert rig.tnc.sent == [] and rig.qru.asked is None and rig.told == 0


async def test_a_text_that_is_no_request_is_not_sent() -> None:
    rig = Rig()
    with pytest.raises(MessagingError):
        rig.qru.ask("hello there")
    assert rig.tnc.asked == 0


async def test_the_same_request_within_half_a_minute_is_refused_with_the_seconds_that_are_left_and_another_is_not() -> None:
    rig = Rig()
    rig.qru.ask("INFO")
    rig.clock.advance(ASK_EVERY_SEC - 11)
    with pytest.raises(MessagingError) as refused:
        rig.qru.ask("info")
    assert (refused.value.code, refused.value.params) == ("qru.too_soon", {"seconds": 11})
    rig.qru.ask("INFO 100")
    rig.qru.ask("RP70")
    rig.clock.advance(11)
    rig.qru.ask("INFO")
    assert len(rig.tnc.sent) == 4


async def test_a_server_that_lists_its_groups_is_noted_with_its_limit_and_range() -> None:
    rig = Rig()
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) RP2M(3) Max 5@50km")
    [server] = rig.qru.servers()
    assert (server.call, server.groups, server.max_objects, server.range, server.unit, server.at, server.sent) == ("DF8LS-10", (("RP70", 10), ("RP2M", 3)), 5, 50, "km", rig.clock(), "")
    assert rig.told == 1


async def test_a_list_that_ends_in_plus_goes_on_in_the_next_message_of_the_same_server() -> None:
    rig = Rig()
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) RP2M(3)+")
    rig.clock.advance(5)
    rig.hear("OH2ABC", "de OH2ABC:FOOD(2) Max 5@50km")
    rig.hear("DF8LS-10", "de DF8LS-10:FUEL(1) Max 5@50km")
    assert [(s.call, s.groups, s.range) for s in rig.qru.servers()] == [("DF8LS-10", (("RP70", 10), ("RP2M", 3), ("FUEL", 1)), 50), ("OH2ABC", (("FOOD", 2),), 50)]
    rig.clock.advance(CONTINUE_SEC + 1)
    rig.hear("DF8LS-10", "de DF8LS-10:POLI(4) Max 5@50km")
    rig.hear("DF8LS-10", "de DF8LS-10:SHOP(1)+")
    rig.clock.advance(CONTINUE_SEC + 1)
    rig.hear("DF8LS-10", "de DF8LS-10:AERO(1) Max 5@50km")
    assert next(s for s in rig.qru.servers() if s.call == "DF8LS-10").groups == (("AERO", 1),), "a list that came too late to belong to the one before replaces it"


async def test_the_closing_line_is_kept_with_the_server_and_a_new_list_is_a_new_round() -> None:
    rig = Rig()
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) Max 5@50km")
    rig.clock.advance(20)
    rig.hear("DF8LS-10", "Sent 5 RP70 Objects Max 5@50km de DF8LS-10")
    [server] = rig.qru.servers()
    assert (server.groups, server.sent, server.sent_at) == ((("RP70", 10),), "Sent 5 RP70 Objects Max 5@50km de DF8LS-10", rig.clock())
    rig.hear("DF8LS-10", "Sent 5 of 12 RP70 Objects, NEXT for more. de DF8LS-10")
    assert rig.qru.servers()[0].sent == "Sent 5 of 12 RP70 Objects, NEXT for more. de DF8LS-10"
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(9) Max 5@50km")
    assert rig.qru.servers()[0].sent == ""
    rig.hear("W1AW", "Sent 2 FOOD Objects Max 5@30mi de W1AW")
    assert [(s.call, s.groups) for s in rig.qru.servers()] == [("DF8LS-10", (("RP70", 9),)), ("W1AW", ())], "a server whose list was not heard has its closing line"


@pytest.mark.parametrize("via, taken", [("rf", True), ("dummy", True), ("rf-gated", True), ("is", False)])
async def test_only_what_was_on_the_air_is_noted(via: Via, taken: bool) -> None:
    rig = Rig()
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) Max 5@50km", via=via)
    assert bool(rig.qru.servers()) is taken


async def test_a_message_that_is_not_to_us_or_not_from_the_server_it_names_or_is_an_ack_is_not_noted() -> None:
    rig = Rig()
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) Max 5@50km", to="OH2XYZ")
    rig.hear("OH2ABC", "de DF8LS-10:RP70(10) Max 5@50km")
    rig.hear("DF8LS-10", "see you at the club")
    rig.qru.on_packet(Packet(rig.clock(), "in", b"", "DF8LS-10", "APRS", (), b"", Message("OH2GBA", "", None, "01")))
    assert rig.qru.servers() == [] and rig.told == 0


async def test_what_is_older_than_an_hour_is_forgotten_the_servers_and_the_request() -> None:
    rig = Rig()
    rig.qru.ask("INFO")
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) Max 5@50km")
    rig.clock.advance(1800)
    rig.hear("OH2ABC", "de OH2ABC:FOOD(2) Max 5@50km")
    rig.clock.advance(1801)
    assert [s.call for s in rig.qru.servers()] == ["OH2ABC"] and rig.qru.asked is None
    told = rig.told
    rig.clock.advance(1800)
    rig.qru.forget()
    assert rig.qru.servers() == [] and rig.told == told + 1
    rig.qru.forget()
    assert rig.told == told + 1, "nothing went: nobody is told"
    assert KEEP_FOR == timedelta(hours=1)


async def test_the_timer_forgets_by_itself_and_tells_the_page(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig()
    rig.hear("DF8LS-10", "de DF8LS-10:RP70(10) Max 5@50km")
    assert rig.qru._timer is not None
    rig.clock.advance(3601)
    rig.qru._timer.cancel()
    await rig.qru._forget(0.0)
    assert rig.qru.servers() == [] and rig.told == 2 and not [r for r in caplog.records if r.levelno >= logging.ERROR]


# ---- through the daemon and the socket

async def test_qru_ask_over_the_socket_sends_one_request_by_radio_only_and_keeps_no_message(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "qru_ask", "text": "rp70 150"})
    await page.until(lambda: page.topics["qru"]["asked"] is not None)
    assert page.topics["qru"]["asked"]["text"] == "RP70 150" and page.topics["qru"]["servers"] == []
    [packet] = [p for p in page.topics["packets"].values() if p["direction"] == "out"]
    assert packet["tnc2"] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY::QRU      :RP70 150"
    await page.quiet(0.2)
    assert page.topics["messages"] == {} and page.of("error") == []
    await page.send({"cmd": "qru_ask", "text": "rp70 150"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("qru_ask", "qru.too_soon") and error["params"]["seconds"] > 0


async def test_qru_ask_is_refused_in_rx_only_and_with_a_text_that_is_none(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    assert await e.ctl.save_config(replace(e.ctl.config, station_transmit=False))
    await page.send({"cmd": "qru_ask", "text": "INFO"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("qru_ask", "transmit.off")
    await page.send({"cmd": "qru_ask", "text": "not a request"})
    await page.expect("error")
    await page.quiet(0.2)
    assert page.topics["qru"] == {"asked": None, "servers": []} and [p for p in page.topics["packets"].values() if p["direction"] == "out"] == []


async def test_the_answers_of_a_server_are_told_in_the_topic_and_stay_ordinary_messages(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "qru_ask", "text": "INFO"})
    await page.until(lambda: page.topics["qru"]["asked"] is not None)
    e.feed(on_air("DF8LS-10", message_info("OH2GBA", "de DF8LS-10:RP70(10) RP2M(3) Max 5@50km"), path="OH2RCH-2*"))
    await page.until(lambda: len(page.topics["qru"]["servers"]) == 1)
    e.feed(on_air("DF8LS-10", message_info("OH2GBA", "Sent 5 RP70 Objects Max 5@50km de DF8LS-10"), path="OH2RCH-2*"))
    await page.until(lambda: page.topics["qru"]["servers"][0]["sent"] != "")
    [server] = page.topics["qru"]["servers"]
    assert (server["call"], server["groups"], server["max_objects"], server["range"], server["unit"]) == ("DF8LS-10", [{"name": "RP70", "count": 10}, {"name": "RP2M", "count": 3}], 5, 50, "km")
    assert server["sent"] == "Sent 5 RP70 Objects Max 5@50km de DF8LS-10" and server["sent_at"] is not None
    await until(lambda: len(page.topics["messages"]) == 2)
    assert sorted(m["text"] for m in page.topics["messages"].values()) == ["Sent 5 RP70 Objects Max 5@50km de DF8LS-10", "de DF8LS-10:RP70(10) RP2M(3) Max 5@50km"]
    assert all(m["state"] == "received" and m["from_call"] == "DF8LS-10" for m in page.topics["messages"].values())


async def test_the_dummy_radio_has_a_qru_server_and_nothing_of_it_reaches_the_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)
    server = await fake_aprsis()
    settings = {"tnc/profile": "dummy", "station/lat": "60.2231", "station/lon": "24.7152", "igate/enabled": "true", "igate/server": server.address, "igate/password": "19628"}
    e = await quick_start(tmp_path, messaging=True, unpaced=True, radio=False, settings=settings)
    await until(lambda: e.ctl.igate.state == "connected")
    e.ctl.qruask.ask("INFO")
    for _ in range(300):
        e.now.advance(1)                                                                    # type: ignore[attr-defined]
        await idle_for(0.02)
        if e.ctl.qruask.servers():
            break
    [listed] = e.ctl.qruask.servers()
    assert (listed.call, listed.groups, listed.range, listed.unit) == ("Q1CLB", (("FOOD", 2), ("RP70", 1)), 50, "km")
    e.now.advance(31)                                                                       # type: ignore[attr-defined]
    e.ctl.qruask.ask("food")
    for _ in range(300):
        e.now.advance(1)                                                                    # type: ignore[attr-defined]
        await idle_for(0.02)
        if e.ctl.qruask.servers()[0].sent:
            break
    assert e.ctl.qruask.servers()[0].sent == "Sent 2 FOOD Objects Max 5@50km de Q1CLB"
    assert {"CAFE", "KIOSK"} <= {s.call for s in e.ctl.stationbook.stations()}, "the objects arrive as objects"
    out = [p for p in await e.packets() if p.direction == "out" and isinstance(p.decoded, Message)]
    assert [p.path for p in out] == [("WIDE1-1", "WIDE2-1", "RFONLY")] * 2 and all(p.via not in GATEABLE for p in await e.packets())
    await idle_for(0.2)
    assert server.packets == [], f"nothing of the Dummy radio reached APRS-IS: {server.packets}"
    await e.stop()
