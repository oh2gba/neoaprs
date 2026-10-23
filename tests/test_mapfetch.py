"""The base map service (neoaprs/services/mapfetch.py) with the fake pmtiles program of tests/support/fakepmtiles.py: the states and what the page is told, the box round the position, no position, the world map
first, a file moved into place only when the program has finished, a cancel, one job at a time, the program fetched when it is missing, the latest daily build."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.config import Config
from neoaprs.geo import box_around
from neoaprs.mapstate import Job, MapError
from neoaprs.pmtilestool import ToolError
from neoaprs.services.mapfetch import DETAIL, WORLD, MapFetch, latest_build
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until
from tests.support.maprig import MapRig
from tests.support.fakepmtiles import FakePmtiles, alive, install_fake

SOURCE = "https://build.example/20261020.pmtiles"
CONFIG = replace(ON_AIR, map_source=SOURCE)
JOBS: tuple[Job, Job] = ("estimate", "fetch")


class Rig(MapRig):
    def __init__(self, data: Path, fake: FakePmtiles, config: Config) -> None:
        super().__init__(data, fake, lambda: self.config)
        self.config = config

    def states(self) -> list[str]:
        return [s.state for s in self.seen]


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    monkeypatch.setenv("PATH", "")                                         # (a real pmtiles on this machine is not the one to run)
    data = tmp_path / "data"
    return Rig(data, install_fake(data / "bin"), CONFIG)


# ---- what is there

def test_before_anything_is_done_there_is_no_map_and_the_area_follows_the_position(rig: Rig) -> None:
    status = rig.status()
    assert (status.state, status.step, status.percent, status.problem, status.blocked) == ("none", "", None, "", "")
    assert status.detail is None and status.world is None and status.estimate is None
    assert (status.radius_km, status.maxzoom) == (150, 12)
    assert status.box == box_around(60.17, 24.94, 150)


async def test_the_files_in_the_data_folder_are_described_by_their_headers(rig: Rig) -> None:
    await rig.service.fetch()
    status = rig.status()
    assert status.state == "ready" and status.detail is not None and status.world is not None
    assert status.detail.name == DETAIL and status.detail.max_zoom == 12 and status.detail.bbox == pytest.approx(box_around(60.17, 24.94, 150), abs=1e-5)
    assert status.world.name == WORLD and status.world.max_zoom == 5 and status.world.bbox == (-180.0, -85.0, 180.0, 85.0)
    assert status.detail.bytes == (rig.data / DETAIL).stat().st_size and status.detail.build == "20261020"


def test_a_map_made_by_hand_has_a_header_and_no_build(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / DETAIL).write_bytes(b"not a map")
    status = rig.status()
    assert status.state == "ready" and status.detail is not None and status.detail.bbox is None and status.detail.build == ""


# ---- the box

async def test_the_area_is_the_box_round_the_position_for_the_radius_and_the_zoom_of_the_settings(rig: Rig) -> None:
    rig.config = replace(CONFIG, station_lat=64.5, station_lon=26.0, map_radius_km=40, map_maxzoom=14)
    await rig.service.estimate()
    west, south, east, north = box_around(64.5, 26.0, 40)
    call = rig.fake.calls()[0]
    assert call[1] == SOURCE and call[2].endswith("basemap.pmtiles.part") and "--maxzoom=14" in call and "--dry-run" in call
    assert f"--bbox={west:.5f},{south:.5f},{east:.5f},{north:.5f}" in call
    assert south < 64.5 < north and west < 26.0 < east
    assert (east - west) > (north - south), "a degree of longitude is shorter this far north"


def test_the_box_is_clamped_at_the_edges_of_the_world() -> None:
    assert box_around(0.0, 0.0, 111.195) == pytest.approx((-1.0, -1.0, 1.0, 1.0), abs=1e-3)
    west, south, east, north = box_around(84.0, 179.5, 500)
    assert east == 180.0 and north == 85.0511 and west < 179.5 and south < 84.0
    pole = box_around(89.9, 10.0, 300)
    assert pole[1] < pole[3] <= 85.0511 and pole[0] < 10.0 < pole[2], "a position past the last tile is moved onto it"
    assert box_around(0.0, 179.9, 5000)[2] == 180.0 and box_around(0.0, -179.9, 5000)[0] == -180.0


# ---- estimate

async def test_an_estimate_is_a_dry_run_that_leaves_the_size_and_the_files_alone(rig: Rig) -> None:
    await rig.service.estimate()
    status = rig.status()
    assert status.estimate is not None and (status.estimate.bytes, status.estimate.tiles, status.estimate.radius_km, status.estimate.maxzoom) == (493_000_000, 41233, 150, 12)
    assert status.estimate.build == "20261020" and status.estimate.box == box_around(60.17, 24.94, 150)
    assert status.state == "none" and status.detail is None
    assert not list(rig.data.glob("*.pmtiles*")), "a dry run makes no file"
    assert "estimating" in rig.states() and rig.states()[-1] == "none"


async def test_the_state_is_estimating_while_it_runs_and_the_steps_are_told(rig: Rig) -> None:
    rig.config = replace(CONFIG, map_source="")
    rig.service = MapFetch(rig.data, lambda: rig.config, FixedClock(), probe=lambda url: url.endswith("20261019.pmtiles"))
    steps: list[tuple[str, str]] = []
    rig.service.changed.connect(lambda: steps.append((rig.service.status().state, rig.service.status().step)))
    remember_stop(rig.service.stop)
    await rig.service.estimate()
    assert steps[0] == ("estimating", "build") and ("estimating", "area") in steps
    assert rig.fake.calls()[0][1] == "https://build.protomaps.com/20261019.pmtiles"
    assert rig.status().estimate is not None and rig.status().estimate.build == "20261019"      # type: ignore[union-attr]


async def test_the_latest_build_is_found_back_to_a_week_and_no_build_is_an_error(rig: Rig) -> None:
    seen: list[str] = []

    def probe(url: str) -> bool:
        seen.append(url)
        return url.endswith("20261015.pmtiles")
    now = FixedClock()()
    assert await latest_build(now, probe) == ("https://build.protomaps.com/20261015.pmtiles", "20261015")
    assert [u[-16:-8] for u in seen] == ["20261021", "20261020", "20261019", "20261018", "20261017", "20261016", "20261015"]
    with pytest.raises(MapError, match="no daily build.*8 days.*connection"):
        await latest_build(now, lambda url: False)


async def test_a_job_with_no_daily_build_fails_with_the_reason_and_the_program_is_not_run(rig: Rig) -> None:
    rig.config = replace(CONFIG, map_source="")
    rig.service = MapFetch(rig.data, lambda: rig.config, FixedClock(), probe=lambda url: False)
    remember_stop(rig.service.stop)
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert status.state == "error" and "no daily build" in status.problem and rig.fake.calls() == []


# ---- no position

async def test_without_a_position_no_job_starts_and_the_reason_says_so(rig: Rig) -> None:
    rig.config = replace(CONFIG, station_lat=None, station_lon=None)
    status = rig.status()
    assert status.box is None and "no position" in status.blocked and status.state == "none"
    for job in JOBS:
        with pytest.raises(MapError, match="no position"):
            rig.service.begin(job)
    with pytest.raises(MapError, match="no position"):
        await rig.service.fetch()
    assert rig.status().state == "none" and rig.status().problem == "" and rig.fake.calls() == []


# ---- the download

async def test_the_world_map_is_made_first_and_then_the_detailed_one(rig: Rig) -> None:
    await rig.service.fetch()
    calls = rig.fake.calls()
    assert [c[2].rsplit("/", 1)[1] for c in calls] == ["basemap-world.pmtiles.part", "basemap.pmtiles.part"]
    assert "--maxzoom=5" in calls[0] and not any(a.startswith("--bbox") for a in calls[0])
    assert "--maxzoom=12" in calls[1] and any(a.startswith("--bbox=") for a in calls[1])
    assert sorted(p.name for p in rig.data.glob("*.pmtiles*")) == ["basemap-world.pmtiles", "basemap.pmtiles"]
    assert json.loads((rig.data / "basemap.json").read_text(encoding="utf-8")) == {"build": "20261020"}
    status = rig.status()
    assert status.state == "ready" and status.estimate is None and status.step == "" and status.percent is None


async def test_the_world_map_is_not_made_again_when_it_is_there(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / WORLD).write_bytes(b"the world")
    await rig.service.fetch()
    assert len(rig.fake.calls()) == 1 and (rig.data / WORLD).read_bytes() == b"the world"


async def test_the_page_is_told_the_steps_and_the_percent_of_each(rig: Rig) -> None:
    await rig.service.fetch()
    working = [s for s in rig.seen if s.state == "downloading"]
    assert [s.step for s in working][0] == "world" and working[-1].step == "area"
    for step in ("world", "area"):
        percents = [s.percent for s in working if s.step == step and s.percent is not None]
        assert percents[0] == 0 and percents[-1] == 100 and percents == sorted(percents) and {0, 25, 50, 75, 100} <= set(percents)
    assert rig.states()[-1] == "ready"


async def test_a_failure_leaves_the_map_that_was_there_and_no_part(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / DETAIL).write_bytes(b"the old map")
    (rig.data / WORLD).write_bytes(b"the old world")
    rig.fake.mode("fail")
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert status.state == "error" and status.problem == 'Failed to extract, Get "https://build.example/20261020.pmtiles": connection refused'
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and (rig.data / WORLD).read_bytes() == b"the old world"
    assert not list(rig.data.glob("*.part")), "the half-made file is removed"


async def test_a_failed_world_map_stops_the_job_before_the_detailed_one(rig: Rig) -> None:
    rig.fake.mode("fail")
    with pytest.raises(ToolError):
        await rig.service.fetch()
    assert len(rig.fake.calls()) == 1 and not list(rig.data.glob("*.pmtiles*"))
    assert rig.status().state == "error" and rig.status().detail is None


async def test_the_next_job_clears_the_error_and_a_stale_part_is_removed(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / "basemap.pmtiles.part").write_bytes(b"left by a crash")
    rig.fake.mode("fail")
    rig.service.begin("estimate")
    await rig.idle()
    assert rig.status().state == "none" and rig.status().problem == "", "a dry run of the fake does not fail"
    rig.service.begin("fetch")
    await rig.idle()
    assert rig.status().state == "error"
    rig.fake.mode("ok")
    rig.service.begin("fetch")
    assert rig.status().problem == "" and rig.status().state == "downloading"
    await rig.idle()
    assert rig.status().state == "ready" and not (rig.data / "basemap.pmtiles.part").exists()


# ---- cancel, one at a time

async def test_a_cancel_ends_the_program_removes_the_part_and_keeps_the_map(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / DETAIL).write_bytes(b"the old map")
    (rig.data / WORLD).write_bytes(b"the world")
    rig.fake.mode("slow")
    rig.service.begin("fetch")
    await until(lambda: rig.status().percent == 10)
    pid = rig.fake.pid()
    assert alive(pid) and rig.service.cancel()
    await rig.idle()
    status = rig.status()
    assert status.state == "ready" and status.problem == "" and status.step == "" and status.percent is None
    assert not alive(pid), "the program was ended"
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and not list(rig.data.glob("*.part"))


async def test_one_job_at_a_time(rig: Rig) -> None:
    rig.fake.mode("slow")
    rig.service.begin("fetch")
    await until(lambda: rig.status().percent == 10)
    assert rig.status().blocked == "a map job is running"
    for job in JOBS:
        with pytest.raises(MapError, match="running already"):
            rig.service.begin(job)
    with pytest.raises(MapError, match="running already"):
        await rig.service.estimate()
    assert rig.service.cancel()
    await rig.idle()
    assert not rig.service.cancel(), "nothing is running to be cancelled"


async def test_stopping_the_service_ends_the_job(rig: Rig) -> None:
    rig.fake.mode("slow")
    rig.service.begin("fetch")
    await until(lambda: rig.status().percent == 10)
    pid = rig.fake.pid()
    await rig.service.stop()
    assert not alive(pid) and rig.status().state == "none"


# ---- the program

async def test_a_missing_program_is_fetched_first_and_the_step_says_so(rig: Rig, tmp_path: Path) -> None:
    (rig.data / "bin" / "pmtiles").unlink()
    asked: list[Path] = []

    async def installer(bin_dir: Path) -> Path:
        asked.append(bin_dir)
        return install_fake(bin_dir).path
    rig.service = MapFetch(rig.data, lambda: rig.config, FixedClock(), installer)
    steps: list[str] = []
    rig.service.changed.connect(lambda: steps.append(rig.service.status().step))
    remember_stop(rig.service.stop)
    await rig.service.estimate()
    assert asked == [rig.data / "bin"] and steps[0] == "tool" and rig.status().estimate is not None


async def test_a_program_that_cannot_be_had_is_the_error_of_the_job(rig: Rig) -> None:
    (rig.data / "bin" / "pmtiles").unlink()

    async def installer(bin_dir: Path) -> Path:
        raise ToolError("could not download https://github.com/x: boom")
    rig.service = MapFetch(rig.data, lambda: rig.config, FixedClock(), installer)
    remember_stop(rig.service.stop)
    rig.service.begin("fetch")
    await rig.idle()
    assert rig.status().state == "error" and rig.status().problem == "could not download https://github.com/x: boom"


async def test_a_program_on_the_path_is_used_before_the_one_in_bin(rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = install_fake(tmp_path / "first")
    monkeypatch.setenv("PATH", str(tmp_path / "first"))
    await rig.service.estimate()
    assert len(first.calls()) == 1 and rig.fake.calls() == []


async def test_a_source_that_names_a_file_is_used_as_it_is(rig: Rig) -> None:
    rig.config = replace(CONFIG, map_source="/maps/planet.pmtiles")
    await rig.service.estimate()
    assert rig.fake.calls()[0][1] == "/maps/planet.pmtiles" and rig.status().estimate is not None and rig.status().estimate.build == ""      # type: ignore[union-attr]
