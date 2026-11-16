"""Asking around (neoaprs/services/generalask.py, the command `general_query` and the topic `general`): the frame of each general query byte for byte, the path given or `beacon/path`, RFONLY, the refusals and the
minute between two queries of a kind, the stations that were quiet before a query and spoke after it, and the whole through the daemon and the socket."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import TOCALL, ax25
from neoaprs.message import MessagingError
from neoaprs.packet import Other, Packet, ThirdParty, Via
from neoaprs.services.common import asked_radio
from neoaprs.services.generalask import ASK_EVERY_SEC, COUNT_FOR, QUERIES, QUIET_BEFORE, GeneralAsk
from neoaprs.source import Source
from neoaprs.station import Station
from neoaprs.radiospec import RadioHeard
from neoaprs.radiotype import FM_ID, HF_ID, RadioId
from tests.support.air import on_air
from tests.support.env import until
from tests.support.rig import ServiceRig
from tests.support.stubtnc import StubTnc
from tests.test_web import with_page
from tests.test_messaging import LineAir, StubPick, pick_of, with_hf


class Book:
    def __init__(self) -> None:
        self.rows: list[Station] = []

    def stations(self) -> list[Station]:
        return self.rows


class Rig(ServiceRig):
    def __init__(self, **changes: object) -> None:
        super().__init__(**changes)
        self.book = Book()
        self.radios = pick_of(self)                                             # (the station's radios as the registry gives them: radio 1 on the stub line)
        self.general = GeneralAsk(self.radios, lambda: self.config, self.book, self.clock)
        self.told = 0
        self.general.changed.connect(self.tell)

    def tell(self) -> None:
        self.told += 1

    def hear(self, source: str, seconds: float = 0.0, via: Via = "rf", direction: str = "in", radio: RadioId | None = None) -> None:
        """A packet of `source`, `seconds` after the clock (on the radio `radio`; None: a packet that names none)."""
        third = ThirdParty(source, "APRS") if via == "rf-gated" else None
        at = self.clock() + timedelta(seconds=seconds)
        packet = Packet(at, direction, b"", "OH2GATE" if third else source, "APRS", ("OH2RCH-2*",), b">here", Other("status", ">here"), third, via, radio_id=radio)    # type: ignore[arg-type]
        self.general.on_packet(packet)

    def station(self, call: str, **heard: object) -> Station:
        return Station(call, first_heard=self.clock() - timedelta(hours=1), last_heard=self.clock(), **heard)       # type: ignore[arg-type]

    def heard_before(self, call: str, minutes: float, radio: RadioId = FM_ID) -> None:
        """The station book heard the station on the radio (radio 1, the rig's, unless another is named) this long before now."""
        at = self.clock() - timedelta(minutes=minutes)
        self.book.rows.append(self.station(call, last_rf_at=at, heard_by={radio: RadioHeard(1, at)}))


# ---- the frame

@pytest.mark.parametrize("kind", ["aprs", "igate", "wx"])
def test_each_query_is_one_frame_from_our_call_to_our_tocall_with_the_query_alone_by_the_beacon_path_and_rfonly(kind: str) -> None:
    rig = Rig()
    asked = rig.general.ask(kind)                                   # type: ignore[arg-type]
    [frame] = rig.tnc.sent
    assert frame.info == QUERIES[kind].encode() == {"aprs": b"?APRS?", "igate": b"?IGATE?", "wx": b"?WX?"}[kind]
    assert (str(frame.source), str(frame.destination)) == ("OH2GBA", TOCALL)
    assert rig.lines() == [f"OH2GBA>{TOCALL},WIDE1-1,WIDE2-1,RFONLY:{QUERIES[kind]}"]
    assert ax25.decode(ax25.encode(frame)).info == frame.info
    assert (asked.kind, asked.at, asked.path, asked.query) == (kind, rig.clock(), ("WIDE1-1", "WIDE2-1", "RFONLY"), QUERIES[kind]) and rig.told == 1


@pytest.mark.parametrize("path, rf_only, line", [
    ("OH2RDK-7,OH2RCH-2", True, "OH2GBA>APZNEO,OH2RDK-7,OH2RCH-2,RFONLY:?APRS?"),
    (" oh2rdk-7 , oh2rch-2 ", False, "OH2GBA>APZNEO,OH2RDK-7,OH2RCH-2:?APRS?"),
    ("WIDE2-2", True, "OH2GBA>APZNEO,WIDE2-2,RFONLY:?APRS?"),
    ("DIRECT", True, "OH2GBA>APZNEO,RFONLY:?APRS?"),
    ("direct", False, "OH2GBA>APZNEO:?APRS?"),
    ("", False, "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:?APRS?"),
    (None, True, "OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY:?APRS?"),
])
def test_the_path_is_the_one_given_explicit_calls_aliases_or_direct_else_the_beacon_path(path: str | None, rf_only: bool, line: str) -> None:
    rig = Rig()
    rig.general.ask("aprs", path, rf_only)
    assert rig.lines() == [line]


@pytest.mark.parametrize("path, code", [("OH2RDK-7,???", "call.shape"), ("A1,A2,A3,A4,A5,A6,A7,A8,A9", "path.too_long"), ("WIDE1-1,DIRECT", "path.direct_alone"),
                                        ("A1,A2,A3,A4,A5,A6,A7,A8", "path.too_long_rf_only")])
def test_a_path_that_is_none_or_too_long_with_rfonly_sends_nothing(path: str, code: str) -> None:
    rig = Rig()
    with pytest.raises(MessagingError) as refused:
        rig.general.ask("aprs", path, True)
    assert refused.value.code == code and rig.tnc.sent == [] and rig.general.asked() == [] and rig.told == 0
    if code == "path.too_long_rf_only":
        assert refused.value.params == {"count": 8, "max": 8}
        rig.general.ask("aprs", path, False)                         # (eight digipeaters fit without RFONLY)
        assert len(rig.tnc.sent) == 1


def test_nothing_is_asked_in_rx_only_without_a_call_or_with_the_radio_away() -> None:
    rig = Rig(station_transmit=False)
    with pytest.raises(MessagingError) as refused:
        rig.general.ask("aprs")
    assert (refused.value.code, str(refused.value)) == ("transmit.off", "RX only: nothing is sent")
    rig.set(station_transmit=True, station_call="")
    with pytest.raises(MessagingError):
        rig.general.ask("aprs")
    rig.set(station_call="OH2GBA")
    rig.tnc.state = Source.State.WAITING
    with pytest.raises(MessagingError):
        rig.general.ask("aprs")
    rig.tnc.state = Source.State.CONNECTED
    rig.tnc.takes = False
    with pytest.raises(MessagingError, match="would not take"):
        rig.general.ask("aprs")
    assert rig.tnc.sent == [] and rig.general.asked() == [] and rig.told == 0
    rig.radios.on.clear()                                                   # (no radio at all: what the settings refuse, and a fresh installation of the round)
    with pytest.raises(MessagingError, match="there is no radio"):
        rig.general.ask("aprs")


def test_a_query_goes_on_the_main_radio_by_the_path_that_radio_carries() -> None:
    rig = Rig(hf_enabled=True, fm_enabled=False)
    hf = with_hf(rig, rig.radios)
    rig.radios.on = {HF_ID}                                                 # (the HF radio alone: the main radio, which carries no path)
    asked = rig.general.ask("aprs")
    assert hf.lines() == ["OH2GBA>APZNEO:?APRS?"] and rig.tnc.sent == [] and asked.path == ()
    rig.radios.on.add(FM_ID)                                                # (both on: the main radio is the first by position, the FM one)
    rig.general.ask("igate")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY:?IGATE?"] and len(hf.sent) == 1


def test_a_kind_goes_once_a_minute_and_the_others_are_not_held_by_it() -> None:
    rig = Rig()
    rig.general.ask("aprs")
    rig.clock.advance(ASK_EVERY_SEC - 15)
    with pytest.raises(MessagingError) as refused:
        rig.general.ask("aprs", "OH2RCH-2", False)
    assert (refused.value.code, refused.value.params, str(refused.value)) == ("general.too_soon", {"query": "?APRS?", "seconds": 15}, "too soon for another ?APRS?: wait 15 s")
    rig.general.ask("igate")
    rig.general.ask("wx")
    assert [f.info for f in rig.tnc.sent] == [b"?APRS?", b"?IGATE?", b"?WX?"]
    rig.clock.advance(15)
    rig.general.ask("aprs")
    assert [a.kind for a in rig.general.asked()] == ["igate", "wx", "aprs"], "the last of each kind, the oldest first"


def test_a_query_goes_on_the_radio_named_and_the_minute_between_two_of_a_kind_is_that_radios(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.queries")
    rig = Rig(hf_enabled=True)
    hf = with_hf(rig, rig.radios)
    asked = rig.general.ask("aprs", radio=HF_ID)
    assert hf.lines() == ["OH2GBA>APZNEO:?APRS?"] and rig.tnc.sent == [] and (asked.radio, asked.path) == (HF_ID, ()), "on the radio named, by the path it carries"
    assert rig.general.ask("aprs").radio == FM_ID and len(rig.tnc.sent) == 1, "the main radio's minute is its own: the same query goes there at once"
    with pytest.raises(MessagingError) as refused:
        rig.general.ask("aprs", radio=HF_ID)
    assert refused.value.code == "general.too_soon" and len(hf.sent) == 1
    assert [(a.radio, a.kind) for a in rig.general.asked_by_radio()] == [(HF_ID, "aprs"), (FM_ID, "aprs")], "the last of each kind on each radio"
    assert [(a.radio, a.kind) for a in rig.general.asked()] == [(FM_ID, "aprs")], "the page is given one of each kind, the latest, whose wait is never shorter than the one in force"
    assert [r.getMessage() for r in caplog.records] == ["asked around: ?APRS? by no digipeaters on Mercury", "asked around: ?APRS? by WIDE1-1,WIDE2-1,RFONLY on FM"], "with two radios on the log says which"


def test_a_query_on_a_radio_that_is_off_or_away_is_refused_and_sends_nothing() -> None:
    rig = Rig()
    with pytest.raises(MessagingError, match="no such radio"):
        rig.general.ask("aprs", radio=HF_ID)
    hf = with_hf(rig, rig.radios)
    hf.state = Source.State.WAITING
    with pytest.raises(MessagingError):
        rig.general.ask("aprs", radio=HF_ID)
    assert rig.tnc.sent == [] and hf.sent == [] and rig.general.asked() == []


class Unnamed(LineAir):
    @property
    def name(self) -> str:
        return ""                                                       # (a radio the log has no word for)


class AllRadios(StubPick):
    """The radios as the registry gives them: `get` has every radio there is, on or off."""

    def get(self, id: RadioId) -> LineAir | None:
        return next((radio for radio in self.radios if radio.id == id), None)


@pytest.mark.parametrize(("air", "words"), [(LineAir, "the radio Mercury is off"), (Unnamed, "that radio is off")])
def test_a_query_on_a_radio_there_is_but_that_is_off_says_so_with_its_name_or_without(air: type[LineAir], words: str) -> None:
    rig = Rig()
    radios = AllRadios([LineAir(rig.tnc, lambda: rig.config), air(StubTnc(max_frame=123), lambda: rig.config, id=HF_ID)])
    radios.on.discard(HF_ID)
    with pytest.raises(MessagingError) as refused:
        asked_radio(radios, lambda: rig.config, HF_ID)
    assert str(refused.value) == words
    with pytest.raises(MessagingError, match="^there is no such radio$"):
        asked_radio(radios, lambda: rig.config, 7)
    assert asked_radio(radios, lambda: rig.config).id == FM_ID


def test_the_stations_counted_after_a_query_are_those_its_radio_heard_that_it_had_not_heard_before() -> None:
    rig = Rig(hf_enabled=True)
    with_hf(rig, rig.radios)
    rig.heard_before("OH2FMQ", 3)                                       # heard on FM three minutes before: no newcomer there, one on HF
    rig.general.ask("aprs", radio=HF_ID)
    rig.general.ask("aprs")
    rig.hear("OH2FMQ", 5, radio=HF_ID)
    rig.hear("OH2FMQ", 6, radio=FM_ID)
    rig.hear("OH2HFX", 7, radio=HF_ID)
    rig.hear("OH2FMX", 8, radio=FM_ID)
    rig.hear("OH2ANY", 9)                                               # (a packet that names no radio counts for every query)
    news = {a.radio: a.new for a in rig.general.asked_by_radio()}
    assert news == {HF_ID: ("OH2FMQ", "OH2HFX", "OH2ANY"), FM_ID: ("OH2FMX", "OH2ANY")}


# ---- who spoke after it

def test_the_stations_heard_after_a_query_that_were_quiet_before_it_are_counted_for_two_minutes() -> None:
    rig = Rig()
    rig.heard_before("OH2AAA", 3)                                       # heard three minutes before: no newcomer
    rig.heard_before("OH2BBB", QUIET_BEFORE.total_seconds() / 60 + 1)   # quiet for eleven minutes: one
    rig.general.ask("aprs")
    rig.hear("OH2AAA", 5)
    rig.hear("OH2BBB", 10)
    rig.hear("OH2CCC", 20)
    rig.hear("OH2CCC", 30)                                               # (once)
    rig.hear("OH2GBA", 2)                                                # our own query, repeated
    rig.hear("OH2DDD", 30, via="rf-gated")                              # an iGate's third-party packet
    rig.hear("OH2EEE", 30, via="is")                                    # the internet
    rig.hear("OH2FFF", COUNT_FOR.total_seconds() + 1)                   # too late
    rig.hear("OH2HHH", 30, direction="out")
    [asked] = rig.general.asked()
    assert asked.new == ("OH2BBB", "OH2CCC") and asked.until == asked.at + COUNT_FOR
    assert rig.told == 1 + 2, "told when one is added, not for the others"


def test_nothing_is_counted_before_a_query() -> None:
    rig = Rig()
    rig.hear("OH2AAA")
    assert rig.general.asked() == [] and rig.told == 0


def test_a_station_counts_for_each_query_it_follows() -> None:
    rig = Rig()
    rig.general.ask("aprs")
    rig.clock.advance(30)
    rig.general.ask("wx")
    rig.hear("OH2MUI", 10)
    assert [a.new for a in rig.general.asked()] == [("OH2MUI",), ("OH2MUI",)]


def test_a_station_the_book_heard_only_from_the_internet_or_an_object_is_no_one_heard_before() -> None:
    rig = Rig()
    rig.book.rows += [rig.station("OH2III", last_is_at=rig.clock() - timedelta(minutes=1)), replace(rig.station("OBJ", last_rf_at=rig.clock()), kind="object")]
    rig.general.ask("aprs")
    rig.hear("OH2III", 5)
    assert rig.general.asked()[0].new == ("OH2III",)


# ---- through the daemon

def _out(page: object) -> list[str]:
    return [p["tnc2"] for p in page.topics["packets"].values() if p["direction"] == "out"]          # type: ignore[attr-defined]


async def test_the_command_sends_the_query_and_the_topic_tells_it_and_who_spoke_after_it(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    assert page.topics["general"] == {"asked": [], "by_radio": []}
    await page.send({"cmd": "general_query", "kind": "aprs", "path": "OH2RDK-7,OH2RCH-2", "rf_only": True})
    await page.until(lambda: page.topics["general"]["asked"] != [])
    [asked] = page.topics["general"]["asked"]
    assert (asked["kind"], asked["query"], asked["path"], asked["new"]) == ("aprs", "?APRS?", ["OH2RDK-7", "OH2RCH-2", "RFONLY"], [])
    await until(lambda: _out(page) == ["OH2GBA>APZNEO,OH2RDK-7,OH2RCH-2,RFONLY:?APRS?"])
    e.feed(on_air("OH2DPN", b"!6010.00N/02450.00E-here", path="OH2RDK-7*,OH2RCH-2*"))
    await page.until(lambda: page.topics["general"]["asked"][0]["new"] == ["OH2DPN"])
    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True})
    error = await page.expect("error")
    assert (error["cmd"], error["code"], error["params"]["query"]) == ("general_query", "general.too_soon", "?APRS?") and error["params"]["seconds"] > 0
    await page.send({"cmd": "general_query", "kind": "wx", "path": "", "rf_only": False})
    await page.until(lambda: len(page.topics["general"]["asked"]) == 2)
    await until(lambda: _out(page)[-1] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:?WX?")


async def test_the_command_is_refused_in_rx_only_and_with_a_path_that_is_none(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "general_query", "kind": "igate", "path": "OH2RDK-7,WIDE1-1,DIRECT", "rf_only": True})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("general_query", "path.direct_alone")
    assert await e.ctl.save_config(replace(e.ctl.config, station_transmit=False))
    await page.send({"cmd": "general_query", "kind": "igate", "path": None, "rf_only": True})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("general_query", "transmit.off")
    await page.quiet(0.2)
    assert page.topics["general"] == {"asked": [], "by_radio": []} and _out(page) == []
