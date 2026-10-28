"""The speeds of a moving station (`speed_series`, neoaprs/web/historywire.py): the packet log reads them from the station's position packets heard in the span, a course and speed after the position and a
Mic-E's alike, leaving out the positions with no speed, the other stations and what we sent; the page that asked is answered with the points, the oldest first, and the call."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.aprsparse import parse
from neoaprs.clock import iso
from neoaprs.packet import Packet
from neoaprs.packetlog import PacketLog
from neoaprs.store import DB_NAME
from neoaprs.web.historywire import SpeedSeriesMsg
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.clock import FixedClock
from tests.support.env import Env
from tests.support.storedb import store_at
from tests.support.wireworld import T0

KNOT = 1.852
MIC_E = ('`(_fn"Oj/', "S32UVT")                                         # 20 knots, course 251 (tests/test_aprsmice.py)


def heard(text: str, source: str, at: datetime, destination: str = "APRS", direction: str = "in") -> Packet:
    """A packet as the radio gave it, its frame and what it decodes to: the log reads the packets back from their frames."""
    info = text.encode("latin-1")
    frame = ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), (ax25.Address.parse("WIDE1*"),), info=info)
    return Packet(at, direction, ax25.encode(frame), source, destination, ("WIDE1*",), info, parse(info, source, destination, at))  # type: ignore[arg-type]


def moving(at: datetime, knots: int, source: str = "OH2ZMA-9", direction: str = "in") -> Packet:
    return heard(f"!6010.00N/02456.00E>090/{knots:03d}", source, at, direction=direction)


def standing(at: datetime, source: str = "OH2ZMA-9") -> Packet:
    return heard("!6010.00N/02456.00E-no speed", source, at)


async def test_the_log_reads_the_speeds_of_the_station_in_the_span_the_oldest_first(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    for packet in (moving(T0 - timedelta(hours=25), 50), moving(T0 - timedelta(hours=2), 36), standing(T0 - timedelta(hours=1)), moving(T0 - timedelta(minutes=30), 0),
                   heard(MIC_E[0], "OH2ZMA-9", T0 - timedelta(minutes=10), MIC_E[1]), moving(T0 - timedelta(minutes=5), 40, "OH2XYZ")):
        assert log.append(packet)
    assert log.append(moving(T0 - timedelta(minutes=3), 60, direction="out"))
    speeds = await log.speeds("OH2ZMA-9", T0 - timedelta(hours=24))
    assert [(at, round(kmh, 3)) for at, kmh in speeds] == [(T0 - timedelta(hours=2), round(36 * KNOT, 3)), (T0 - timedelta(minutes=30), 0.0), (T0 - timedelta(minutes=10), round(20 * KNOT, 3))], \
        "the one before the span, the position with no speed, the other station's and what we sent are left out; a Mic-E's speed counts, and so does a 0"
    assert await log.speeds("OH2NONE", T0 - timedelta(hours=24)) == []


async def test_the_page_that_asks_is_answered_with_the_points_and_the_call_and_a_station_with_no_speed_with_none(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    now = e.now()
    for packet in (moving(now - timedelta(hours=30), 10), moving(now - timedelta(hours=3), 36), moving(now - timedelta(minutes=2), 5), standing(now - timedelta(minutes=1), "OH2RDG")):
        assert e.ctl.packetlog.append(packet)
    await e.settled()
    await page.send({"cmd": "speed_series", "call": "OH2ZMA-9", "hours": 24})
    answer = SpeedSeriesMsg.model_validate_json(json.dumps(await page.expect("speed_series")))
    assert (answer.call, answer.hours) == ("OH2ZMA-9", 24)
    assert answer.points == [(iso(now - timedelta(hours=3)), 66.7), (iso(now - timedelta(minutes=2)), 9.3)], "rounded to a tenth of a km/h"
    await page.send({"cmd": "speed_series", "call": "OH2ZMA-9", "hours": 48})
    assert len((await page.expect("speed_series"))["points"]) == 3, "a longer span reaches further back"
    await page.send({"cmd": "speed_series", "call": "OH2RDG", "hours": 24})
    assert (await page.expect("speed_series"))["points"] == []
    await page.send({"cmd": "speed_series", "call": "", "hours": 24})
    assert (await page.expect("error"))["cmd"] == "speed_series"
    await e.stop()
