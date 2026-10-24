"""Our own objects and bulletins inside the whole daemon, the radio a fake TNC on the loopback: an object goes out as a KISS frame and is on the map as ours, a copy of it that is heard back makes no second one,
another station that reports it takes it over, a kill is sent three times, a bulletin goes out and is not heard as a bulletin of somebody else, nothing is sent without a call, a restart finds both, and the commands
and topics of the page."""
from pathlib import Path

import pytest

from neoaprs.station import Station
from neoaprs.web.ownwire import OwnBulletinRow, OwnObjectRow
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import on_air, said
from tests.support.env import Env, idle_for, quick_start, until

OBJECT_INFO = b";LEADER   *211200z6010.20N/02456.40E>Rescue 1"


async def started(tmp_path: Path, **kwargs: object) -> Env:
    return await quick_start(tmp_path, own=True, unpaced=True, **kwargs)


def make(e: Env, name: str = "LEADER", **values: object) -> None:
    fields: dict[str, object] = {"lat": 60.17, "lon": 24.94, "symbol_table": "/", "symbol_code": ">", "comment": "Rescue 1", **values}
    e.ctl.ownobjects.set(name, "object", **fields)                           # type: ignore[arg-type]


def own(e: Env, name: str = "LEADER") -> Station:
    station = e.ctl.stationbook.get(name)
    assert station is not None
    return station


async def test_an_object_goes_out_as_a_kiss_frame_and_is_on_the_map_as_ours(tmp_path: Path) -> None:
    e = await started(tmp_path)
    make(e)
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:" + OBJECT_INFO.decode() and frame.is_ui
    station = own(e)
    assert (station.kind, station.own, station.is_me, station.reported_by, station.lat, station.lon, station.symbol_code, station.last_comment) == ("object", True, False, "OH2GBA", 60.17, 24.94, ">", "Rescue 1")
    [sent] = [p for p in await e.packets() if p.direction == "out"]
    assert sent.kind == "object" and sent.source == "OH2GBA"
    assert "LEADER" not in [s.call for s in await e.stations()], "our object is not in the station cache: the table of our own objects keeps it"
    await e.stop()


async def test_a_copy_of_our_object_that_a_digipeater_repeats_or_the_tnc_echoes_makes_no_second_object(tmp_path: Path) -> None:
    e = await started(tmp_path)
    make(e)
    [frame] = await said(e)
    before = len(e.ctl.stationbook)
    e.feed(on_air("OH2GBA", frame.info, "APZNEO", "OH2RCH-2*,WIDE2-1"))
    e.feed(on_air("OH2GBA", frame.info, "APZNEO", "WIDE1-1"))
    await until(lambda: e.tnc.stats.packets >= 2)
    await e.settled()
    assert len(e.ctl.stationbook) == before and [s.call for s in e.ctl.stationbook.stations() if s.kind == "object"] == ["LEADER"]
    station = own(e)
    assert station.own and station.reported_by == "OH2GBA" and station.packets == 1, "it is still the one we send: what is heard back is nobody's report"
    assert [o.name for o in e.ctl.ownobjects.records()] == ["LEADER"]
    assert [s.call for s in await e.stations()].count("LEADER") == 0
    await e.stop()


async def test_the_object_of_another_station_is_still_heard_shown_and_cached_next_to_ours(tmp_path: Path) -> None:
    e = await started(tmp_path)
    make(e)
    e.feed(on_air("OH2XYZ", b";STORM    *211200z6020.00N/02500.00E>Storm cell", "APRS", "WIDE1-1"))
    await until(lambda: e.ctl.stationbook.get("STORM") is not None)
    storm = e.ctl.stationbook.get("STORM")
    assert storm is not None and (storm.kind, storm.own, storm.reported_by) == ("object", False, "OH2XYZ") and own(e).own
    assert "STORM" in [s.call for s in await e.stations()]
    await e.stop()


async def test_another_station_that_reports_our_object_takes_it_over_and_we_stop(tmp_path: Path) -> None:
    e = await started(tmp_path)
    make(e)
    await said(e)
    e.feed(on_air("OH2XYZ", b";LEADER   *211201z6030.00N/02510.00E>Mine now", "APRS", "WIDE1-1"))
    await until(lambda: e.ctl.ownobjects.get("LEADER") is None)
    station = own(e)
    assert (station.own, station.reported_by, station.lat) == (False, "OH2XYZ", 60.5), "the map shows theirs"
    e.now.advance(3600)                                                     # type: ignore[attr-defined]
    await idle_for(0.15)
    assert await said(e, 1, 0.2) == []
    await e.settled()
    assert await e.ctl.ownlog.objects() == []
    await e.stop()


async def test_another_stations_kill_of_the_name_of_our_object_does_not_end_it(tmp_path: Path) -> None:
    e = await started(tmp_path)
    make(e)
    await said(e)
    e.feed(on_air("OH2XYZ", b";LEADER   _211201z6030.00N/02510.00E>", "APRS", "WIDE1-1"))
    await until(lambda: e.tnc.stats.packets >= 1)
    await e.settled()
    assert own(e).own and e.ctl.ownobjects.get("LEADER") is not None
    await e.stop()


async def test_the_decay_goes_on_by_the_clock_and_a_kill_is_sent_three_times_and_then_the_object_is_off_the_map(tmp_path: Path) -> None:
    e = await started(tmp_path)
    make(e)
    [first] = await said(e)
    e.now.advance(60)                                                       # type: ignore[attr-defined]
    [second] = await said(e)
    assert first.info[:11] == second.info[:11] == b";LEADER   *" and first.info[11:18] == b"211200z" and second.info[11:18] == b"211201z", "each copy carries the time it is sent"
    killed = e.ctl.ownobjects.kill("LEADER")
    assert killed is not None and e.ctl.stationbook.get("LEADER") is None, "it leaves the map at once"
    frames = []
    for _ in range(3):
        e.now.advance(180)                                                  # type: ignore[attr-defined]
        frames += await said(e)
    assert [f.info[:11] for f in frames] == [b";LEADER   _"] * 3
    await until(lambda: e.ctl.ownobjects.get("LEADER") is None)
    await e.settled()
    assert await e.ctl.ownlog.objects() == []
    await e.stop()


async def test_a_bulletin_goes_out_and_the_copy_that_is_heard_back_is_not_a_bulletin_of_somebody_else(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.ctl.ownbulletins.post("BLN1", "Road closed at Kaivopuisto")
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::BLN1     :Road closed at Kaivopuisto"
    e.feed(on_air("OH2GBA", frame.info, "APZNEO", "OH2RCH-2*,WIDE2-1"))
    e.feed(on_air("OH2XYZ", b":BLN2     :Gale warning", "APRS", "WIDE1-1"))                   # (another station's bulletin is the board's as ever)
    await until(lambda: [b.key for b in e.ctl.bulletins.records()] == ["OH2XYZ/BLN2"])
    await e.settled()
    assert [b.slot for b in e.ctl.ownbulletins.records()] == ["BLN1"] and e.ctl.ownbulletins.records()[0].sent == 1
    assert [b.key for b in await e.ctl.bulletinlog.all()] == ["OH2XYZ/BLN2"], "nothing of ours in the board's table"
    assert [m for m in e.ctl.messaging.records() if m.state == "overheard"] == [] and e.ctl.messaging.records() == []
    await e.stop()


async def test_nothing_is_sent_and_nothing_is_made_without_a_call(tmp_path: Path) -> None:
    e = Env(tmp_path, operator=False)
    await e.start(connected=False)
    with pytest.raises(Exception, match="set your call first"):
        make(e)
    with pytest.raises(Exception, match="set your call first"):
        e.ctl.ownbulletins.post("BLN1", "x")
    assert e.ctl.ownobjects.records() == [] and e.ctl.ownbulletins.records() == []
    await e.stop()


async def test_a_restart_finds_both_puts_the_objects_on_the_map_and_goes_on_with_the_schedule(tmp_path: Path) -> None:
    first = await started(tmp_path)
    make(first)
    e_clock = first.now
    await said(first)
    first.ctl.ownbulletins.post("BLN1", "kept bulletin")
    await said(first)
    await first.settled()
    await first.stop()

    second = Env(tmp_path, clock=e_clock)
    second.ctl.ownobjects.tick_sec = second.ctl.ownbulletins.tick_sec = 0.02
    second.ctl.sender.spacing_sec = 0.0
    await second.start()
    await second.until_usable()
    station = own(second)
    assert station.own and station.symbol_code == ">" and station.last_comment == "Rescue 1" and station.packets == 1
    assert [(o.name, o.sent) for o in second.ctl.ownobjects.records()] == [("LEADER", 1)] and [(b.slot, b.sent) for b in second.ctl.ownbulletins.records()] == [("BLN1", 1)]
    assert await said(second, 1, 0.2) == [], "nothing is sent for the restart"
    e_clock.advance(60)                                                     # type: ignore[attr-defined]
    [frame] = await said(second)
    assert frame.info[:11] == b";LEADER   *"
    e_clock.advance(60)                                                     # type: ignore[attr-defined]
    [bulletin] = await said(second)
    assert bulletin.info == b":BLN1     :kept bulletin"
    await second.stop()


async def test_the_page_makes_changes_and_kills_an_object_and_posts_and_deletes_a_bulletin_and_is_told_what_changes(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.ownobjects.tick_sec = e.ctl.ownbulletins.tick_sec = 0.02
    e.ctl.sender.spacing_sec = 0.0
    await e.start()
    await e.until_usable()
    page = await e.ws()
    await page.expect("hello")
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    values = {"cmd": "object_set", "name": "LEADER", "kind": "object", "lat": 60.17, "lon": 24.94, "symbol_table": "/", "symbol_code": ">", "comment": "Rescue 1", "course_deg": 88, "speed_kmh": 40, "path": None}
    await page.send(values)
    await page.until(lambda: "LEADER" in page.topics["own_objects"] and "LEADER" in page.topics["stations"])
    row = OwnObjectRow.model_validate(page.topics["own_objects"]["LEADER"])
    assert (row.state, row.kind, row.course_deg, row.path) == ("live", "object", 88, None) and page.topics["stations"]["LEADER"]["own"] is True and page.topics["stations"]["LEADER"]["reported_by"] == "OH2GBA"
    [frame] = await said(e)
    assert frame.info.endswith(b">088/022Rescue 1") and frame.info.startswith(b";LEADER   *")
    await page.until(lambda: page.topics["own_objects"]["LEADER"]["sent"] == 1)
    await page.send({**values, "comment": "Moved", "lat": 60.2})
    await page.until(lambda: page.topics["own_objects"]["LEADER"]["comment"] == "Moved" and page.topics["stations"]["LEADER"]["lat"] == 60.2)
    await page.send({"cmd": "forget_station", "call": "LEADER"})
    await page.expect("error")
    await page.send({**values, "name": "OH2GBA"})
    assert "our own call" in (await page.expect("error"))["text"]
    await page.send({"cmd": "object_kill", "name": "LEADER"})
    await page.until(lambda: "LEADER" not in page.topics["stations"] and page.topics["own_objects"].get("LEADER", {}).get("state") == "killing")
    await page.send({"cmd": "object_kill", "name": "NOBODY"})
    assert "no object or item" in (await page.expect("error"))["text"]

    await page.send({"cmd": "bulletin_post", "slot": "BLN3HAMS", "text": "Net tonight 20:00"})
    await page.until(lambda: "BLN3HAMS" in page.topics["own_bulletins"])
    bulletin = OwnBulletinRow.model_validate(page.topics["own_bulletins"]["BLN3HAMS"])
    assert (bulletin.kind, bulletin.group, bulletin.text) == ("group", "HAMS", "Net tonight 20:00")
    await page.send({"cmd": "bulletin_post", "slot": "NWS-WARN", "text": "x"})
    assert "is not BLN0" in (await page.expect("error"))["text"]
    await page.send({"cmd": "bulletin_unpost", "slot": "BLN3HAMS"})
    await page.until(lambda: "BLN3HAMS" not in page.topics["own_bulletins"])
    await page.send({"cmd": "bulletin_unpost", "slot": "BLN3HAMS"})
    assert "no bulletin" in (await page.expect("error"))["text"]
    await e.stop()
