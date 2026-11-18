"""What the statistics card counts from the packet log (`packet_stats`, neoaprs/packetstats.py): the packets heard by the hour by radio, what went out on each radio by what it was, the packets that came by
several ways, the copies of the last hour; an hour that is over is counted once and kept, the running one counted again."""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.aprsisline import parse_is_line
from neoaprs.packet import Packet
from neoaprs.packetlog import PacketLog
from neoaprs.packetstats import WEEK_HOURS
from neoaprs.store import DB_NAME
from neoaprs.tncmode import packet_of
from neoaprs.web.historywire import PacketStatsMsg
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.clock import FixedClock
from tests.support.env import Env
from tests.support.storedb import store_at
from tests.support.wireworld import T0

ME = "OH2GBA"
TOP = T0.replace(minute=0, second=0, microsecond=0)


def frame(info: str, source: str = "OH2RDG", path: tuple[str, ...] = ()) -> tuple[bytes, ax25.Frame]:
    made = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), tuple(ax25.Address.parse(a) for a in path), info=info.encode("latin-1"))
    return ax25.encode(made), made


def on_air(at: datetime, info: str = "!6010.00N/02456.00E-test", source: str = "OH2RDG", radio: int = 1, path: tuple[str, ...] = (), direction: str = "in") -> Packet:
    raw, made = frame(info, source, path)
    return packet_of("in" if direction == "in" else "out", raw, made, at, radio_id=radio)


def from_internet(at: datetime, source: str = "OH2NET") -> Packet:
    return parse_is_line(f"{source}>APRS,TCPIP*,qAC,T2FINLAND:!6010.00N/02456.00E-net", at)


async def test_the_packets_heard_are_counted_by_the_hour_and_by_the_radio_the_internet_apart(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    clock = FixedClock(TOP + timedelta(minutes=30))
    log = PacketLog(store.db, clock)
    for minutes, radio in ((-90, 1), (-50, 1), (-40, 2), (5, 2), (10, 1)):
        assert log.append(on_air(TOP + timedelta(minutes=minutes), radio=radio))
    assert log.append(from_internet(TOP + timedelta(minutes=-20)))
    assert log.append(on_air(TOP + timedelta(minutes=1), source=ME, direction="out"))       # (ours: never heard)
    counted = await log.stats.counted(ME, internet=True)
    assert counted.start == TOP - timedelta(hours=2) and counted.hours == 3, "from the hour of the oldest packet, the running hour last"
    assert counted.heard == {1: [1, 1, 1], 2: [0, 1, 1], None: [0, 1, 0]}
    without = await log.stats.counted(ME, internet=False)
    assert None not in without.heard, "with the internet stations off none from APRS-IS is counted"


async def test_what_went_out_is_counted_by_radio_and_by_what_it_was_over_the_last_day(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    clock = FixedClock(TOP + timedelta(minutes=30))
    log = PacketLog(store.db, clock)
    sent = [("!6010.00N/02456.00E-beacon", ME, 1), (">On the air", ME, 1), (":OH2RDG   :hello{12", ME, 1), (":OH2RDG   :ack7", ME, 1), (":OH2RDG   :rej8", ME, 2),
            (";LEADER   *111111z6010.00N/02456.00E-", ME, 2), ("!6010.00N/02456.00E-theirs", "OH2RDG", 2)]
    for info, source, radio in sent:
        assert log.append(on_air(TOP + timedelta(minutes=2), info, source, radio, direction="out"))
    assert log.append(on_air(TOP - timedelta(hours=25), "!6010.00N/02456.00E-old", ME, 1, direction="out"))      # (more than a day ago: not counted)
    counted = await log.stats.counted(ME, internet=True)
    assert counted.sent[1] == {"repeated": 0, "beacon": 2, "object": 0, "ack": 1, "message": 1, "other": 0}
    assert counted.sent[2] == {"repeated": 1, "beacon": 0, "object": 1, "ack": 1, "message": 0, "other": 0}
    assert counted.repeated_hour == 1, "the digipeater's copy of the last hour"


async def test_a_packet_that_came_by_several_ways_is_one_packet_of_several_frames(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    clock = FixedClock(TOP + timedelta(minutes=30))
    log = PacketLog(store.db, clock)
    at = TOP + timedelta(minutes=3, seconds=10)
    assert log.append(on_air(at))                                                              # direct
    assert log.append(on_air(at + timedelta(seconds=2), path=("OH2RCH-2*", "WIDE2-1")))         # the same again through a digipeater
    assert log.append(on_air(at + timedelta(seconds=3), radio=2))                                # and on another radio
    assert log.append(on_air(at + timedelta(minutes=10)))                                        # the same beacon ten minutes later: a packet of its own
    assert log.append(on_air(at, "!6010.00N/02456.00E-other", "OH2XYZ"))
    assert log.append(from_internet(at, "OH2RDG"))                                              # (the internet is no way of the radios)
    counted = await log.stats.counted(ME, internet=True)
    assert (counted.packets, counted.frames) == (3, 5)


async def test_an_hour_that_is_over_is_counted_once_and_the_running_one_again(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    clock = FixedClock(TOP + timedelta(minutes=30))
    log = PacketLog(store.db, clock)
    assert log.append(on_air(TOP - timedelta(minutes=30)))
    assert log.append(on_air(TOP + timedelta(minutes=10)))
    assert (await log.stats.counted(ME, internet=True)).heard[1] == [1, 1]
    assert log.append(on_air(TOP - timedelta(minutes=20)))                                      # (written into an hour already counted: it stays as it was counted)
    assert log.append(on_air(TOP + timedelta(minutes=20)))
    assert (await log.stats.counted(ME, internet=True)).heard[1] == [1, 1], "within the minute the answer is given again"
    clock.advance(61)
    assert (await log.stats.counted(ME, internet=True)).heard[1] == [1, 2], "the running hour is counted again, the hour that is over is not"
    clock.advance(3600)
    assert (await log.stats.counted(ME, internet=True)).heard[1] == [1, 2, 0], "the hour that ended is counted once more as it ends"
    await log.forget_heard(ME)
    clock.advance(1)
    assert (await log.stats.counted(ME, internet=True)).heard == {}, "forgetting the heard packets counts anew"


async def test_the_week_is_the_most_that_is_counted(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock(TOP + timedelta(minutes=30)))
    assert log.append(on_air(TOP - timedelta(hours=WEEK_HOURS + 5)))
    assert log.append(on_air(TOP - timedelta(hours=WEEK_HOURS - 1)))
    counted = await log.stats.counted(ME, internet=True)
    assert counted.hours == WEEK_HOURS and counted.start == TOP - timedelta(hours=WEEK_HOURS - 1)
    assert counted.heard[1][0] == 1 and sum(counted.heard[1]) == 1


async def test_the_page_is_answered_with_the_counts_and_the_gated_hour_while_the_igate_is_on(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    top = e.now().replace(minute=0, second=0, microsecond=0)
    assert e.ctl.packetlog.append(on_air(top - timedelta(minutes=70), radio=1))
    await e.settled()
    await page.send({"cmd": "packet_stats"})
    answer = PacketStatsMsg.model_validate_json(json.dumps(await page.expect("packet_stats")))
    assert answer.heard[0].radio == 1 and sum(answer.heard[0].counts) == 1 and len(answer.heard[0].counts) == answer.hours
    assert answer.gated_hour is None, "the iGate is off out of the box"
    await e.stop()


async def test_two_pages_that_ask_at_once_while_the_week_is_counted_get_the_same_counts_never_doubled(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock(TOP + timedelta(minutes=30)))
    for hours in (100, 50, 13, 1):
        assert log.append(on_air(TOP - timedelta(hours=hours)))
    first, second = await asyncio.gather(log.stats.counted(ME, internet=True), log.stats.counted(ME, internet=True))
    assert sum(first.heard[1]) == sum(second.heard[1]) == 4
