"""The queries (neoaprs/services/queries.py) on a Tnc that is a stub, the real beacon and station book and a clock the test holds: each query to us gives the frame it should, by the path of the asker; the
general query waits and is taken once in ten minutes; and what is not a query, not to us or not heard is left alone."""
import logging
from datetime import timedelta

import pytest

from neoaprs import ax25
from neoaprs.aprsmessage import MAX_TEXT, parse_message
from neoaprs.packet import Message, Other, Packet, Status
from neoaprs.services.beacon import Beacon
from neoaprs.message import MessageRecord
from neoaprs.ownobject import make_object
from neoaprs.services.queries import ANSWER_FRAMES_MAX, GENERAL_DELAY_MAX_SEC, GENERAL_EVERY_SEC, Queries, directs_messages, path_text
from neoaprs.source import Source
from neoaprs.stationbook import StationBook
from tests.support.clock import FixedClock
from tests.support.rig import ServiceRig
from tests.support.env import idle_for, remember_stop, until


class Rig(ServiceRig):
    def __init__(self, delay: float = 0.0, **changes: object) -> None:
        super().__init__(**changes)
        self.book = StationBook(self.clock)
        self.book.set_me(self.config.station_call, self.config.station_lat, self.config.station_lon)
        self.paths: dict[str, tuple[str, ...]] = {}
        self.status_text = ""                                          # what the status service says it sent last
        self.beacon = Beacon(self.tnc, lambda: self.config, self.clock)
        self.q = Queries(self.tnc, lambda: self.config, self.beacon, lambda: self.beacon.status_frame(self.status_text), self.book, lambda call: self.paths.get(call, self.config.beacon_path_calls), self.clock, delay=lambda: delay)
        remember_stop(self.q.stop)

    def packet(self, source: str, decoded: object, path: tuple[str, ...] = ("OH2RCH-2*",), direction: str = "in", destination: str = "APZNEO", third: object = None) -> Packet:
        return Packet(self.clock(), direction, b"", source, destination, path, b"", decoded, third)    # type: ignore[arg-type]

    def ask(self, source: str, text: str, to: str = "OH2GBA", msg_id: str | None = None, **kwargs: object) -> None:
        self.q.on_packet(self.packet(source, Message(to, text, msg_id), **kwargs))      # type: ignore[arg-type]

    def hear_direct(self, call: str, seconds_ago: float = 0.0) -> None:
        """The station was heard direct that long ago (the clock is put back for the moment)."""
        now = self.clock()
        self.clock.set(now - timedelta(seconds=seconds_ago))
        self.book.take(self.packet(call, Status("hello"), path=()))
        self.clock.set(now)

    def message_of(self, frame: ax25.Frame) -> tuple[str, str, str | None]:
        assert frame.info[:1] == b":"
        m = parse_message(frame.info[1:])
        return m.addressee, m.text, m.msg_id


# ---- the position and the status -----------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("to", ["OH2GBA", "oh2gba"])
def test_aprsp_is_answered_with_the_beacons_position_frame_by_the_beacon_path(to: str) -> None:
    rig = Rig()
    rig.ask("OH2RDG", "?APRSP", to=to)
    assert rig.tnc.sent == [rig.beacon.frame()] and rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS"]


def test_the_answer_goes_by_the_path_of_the_asker_and_a_direct_one_has_none() -> None:
    rig = Rig()
    rig.paths["OH2RDG"] = ("OH2RCH-2", "WIDE2-1")
    rig.ask("OH2RDG", "?APRSP")
    rig.paths["OH2ABC"] = ()
    rig.ask("OH2ABC", "?APRSP")
    rig.ask("OH2XYZ", "?APRSP")
    assert [f.path_text for f in rig.tnc.sent] == ["OH2RCH-2,WIDE2-1", "", "WIDE1-1,WIDE2-1"]
    assert {f.info for f in rig.tnc.sent} == {rig.beacon.frame().info}


def test_aprss_is_answered_with_the_status_report_last_sent_and_with_nothing_while_none_has_been() -> None:
    rig = Rig()
    rig.ask("OH2RDG", "?APRSS")
    assert rig.tnc.sent == []
    rig.status_text = "QRV 145.500"
    rig.ask("OH2RDG", "?APRSS")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500"]


def test_a_query_is_read_without_regard_to_case_or_blanks_and_is_ours_only_with_our_exact_call() -> None:
    rig = Rig(station_call="OH2GBA-9")
    rig.ask("OH2RDG", "  ?aprsp ", to="OH2GBA")
    assert rig.tnc.sent == [], "the base call is not ours when ours has an SSID"
    rig.ask("OH2ABC", "  ?aprsp ", to="OH2GBA-9")
    assert len(rig.tnc.sent) == 1


# ---- the directs ---------------------------------------------------------------------------------------------------------------------------------

def test_aprsd_lists_the_calls_heard_direct_in_the_last_hour_the_one_heard_last_first() -> None:
    rig = Rig()
    rig.hear_direct("OH2PU-9", 600)
    rig.hear_direct("OH2RCH-2", 60)
    rig.hear_direct("OH2OLD", 3601)
    rig.book.take(rig.packet("OH2VIA", Status("hello")))                                 # (heard by way of a digipeater)
    rig.ask("OH2RDG", "?APRSD")
    [frame] = rig.tnc.sent
    assert rig.message_of(frame) == ("OH2RDG", "Directs= OH2RCH-2 OH2PU-9", None)
    assert (str(frame.source), str(frame.destination), frame.path_text) == ("OH2GBA", "APZNEO", "WIDE1-1,WIDE2-1")


def test_aprsd_with_nobody_heard_direct_says_none_and_never_lists_us_or_an_object() -> None:
    rig = Rig()
    rig.ask("OH2RDG", "?APRSD")
    assert rig.message_of(rig.tnc.sent[0])[1] == "Directs= none"
    me = rig.book.me
    assert me is not None and me.last_direct_at is None


def test_aprsd_is_split_over_two_messages_of_at_most_67_bytes_and_the_rest_is_left_out() -> None:
    rig = Rig()
    calls = [f"OH2{chr(65 + n)}{chr(65 + n)}-{n % 10 + 1}" for n in range(20)]
    for n, call in enumerate(calls):
        rig.hear_direct(call, 600 - n)
    rig.ask("OH2RDG", "?APRSD")
    assert len(rig.tnc.sent) == 2
    texts = [rig.message_of(f)[1] for f in rig.tnc.sent]
    assert all(len(t.encode()) <= MAX_TEXT and t.startswith("Directs= ") for t in texts)
    shown = [c for t in texts for c in t.split()[1:]]
    assert shown == list(reversed(calls))[: len(shown)] and 0 < len(shown) < 20


def test_directs_messages_fill_a_message_before_starting_the_next() -> None:
    assert directs_messages([]) == ["Directs= none"]
    assert directs_messages(["A", "B"]) == ["Directs= A B"]
    long = [f"OH2AB{n}-1" for n in range(10)]                                          # 9 characters and a blank each
    texts = directs_messages(long)
    assert len(texts) == 2 and all(len(t) <= MAX_TEXT for t in texts) and texts[0].count("OH2") == 6
    assert len(directs_messages([f"OH2AB{n % 10}-1" for n in range(100)])) == 2


# ---- the path ------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["?APRST", "?PING?", "?ping?"])
def test_aprst_and_ping_are_answered_with_the_header_of_the_query_as_we_heard_it(query: str) -> None:
    rig = Rig()
    rig.ask("OH2RDG", query, path=("WIDE1*", "OH2RCH-2*", "WIDE2-1"), destination="APZNEO")
    [frame] = rig.tnc.sent
    assert rig.message_of(frame) == ("OH2RDG", "OH2RDG>APZNEO,WIDE1*,OH2RCH-2*,WIDE2-1:", None), "the header as the specification's example has it, no Path= in front"


def test_the_path_of_a_direct_query_is_just_the_header_and_a_long_one_loses_its_last_digipeaters() -> None:
    rig = Rig()
    rig.ask("OH2RDG", "?APRST", path=())
    assert rig.message_of(rig.tnc.sent[0])[1] == "OH2RDG>APZNEO:"
    long = rig.packet("OH2RDG-15", Message("OH2GBA", "?APRST"), path=("OH2RCH-12*", "OH2RCH-13*", "OH2RCH-14*", "OH2RCH-15*", "WIDE2-2", "WIDE3-3"))
    text = path_text(long)
    assert len(text.encode()) <= MAX_TEXT and text.startswith("OH2RDG-15>APZNEO,OH2RCH-12*,OH2RCH-13*") and text.endswith(":") and "WIDE3-3" not in text


# ---- what a query carries ------------------------------------------------------------------------------------------------------------------------

def test_a_query_with_a_message_id_is_answered_all_the_same_and_the_answer_has_no_id() -> None:
    rig = Rig()
    rig.ask("OH2RDG", "?APRSD", msg_id="12")
    assert rig.message_of(rig.tnc.sent[0]) == ("OH2RDG", "Directs= none", None)


def test_the_same_query_from_the_same_station_within_half_a_minute_is_answered_once() -> None:
    rig = Rig()
    for _ in range(3):
        rig.ask("OH2RDG", "?APRSP", path=("OH2RCH-2*",))                                 # (the copies of one transmission)
    assert len(rig.tnc.sent) == 1
    rig.ask("OH2RDG", "?APRSS")
    rig.ask("OH2ABC", "?APRSP")
    assert len(rig.tnc.sent) == 2, "another query, or another station, is answered"
    rig.clock.advance(31)
    rig.ask("OH2RDG", "?APRSP")
    assert len(rig.tnc.sent) == 3


@pytest.mark.parametrize("text, to", [("?APRSP", "OH2XYZ"), ("?APRSPX", "OH2GBA"), ("hello ?APRSP", "OH2GBA"), ("APRSP", "OH2GBA"), ("", "OH2GBA"), ("?APRS", "OH2GBA"), ("?APRSD?", "OH2GBA")])
def test_what_is_not_a_query_to_us_is_left_alone(text: str, to: str) -> None:
    rig = Rig()
    rig.ask("OH2RDG", text, to=to)
    assert rig.tnc.sent == []


def test_an_ack_a_reject_our_own_echo_and_a_packet_we_sent_are_not_queries() -> None:
    rig = Rig()
    rig.q.on_packet(rig.packet("OH2RDG", Message("OH2GBA", "?APRSP", ack_id="3")))
    rig.q.on_packet(rig.packet("OH2RDG", Message("OH2GBA", "?APRSP", rej_id="3")))
    rig.ask("OH2GBA", "?APRSP")
    rig.ask("OH2RDG", "?APRSP", direction="out")
    assert rig.tnc.sent == []


def test_the_asker_of_a_third_party_query_is_the_sender_inside() -> None:
    from neoaprs.packet import ThirdParty
    rig = Rig()
    rig.ask("OH7JHF-1", "?APRSD", third=ThirdParty("OH2DPN", "APRS", ("TCPIP",)), path=("OH2RCH-3*",))
    assert rig.message_of(rig.tnc.sent[0])[0] == "OH2DPN"
    rig.ask("OH7JHF-1", "?APRST", third=ThirdParty("OH2DPN", "APRS", ("TCPIP",)), path=("OH2RCH-3*",))
    assert rig.message_of(rig.tnc.sent[1]) == ("OH2DPN", "OH7JHF-1>APZNEO,OH2RCH-3*:", None), "the path of the frame we heard"


def test_nothing_is_sent_while_the_tnc_is_not_connected_and_the_log_says_so(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.queries")
    rig = Rig()
    rig.tnc.state = Source.State.WAITING
    rig.ask("OH2RDG", "?APRSP")
    assert rig.tnc.sent == [] and any("not connected" in r.getMessage() for r in caplog.records)


def test_nothing_is_sent_while_the_radio_is_silent_and_the_log_says_so(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.queries")
    rig = Rig()
    rig.tnc.state = Source.State.SILENT
    rig.ask("OH2RDG", "?APRSP")
    assert rig.tnc.sent == [] and any("the radio is silent" in r.getMessage() for r in caplog.records)


def test_a_tnc_that_will_not_take_the_frame_is_told(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.queries")
    rig = Rig()
    rig.tnc.takes = False
    rig.ask("OH2RDG", "?APRSP")
    assert any("would not take" in r.getMessage() for r in caplog.records)


# ---- the general query ---------------------------------------------------------------------------------------------------------------------------

def general(rig: Rig, source: str = "OH2RDG", text: str = "?APRS?") -> None:
    rig.q.on_packet(rig.packet(source, Other("query", text)))


async def test_the_general_query_in_a_message_is_not_answered_whoever_it_is_addressed_to() -> None:
    rig = Rig()
    for to in ("ALL", "OH2XYZ", "OH2GBA"):
        rig.ask("OH2RDG", "?APRS?", to=to)
    await idle_for(0.1)
    assert rig.tnc.sent == []


async def test_the_general_query_in_the_information_field_of_a_packet_is_answered_with_the_position_and_then_the_status_by_the_path_of_the_asker() -> None:
    rig = Rig(delay=0.05)
    rig.status_text = "QRV 145.500"
    rig.paths["OH2RDG"] = ("OH2RCH-2",)
    general(rig)
    assert rig.tnc.sent == []
    await until(lambda: len(rig.tnc.sent) == 2)
    assert [f.info for f in rig.tnc.sent] == [rig.beacon.frame().info, b">211200zQRV 145.500"] and {f.path_text for f in rig.tnc.sent} == {"OH2RCH-2"}


async def test_the_general_query_gives_the_position_alone_while_no_status_has_been_sent() -> None:
    rig = Rig()
    general(rig)
    await until(lambda: len(rig.tnc.sent) == 1)
    await idle_for(0.1)
    assert [f.info for f in rig.tnc.sent] == [rig.beacon.frame().info]


async def test_the_general_query_is_taken_once_in_ten_minutes() -> None:
    rig = Rig()
    general(rig, "OH2RDG")
    general(rig, "OH2DEF")
    await until(lambda: len(rig.tnc.sent) == 1)
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(GENERAL_EVERY_SEC - 1)
    general(rig)
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(2)
    general(rig)
    await until(lambda: len(rig.tnc.sent) == 2)


@pytest.mark.parametrize("text, inside", [
    ("?APRS?V60.17,24.94,0010", True), ("?APRS? 60.17,24.94,0010", True), ("?APRS?V60.17,24.94,0000", True), ("?APRS?V60.5,24.94,0030", True), ("?APRS?V60.5,24.94,0020", False),
    ("?APRS?V34.02,-117.15,0200", False), ("?APRS?V60.17,-24.94,1000", False), ("?APRS?V60.17,-24.94,2000", True), ("?APRS?V-33.87,151.21,0100", False), ("?APRS?V60.17,24.94,0010 ", True), ("?aprs?V60.17,24.94,0010", True)])
async def test_a_footprint_is_honoured_we_answer_only_from_inside_it(text: str, inside: bool) -> None:
    rig = Rig()                                          # (we are at 60.17 N 24.94 E)
    general(rig, text=text)
    await idle_for(0.1)
    assert len(rig.tnc.sent) == (1 if inside else 0)


async def test_a_footprint_that_does_not_read_is_not_answered_and_a_query_outside_the_footprint_does_not_start_the_ten_minutes() -> None:
    rig = Rig()
    for text in ("?APRS?V60.17,24.94", "?APRS?V95.0,24.94,0010", "?APRS?x", "?APRS?V60.17,24.94,00100"):
        general(rig, text=text)
    general(rig, text="?APRS?V34.02,-117.15,0200")
    await idle_for(0.1)
    assert rig.tnc.sent == []
    general(rig, "OH2ABC")
    await until(lambda: len(rig.tnc.sent) == 1)


async def test_an_answer_that_is_waiting_is_not_sent_when_the_queries_stop() -> None:
    rig = Rig(delay=60.0)
    general(rig)
    await rig.q.stop()
    assert rig.tnc.sent == []


async def test_the_wait_is_a_random_time_from_nothing_to_two_minutes_by_default() -> None:
    rig = Rig()
    q = Queries(rig.tnc, lambda: rig.config, rig.beacon, rig.book, lambda call: (), rig.clock)
    waits = [q._delay() for _ in range(200)]
    assert all(0.0 <= w <= GENERAL_DELAY_MAX_SEC for w in waits) and max(waits) > 60 and min(waits) < 60
    assert GENERAL_DELAY_MAX_SEC == 120.0 and GENERAL_EVERY_SEC == 600.0


async def test_a_general_query_heard_while_the_tnc_is_away_gives_no_answer_when_the_wait_is_over() -> None:
    rig = Rig()
    general(rig)
    rig.tnc.state = Source.State.WAITING
    await idle_for(0.1)
    assert rig.tnc.sent == []


# ---- ?APRSO and ?APRSM: several frames, one at a time ---------------------------------------------------------------------------------------------

class Held:
    """A service that holds records (our objects, our messages), for the queries to read."""
    def __init__(self, records: list[object]) -> None:
        self.held = records

    def records(self) -> list[object]:
        return self.held


def paced_rig(objects: tuple[object, ...] = (), messages: tuple[object, ...] = ()) -> Rig:
    rig = Rig()
    rig.q = Queries(rig.tnc, lambda: rig.config, rig.beacon, lambda: None, rig.book, lambda call: rig.config.beacon_path_calls, rig.clock,
                    objects=Held(list(objects)), messages=Held(list(messages)), spacing_sec=0.05)                     # type: ignore[arg-type]
    remember_stop(rig.q.stop)
    return rig


async def test_aprso_is_answered_with_each_live_object_and_item_once_one_at_a_time_and_at_most_five() -> None:
    now = FixedClock()()
    live = [make_object(now, f"OBJ{n}", "object", 60.0 + n / 100, 24.0, "/", ">") for n in range(6)]
    item = make_object(now, "AID", "item", 60.5, 24.5, "\\", "+")
    rig = paced_rig((live[0].killed(now), item, *live))
    rig.ask("OH2RDG", "?APRSO")
    assert len(rig.tnc.sent) == 1, "the first goes at once, the rest are paced"
    await until(lambda: len(rig.tnc.sent) == ANSWER_FRAMES_MAX)
    await idle_for(0.2)
    infos = [f.info for f in rig.tnc.sent]
    assert len(infos) == ANSWER_FRAMES_MAX and infos[0].startswith(b")AID!") and all(i.startswith(b";OBJ") and i[10:11] == b"*" for i in infos[1:]), "a killed object is not sent"
    assert {f.path_text for f in rig.tnc.sent} == {"WIDE1-1,WIDE2-1"}
    rig.ask("OH2RDG", "?APRSO")
    await idle_for(0.1)
    assert len(rig.tnc.sent) == ANSWER_FRAMES_MAX, "the same query again at once is answered once"


async def test_aprsm_sends_again_our_messages_to_the_asker_that_no_ack_settled_and_changes_nothing() -> None:
    at = FixedClock()()
    rows = [("OH2RDG", "one", "01", "sending"), ("OH2RDG", "two", "02", "acked"), ("OH2RDG", "three", "03", "failed"), ("OH2XYZ", "other", "04", "sending"),
            ("OH2RDG", "four", "05", "unconfirmed"), ("OH2RDG", "?APRSP", None, "unconfirmed"), ("OH2RDG", "five", "06", "rejected")]
    messages = [MessageRecord(n, at, "out", "OH2GBA", to, text, ident, state) for n, (to, text, ident, state) in enumerate(rows, start=1)]       # type: ignore[arg-type]
    messages.append(MessageRecord(9, at, "in", "OH2RDG", "OH2GBA", "theirs", "07", "received"))
    rig = paced_rig(messages=tuple(messages))
    rig.ask("OH2RDG", "?APRSM")
    await until(lambda: len(rig.tnc.sent) == 3)
    await idle_for(0.2)
    assert [rig.message_of(f) for f in rig.tnc.sent] == [("OH2RDG", "one", "01"), ("OH2RDG", "three", "03"), ("OH2RDG", "four", "05")]
    assert rig.tnc.sent[0].info == b":OH2RDG   :one{01}" and [m.state for m in messages] == ["sending", "acked", "failed", "sending", "unconfirmed", "unconfirmed", "rejected", "received"]
    rig.ask("OH2NEW", "?APRSM")
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 3, "nothing is owed to a station we never wrote to: no answer"
