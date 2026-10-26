"""Forget all stations (`forget_all_stations`, Controller.forget_stations): every station heard goes with its packets and its weather, in the book, the pages and the database; our own station, our objects and bulletins,
the messages, the preferences of the stations, the settings and what we sent stay. Internet-only and Dummy stations go too, and a station heard afterwards is a new one."""
from pathlib import Path

from tests.support.air import from_internet, message_info, on_air
from tests.support.env import Env, quick_start, until
from tests.support.fakeaprsis import fake_aprsis

WEATHER = b"_10090556c220s004g005t077r000p000P000h50b09720"


async def world(tmp_path: Path) -> Env:
    """A daemon with a page, the internet on, a message and a weather station heard, an object and a bulletin of ours, and a path set for a station."""
    server = await fake_aprsis()
    e = await quick_start(tmp_path, web=True, messaging=True, own=True, unpaced=True, settings={"igate/enabled": "true", "igate/server": server.address, "igate/password": "19628"})
    e.feed(on_air("OH2RDG", b"=6012.34N/02456.78E-radio"))
    e.feed(on_air("OH2WX", WEATHER))
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: e.ctl.stationbook.get("OH2WX") is not None and len(e.ctl.messaging.records()) == 1)
    e.ctl.hear_internet(from_internet("OH2NET", b"=6012.34N/02456.78E-net", e.now()))
    e.ctl.ownobjects.set("LEADER", "object", lat=60.17, lon=24.94, symbol_table="/", symbol_code=">", comment="Rescue 1")        # type: ignore[arg-type]
    e.ctl.ownbulletins.post("BLN3HAMS", "Net tonight")
    await e.ctl.prefbook.set_path("OH2RDG", "WIDE1-1")
    await e.settled()
    return e


async def test_forget_all_removes_every_station_and_packet_heard_and_keeps_what_is_ours(tmp_path: Path) -> None:
    e = await world(tmp_path)
    page = await e.ws()
    await page.until(lambda: {"OH2RDG", "OH2NET", "OH2WX", "LEADER", "OH2GBA"} <= set(page.topics["stations"]) and page.topics["packets"])
    sent_before = [p for p in await e.packets() if p.direction == "out"]
    assert sent_before and await e.ctl.weatherlog.latest("OH2WX") is not None

    await page.send({"cmd": "forget_all_stations"})
    await page.until(lambda: set(page.topics["stations"]) == {"OH2GBA", "LEADER"})
    assert {r["direction"] for r in page.topics["packets"].values()} <= {"out"}
    await e.settled()
    assert sorted(s.call for s in e.ctl.stationbook.stations()) == ["LEADER", "OH2GBA"]
    assert [s.call for s in await e.stations()] == ["OH2GBA"], "the cache in the database follows (ours stays)"
    packets = await e.packets()
    assert [p for p in packets if p.direction == "in"] == [] and {p.raw for p in sent_before} <= {p.raw for p in packets}, "what was heard goes, what we sent stays"
    assert await e.ctl.weatherlog.latest("OH2WX") is None
    assert [m.text for m in e.ctl.messaging.records()] == ["Moi!"] and [b.slot for b in e.ctl.ownbulletins.records()] == ["BLN3HAMS"] and [o.name for o in e.ctl.ownobjects.records()] == ["LEADER"]
    assert e.ctl.prefbook.all()["OH2RDG"].path == ("WIDE1-1",) and e.ctl.config.station_call == "OH2GBA"

    e.feed(on_air("OH2RDG", b"=6012.34N/02456.78E-radio again"))
    await page.until(lambda: "OH2RDG" in page.topics["stations"])
    assert page.topics["stations"]["OH2RDG"]["packets"] == 1, "a station heard again is a new one"
    await e.stop()


async def test_forget_all_is_the_same_with_nothing_to_forget_and_the_database_is_what_a_restart_finds(tmp_path: Path) -> None:
    e = await world(tmp_path)
    page = await e.ws()
    await page.send({"cmd": "forget_all_stations"})
    await page.send({"cmd": "forget_all_stations"})
    await page.send({"cmd": "ping"})
    await page.expect("pong")
    assert not page.of("error")
    await e.settled()
    await e.stop()
    second = Env(tmp_path)
    await second.start()
    assert sorted(s.call for s in second.ctl.stationbook.stations()) == ["LEADER", "OH2GBA"]
    assert [p for p in await second.packets() if p.direction == "in"] == []
    await second.stop()
