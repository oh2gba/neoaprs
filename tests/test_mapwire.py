"""The base map over the socket: the topic `map`, the commands `map_estimate`, `map_fetch` and `map_cancel` (each refusal an `error` that says why), and the two files served with byte ranges once they exist, in the whole
daemon cutting the made-up planet of tests/support/madepmtiles.py from a range server on the loopback (tests/support/rangeserver.py): the dry run's numbers on the wire, the files the download makes, a cancel, the end of the
daemon while a cut runs."""
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.geo import box_around
from tests.support.env import Env, until_started
from tests.support.madepmtiles import every_tile, planet, tiles_of
from tests.support.maprig import data_offset
from tests.support.rangeserver import RangeServer, range_server
from tests.support.wsclient import WsClient

pytestmark = pytest.mark.usefixtures("no_shipped_world")


async def daemon(tmp_path: Path, operator: bool = True, hold: bool = False) -> tuple[Env, WsClient, RangeServer]:
    """The daemon with a source of the test in its settings (no daily build is looked for; the server holds its answers for tile data when asked to), and a page that has the topic."""
    server = await range_server(planet())
    if hold:
        server.hold_from = data_offset(planet())
    e = Env(tmp_path, web=True, radio=False, operator=operator)
    await e.start(connected=False)
    if operator:
        await e.ctl.save_config(replace(e.ctl.config, map_source=server.url))
    page = await e.ws()
    await page.until(lambda: "map" in page.topics)
    return e, page, server


async def test_the_page_is_told_the_state_of_the_map_with_the_area_of_the_settings(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, radio=False)
    await e.start(connected=False)
    page = await e.ws()
    await page.expect("hello")
    value = (await page.expect("state", "map"))["value"]
    assert (value["state"], value["step"], value["percent"], value["problem"], value["blocked"]) == ("none", "", None, "", "")
    assert (value["radius_km"], value["maxzoom"], value["detail"], value["world"], value["estimate"]) == (150, 12, None, None, None)
    west, south, east, north = value["box"]
    assert south < 60.17 < north and west < 24.94 < east
    await page.send({"cmd": "set_config", "values": {"map/radius_km": "50", "map/maxzoom": "14"}})
    await page.until(lambda: page.topics["map"]["radius_km"] == 50 and page.topics["map"]["maxzoom"] == 14)
    assert page.topics["map"]["box"][2] - page.topics["map"]["box"][0] < east - west


async def test_an_estimate_then_a_download_are_told_and_the_two_files_are_served(tmp_path: Path) -> None:
    e, page, server = await daemon(tmp_path)
    await page.send({"cmd": "map_estimate"})
    await page.until(lambda: page.topics["map"]["estimate"] is not None)
    estimate = page.topics["map"]["estimate"]
    box = box_around(60.17, 24.94, 150)
    assert (estimate["tiles"], estimate["radius_km"], estimate["maxzoom"], estimate["build"], estimate["box"]) == (len(tiles_of(box, 0, 6)), 150, 12, "20261020", list(box))
    assert page.topics["map"]["state"] == "none" and all(last < data_offset(planet()) for _, last in server.asked), "no tile data is fetched for a dry run"
    assert (await e.fetch("/basemap.pmtiles")).code == 404
    await page.send({"cmd": "map_fetch"})
    await page.until(lambda: page.topics["map"]["state"] == "ready", 10)
    value = page.topics["map"]
    assert value["detail"]["name"] == "basemap.pmtiles" and value["detail"]["max_zoom"] == 6 and value["detail"]["build"] == "20261020"
    assert value["detail"]["bytes"] == estimate["bytes"] and len(every_tile((tmp_path / "basemap.pmtiles").read_bytes())) == estimate["tiles"], "the dry run said what the download made"
    assert value["world"]["name"] == "basemap-world.pmtiles" and value["world"]["max_zoom"] == 5 and value["estimate"] is None
    assert [op["value"]["state"] for op in page.ops("map") if op["op"] == "replace"][-1] == "ready"
    for name, head in (("basemap.pmtiles", b"PMTiles\x03"), ("basemap-world.pmtiles", b"PMTiles\x03")):
        whole = await e.fetch(f"/{name}")
        assert whole.code == 200 and whole.body[:8] == head
        part = await e.fetch(f"/{name}?v=1", headers={"Range": "bytes=0-7"})
        assert part.code == 206 and part.body == head


async def test_a_cancel_ends_the_job_and_every_refusal_is_an_error_with_the_reason(tmp_path: Path) -> None:
    e, page, server = await daemon(tmp_path, hold=True)
    await page.send({"cmd": "map_cancel"})
    assert (await page.expect("error"))["text"] == "map_cancel: no map job is running"
    await page.send({"cmd": "map_fetch"})
    await until_started(lambda: server.holding > 0)
    await page.until(lambda: page.topics["map"]["state"] == "downloading")
    assert page.topics["map"]["step"] == "world" and page.topics["map"]["blocked"] == "a map job is running"
    await page.send({"cmd": "map_estimate"})
    assert (await page.expect("error"))["text"] == "map_estimate: a map job is running already"
    await page.send({"cmd": "map_cancel"})
    await page.until(lambda: page.topics["map"]["state"] == "none" and page.topics["map"]["percent"] is None)
    assert page.topics["map"]["problem"] == ""
    await until_started(lambda: server.holding == 0)
    assert not list(tmp_path.glob("*.part"))


async def test_a_daemon_that_ends_while_a_cut_runs_stops_it(tmp_path: Path) -> None:
    e, page, server = await daemon(tmp_path, hold=True)
    await page.send({"cmd": "map_fetch"})
    await until_started(lambda: server.holding > 0)
    await e.stop()
    await until_started(lambda: server.holding == 0)             # (the connections that waited for the server were shut)
    assert not list(tmp_path.glob("*.part"))


async def test_a_failed_job_is_the_state_error_with_the_reason(tmp_path: Path) -> None:
    e, page, server = await daemon(tmp_path)
    server.mode = "missing"
    await page.send({"cmd": "map_fetch"})
    await page.until(lambda: page.topics["map"]["state"] == "error")
    assert page.topics["map"]["problem"] == "the map server answered 404 Not Found" and page.topics["map"]["detail"] is None


async def test_without_a_position_the_jobs_are_refused_and_the_topic_says_why(tmp_path: Path) -> None:
    e, page, _ = await daemon(tmp_path, operator=False)
    value = page.topics["map"]
    assert value["box"] is None and "no position" in value["blocked"]
    for cmd in ("map_estimate", "map_fetch"):
        await page.send({"cmd": cmd})
        assert (await page.expect("error"))["text"].startswith(f"{cmd}: the station has no position")
