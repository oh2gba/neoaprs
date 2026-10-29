"""The general query `?IGATE?` (neoaprs/services/queries.py) on the rig of tests/test_queries.py and an iGate that is a stand-in (its state and its count of packets gated): answered with our station capabilities,
`<IGATE,MSG_CNT=0,LOC_CNT=n,UPL_CNT=n`, after the general query's wait and by the asker's path, while the iGate is connected; not while it is off, connecting or only listening, not under RX only, not again within
the ten minutes of the general query (its own, apart from ?APRS?'s), and LOC_CNT is the stations heard direct in the last hour only."""
import logging
from dataclasses import replace

import pytest

from neoaprs import aprsparse
from neoaprs.packet import Other, Status
from neoaprs.services.answers import ANSWER_AGAIN_SEC
from neoaprs.services.queries import GENERAL_EVERY_SEC, IgateCounts, Queries, capabilities_info
from tests.support.env import idle_for, remember_stop, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.igateworld import iworld
from tests.test_queries import Rig, general


class FakeIgate:
    """The iGate as the queries see it."""
    def __init__(self, state: str = "connected", gated: int = 0) -> None:
        self.state, self.gated = state, gated


def rig_with(igate: IgateCounts | None, delay: float = 0.0, **changes: object) -> Rig:
    rig = Rig(delay=delay, **changes)
    rig.q = Queries(rig.tnc, lambda: rig.config, rig.beacon, lambda: rig.beacon.status_frame(rig.status_text), rig.book, lambda call: rig.paths.get(call, rig.config.beacon_path_calls), rig.clock,
                    delay=lambda: delay, igate=igate)
    remember_stop(rig.q.stop)
    return rig


def igate_query(rig: Rig, source: str = "OH2RDG", text: str = "?IGATE?") -> None:
    general(rig, source, text)


def test_the_capabilities_are_the_specifications_tokens_with_the_count_of_packets_uploaded() -> None:
    assert capabilities_info(14, 812) == b"<IGATE,MSG_CNT=0,LOC_CNT=14,UPL_CNT=812"
    decoded = aprsparse.parse(capabilities_info(3, 0), "OH2GBA", "APZNEO", Rig().clock())
    assert isinstance(decoded, Other) and decoded.kind == "capabilities" and decoded.items == {"IGATE": "", "MSG_CNT": "0", "LOC_CNT": "3", "UPL_CNT": "0"}


async def test_a_connected_igate_answers_with_its_capabilities_after_the_wait_by_the_path_of_the_asker() -> None:
    rig = rig_with(FakeIgate(gated=812), delay=0.05)
    rig.status_text = "QRV 145.500"
    rig.paths["OH2RDG"] = ("OH2RCH-2",)
    rig.hear_direct("OH2PU-9")
    igate_query(rig)
    assert rig.tnc.sent == []
    await until(lambda: len(rig.tnc.sent) == 1)
    await idle_for(0.1)
    assert rig.lines() == ["OH2GBA>APZNEO,OH2RCH-2:<IGATE,MSG_CNT=0,LOC_CNT=1,UPL_CNT=812"], "the capabilities alone: no position, no status"


async def test_loc_cnt_counts_the_stations_heard_direct_in_the_last_hour_and_no_other() -> None:
    rig = rig_with(FakeIgate())
    rig.hear_direct("OH2PU-9")
    rig.hear_direct("OH2ABC", seconds_ago=59 * 60)
    rig.hear_direct("OH2OLD", seconds_ago=61 * 60)                                      # heard direct, but too long ago
    rig.book.take(rig.packet("OH2FAR", Status("hello"), path=("OH2RCH-2*", "WIDE2-1")))     # heard just now, by a digipeater
    rig.book.take(rig.packet("OH2GBA", Status("me"), path=()))                          # ourselves
    igate_query(rig)
    await until(lambda: len(rig.tnc.sent) == 1)
    assert rig.tnc.sent[0].info == b"<IGATE,MSG_CNT=0,LOC_CNT=2,UPL_CNT=0"


@pytest.mark.parametrize("state", ["off", "connecting", "listening", "unverified"])
async def test_an_igate_that_does_not_gate_does_not_answer_and_the_log_says_why_at_debug(state: str, caplog: pytest.LogCaptureFixture) -> None:
    rig = rig_with(FakeIgate(state))
    with caplog.at_level(logging.DEBUG, logger="neoaprs.queries"):
        igate_query(rig)
        await idle_for(0.1)
    assert rig.tnc.sent == [] and rig.q._general_until == {}, "a query not answered does not start the ten minutes"
    assert [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "neoaprs.queries"] == [(logging.DEBUG, f"the general query ?IGATE? of OH2RDG is not answered: the iGate is {state}")]


@pytest.mark.parametrize("password, answered", [("19628", True), ("", False)])
async def test_the_real_igate_logged_in_and_verified_is_answered_for_and_one_that_only_listens_is_not(password: str, answered: bool) -> None:
    w = await iworld(await fake_aprsis(verified=answered), igate_password=password)
    w.hear()
    rig = rig_with(w.igate)
    igate_query(rig)
    await idle_for(0.1)
    assert rig.lines() == (["OH2GBA>APZNEO,WIDE1-1,WIDE2-1:<IGATE,MSG_CNT=0,LOC_CNT=0,UPL_CNT=1"] if answered else [])


async def test_queries_made_without_an_igate_never_answer() -> None:
    rig = rig_with(None)
    igate_query(rig)
    await idle_for(0.1)
    assert rig.tnc.sent == []


async def test_an_igate_that_stops_gating_during_the_wait_sends_nothing() -> None:
    igate = FakeIgate()
    rig = rig_with(igate, delay=0.05)
    igate_query(rig)
    igate.state = "connecting"
    await idle_for(0.15)
    assert rig.tnc.sent == []


async def test_nothing_is_answered_under_rx_only_neither_when_heard_nor_when_the_wait_is_over() -> None:
    rig = rig_with(FakeIgate(), station_transmit=False)
    igate_query(rig)
    await idle_for(0.1)
    assert rig.tnc.sent == []
    rig = rig_with(FakeIgate(), delay=0.05)
    igate_query(rig)
    rig.set(station_transmit=False)
    await idle_for(0.15)
    assert rig.tnc.sent == []


async def test_it_is_taken_once_in_ten_minutes_apart_from_the_query_aprs() -> None:
    rig = rig_with(FakeIgate())
    igate_query(rig, "OH2RDG")
    igate_query(rig, "OH2RDG")
    rig.clock.advance(ANSWER_AGAIN_SEC + 1)
    igate_query(rig, "OH2DEF")
    await until(lambda: len(rig.tnc.sent) == 1)
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 1
    general(rig, "OH2DEF")                                                     # ?APRS? keeps its own ten minutes
    await until(lambda: len(rig.tnc.sent) == 2)
    assert rig.tnc.sent[1].info == rig.beacon.frame().info
    rig.clock.advance(GENERAL_EVERY_SEC - ANSWER_AGAIN_SEC)
    igate_query(rig)
    await until(lambda: len(rig.tnc.sent) == 3)
    assert rig.tnc.sent[2].info.startswith(b"<IGATE,")


@pytest.mark.parametrize("text, inside", [("?IGATE?V60.17,24.94,0010", True), ("?igate? 60.17,24.94,0010", True), ("?IGATE?V34.02,-117.15,0200", False), ("?IGATE?x", False)])
async def test_a_footprint_is_honoured_as_the_one_of_aprs_is(text: str, inside: bool) -> None:
    rig = rig_with(FakeIgate())                                               # (we are at 60.17 N 24.94 E)
    igate_query(rig, text=text)
    await idle_for(0.1)
    assert len(rig.tnc.sent) == (1 if inside else 0)


async def test_igate_as_the_text_of_a_message_to_us_is_not_answered_as_aprs_is_not() -> None:
    rig = rig_with(FakeIgate())
    rig.ask("OH2RDG", "?IGATE?")
    await idle_for(0.1)
    assert rig.tnc.sent == []


async def test_a_query_over_the_internet_or_from_ourselves_is_not_answered() -> None:
    rig = rig_with(FakeIgate())
    rig.q.on_packet(replace(rig.packet("OH2RDG", Other("query", "?IGATE?")), via="is"))
    igate_query(rig, "OH2GBA")
    await idle_for(0.1)
    assert rig.tnc.sent == [] and rig.q._general_until == {}
