"""The base map over the socket: the topic `map`, the commands `map_estimate`, `map_fetch` and `map_cancel` (each refusal an `error` that says why), and the two files served with byte ranges once they exist, in the whole
daemon with the fake pmtiles program of tests/support/fakepmtiles.py."""
from dataclasses import replace
from pathlib import Path

import pytest

from tests.support.env import Env
from tests.support.fakepmtiles import alive, install_fake
from tests.support.wsclient import WsClient


SOURCE = "https://build.example/20261020.pmtiles"


async def daemon(tmp_path: Path, mode: str = "ok", operator: bool = True) -> tuple[Env, WsClient]:
    """The daemon with the fake program in its bin folder, a source of the test (no daily build is looked for), and a page that has the topic."""
    install_fake(tmp_path / "bin").mode(mode)
    e = Env(tmp_path, web=True, radio=False, operator=operator)
    await e.start(connected=False)
    if operator:
        await e.ctl.save_config(replace(e.ctl.config, map_source=SOURCE))
    page = await e.ws()
    await page.until(lambda: "map" in page.topics)
    return e, page


@pytest.fixture(autouse=True)
def only_the_fake_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")                                         # (a pmtiles on this machine is not the one to run)


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
    e, page = await daemon(tmp_path)
    await page.send({"cmd": "map_estimate"})
    await page.until(lambda: page.topics["map"]["estimate"] is not None)
    estimate = page.topics["map"]["estimate"]
    assert (estimate["bytes"], estimate["radius_km"], estimate["maxzoom"]) == (493_000_000, 150, 12)
    assert page.topics["map"]["state"] == "none"
    assert (await e.fetch("/basemap.pmtiles")).code == 404
    await page.send({"cmd": "map_fetch"})
    await page.until(lambda: page.topics["map"]["state"] == "ready", 10)
    value = page.topics["map"]
    assert value["detail"]["name"] == "basemap.pmtiles" and value["detail"]["max_zoom"] == 12 and value["detail"]["build"] == "20261020"
    assert value["world"]["name"] == "basemap-world.pmtiles" and value["world"]["max_zoom"] == 5 and value["estimate"] is None
    assert [op["value"]["state"] for op in page.ops("map") if op["op"] == "replace"][-1] == "ready"
    for name, head in (("basemap.pmtiles", b"PMTiles\x03"), ("basemap-world.pmtiles", b"PMTiles\x03")):
        whole = await e.fetch(f"/{name}")
        assert whole.code == 200 and whole.body[:8] == head
        part = await e.fetch(f"/{name}?v=1", headers={"Range": "bytes=0-7"})
        assert part.code == 206 and part.body == head


async def test_a_cancel_ends_the_job_and_every_refusal_is_an_error_with_the_reason(tmp_path: Path) -> None:
    e, page = await daemon(tmp_path, "slow")
    await page.send({"cmd": "map_cancel"})
    assert (await page.expect("error"))["text"] == "map_cancel: no map job is running"
    await page.send({"cmd": "map_fetch"})
    await page.until(lambda: page.topics["map"]["percent"] == 10)
    assert page.topics["map"]["state"] == "downloading" and page.topics["map"]["step"] == "world" and page.topics["map"]["blocked"] == "a map job is running"
    await page.send({"cmd": "map_estimate"})
    assert (await page.expect("error"))["text"] == "map_estimate: a map job is running already"
    pid = int((tmp_path / "bin" / "pid").read_text(encoding="utf-8"))
    await page.send({"cmd": "map_cancel"})
    await page.until(lambda: page.topics["map"]["state"] == "none" and page.topics["map"]["percent"] is None)
    assert page.topics["map"]["problem"] == "" and not alive(pid)


async def test_a_failed_job_is_the_state_error_with_the_reason(tmp_path: Path) -> None:
    e, page = await daemon(tmp_path, "fail")
    await page.send({"cmd": "map_fetch"})
    await page.until(lambda: page.topics["map"]["state"] == "error")
    assert "connection refused" in page.topics["map"]["problem"] and page.topics["map"]["detail"] is None


async def test_without_a_position_the_jobs_are_refused_and_the_topic_says_why(tmp_path: Path) -> None:
    e, page = await daemon(tmp_path, operator=False)
    value = page.topics["map"]
    assert value["box"] is None and "no position" in value["blocked"]
    for cmd in ("map_estimate", "map_fetch"):
        await page.send({"cmd": cmd})
        assert (await page.expect("error"))["text"].startswith(f"{cmd}: the station has no position")
