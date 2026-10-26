"""The QRU server (neoaprs/services/qru.py) on a Tnc that is a stub, a real station book and a clock the test holds: the list of groups, the objects of a group near the asker, the limit and `NEXT`, the range, the
answers that are never given, and the pace and the path of the frames."""
import asyncio
import logging
from datetime import datetime

import pytest

from neoaprs.aprsmessage import MAX_TEXT, parse_message
from neoaprs.ownobject import OwnObject, make_object
from neoaprs.packet import Message, Packet, Position, ThirdParty, Via
from neoaprs.stationbook import StationBook
from neoaprs.source import Source
from neoaprs.services.qru import ANSWER_FRAMES_MAX, FIRST_WAIT_SEC, RANGE_KM, Qru, Request, info_texts, request_of
from tests.support.env import idle_for, remember_stop, until
from tests.support.rig import ServiceRig
from tests.support.stubtnc import StubTnc
from tests.support.virtualtime import virtual_time

HELSINKI = (60.17, 24.94)


class Held:
    def __init__(self) -> None:
        self.held: list[OwnObject] = []

    def records(self) -> list[OwnObject]:
        return self.held


class Rig(ServiceRig):
    def __init__(self, tnc: StubTnc | None = None, first_wait_sec: float = 0.0, **changes: object) -> None:
        super().__init__(None, tnc, **changes)
        self.book = StationBook(self.clock)
        self.objects = Held()
        self.paths: dict[str, tuple[str, ...]] = {}
        self.qru = Qru(self.tnc, lambda: self.config, self.objects, self.book, lambda call: self.paths.get(call, self.config.beacon_path_calls), self.clock, spacing_sec=0.02, first_wait_sec=first_wait_sec)
        remember_stop(self.qru.stop)

    def add(self, name: str, group: str, lat: float = 60.2, lon: float = 24.9, on_request: bool = False, kind: str = "object", comment: str = "") -> OwnObject:
        made = make_object(self.clock(), name, kind, lat, lon, "/", "r", comment, qru_group=group, on_request=on_request)
        self.objects.held.append(made)
        return made

    def hear_at(self, call: str, lat: float, lon: float) -> None:
        self.book.take(Packet(self.clock(), "in", b"", call, "APRS", (), b"", Position(lat, lon, "/", ">")))

    def ask(self, source: str, text: str, to: str = "QRU", msg_id: str | None = None, via: Via = "rf") -> bool:
        third = ThirdParty(source, "APRS") if via == "rf-gated" else None
        packet = Packet(self.clock(), "in", b"", "OH2GATE" if third else source, "APRS", ("OH2RCH-2*",), b"", Message(to, text, msg_id), third, via)
        return self.qru.heard(packet, Message(to, text, msg_id))

    def texts(self) -> list[str]:
        return [parse_message(f.info[1:]).text for f in self.tnc.sent if f.info[:1] == b":"]

    def names(self) -> list[str]:
        return [f.info[1:10].decode().strip() for f in self.tnc.sent if f.info[:1] == b";"]


# ---- reading a request ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [("INFO", Request("INFO", None)), ("info 250", Request("INFO", 250)), ("?", Request("INFO", None)), ("? 20", Request("INFO", 20)), (" rp70 ", Request("RP70", None)),
                                            ("RP70 150", Request("RP70", 150)), ("?INFO", Request("INFO", None)), ("?test", Request("TEST", None)), ("?POST 20000", Request("POST", 20000)), ("?RP70 150", Request("RP70", 150)),
                                            ("next", Request("NEXT", None)), ("LIFEBOAT", Request("LIFEBOAT", None)), ("T2SRV 99999", Request("T2SRV", 99999))])
def test_a_request_is_a_word_and_a_distance_in_kilometres(text: str, expected: Request) -> None:
    assert request_of(text) == expected


@pytest.mark.parametrize("text", ["", "hello there", "RP70 far", "RP70 150 3", "LIFEBOATS", "RP-70", "T2SRV 100000", "INFO?", "?APRSP", "?aprsd 5", "?PING?", "?RP-70", "??", "Are you there?"])
def test_a_text_that_is_no_request_is_none(text: str) -> None:
    assert request_of(text) is None


def test_the_list_of_groups_is_one_message_that_ends_with_the_limit_and_the_range() -> None:
    assert info_texts("OH2GBA-10", [("FOOD", 1), ("RP70", 3)], 50) == ["de OH2GBA-10:FOOD(1) RP70(3) Max 5@50km"]


def test_a_long_list_goes_over_two_messages_the_first_ending_in_plus_and_what_does_not_fit_is_left_out() -> None:
    groups = [(f"GRP{n:02d}", n + 1) for n in range(30)]
    texts = info_texts("OH2GBA-10", groups, 250)
    assert len(texts) == 2 and texts[0].endswith("+") and texts[1].endswith(" Max 5@250km") and all(len(t.encode()) <= MAX_TEXT for t in texts)
    assert 0 < sum(text.count("(") for text in texts) < 30


# ---- INFO ----------------------------------------------------------------------------------------------------------------------------------------

def test_info_answers_with_the_groups_near_the_asker_and_how_many_objects_each_has() -> None:
    rig = Rig()
    rig.hear_at("OH2RDG", *HELSINKI)
    rig.add("PUB1", "FOOD")
    rig.add("PUB2", "FOOD")
    rig.add("PUMP", "FUEL")
    rig.add("FAR", "FUEL", 62.5, 24.9)
    rig.add("HIDDEN", "RP70", on_request=True)
    rig.add("PLAIN", "")
    killed = rig.add("DEAD", "POLI")
    rig.objects.held[-1] = killed.killed(rig.clock())
    assert rig.ask("OH2RDG", "INFO") is True
    assert rig.texts() == ["de OH2GBA:FOOD(2) FUEL(1) RP70(1) Max 5@50km"], "an object that is on request is a member of its group; a killed one and one with no group are not"
    assert rig.tnc.sent[0].path_text == "WIDE1-1,WIDE2-1,RFONLY" and rig.names() == []


def test_info_with_a_distance_names_the_range_and_a_question_mark_asks_the_same() -> None:
    rig = Rig()
    rig.hear_at("OH2RDG", *HELSINKI)
    rig.add("PUMP", "FUEL")
    rig.add("FAR", "FUEL", 62.5, 24.9)
    rig.ask("OH2RDG", "INFO 300")
    rig.clock.advance(60)
    rig.ask("OH2RDG", "?")
    assert rig.texts() == ["de OH2GBA:FUEL(2) Max 5@300km", "de OH2GBA:FUEL(1) Max 5@50km"]


def test_a_station_whose_position_we_do_not_know_is_offered_every_object() -> None:
    rig = Rig()
    rig.add("FAR", "FUEL", 62.5, 24.9)
    rig.add("NEAR", "FUEL")
    rig.ask("OH2NEW", "INFO")
    assert rig.texts() == ["de OH2GBA:FUEL(2) Max 5@50km"]


def test_the_answer_goes_by_the_path_of_the_asker_with_rfonly_added_so_that_the_igates_keep_it_off_the_internet() -> None:
    rig = Rig()
    rig.paths["OH2RDG"] = ("OH2RCH-2", "WIDE2-1")
    rig.add("PUMP", "FUEL")
    rig.ask("OH2RDG", "INFO")
    assert [f.path_text for f in rig.tnc.sent] == ["OH2RCH-2,WIDE2-1,RFONLY"]


def test_an_answer_with_a_path_too_long_for_rfonly_is_not_sent(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig()
    rig.paths["OH2RDG"] = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8")
    rig.add("PUMP", "FUEL")
    with caplog.at_level(logging.WARNING, logger="neoaprs.queries"):
        rig.ask("OH2RDG", "INFO")
    assert rig.tnc.sent == [] and "path too long" in caplog.text


@pytest.mark.parametrize("via, taken", [("rf", True), ("dummy", True), ("is", False), ("rf-gated", False)])
def test_only_a_request_heard_on_the_radio_is_answered_never_one_that_came_by_the_internet(via: Via, taken: bool) -> None:
    rig = Rig()
    rig.add("PUMP", "FUEL")
    assert rig.ask("OH2RDG", "INFO", via=via) is taken
    assert (len(rig.tnc.sent) == 1) is taken


def test_a_request_with_a_message_id_is_answered_and_sends_no_ack() -> None:
    rig = Rig()
    rig.add("PUMP", "FUEL")
    assert rig.ask("OH2RDG", "?INFO", msg_id="B3") is True
    assert rig.texts() == ["de OH2GBA:FUEL(1) Max 5@50km"], "no ack: a message to QRU is a broadcast"


# ---- a group -------------------------------------------------------------------------------------------------------------------------------------

async def test_a_group_is_answered_with_its_objects_the_nearest_first_one_at_a_time_and_a_message_that_says_how_many_went() -> None:
    rig = Rig()
    rig.hear_at("OH2RDG", *HELSINKI)
    rig.add("RPFAR", "RP70", 60.45, 24.94, on_request=True, comment="438.850MHz Toff -760")
    rig.add("RPNEAR", "RP70", 60.18, 24.95, comment="438.925MHz Toff -760")
    rig.add("PUMP", "FUEL")
    rig.add("RP2", "RP2M")
    rig.ask("OH2RDG", "rp70")
    assert len(rig.tnc.sent) == 1, "the first goes at once, the rest are paced"
    await until(lambda: len(rig.tnc.sent) == 3)
    await idle_for(0.1)
    assert rig.names() == ["RPNEAR", "RPFAR"] and rig.texts() == ["Sent 2 RP70 Objects Max 5@50km de OH2GBA"]
    assert rig.tnc.sent[0].info == b";RPNEAR   *211200z6010.80N/02457.00Er438.925MHz Toff -760"
    assert {f.path_text for f in rig.tnc.sent} == {"WIDE1-1,WIDE2-1,RFONLY"} and [parse_message(f.info[1:]).msg_id for f in rig.tnc.sent if f.info[:1] == b":"] == [None]


async def test_an_item_of_the_group_is_sent_as_an_item() -> None:
    rig = Rig()
    rig.add("WELL", "WATER", kind="item")
    rig.ask("OH2RDG", "WATER")
    await until(lambda: len(rig.tnc.sent) == 2)
    assert rig.tnc.sent[0].info.startswith(b")WELL!") and rig.texts() == ["Sent 1 WATER Objects Max 5@50km de OH2GBA"]


async def test_at_most_five_objects_go_out_and_next_sends_the_following_ones() -> None:
    rig = Rig()
    rig.hear_at("OH2RDG", *HELSINKI)
    for n in range(12):
        rig.add(f"PUB{n:02d}", "FOOD", 60.17 + n / 1000, 24.94)
    rig.ask("OH2RDG", "FOOD")
    await until(lambda: len(rig.tnc.sent) == ANSWER_FRAMES_MAX + 1)
    assert rig.names() == [f"PUB{n:02d}" for n in range(5)] and rig.texts() == ["Sent 5 of 12 FOOD Objects, NEXT for more. de OH2GBA"]
    rig.clock.advance(60)
    rig.ask("OH2RDG", "next")
    await until(lambda: len(rig.tnc.sent) == 2 * (ANSWER_FRAMES_MAX + 1))
    assert rig.names()[5:] == [f"PUB{n:02d}" for n in range(5, 10)] and rig.texts()[1] == "Sent 5 of 12 FOOD Objects, NEXT for more. de OH2GBA"
    rig.clock.advance(60)
    rig.ask("OH2RDG", "NEXT")
    await until(lambda: len(rig.tnc.sent) == 2 * (ANSWER_FRAMES_MAX + 1) + 3)
    await idle_for(0.1)
    assert rig.names()[10:] == ["PUB10", "PUB11"] and rig.texts()[2] == "Sent 2 FOOD Objects Max 5@50km de OH2GBA"
    rig.clock.advance(60)
    rig.ask("OH2RDG", "NEXT")
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 2 * (ANSWER_FRAMES_MAX + 1) + 3, "nothing is left after the last: no answer"


async def test_next_goes_on_where_that_station_stopped_and_is_forgotten_after_an_hour() -> None:
    rig = Rig()
    for n in range(7):
        rig.add(f"PUB{n}", "FOOD")
    rig.ask("OH2NEXT", "NEXT")
    await idle_for(0.05)
    assert rig.tnc.sent == [], "it asked for no group before"
    rig.ask("OH2RDG", "FOOD")
    await until(lambda: len(rig.tnc.sent) == 6)
    rig.ask("OH2ABC", "NEXT")
    rig.clock.advance(3601)
    rig.ask("OH2RDG", "NEXT")
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 6


async def test_a_distance_in_the_request_is_the_range_of_the_group() -> None:
    rig = Rig()
    rig.hear_at("OH2RDG", *HELSINKI)
    rig.add("NEAR", "FUEL")
    rig.add("FAR", "FUEL", 62.5, 24.9)
    rig.ask("OH2RDG", "FUEL")
    await until(lambda: len(rig.tnc.sent) == 2)
    rig.clock.advance(60)
    rig.ask("OH2RDG", "FUEL 300")
    await until(lambda: len(rig.tnc.sent) == 5)
    assert rig.names() == ["NEAR", "NEAR", "FAR"] and rig.texts()[1] == "Sent 2 FUEL Objects Max 5@300km de OH2GBA"


# ---- what is not answered ------------------------------------------------------------------------------------------------------------------------

async def test_nothing_is_answered_where_nothing_is_in_range_or_the_group_has_no_object(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig()
    rig.hear_at("OH2RDG", *HELSINKI)
    rig.add("FAR", "FUEL", 62.5, 24.9)
    with caplog.at_level(logging.DEBUG, logger="neoaprs.qru"):
        for text in ("INFO 10", "FUEL", "FOOD"):
            assert rig.ask("OH2RDG", text) is True
        await idle_for(0.1)
    assert rig.tnc.sent == [] and not [r for r in caplog.records if r.levelno > logging.DEBUG]


def test_a_message_to_qru_is_not_taken_while_we_serve_no_group_or_when_it_is_no_request() -> None:
    rig = Rig()
    assert rig.ask("OH2RDG", "INFO") is False
    rig.add("PLAIN", "")
    rig.add("HIDDEN", "FOOD")
    rig.objects.held[-1] = rig.objects.held[-1].killed(rig.clock())
    assert rig.ask("OH2RDG", "INFO") is False
    rig.add("PUB", "FOOD")
    assert rig.ask("OH2RDG", "hello there, anyone?") is False and rig.ask("OH2RDG", "INFO") is True
    assert rig.texts() == ["de OH2GBA:FOOD(1) Max 5@50km"]


def test_the_same_request_from_the_same_station_within_half_a_minute_is_answered_once() -> None:
    rig = Rig()
    rig.add("PUB", "FOOD")
    for _ in range(3):
        rig.ask("OH2RDG", "INFO")
    assert len(rig.tnc.sent) == 1
    rig.ask("OH2RDG", "info 100")
    rig.ask("OH2ABC", "INFO")
    assert len(rig.tnc.sent) == 3, "another request, or another station, is answered"
    rig.clock.advance(31)
    rig.ask("OH2RDG", "INFO")
    assert len(rig.tnc.sent) == 4


def test_nothing_is_sent_while_the_interlock_holds_everything_back_or_the_radio_is_away() -> None:
    rig = Rig()
    rig.add("PUB", "FOOD")
    rig.set(station_transmit=False)
    assert rig.ask("OH2RDG", "INFO") is True
    rig.set(station_transmit=True)
    rig.tnc.state = Source.State.WAITING
    rig.ask("OH2RDG", "INFO")
    assert rig.tnc.sent == []
    rig.tnc.state = Source.State.CONNECTED
    rig.ask("OH2RDG", "INFO")
    assert len(rig.tnc.sent) == 1


async def test_an_answer_that_is_waiting_is_not_sent_when_the_server_stops() -> None:
    rig = Rig()
    for n in range(3):
        rig.add(f"PUB{n}", "FOOD")
    rig.ask("OH2RDG", "FOOD")
    await rig.qru.stop()
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 1


async def test_the_clock_of_the_server_stamps_the_objects() -> None:
    rig = Rig()
    rig.add("PUB", "FOOD")
    rig.clock.set(datetime(2026, 11, 2, 7, 5, tzinfo=rig.clock().tzinfo))
    rig.ask("OH2RDG", "FOOD")
    assert RANGE_KM == 50 and rig.tnc.sent[0].info.startswith(b";PUB      *020705z")


# ---- the first frame waits for the digipeaters ---------------------------------------------------------------------------------------------------

async def test_the_first_frame_of_an_answer_waits_about_five_seconds_for_the_digipeaters_to_finish_repeating_the_request_then_the_frames_are_spaced() -> None:
    rig = Rig(first_wait_sec=FIRST_WAIT_SEC)
    rig.add("PUMP", "FUEL")
    rig.add("WELL", "FUEL", 60.21)
    assert FIRST_WAIT_SEC == 5.0
    async with virtual_time() as time:
        rig.ask("OH2RDG", "FUEL")
        await idle_for(0)
        assert rig.tnc.sent == [], "nothing at once"
        await asyncio.sleep(FIRST_WAIT_SEC - 0.5)
        assert rig.tnc.sent == [], "not before the wait is over"
        await asyncio.sleep(0.51)
        assert len(rig.tnc.sent) == 1, "then the first object"
        await asyncio.sleep(0.05)
        assert len(rig.tnc.sent) == 3 and rig.texts() == ["Sent 2 FUEL Objects Max 5@50km de OH2GBA"], "the rest, spaced as before"
        assert FIRST_WAIT_SEC <= time.skipped < FIRST_WAIT_SEC + 1


async def test_the_list_of_groups_waits_too() -> None:
    rig = Rig(first_wait_sec=FIRST_WAIT_SEC)
    rig.add("PUMP", "FUEL")
    async with virtual_time():
        rig.ask("OH2RDG", "INFO")
        await asyncio.sleep(FIRST_WAIT_SEC - 0.5)
        assert rig.tnc.sent == []
        await asyncio.sleep(0.6)
        assert rig.texts() == ["de OH2GBA:FUEL(1) Max 5@50km"]


async def test_the_copies_of_the_request_that_come_while_the_answer_waits_are_not_answered_again_and_a_stop_ends_the_wait() -> None:
    rig = Rig(first_wait_sec=FIRST_WAIT_SEC)
    rig.add("PUMP", "FUEL")
    async with virtual_time():
        rig.ask("OH2RDG", "INFO")
        await asyncio.sleep(2)
        rig.ask("OH2RDG", "INFO")
        await asyncio.sleep(FIRST_WAIT_SEC)
        assert len(rig.tnc.sent) == 1
        rig.clock.advance(60)
        rig.ask("OH2RDG", "INFO")
        await rig.qru.stop()
        await asyncio.sleep(FIRST_WAIT_SEC * 2)
        assert len(rig.tnc.sent) == 1, "an answer that is waiting is not sent when the server stops"
