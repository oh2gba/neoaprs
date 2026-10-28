"""The packets by the hour (`packet_history`, neoaprs/web/historywire.py): the packet log counts what was heard in each hour of the clock, and the page is answered with a count for every hour asked for, the running one
last, hours with nothing as 0, the packets we sent left out."""
import json
from datetime import timedelta
from pathlib import Path

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
