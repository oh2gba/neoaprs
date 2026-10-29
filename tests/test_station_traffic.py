"""One station's packets for its panel in the Stations tab (`station_traffic`, neoaprs/web/packetwire.py): the packet log reads those the station sent (its own, and those inside a third-party packet an iGate put on the
air) and the messages we sent to it, the newest first and at most as many as asked for; while Internet stations is off none that came from APRS-IS; and the page that asked is answered with them as rows of the
Packets tab."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.aprsthirdparty import parse_packet
from neoaprs.packet import Packet
from neoaprs.packetlog import PacketLog
from neoaprs.store import DB_NAME
from neoaprs.web.packetwire import TRAFFIC_KEPT, StationTrafficMsg
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.clock import FixedClock
from tests.support.env import Env
from tests.support.storedb import store_at
from tests.support.wireworld import T0, internet


def frame(text: str, source: str, at: datetime, direction: str = "in") -> Packet:
    """A packet as the radio gave it (or as we sent it), its frame and what it decodes to; a text that begins with `}` is a third-party packet an iGate put on the air."""
    info = text.encode("latin-1")
    raw = ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), (ax25.Address.parse("WIDE1*"),), info=info))
    decoded, third = parse_packet(info, source, "APRS", at)
    return Packet(at, direction, raw, source, "APRS", ("WIDE1*",), info, decoded, third, "rf-gated" if third else "rf")  # type: ignore[arg-type]


def world(at: datetime) -> list[Packet]:
    """OH2RDG's traffic and the rest, the oldest first: 0 its position, 1 another station, 2 our message to it, 3 our message to another, 4 its message to us, 5 its packet inside a third-party one, 6 another's
    inside one, 7 our ack to it, 8 its position from APRS-IS."""
    s = timedelta(seconds=1)
    return [frame("!6010.00N/02456.00E>x", "OH2RDG", at), frame("!6011.00N/02456.00E>x", "OH2XYZ", at + s), frame(":OH2RDG   :hello{01", "OH2GBA", at + 2 * s, "out"),
            frame(":OH2XYZ   :hi{02", "OH2GBA", at + 3 * s, "out"), frame(":OH2GBA   :hello back{7", "OH2RDG", at + 4 * s), frame("}OH2RDG>APRS,TCPIP,OH7JHF-1*:>gated", "OH7JHF-1", at + 5 * s),
            frame("}OH2XYZ>APRS,TCPIP,OH7JHF-1*:>gated", "OH7JHF-1", at + 6 * s), frame(":OH2RDG   :ack7", "OH2GBA", at + 7 * s, "out"),
            internet("OH2RDG>APRS,TCPIP*,qAC,T2FINLAND:!6010.00N/02456.00E>from the internet", at + 8 * s)]


async def test_the_log_reads_the_station_s_packets_both_ways_the_newest_first(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    for packet in world(T0):
        assert log.append(packet)
    found = await log.traffic("OH2RDG", "OH2GBA", 50)
    assert [p.heard_at for _, p in found] == [T0 + timedelta(seconds=n) for n in (8, 7, 5, 4, 2, 0)], "its own, ours to it, its inside a third-party packet; not the others'"
    assert [p.sender for _, p in found] == ["OH2RDG", "OH2GBA", "OH2RDG", "OH2RDG", "OH2GBA", "OH2RDG"]
    assert [number for number, _ in found] == [9, 8, 6, 5, 3, 1], "each with its number in the log"
    assert [p.heard_at for _, p in await log.traffic("OH2RDG", "OH2GBA", 50, internet=False)] == [T0 + timedelta(seconds=n) for n in (7, 5, 4, 2, 0)], "Internet stations off: not the one from APRS-IS"
    assert [p.heard_at for _, p in await log.traffic("OH2RDG", "OH2GBA", 2)] == [T0 + timedelta(seconds=8), T0 + timedelta(seconds=7)], "at most as many as asked for, the latest"
    assert await log.traffic("OH2NONE", "OH2GBA", 50) == []


async def test_the_page_that_asks_is_answered_with_the_rows_of_the_station_and_none_from_the_internet_while_it_is_off(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert not e.ctl.config.igate_enabled
    now = e.now() - timedelta(minutes=5)
    for packet in world(now):
        assert e.ctl.packetlog.append(packet)
    for n in range(TRAFFIC_KEPT + 5):
        assert e.ctl.packetlog.append(frame(f">status {n}", "OH2MNY", now + timedelta(seconds=10 + n)))
    await e.settled()
    await page.send({"cmd": "station_traffic", "call": "OH2RDG"})
    answer = StationTrafficMsg.model_validate_json(json.dumps(await page.expect("station_traffic")))
    assert answer.call == "OH2RDG"
    assert [(p.direction, p.sender, p.via) for p in answer.packets] == [("out", "OH2GBA", "rf"), ("in", "OH2RDG", "rf-gated"), ("in", "OH2RDG", "rf"), ("out", "OH2GBA", "rf"), ("in", "OH2RDG", "rf")]
    assert answer.packets[1].gate == "OH7JHF-1" and answer.packets[0].tnc2.endswith("::OH2RDG   :ack7")
    await page.send({"cmd": "station_traffic", "call": "OH2MNY"})
    many = await page.expect("station_traffic")
    assert len(many["packets"]) == TRAFFIC_KEPT and many["packets"][0]["tnc2"].endswith(f">status {TRAFFIC_KEPT + 4}"), "the cap: the latest"
    await page.send({"cmd": "station_traffic", "call": ""})
    assert (await page.expect("error"))["cmd"] == "station_traffic"
    await e.stop()
