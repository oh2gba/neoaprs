"""The Send on of Ask around and of Local info (neoaprs/beaconrule.py `send_on_radios`, neoaprs/services/generalask.py, neoaprs/services/qruask.py): each has a tick per radio that can send, in the beacon's
pattern (`radio/<id>/ask`, `radio/<id>/local_info`). A press sends one frame on each ticked radio that takes frames now and nothing on a radio that is unticked, only receives or is off; it is all or
nothing while a ticked radio is inside its wait; the record of a press holds its radios, and a station (an object) heard on two of them is counted once. With one radio that can send, on that one whatever is
stored; with several and none ticked, on none. A group's request and Ask again go on the one radio named, the radio the server answered on.

What goes on the air is counted per radio, on stub lines under a clock the test holds and a registry that reads the settings as they are (tests/test_status_send_on.py `Registry`); the last tests run the
whole daemon (migration 34 writes the ticks of a data folder of 0.20.1: tests/test_no_main_radio.py)."""
import logging
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.aprsmessage import format_message
from neoaprs.beaconrule import send_on_radios
from neoaprs.config import Config
from neoaprs.message import MessagingError
from neoaprs.packet import Message, Other, Packet
from neoaprs.qrutext import ASK_EVERY_SEC as QRU_EVERY_SEC, ASK_GAP_SEC
from neoaprs.radiospec import RadioHeard, RadioId, RadioSpec
from neoaprs.services.generalask import ASK_EVERY_SEC, GeneralAsk
from neoaprs.services.qruask import AskedOn, QruAsk
from neoaprs.source import Source
from neoaprs.station import Station
from neoaprs.web.confighandlers import with_radio_values
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, remember_stop, until
from tests.support.stubtnc import StubTnc
from tests.test_qruask import object_report
from tests.test_status_send_on import Registry

FM = RadioSpec(1, "fm", "kenwood-tnc2", "", True, 1, settings={"path": "WIDE1-1,WIDE2-1"})
HF = RadioSpec(2, "hf", "dummy-hf", "", True, 2)
LORA = RadioSpec(3, "lora", "dummy-lora", "", True, 3)
RX = RadioSpec(4, "fm", "tnc-text", "", True, 4, settings={"port": "/dev/ttyUSB7", "ask": "true", "local_info": "true"})       # (ticks stored from another type: a radio that only receives has no such field)
OFF = RadioSpec(5, "fm", "kiss", "", False, 5, settings={"ask": "true", "local_info": "true"})
KEYS = ("ask", "local_info")


def ticked(spec: RadioSpec, on: bool = True) -> RadioSpec:
    """The radio with the row of both things stored: ticked, or unticked."""
    return replace(spec, settings={**spec.settings, **dict.fromkeys(KEYS, "true" if on else "false")})


class Asking:
    """Asking around and asking QRU of a station with these radios."""
    def __init__(self, *specs: RadioSpec, **changes: object) -> None:
        self.clock = FixedClock()
        self.config: Config = replace(ON_AIR, **{"radios": specs, **changes})  # type: ignore[arg-type]
        self.lines: dict[RadioId, StubTnc] = {spec.id: StubTnc(max_frame=123 if spec.kind == "hf" else None, id=spec.id) for spec in specs}
        self.short: tuple[RadioId, ...] = ()
        self.rows: list[Station] = []
        self.radios = Registry(self)          # type: ignore[arg-type]  # (it reads the settings, the lines and `short`, which this has as the status's station does)
        self.general = GeneralAsk(self.radios, lambda: self.config, self, self.clock)
        self.qru = QruAsk(self.radios, lambda: self.config, self.path_for, self.clock)
        remember_stop(self.qru.stop)

    def stations(self) -> list[Station]:
        return self.rows

    def path_for(self, call: str, attempt: int | None, radio: RadioId) -> tuple[str, ...]:
        """The path of messages to a station on the radio: here the radio's own."""
        spec = self.config.radio(radio)
        return tuple(hop for hop in ("" if spec is None else spec.settings.get("path", "")).split(",") if hop)

    def put(self, *specs: RadioSpec) -> None:
        self.config = replace(self.config, radios=tuple(next((new for new in specs if new.id == s.id), s) for s in self.config.radios))

    def frames(self) -> dict[RadioId, int]:
        return {id: len(line.sent) for id, line in self.lines.items()}

    def tnc2(self, id: RadioId) -> list[str]:
        return [frame.tnc2() for frame in self.lines[id].sent]

    def heard_before(self, call: str, minutes: float, radio: RadioId) -> None:
        at = self.clock() - timedelta(minutes=minutes)
        self.rows.append(Station(call, first_heard=at, last_heard=at, last_rf_at=at, heard_by={radio: RadioHeard(1, at)}))

    def hear(self, source: str, seconds: float, radio: RadioId | None) -> None:
        at = self.clock() + timedelta(seconds=seconds)
        self.general.on_packet(Packet(at, "in", b"", source, "APRS", (), b">here", Other("status", ">here"), None, "rf", radio_id=radio))

    def answer(self, source: str, text: str, radio: RadioId | None) -> None:
        """A message of a QRU server to us, heard on the radio."""
        info = b":" + format_message("OH2GBA", text, None, None)
        self.qru.on_packet(Packet(self.clock(), "in", b"", source, "APRS", (), info, Message("OH2GBA", text, None), None, "rf", radio_id=radio))

    def object_from(self, source: str, name: str, radio: RadioId | None) -> None:
        self.qru.on_packet(replace(object_report(source, name, self.clock()), radio_id=radio))


# ---- ticked nowhere ---------------------------------------------------------------------------------------------------------------------------------

async def test_with_several_radios_on_and_none_ticked_nothing_goes_and_the_press_is_refused_with_no_radio() -> None:
    station = Asking(FM, HF, LORA, RX, replace(OFF, settings={}))
    for kind in ("aprs", "igate", "wx"):
        with pytest.raises(MessagingError) as refused:
            station.general.ask(kind)          # type: ignore[arg-type]
        assert refused.value.code == "radio.none"
    with pytest.raises(MessagingError) as refused:
        station.qru.ask("INFO")
    assert refused.value.code == "radio.none" and station.frames() == dict.fromkeys(station.lines, 0), "not one frame: no radio of the station stands in for the ticks"
    station.put(ticked(LORA))
    station.qru.ask("INFO")
    assert isinstance(station.qru.asked, AskedOn) and station.qru.asked.radios == (3,) and station.frames()[3] == 1


async def test_with_one_radio_that_can_send_everything_goes_on_it_whatever_is_stored() -> None:
    for spec in (HF, ticked(HF, False), ticked(HF)):
        station = Asking(spec, RX, replace(ticked(FM), enabled=False))
        assert station.general.ask("aprs").radios == (2,)
        station.qru.ask("INFO")
        assert station.frames() == {2: 2, 4: 0, 1: 0}
        assert station.tnc2(2) == ["OH2GBA>APZNEO:?APRS?", "OH2GBA>APZNEO::QRU      :INFO"], "Mercury carries no path"


# ---- Ask around -------------------------------------------------------------------------------------------------------------------------------------

def test_a_query_goes_once_on_each_ticked_radio_and_on_no_unticked_receive_only_or_off_radio() -> None:
    station = Asking(ticked(FM), ticked(HF), ticked(LORA, False), RX, OFF)
    asked = station.general.ask("aprs")
    assert station.frames() == {1: 1, 2: 1, 3: 0, 4: 0, 5: 0}
    assert station.lines[4].asked == 0 and station.lines[5].asked == 0, "a radio that only receives and one that is off are not even offered the frame"
    assert station.tnc2(1) == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY:?APRS?"] and station.tnc2(2) == ["OH2GBA>APZNEO:?APRS?"], "each by the path it carries: Mercury none"
    assert (asked.radios, asked.path) == ((1, 2), ("WIDE1-1", "WIDE2-1", "RFONLY")), "the record holds its radios, and the path of the one that carries a path"
    assert [(s.kind, s.radio) for s in station.general.sent_on()] == [("aprs", 1), ("aprs", 2)]


def test_a_path_typed_goes_on_the_radios_that_carry_a_path_and_each_radios_own_differ_when_none_is_typed() -> None:
    station = Asking(ticked(FM), ticked(HF), ticked(LORA))
    typed = station.general.ask("aprs", "OH2RDK-7,OH2RCH-2", False)
    assert [station.tnc2(id) for id in (1, 2, 3)] == [["OH2GBA>APZNEO,OH2RDK-7,OH2RCH-2:?APRS?"], ["OH2GBA>APZNEO:?APRS?"], ["OH2GBA>APZNEO,OH2RDK-7,OH2RCH-2:?APRS?"]]
    assert typed.path == ("OH2RDK-7", "OH2RCH-2")
    own = station.general.ask("wx")
    assert [station.tnc2(id)[-1] for id in (1, 2, 3)] == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY:?WX?", "OH2GBA>APZNEO:?WX?", "OH2GBA>APZNEO,WIDE1-1,RFONLY:?WX?"], "none typed: each radio's own (LoRa's WIDE1-1)"
    assert own.path is None and own.radios == (1, 2, 3), "the FM radio's own path and the LoRa radio's differ: the record names none"


def test_a_press_is_all_or_nothing_while_a_ticked_radio_is_inside_its_minute() -> None:
    station = Asking(ticked(FM, False), ticked(HF))
    station.general.ask("aprs")
    assert station.frames() == {1: 0, 2: 1}
    station.clock.advance(20)
    station.put(ticked(FM))                                         # (the FM radio ticked too, 20 s after the query on Mercury)
    station.clock.advance(10)
    with pytest.raises(MessagingError) as refused:
        station.general.ask("aprs")
    assert (refused.value.code, refused.value.params) == ("general.too_soon", {"query": "?APRS?", "seconds": ASK_EVERY_SEC - 30}), "the Mercury radio's minute holds the whole press"
    assert station.frames() == {1: 0, 2: 1}, "nothing on the FM radio either, though its own minute is free"
    assert station.general.ask("igate").radios == (1, 2) and station.frames() == {1: 1, 2: 2}, "another kind is not held"
    station.clock.advance(ASK_EVERY_SEC - 30)
    assert station.general.ask("aprs").radios == (1, 2)
    assert station.frames() == {1: 2, 2: 3}
    station.put(ticked(HF, False))                                  # (Mercury unticked: its minute holds nothing any more)
    station.clock.advance(ASK_EVERY_SEC)
    station.general.ask("aprs")
    station.put(ticked(FM, False), ticked(HF))
    assert station.general.ask("aprs").radios == (2,), "the minute is each radio's: the FM radio's does not hold a query that does not go on it"
    assert station.frames() == {1: 3, 2: 4}


def test_a_path_that_is_none_or_a_ticked_radio_that_waits_sends_nothing_on_any_radio() -> None:
    station = Asking(ticked(FM), ticked(HF))
    for path, code in (("OH2RDK-7,???", "call.shape"), ("A1,A2,A3,A4,A5,A6,A7,A8", "path.too_long_rf_only")):
        with pytest.raises(MessagingError) as refused:
            station.general.ask("aprs", path, True)
        assert refused.value.code == code
    assert station.frames() == {1: 0, 2: 0} and station.general.asked() == [], "the Mercury radio would have taken its frame, which carries no path: nothing went"
    assert station.lines[1].asked == 0 and station.lines[2].asked == 0


def test_a_ticked_radio_that_takes_no_frames_now_is_left_out_and_none_that_does_is_a_refusal_with_its_reason() -> None:
    station = Asking(ticked(FM), ticked(HF))
    station.lines[2].held = "the channel is busy"
    assert station.general.ask("aprs").radios == (1,) and station.frames() == {1: 1, 2: 0}, "on the radio that takes frames now"
    station.lines[2].held = ""
    station.clock.advance(30)
    with pytest.raises(MessagingError) as refused:
        station.general.ask("aprs")
    assert refused.value.code == "general.too_soon" and station.frames() == {1: 1, 2: 0}, "the FM radio's minute holds the press though Mercury is free now"
    station.clock.advance(30)
    station.lines[1].state = station.lines[2].state = Source.State.WAITING
    with pytest.raises(MessagingError) as refused:
        station.general.ask("aprs")
    assert refused.value.code == "radio.not_connected" and station.frames() == {1: 1, 2: 0}
    station.lines[1].state = station.lines[2].state = Source.State.CONNECTED
    station.lines[1].takes = False
    assert station.general.ask("aprs").radios == (2,), "a radio that did not take its frame is not in the record"
    station.lines[2].takes = False
    station.clock.advance(ASK_EVERY_SEC)
    with pytest.raises(MessagingError) as refused:
        station.general.ask("aprs")
    assert refused.value.code == "radio.not_taken" and station.frames() == {1: 1, 2: 1}


def test_a_station_heard_on_two_radios_after_a_press_is_counted_once() -> None:
    station = Asking(ticked(FM), ticked(HF), ticked(LORA, False))
    station.heard_before("OH2FMQ", 3, 1)                             # heard on FM three minutes before: no newcomer there, one on Mercury
    station.general.ask("aprs")
    station.hear("OH2NEW", 5, 1)
    station.hear("OH2NEW", 6, 2)                                     # (the same station on the second radio)
    station.hear("OH2FMQ", 7, 1)
    station.hear("OH2FMQ", 8, 2)
    station.hear("OH2FMQ", 9, 2)
    station.hear("OH2LOR", 10, 3)                                    # (on a radio the press did not go on)
    station.hear("OH2ANY", 11, None)                                 # (a packet that names no radio: quiet on every radio of the press)
    station.hear("OH2FMQ", 12, None)
    [asked] = station.general.asked()
    assert asked.new == ("OH2NEW", "OH2FMQ", "OH2ANY"), "each once, whatever number of radios heard it; what a radio the press did not go on heard is not counted"


FM2 = RadioSpec(6, "fm", "kiss", "", True, 6, settings={"path": "WIDE2-2"})
HF2 = RadioSpec(7, "hf", "dummy-hf", "", True, 7)
HF3 = RadioSpec(8, "hf", "dummy-hf", "", True, 8)


def test_six_radios_that_send_an_hour_of_presses_one_query_a_minute_of_each_kind_on_each_ticked_radio_and_none_on_another() -> None:
    station = Asking(replace(FM, settings={**FM.settings, "ask": "true"}), replace(FM2, settings={**FM2.settings, "ask": "false"}), HF, replace(HF2, settings={"ask": "true"}), HF3,
                     replace(LORA, settings={"ask": "true"}), RX, OFF)
    assert send_on_radios("ask", station.config.radios) == (1, 3, 7), "the ticked ones by position; a radio without a row beside them is unticked"
    sent = refused = 0
    for _ in range(120):                                           # a press of each kind every 30 seconds for an hour: every second one is inside the minute of all three radios
        for kind in ("aprs", "igate", "wx"):
            try:
                assert station.general.ask(kind).radios == (1, 3, 7)        # type: ignore[arg-type]
                sent += 1
            except MessagingError as e:
                assert (e.code, e.params["seconds"]) == ("general.too_soon", 30)
                refused += 1
        station.clock.advance(30)
    assert (sent, refused) == (180, 180)
    per_radio = {id: Counter(line.split(":", 1)[1] for line in station.tnc2(id)) for id in station.lines}
    assert per_radio[1] == per_radio[3] == per_radio[7] == Counter({"?APRS?": 60, "?IGATE?": 60, "?WX?": 60}), "one of each kind a minute on each ticked radio"
    assert all(not per_radio[id] and station.lines[id].asked == 0 for id in (6, 2, 8, 4, 5)), "the unticked, those without a row, the monitor and the one that is off were never offered a frame"


def test_a_ticked_radio_that_is_away_holds_the_press_inside_its_minute_and_is_left_out_after_it() -> None:
    station = Asking(ticked(FM, False), ticked(HF))
    station.general.ask("aprs")
    station.lines[2].state = Source.State.WAITING                   # (Mercury away, 0 s after its query)
    station.put(ticked(FM))
    station.clock.advance(30)
    with pytest.raises(MessagingError) as refused:
        station.general.ask("aprs")
    assert refused.value.code == "general.too_soon" and station.frames() == {1: 0, 2: 1}, "all or nothing: the minute of a ticked radio holds the press though that radio is away"
    station.clock.advance(30)
    assert station.general.ask("aprs").radios == (1,) and station.frames() == {1: 1, 2: 1}, "outside its minute it is left out and the press goes"
    station.lines[2].state = Source.State.CONNECTED
    station.clock.advance(1)
    with pytest.raises(MessagingError):
        station.general.ask("aprs")
    assert station.frames() == {1: 1, 2: 1}, "the radio that is back gets no query of its own a second later: the FM radio's minute holds the press"


def test_the_log_says_each_radio_a_query_went_on_and_a_radio_that_did_not_take_its_frame(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    station = Asking(ticked(FM), ticked(HF), ticked(LORA))
    station.lines[3].takes = False
    assert station.general.ask("aprs").radios == (1, 2)
    assert [(r.name, r.levelname, r.getMessage()) for r in caplog.records] == [
        ("neoaprs.services", "WARNING", "asking around: the LoRa radio did not take the frame"),
        ("neoaprs.queries", "INFO", "asked around: ?APRS? by WIDE1-1,WIDE2-1,RFONLY on FM"),
        ("neoaprs.queries", "INFO", "asked around: ?APRS? by no digipeaters on Mercury")]


# ---- Local info -------------------------------------------------------------------------------------------------------------------------------------

async def test_the_request_info_goes_once_on_each_ticked_radio_and_on_no_unticked_receive_only_or_off_radio() -> None:
    station = Asking(ticked(FM), ticked(HF), ticked(LORA, False), RX, OFF)
    station.qru.ask("INFO 50")
    assert station.frames() == {1: 1, 2: 1, 3: 0, 4: 0, 5: 0} and station.lines[4].asked == 0 and station.lines[5].asked == 0
    assert station.tnc2(1) == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY::QRU      :INFO 50"] and station.tnc2(2) == ["OH2GBA>APZNEO::QRU      :INFO 50"]
    assert isinstance(station.qru.asked, AskedOn) and station.qru.asked.radios == (1, 2), "the request records its radios"


async def test_a_request_is_all_or_nothing_while_a_ticked_radio_is_inside_one_of_its_waits() -> None:
    station = Asking(ticked(FM, False), ticked(HF))
    station.qru.ask("INFO")
    station.put(ticked(FM))
    station.clock.advance(ASK_GAP_SEC - 4)
    with pytest.raises(MessagingError) as refused:
        station.qru.ask("RP70")
    assert (refused.value.code, refused.value.params) == ("qru.too_soon", {"seconds": 4}), "the gap of the Mercury radio holds the whole request"
    station.clock.advance(4)
    with pytest.raises(MessagingError) as refused:
        station.qru.ask("INFO")
    assert refused.value.params == {"seconds": QRU_EVERY_SEC - ASK_GAP_SEC}, "the same text within the Mercury radio's minute: nothing on the FM radio either"
    assert station.frames() == {1: 0, 2: 1}
    station.qru.ask("RP70")
    assert station.frames() == {1: 1, 2: 2}, "another text after the gap: on both"
    station.clock.advance(QRU_EVERY_SEC)
    station.qru.ask("INFO")
    assert station.frames() == {1: 2, 2: 3}


async def test_a_groups_request_and_ask_again_go_on_the_one_radio_the_server_answered_on() -> None:
    station = Asking(ticked(FM), ticked(HF), LORA)
    station.qru.ask("INFO")
    station.answer("OH2DPN", "de OH2DPN:RP70(2) Max 5@50km", 2)
    [server] = station.qru.servers()
    assert server.radio == 2, "the server's row carries the radio it answered on"
    station.answer("OH2DPN", "de OH2DPN:RP70(2) Max 5@50km", 3)        # (the copy a radio we did not ask on heard)
    assert station.qru.servers()[0].radio == 2, "of the radios the request went on: a copy heard on another radio says nothing"
    station.clock.advance(ASK_GAP_SEC)
    station.qru.ask("RP70", radio=server.radio)
    assert station.frames() == {1: 1, 2: 2, 3: 0}, "the group's request on the Mercury radio alone"
    assert isinstance(station.qru.asked, AskedOn) and station.qru.asked.radios == (2,)
    with pytest.raises(MessagingError) as refused:
        station.qru.ask("RP70", radio=2)
    assert refused.value.code == "qru.too_soon" and station.frames() == {1: 1, 2: 2, 3: 0}
    station.qru.ask("FOOD", radio=3)
    assert station.frames() == {1: 1, 2: 2, 3: 1}, "a radio named takes the request whatever its tick, and its waits are its own"
    for off, code in ((4, "radio.receive_only"), (9, "radio.unknown")):
        with pytest.raises(MessagingError) as refused:
            station_with_rx = Asking(ticked(FM), RX)
            station_with_rx.qru.ask("RP70", radio=off)
        assert refused.value.code == code


async def test_an_object_heard_on_two_radios_of_a_request_is_counted_once_and_one_on_another_radio_is_not() -> None:
    station = Asking(ticked(FM), ticked(HF), LORA)
    station.qru.ask("TEST 150")
    station.object_from("OH2DPN", "BOTH", 1)
    station.object_from("OH2DPN", "BOTH", 2)
    station.object_from("OH2DPN", "ONHF", 2)
    station.object_from("OH2DPN", "ONLORA", 3)
    station.object_from("OH2DPN", "NAMELESS", None)                # (a packet that names no radio counts for every request)
    station.answer("OH2DPN", "Sent 3 TEST Objects Max 5@150km de OH2DPN", 1)
    [server] = station.qru.servers()
    assert server.received == ("BOTH", "NAMELESS", "ONHF") and server.radio == 1


# ---- the rule and the row a tick writes ---------------------------------------------------------------------------------------------------------------

def test_each_thing_has_its_own_ticks_read_by_the_one_rule() -> None:
    specs = (replace(FM, settings={"ask": "true"}), replace(HF, settings={"local_info": "true"}), LORA)
    assert send_on_radios("ask", specs) == (1,) and send_on_radios("local_info", specs) == (2,) and send_on_radios("status", specs) == ()
    assert send_on_radios("ask", (FM, RX)) == (1,) and send_on_radios("ask", (FM, RX, HF)) == (), "a row a radio that only receives kept from another type is not read"
    assert send_on_radios("ask", (FM, HF, OFF)) == (), "a ticked radio that is off is none: ticked nowhere"


def test_a_tick_stores_itself_alone_whatever_the_number_and_one_sent_back_as_it_is_stores_nothing() -> None:
    base = replace(ON_AIR, radios=(FM, FM2, HF, replace(HF2, settings={"status": "true"}), HF3, LORA, RX, OFF))       # (0.20.1 stored a status tick only where it was ticked: radio 7's)
    rows = lambda config, key: {s.id: s.settings.get(key) for s in config.radios}      # noqa: E731
    one = with_radio_values(base, {"radio/6/ask": "true"})
    assert rows(one, "ask") == {**rows(base, "ask"), 6: "true"}, "the tick pressed, of six radios that send: no other row is written"
    assert rows(one, "local_info") == rows(base, "local_info") and rows(one, "status") == rows(base, "status"), "the row of one thing: no other thing is touched"
    assert send_on_radios("ask", one.radios) == (6,), "a radio with no row is unticked: it is the same as a row that says false"
    assert with_radio_values(base, {"radio/7/status": "true", "radio/2/status": "false", "radio/1/ask": "false"}) == base, "a tick that is the one in force, stored or the default, stores nothing"
    off = with_radio_values(base, {"radio/7/status": "false"})
    assert rows(off, "status")[7] == "false" and send_on_radios("status", off.radios) == (), "the last tick taken away: ticked nowhere"


# ---- the whole daemon -------------------------------------------------------------------------------------------------------------------------------

async def test_a_daemon_with_fm_and_mercury_asks_on_the_fm_radio_ticked_when_mercury_came_and_then_on_the_ticked_radios(tmp_path: Path) -> None:
    clock = FixedClock()
    e = Env(tmp_path, clock=clock, web=True, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})          # (radio 1 ticked for both when radio 2 came beside it, as the controller writes it)
    e.mercury._finder = lambda: None                          # (no program: the Dummy Mercury radio works without its speaker)
    out: list[tuple[RadioId | None, bytes]] = []
    e.ctl.radio_packet.connect(lambda p: out.append((p.radio_id, ax25.decode(p.raw).info)) if p.direction == "out" else None)
    await e.start()
    await until(lambda: e.tnc.usable and e.hf.usable)
    page = await e.ws()
    await page.until(lambda: "radios" in page.topics and "general" in page.topics)
    assert {spec.id: (spec.settings.get("ask"), spec.settings.get("local_info")) for spec in await e.ctl.store.read_radios()} == {1: ("true", "true"), 2: (None, None)}
    asks = lambda: Counter((id, info) for id, info in out if info.startswith((b"?", b":QRU")))       # noqa: E731

    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True})
    await page.send({"cmd": "qru_ask", "text": "INFO"})
    await until(lambda: sum(asks().values()) == 2)
    assert asks() == Counter({(1, b"?APRS?"): 1, (1, b":QRU      :INFO"): 1}), "on the FM radio alone"

    await page.send({"cmd": "set_config", "values": {"radio/1/ask": "true", "radio/2/ask": "true"}})          # (the tick of radio 2; radio 1 sent back as it is)
    await page.until(lambda: page.topics["radios"]["2"]["choices"]["ask"])
    assert {spec.id: (spec.settings.get("ask"), spec.settings.get("local_info")) for spec in await e.ctl.store.read_radios()} == {1: ("true", "true"), 2: ("true", None)}
    clock.advance(ASK_EVERY_SEC)
    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True})
    await page.until(lambda: [a["radios"] for a in page.topics["general"]["asked"]] == [[1, 2]])
    await page.send({"cmd": "qru_ask", "text": "INFO"})
    await until(lambda: sum(asks().values()) == 5)
    assert asks() == Counter({(1, b"?APRS?"): 2, (2, b"?APRS?"): 1, (1, b":QRU      :INFO"): 2}), "Ask around on both; Local info, whose ticks are its own, still on the FM radio"

    await page.send({"cmd": "set_config", "values": {"radio/1/local_info": "false", "radio/2/local_info": "true"}})
    await page.until(lambda: page.topics["radios"]["2"]["choices"]["local_info"])
    assert {spec.id: spec.settings.get("local_info") for spec in await e.ctl.store.read_radios()} == {1: "false", 2: "true"}, "each tick the page sent is stored, the one taken away too"
    clock.advance(ASK_EVERY_SEC)
    await page.send({"cmd": "qru_ask", "text": "INFO"})
    await page.until(lambda: page.topics["qru"]["asked"]["radios"] == [2])
    assert asks()[(2, b":QRU      :INFO")] == 1 and asks()[(1, b":QRU      :INFO")] == 2
    await e.stop()


async def test_a_form_that_sends_back_what_it_was_given_stores_no_tick_and_so_chooses_nothing(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    e.mercury._finder = lambda: None
    await e.start()
    page = await e.ws()
    await page.until(lambda: "config" in page.topics)
    given = {key: value for key, value in page.topics["config"]["radio_values"].items() if key.startswith("radio/")}
    assert given["radio/1/ask"] == "true" and given["radio/2/local_info"] == "false"
    before = {spec.id: dict(spec.settings) for spec in await e.ctl.store.read_radios()}
    await page.send({"cmd": "set_config", "values": {**given, "station/comment": "sent back"}})
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "sent back")
    radios = await e.ctl.store.read_radios()
    assert {spec.id: dict(spec.settings) for spec in radios} == before and not any(key in radios[1].settings for key in ("status", *KEYS)), "a default sent back stays the default"
    await e.stop()
