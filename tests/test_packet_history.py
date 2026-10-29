"""The packets by the hour (`packet_history`, neoaprs/web/historywire.py): the packet log counts what was heard in each hour of the clock, and the page is answered with a count for every hour asked for, the running one
last, hours with nothing as 0, the packets we sent left out."""
import json
from datetime import timedelta
from pathlib import Path

from neoaprs.aprsisline import parse_is_line
from neoaprs.clock import iso
from neoaprs.packetlog import PacketLog
from neoaprs.store import DB_NAME
from neoaprs.web.historywire import PacketHistoryMsg
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.clock import FixedClock
from tests.support.env import Env
from tests.support.storedb import store_at
from tests.support.wireworld import T0, heard


def position(at, source: str = "OH2RDG", direction: str = "in"):
    packet = heard("!6010.00N/02456.00E-test", source, ("WIDE1*",), at)
    return packet if direction == "in" else packet.__class__(at, "out", packet.raw, packet.source, packet.destination, packet.path, packet.info, packet.decoded)


async def test_the_log_counts_the_packets_heard_in_each_hour_of_the_clock(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    top = T0.replace(minute=0, second=0, microsecond=0)
    for minutes in (-125, -61, -60, -59, -1, 0, 5, 59):                     # -125 is before the hours asked for; -61 is the first of them; -60, -59 and -1 the last whole hour; 0, 5 and 59 the running one
        assert log.append(position(top + timedelta(minutes=minutes)))
    assert log.append(position(top + timedelta(minutes=10), direction="out"))
    assert log.append(position(top + timedelta(minutes=-200)))                # (before the hours asked for)
    counted = await log.heard_by_hour(top - timedelta(hours=2))
    assert counted == {top - timedelta(hours=2): 1, top - timedelta(hours=1): 3, top: 3}
    assert await log.heard_by_hour(top + timedelta(hours=1)) == {}


async def test_the_page_is_answered_with_a_count_for_every_hour_asked_for_the_running_one_last(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    now = e.now()
    top = now.replace(minute=0, second=0, microsecond=0)
    for minutes in (-130, -70, -65, -3):
        assert e.ctl.packetlog.append(position(top + timedelta(minutes=minutes)))
    assert e.ctl.packetlog.append(position(top + timedelta(minutes=-2), direction="out"))
    await e.settled()
    await page.send({"cmd": "packet_history", "hours": 4})
    answer = PacketHistoryMsg.model_validate_json(json.dumps(await page.expect("packet_history")))
    assert answer.hours == 4 and answer.start == iso(top - timedelta(hours=3))
    assert answer.counts == [1, 2, 1, 0], "the packet we sent is not counted, and the running hour has none"
    await page.send({"cmd": "packet_history", "hours": 0})
    assert (await page.expect("error"))["cmd"] == "packet_history"
    await e.stop()


async def test_the_log_counts_the_packets_of_one_station_by_the_source_and_leaves_the_others_out(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    top = T0.replace(minute=0, second=0, microsecond=0)
    for minutes, source in ((-61, "OH2RDG"), (-30, "OH2RDG"), (-30, "OH2RDG-7"), (-20, "OH2XYZ"), (5, "OH2RDG"), (6, "OH2XYZ")):
        assert log.append(position(top + timedelta(minutes=minutes), source))
    assert log.append(position(top + timedelta(minutes=7), "OH2RDG", direction="out"))
    since = top - timedelta(hours=2)
    assert await log.heard_by_hour(since, "OH2RDG") == {top - timedelta(hours=2): 1, top - timedelta(hours=1): 1, top: 1}, "another ssid is another station, and what we sent is not heard"
    assert await log.heard_by_hour(since, "OH2XYZ") == {top - timedelta(hours=1): 1, top: 1}
    assert await log.heard_by_hour(since, "OH2NONE") == {}
    assert sum((await log.heard_by_hour(since)).values()) == 6, "and without a call every packet heard is counted, as before"


async def test_the_page_that_asks_for_a_station_is_answered_with_its_counts_and_the_call_and_the_whole_count_has_no_call(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    top = e.now().replace(minute=0, second=0, microsecond=0)
    for minutes, source in ((-70, "OH2RDG"), (-65, "OH2XYZ"), (-3, "OH2RDG"), (-2, "OH2RDG")):
        assert e.ctl.packetlog.append(position(top + timedelta(minutes=minutes), source))
    await e.settled()
    await page.send({"cmd": "packet_history", "hours": 3, "call": "OH2RDG"})
    answer = PacketHistoryMsg.model_validate_json(json.dumps(await page.expect("packet_history")))
    assert (answer.call, answer.hours, answer.start, answer.counts) == ("OH2RDG", 3, iso(top - timedelta(hours=2)), [1, 2, 0])
    await page.send({"cmd": "packet_history", "hours": 3, "call": "OH2NONE"})
    assert (await page.expect("packet_history"))["counts"] == [0, 0, 0], "a station with no packets has every hour 0"
    await page.send({"cmd": "packet_history", "hours": 3})
    whole = await page.expect("packet_history")
    assert (whole["call"], whole["counts"]) == (None, [2, 2, 0])
    await page.send({"cmd": "packet_history", "hours": 3, "call": ""})
    assert (await page.expect("error"))["cmd"] == "packet_history"
    await e.stop()


async def test_without_the_internet_the_packets_from_aprs_is_are_not_counted_nor_their_speeds_read(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    top = T0.replace(minute=0, second=0, microsecond=0)
    assert log.append(position(top - timedelta(minutes=30)))                                                                      # heard on the air
    assert log.append(parse_is_line("OH2RDG>APRS,TCPIP*,qAC,T2:!6011.00N/02456.00E>090/050from the internet", top - timedelta(minutes=20)))   # the same station over APRS-IS, with a speed
    assert log.append(parse_is_line("OH7XYZ>APRS,TCPIP*,qAC,T2:!6016.00N/02456.00E-only the internet", top - timedelta(minutes=10)))
    since = top - timedelta(hours=1)
    assert await log.heard_by_hour(since) == {top - timedelta(hours=1): 3}
    assert await log.heard_by_hour(since, internet=False) == {top - timedelta(hours=1): 1}, "only what the radio heard"
    assert await log.heard_by_hour(since, "OH2RDG", internet=False) == {top - timedelta(hours=1): 1}
    assert await log.heard_by_hour(since, "OH7XYZ", internet=False) == {}
    assert [round(kmh) for _, kmh in await log.speeds("OH2RDG", since)] == [93]
    assert await log.speeds("OH2RDG", since, internet=False) == [], "the speed came over APRS-IS"
