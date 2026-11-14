"""The signal of what is heard kept and told (neoaprs/reading.py): a packet's two readings go into the packet log and come back, the station cache keeps the station's last one, a message keeps the reading of the packet
that carried it (ours the ack's that came back, and none again when it is sent anew), the signal series of a station reads the packets heard direct from it in the span; and the daemon on the Dummy HF radio tells it
all on the wire: the packet's row, the station's, our message's when the made-up station acks it, its answer's, and the `signal_series` the page asks for."""
import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, dummyline
from neoaprs.aprsparse import parse
from neoaprs.packet import Packet
from neoaprs.packetlog import PacketLog
from neoaprs.source import Source
from neoaprs.station import Station
from neoaprs.store import DB_NAME
from neoaprs.web.historywire import SignalSeriesMsg
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.clock import FixedClock
from tests.support.env import Env, until_started
from tests.support.storedb import store_at
from tests.support.wireworld import T0
from tests.test_messagelog import came, opened, out, settled


def heard(source: str, at: datetime, snr: float | None, rssi: float | None = None, path: tuple[str, ...] = (), text: str = "!6027.11N/02216.00E-") -> Packet:
    """A packet as the radio gave it, its frame and what it decodes to (the log reads the packets back from their frames), with the readings the radio measured."""
    info = text.encode("latin-1")
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path), info=info)
    return Packet(at, "in", ax25.encode(frame), source, "APRS", tuple(str(a) for a in frame.path), info, parse(info, source, "APRS", at), radio="hf", snr=snr, rssi=rssi)


async def test_a_packets_readings_are_kept_and_come_back_and_one_without_has_none(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    for packet in (heard("Q3TKU", T0, -2.5), heard("OH2LRA-7", T0 + timedelta(seconds=1), 7.25, -112.0), heard("OH2RDG", T0 + timedelta(seconds=2), None)):
        assert log.append(packet)
    back = await log.recent(10)
    assert [(p.source, p.snr, p.rssi) for p in back] == [("OH2RDG", None, None), ("OH2LRA-7", 7.25, -112.0), ("Q3TKU", -2.5, None)]


async def test_the_signal_series_is_the_packets_heard_direct_from_the_station_in_the_span_the_oldest_first(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    for packet in (heard("Q3TKU", T0 - timedelta(hours=25), 1.0), heard("Q3TKU", T0 - timedelta(hours=2), -2.5), heard("Q3TKU", T0 - timedelta(hours=1), None),
                   heard("Q3TKU", T0 - timedelta(minutes=30), 9.0, path=("OH2RCH-2*",)), heard("Q3TKU", T0 - timedelta(minutes=10), 4.0, -101.0), heard("Q5OUL", T0 - timedelta(minutes=5), 3.0)):
        assert log.append(packet)
    assert await log.readings("Q3TKU", T0 - timedelta(hours=24)) == [(T0 - timedelta(hours=2), -2.5, None), (T0 - timedelta(minutes=10), 4.0, -101.0)], \
        "the one before the span, the one without a reading, the digipeater's copy and the other station's are left out"
    assert await log.readings("Q3TKU", T0 - timedelta(hours=24), count=1) == [(T0 - timedelta(minutes=10), 4.0, -101.0)], "at most so many, the latest"
    assert await log.readings("OH2NONE", T0 - timedelta(hours=24)) == []


async def test_the_station_cache_keeps_the_last_reading_with_its_time(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    station = Station("Q3TKU", first_heard=T0, last_heard=T0, snr=-2.5, rssi=None, signal_at=T0)
    assert log.save_station(station) and log.save_station(replace(station, call="OH2RDG", snr=None, signal_at=None))
    log.flush_stations()
    kept = {s.call: s for s in await log.stations()}
    assert (kept["Q3TKU"].snr, kept["Q3TKU"].rssi, kept["Q3TKU"].signal_at) == (-2.5, None, T0) and (kept["OH2RDG"].snr, kept["OH2RDG"].signal_at) == (None, None)


async def test_a_message_keeps_the_reading_of_its_packet_and_ours_the_acks(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    ours, theirs = await log.insert(out()), await log.insert(replace(came(), snr=-2.5))
    assert ours is not None and theirs is not None and ours.snr is None
    acked = replace(ours, state="acked", attempts=1, acked_at=T0 + timedelta(seconds=12), snr=6.1)
    assert log.update_state(acked)
    await settled(log)
    assert await log.recent() == [theirs, acked]
    again = replace(acked, state="sending", attempts=0, acked_at=None, snr=None)
    assert log.update_state(again)
    await settled(log)
    assert (await log.recent())[1].snr is None, "sent anew, it has no answer yet"


async def test_the_daemon_on_the_dummy_hf_radio_tells_the_snr_of_the_packets_the_stations_our_message_its_answer_and_the_series(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)
    e = Env(tmp_path, radio=False, web=True, settings={"station/call": "OH2GBA", "fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf", "station/lat": "60.17", "station/lon": "24.94", "messages/alert": "false"})
    e.ctl.mercury._finder = lambda: None                                         # (no speaker: the Dummy HF radio works without it)
    await e.start()
    await until_started(lambda: e.hf.state is Source.State.CONNECTED)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    for _ in range(400):
        e.now.advance(5)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.01)
        turku = e.ctl.stationbook.get("Q3TKU")
        if turku is not None and turku.snr is not None:
            break
    turku = e.ctl.stationbook.get("Q3TKU")
    assert turku is not None and turku.snr is not None and turku.signal_at == turku.last_heard and turku.rssi is None
    record = await e.ctl.messaging.send("Q3TKU", "hello Turku")
    for _ in range(1000):
        e.now.advance(1)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.01)
        answered = [r for r in e.ctl.messaging.records() if r.direction == "in" and r.from_call == "Q3TKU"]
        mine = e.ctl.messaging.get(record.id)
        if answered and mine is not None and mine.state == "acked":
            break
    mine = e.ctl.messaging.get(record.id)
    assert mine is not None and mine.state == "acked" and mine.snr is not None, "our message has the SNR of the ack that came back"
    assert answered and answered[0].snr is not None and answered[0].radio == "hf", "the answer has the SNR of the packet that carried it"
    await e.settled()
    await page.until(lambda: any(row["snr"] is not None for row in page.topics["packets"].values()) and page.topics["messages"].get(str(record.id), {}).get("snr") == mine.snr)
    assert page.topics["stations"]["Q3TKU"]["snr"] is not None and page.topics["hf"]["readings"] == ["snr"] and page.topics["tnc"]["readings"] == []
    await page.send({"cmd": "signal_series", "call": "Q3TKU", "hours": 24})
    answer = SignalSeriesMsg.model_validate_json(json.dumps(await page.expect("signal_series")))
    assert answer.call == "Q3TKU" and answer.points and all(snr is not None and rssi is None for _, snr, rssi in answer.points)
    await page.send({"cmd": "signal_series", "call": "", "hours": 24})
    assert (await page.expect("error"))["cmd"] == "signal_series"
    await e.stop()
