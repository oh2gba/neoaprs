"""?APRSH and the general queries that are never answered (neoaprs/services/queries.py): the hours a station was heard in, told from the packet log; the station never heard; the forms of the query; and `?WX?` and
`?IGATE?`, which pass without an answer and without a word above DEBUG."""
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs.aprsisline import parse_is_line
from neoaprs import aprsparse
from neoaprs.packet import Message, Other, Packet, Status, Undecoded
from neoaprs.packetlog import PacketLog
from neoaprs.services.queries import HEARD_HOURS, Queries, heard_text, hourly_counts
from tests.support.clock import FixedClock
from tests.support.env import idle_for, remember_stop, until
from tests.support.storedb import log_at
from tests.test_queries import Rig


class Log:
    """The packet log as the queries ask it: the times each station was heard."""
    def __init__(self, heard: dict[str, list[datetime]]) -> None:
        self.heard = heard
        self.asked: list[tuple[str, datetime]] = []

    async def heard_since(self, call: str, when: datetime) -> list[datetime]:
        self.asked.append((call, when))
        return [t for t in self.heard.get(call, []) if t >= when]


def rig_with(heard: dict[str, tuple[int, ...]] | None = None, no_log: bool = False) -> tuple[Rig, Log]:
    """A rig whose queries read the packet log `heard`: for each call the minutes ago its packets were heard (a station heard now is `(0,)`)."""
    rig = Rig()
    log = Log({call: [rig.clock() - timedelta(minutes=m) for m in minutes] for call, minutes in (heard or {}).items()})
    rig.q = Queries(rig.tnc, lambda: rig.config, rig.beacon, lambda: None, rig.book, lambda call: rig.paths.get(call, rig.config.beacon_path_calls), rig.clock, heard=None if no_log else log)
    remember_stop(rig.q.stop)
    return rig, log


def test_the_hours_are_counted_back_from_now_the_hour_just_gone_first() -> None:
    now = FixedClock()()
    at = [now - timedelta(minutes=m) for m in (0, 59, 61, 120, 179, 180, 7 * 60 + 59, 8 * 60, 9 * 60)]
    assert hourly_counts(at, now) == [2, 1, 2, 1, 0, 0, 0, 1] and len(hourly_counts([], now)) == HEARD_HOURS
    assert hourly_counts([now + timedelta(minutes=1)], now) == [0] * HEARD_HOURS, "a time in the future is none of the hours"


def test_the_text_is_the_one_of_the_specification_with_a_dot_for_an_hour_with_none() -> None:
    assert heard_text("N0QBF", [1, 3, 2, 0, 0, 4, 5, 6]) == "N0QBF HEARD: 1 3 2 . . 4 5 6"
    assert heard_text("N0QBF", [0] * 8) == "N0QBF HEARD: . . . . . . . ."
    assert heard_text("N0QBF", [12345, 0, 0, 0, 0, 0, 0, 1]) == "N0QBF HEARD: 9999 . . . . . . 1"
    assert heard_text("N0QBF", None) == "N0QBF NOT HEARD"


@pytest.mark.parametrize("text", ["?APRSH OH2PU-9", "?APRSHOH2PU-9", "?aprsh oh2pu-9", "  ?APRSH   OH2PU-9  "])
async def test_aprsh_tells_in_which_of_the_last_eight_hours_the_station_was_heard(text: str) -> None:
    rig, log = rig_with({"OH2PU-9": (10, 20, 90, 100, 110, 130, 400, 470)})
    rig.ask("OH2RDG", text)
    await until(lambda: len(rig.tnc.sent) == 1)
    assert rig.message_of(rig.tnc.sent[0]) == ("OH2RDG", "OH2PU-9 HEARD: 2 3 1 . . . 1 1", None)
    assert [(call, rig.clock() - when) for call, when in log.asked] == [("OH2PU-9", timedelta(hours=8))]
    assert rig.tnc.sent[0].path_text == "WIDE1-1,WIDE2-1"


async def test_aprsh_goes_by_the_path_of_the_asker_and_is_a_message_of_ours_without_an_id() -> None:
    rig, _ = rig_with({"OH2PU-9": (0,)})
    rig.paths["OH2RDG"] = ("OH2RCH-2",)
    rig.ask("OH2RDG", "?APRSH OH2PU-9", msg_id="07")
    await until(lambda: len(rig.tnc.sent) == 1)
    assert rig.tnc.sent[0].path_text == "OH2RCH-2" and rig.message_of(rig.tnc.sent[0])[2] is None


async def test_aprsh_for_a_station_heard_before_but_not_in_these_hours_gives_dots_and_for_one_never_heard_says_so() -> None:
    rig, _ = rig_with()
    rig.book.take(rig.packet("OH2OLD", Status("hello")))
    rig.ask("OH2RDG", "?APRSH OH2OLD")
    rig.ask("OH2RDG", "?APRSH OH2NEW")
    await until(lambda: len(rig.tnc.sent) == 2)
    assert sorted(rig.message_of(f)[1] for f in rig.tnc.sent) == ["OH2NEW NOT HEARD", "OH2OLD HEARD: . . . . . . . ."]


async def test_aprsh_for_a_station_known_from_the_internet_alone_says_it_was_not_heard() -> None:
    rig, _ = rig_with()
    rig.book.take(parse_is_line("OH2NET>APRS,TCPIP*,qAC,T2FINLAND:>on the net", rig.clock()))
    rig.book.take(rig.packet("OH2OLD", Status("hello")))
    rig.ask("OH2RDG", "?APRSH OH2NET")
    rig.ask("OH2RDG", "?APRSH OH2OLD")
    await until(lambda: len(rig.tnc.sent) == 2)
    assert sorted(rig.message_of(f)[1] for f in rig.tnc.sent) == ["OH2NET NOT HEARD", "OH2OLD HEARD: . . . . . . . ."], "the internet is not the air: ?APRSH is about what was heard on the radio"


async def test_the_same_aprsh_is_answered_once_and_another_call_is_a_query_of_its_own() -> None:
    rig, log = rig_with({"OH2PU-9": (0,), "OH2PU-7": (0,)})
    for _ in range(3):
        rig.ask("OH2RDG", "?APRSH OH2PU-9")
    rig.ask("OH2RDG", "?APRSH OH2PU-7")
    await until(lambda: len(rig.tnc.sent) == 2)
    await idle_for(0.1)
    assert len(rig.tnc.sent) == 2 and len(log.asked) == 2
    rig.clock.advance(31)
    rig.ask("OH2RDG", "?APRSH OH2PU-9")
    await until(lambda: len(rig.tnc.sent) == 3)


@pytest.mark.parametrize("text", ["?APRSH", "?APRSH   ", "?APRSH OH2PU-9 OH2XYZ", "?APRSH OH2GBA", "?APRSH WAYTOOLONGCALL"])
async def test_aprsh_without_a_call_with_two_or_about_ourselves_is_not_answered(text: str, caplog: pytest.LogCaptureFixture) -> None:
    rig, log = rig_with({"OH2PU-9": (0,)})
    with caplog.at_level(logging.DEBUG):
        rig.ask("OH2RDG", text)
        await idle_for(0.1)
    assert rig.tnc.sent == [] and log.asked == []


async def test_aprsh_with_no_packet_log_is_not_answered() -> None:
    rig, _ = rig_with(no_log=True)
    rig.ask("OH2RDG", "?APRSH OH2PU-9")
    await idle_for(0.1)
    assert rig.tnc.sent == []


async def test_aprsh_is_not_answered_while_the_interlock_holds_everything_back() -> None:
    rig, log = rig_with({"OH2PU-9": (0,)})
    rig.set(station_transmit=False)
    rig.ask("OH2RDG", "?APRSH OH2PU-9")
    await idle_for(0.1)
    assert rig.tnc.sent == [] and log.asked == []
    rig.set(station_transmit=True)
    rig.ask("OH2RDG", "?APRSH OH2PU-9")
    await until(lambda: len(rig.tnc.sent) == 1)


async def test_the_packet_log_gives_the_times_a_station_was_heard_and_not_those_we_sent(tmp_path: Path) -> None:
    log, _, clock = await log_at(tmp_path, PacketLog)
    now = clock()

    def packet(source: str, minutes: int, direction: str = "in") -> Packet:
        return Packet(now - timedelta(minutes=minutes), direction, b"", source, "APRS", (), b"", Status("x"))
    for item in (packet("OH2PU-9", 30), packet("OH2PU-9", 600), packet("OH2PU-7", 20), packet("OH2PU-9", 5), packet("OH2PU-9", 10, "out")):
        assert log.append(item)
    assert log.db is not None
    await log.db.barrier()
    assert [now - t for t in await log.heard_since("OH2PU-9", now - timedelta(hours=8))] == [timedelta(minutes=30), timedelta(minutes=5)]
    assert await log.heard_since("OH2NOBODY", now - timedelta(hours=8)) == []


# ---- ?WX? and ?IGATE? ----------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("info", [b"?WX?", b"?IGATE?", b"?WX?V60.17,24.94,0100", b"?wx?"])
def test_the_parser_reads_a_general_query_as_a_query_and_not_as_undecoded(info: bytes) -> None:
    decoded = aprsparse.parse(info, "OH2RDG", "APRS", FixedClock()())
    assert isinstance(decoded, Other) and decoded.kind == "query" and not isinstance(decoded, Undecoded)


@pytest.mark.parametrize("text", ["?WX?", "?IGATE?", "?WX?V60.17,24.94,0100", "?IGATE? "])
async def test_wx_and_igate_are_recognised_logged_at_debug_and_never_answered(text: str, caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig()
    rig.status_text = "QRV"
    with caplog.at_level(logging.DEBUG, logger="neoaprs.queries"):
        rig.q.on_packet(rig.packet("OH2RDG", Other("query", text), destination="WX"))
        await idle_for(0.15)
    assert rig.tnc.sent == []
    assert [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "neoaprs.queries"] == [(logging.DEBUG, f"the general query {text.strip()} of OH2RDG has nothing to be answered with here")]


async def test_wx_and_igate_as_the_text_of_a_message_to_us_are_no_query_and_are_not_answered() -> None:
    rig = Rig()
    for text in ("?WX?", "?IGATE?"):
        rig.ask("OH2RDG", text)
    await idle_for(0.1)
    assert rig.tnc.sent == []


async def test_a_general_query_of_our_own_station_or_another_kind_of_packet_is_left_alone() -> None:
    rig = Rig()
    rig.q.on_packet(rig.packet("OH2GBA", Other("query", "?WX?")))
    rig.q.on_packet(rig.packet("OH2RDG", Other("weather", "?WX?")))
    rig.q.on_packet(rig.packet("OH2RDG", Message("ALL", "?WX?")))
    await idle_for(0.1)
    assert rig.tnc.sent == []
