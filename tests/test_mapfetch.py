"""The base map service (neoaprs/services/mapfetch.py) cutting the made-up planet of tests/support/madepmtiles.py from a range server on the loopback: the states and what the page is told, the box round the position,
no position, the world map first, a file moved into place only when it is whole, the numbers of the dry run, a cancel, one job at a time, the latest daily build, an old pmtiles program left alone."""
import json
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio

import neoaprs.services.mapfetch as mapfetch
from neoaprs.geo import box_around
from neoaprs.mapstate import Job, MapError
from neoaprs.pmtilesarchive import latest_build
from neoaprs.pmtilescut import CutError
from neoaprs.services.mapfetch import DETAIL, FAILED, WORLD, MapFetch
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until_started
from tests.support.madepmtiles import every_tile, planet, tile_id, tiles_of
from tests.support.maprig import MapRig, config_for, data_offset, own_world
from tests.support.rangeserver import RangeServer, range_server

JOBS: tuple[Job, Job] = ("estimate", "fetch")
ZOOMS = 6                                                                  # the deepest zoom of the planet


class Rig(MapRig):
    def __init__(self, data: Path, server: RangeServer) -> None:
        super().__init__(data, server, lambda: self.config)
        self.config = config_for(server)

    def states(self) -> list[str]:
        return [s.state for s in self.seen]

    def hold_tiles(self) -> None:
        """The server gives the directories and holds every answer for tile data."""
        self.server.hold_from = data_offset(planet())


@pytest_asyncio.fixture
async def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path / "data", await range_server(planet()))


def tiles_in(path: Path) -> dict[int, bytes]:
    return every_tile(path.read_bytes())


def expected(box: tuple[float, float, float, float] | None, deepest: int) -> dict[int, bytes]:
    """The tiles a cut of the planet must hold, by the tile numbers of the map, each with the bytes the planet stores for it."""
    stored = every_tile(planet())
    keys = tiles_of(box or (-180.0, -85.0511, 180.0, 85.0511), 0, deepest)
    return {tile_id(*key): stored[tile_id(*key)] for key in keys}


# ---- what is there

async def test_before_anything_is_done_there_is_no_map_and_the_area_follows_the_position(rig: Rig) -> None:
    status = rig.status()
    assert (status.state, status.step, status.percent, status.problem, status.blocked) == ("none", "", None, "", "")
    assert status.detail is None and status.world is None and status.estimate is None
    assert (status.radius_km, status.maxzoom) == (150, 12)
    assert status.box == box_around(60.17, 24.94, 150)


async def test_the_files_in_the_data_folder_are_described_by_their_headers(rig: Rig) -> None:
    await rig.service.fetch()
    status = rig.status()
    assert status.state == "ready" and status.detail is not None and status.world is not None
    assert status.detail.name == DETAIL and status.detail.max_zoom == ZOOMS and status.detail.bbox == pytest.approx(box_around(60.17, 24.94, 150), abs=1e-5)
    assert status.world.name == WORLD and status.world.max_zoom == 5 and status.world.bbox == pytest.approx((-180.0, -85.0511287, 180.0, 85.0511287), abs=1e-6)
    assert status.detail.bytes == (rig.data / DETAIL).stat().st_size and status.detail.build == "20261020"


async def test_a_map_made_by_hand_has_a_header_and_no_build(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / DETAIL).write_bytes(b"not a map")
    status = rig.status()
    assert status.state == "ready" and status.detail is not None and status.detail.bbox is None and status.detail.build == ""


# ---- the box

async def test_the_area_is_the_box_round_the_position_for_the_radius_and_the_zoom_of_the_settings(rig: Rig) -> None:
    rig.config = config_for(rig.server, station_lat=64.5, station_lon=26.0, map_radius_km=40, map_maxzoom=4)
    await rig.service.fetch()
    box = box_around(64.5, 26.0, 40)
    west, south, east, north = box
    assert south < 64.5 < north and west < 26.0 < east
    assert (east - west) > (north - south), "a degree of longitude is shorter this far north"
    assert tiles_in(rig.data / DETAIL) == expected(box, 4)
    assert rig.status().detail is not None and rig.status().detail.max_zoom == 4     # type: ignore[union-attr]


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
    box = box_around(60.17, 24.94, 150)
    assert status.estimate is not None and (status.estimate.tiles, status.estimate.radius_km, status.estimate.maxzoom) == (len(tiles_of(box, 0, ZOOMS)), 150, 12)
    assert status.estimate.build == "20261020" and status.estimate.box == box and status.estimate.bytes > 0
    assert status.state == "none" and status.detail is None
    assert not list(rig.data.glob("*.pmtiles*")), "a dry run makes no file"
    assert rig.server.asked and all(last < data_offset(planet()) for _, last in rig.server.asked), "no tile data is fetched"
    assert "estimating" in rig.states() and rig.states()[-1] == "none"


async def test_the_numbers_of_a_dry_run_are_those_of_the_map_the_download_makes(rig: Rig) -> None:
    await rig.service.estimate()
    estimate = rig.status().estimate
    assert estimate is not None
    await rig.service.fetch()
    detail = rig.status().detail
    assert detail is not None and detail.bytes == estimate.bytes and len(tiles_in(rig.data / DETAIL)) == estimate.tiles
    assert rig.status().estimate is None, "the estimate is told away once the map is made"


async def test_the_state_is_estimating_while_it_runs_and_the_steps_are_told(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no source in the settings the latest daily build is looked for (the probe of the test knows the day before); the address it gives is the server of the test."""
    asked: list[str] = []

    async def latest(now: object, probe: object) -> tuple[str, str]:
        asked.append("probed")
        return rig.server.url, "20261019"
    monkeypatch.setattr(mapfetch, "latest_build", latest)
    rig.config = replace(ON_AIR, map_source="")
    steps: list[tuple[str, str]] = []
    rig.service.changed.connect(lambda: steps.append((rig.service.status().state, rig.service.status().step)))
    await rig.service.estimate()
    assert steps[0] == ("estimating", "build") and ("estimating", "area") in steps and asked == ["probed"]
    assert rig.status().estimate is not None and rig.status().estimate.build == "20261019"      # type: ignore[union-attr]


async def test_the_latest_build_is_found_back_to_a_week_and_no_build_is_an_error() -> None:
    seen: list[str] = []

    def probe(url: str) -> bool:
        seen.append(url)
        return url.endswith("20261015.pmtiles")
    now = FixedClock()()
    assert await latest_build(now, probe) == ("https://build.protomaps.com/20261015.pmtiles", "20261015")
    assert [u[-16:-8] for u in seen] == ["20261021", "20261020", "20261019", "20261018", "20261017", "20261016", "20261015"]
    with pytest.raises(MapError, match="no daily build.*8 days.*connection"):
        await latest_build(now, lambda url: False)


async def test_a_job_with_no_daily_build_fails_with_the_reason_and_nothing_is_asked_of_the_server(rig: Rig) -> None:
    rig.config = replace(ON_AIR, map_source="")
    rig.service = MapFetch(rig.data, lambda: rig.config, FixedClock(), probe=lambda url: False, world=own_world)
    remember_stop(rig.service.stop)
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert status.state == "error" and "no daily build" in status.problem and rig.server.asked == []


# ---- no position

async def test_without_a_position_no_job_starts_and_the_reason_says_so(rig: Rig) -> None:
    rig.config = replace(rig.config, station_lat=None, station_lon=None)
    status = rig.status()
    assert status.box is None and "no position" in status.blocked and status.state == "none"
    for job in JOBS:
        with pytest.raises(MapError, match="no position"):
            rig.service.begin(job)
    with pytest.raises(MapError, match="no position"):
        await rig.service.fetch()
    assert rig.status().state == "none" and rig.status().problem == "" and rig.server.asked == []


# ---- the download

async def test_the_world_map_is_made_first_and_then_the_detailed_one(rig: Rig) -> None:
    await rig.service.fetch()
    assert sorted(p.name for p in rig.data.glob("*.pmtiles*")) == ["basemap-world.pmtiles", "basemap.pmtiles"]
    assert tiles_in(rig.data / WORLD) == expected(None, 5), "every tile of the world to zoom 5, as the planet has them"
    assert tiles_in(rig.data / DETAIL) == expected(box_around(60.17, 24.94, 150), ZOOMS)
    assert [s.step for s in rig.seen if s.state == "downloading"][0] == "world" and rig.seen[-2].step == "area"
    assert json.loads((rig.data / "basemap.json").read_text(encoding="utf-8")) == {"build": "20261020"}
    status = rig.status()
    assert status.state == "ready" and status.estimate is None and status.step == "" and status.percent is None


async def test_the_world_map_is_not_made_again_when_it_is_there(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / WORLD).write_bytes(b"the world")
    await rig.service.fetch()
    assert (rig.data / WORLD).read_bytes() == b"the world" and "world" not in {s.step for s in rig.seen}
    assert (rig.data / DETAIL).is_file()


async def test_the_page_is_told_the_steps_and_the_percent_of_each(rig: Rig) -> None:
    await rig.service.fetch()
    working = [s for s in rig.seen if s.state == "downloading"]
    assert [s.step for s in working][0] == "world" and working[-1].step == "area"
    for step, name in (("world", WORLD), ("area", DETAIL)):
        percents = [s.percent for s in working if s.step == step and s.percent is not None]
        assert percents[-1] == 100 and percents == sorted(percents)
        sizes = [s.downloaded for s in working if s.step == step and s.downloaded is not None]
        assert sizes == sorted(sizes) and sizes[-1] == (rig.data / name).stat().st_size, "the size of what has come only grows, to the size of the map"
    assert rig.states()[-1] == "ready"


async def test_a_failure_leaves_the_map_that_was_there_and_no_part(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / DETAIL).write_bytes(b"the old map")
    (rig.data / WORLD).write_bytes(b"the old world")
    rig.server.mode = "missing"
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert status.state == "error" and status.problem == "the map server answered 404 Not Found"
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and (rig.data / WORLD).read_bytes() == b"the old world"
    assert not list(rig.data.glob("*.part")), "the half-made file is removed"


async def test_the_error_text_names_no_address_and_no_folder(rig: Rig) -> None:
    for mode in ("missing", "wrong", "whole"):
        rig.server.mode = mode
        rig.service.begin("estimate")
        await rig.idle()
        problem = rig.status().problem
        assert rig.status().state == "error" and problem and "127.0.0.1" not in problem and str(rig.data) not in problem, problem


async def test_a_failed_world_map_stops_the_job_before_the_detailed_one(rig: Rig) -> None:
    rig.server.mode = "missing"
    with pytest.raises(CutError):
        await rig.service.fetch()
    assert not list(rig.data.glob("*.pmtiles*"))
    assert rig.status().state == "error" and rig.status().detail is None


async def test_the_next_job_clears_the_error_and_a_stale_part_is_removed(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / "basemap.pmtiles.part").write_bytes(b"left by a crash")
    rig.service.begin("estimate")
    await rig.idle()
    assert rig.status().state == "none" and rig.status().problem == ""
    rig.server.mode = "missing"
    rig.service.begin("fetch")
    await rig.idle()
    assert rig.status().state == "error"
    rig.server.mode = "ranges"
    rig.service.begin("fetch")
    assert rig.status().problem == "" and rig.status().state == "downloading"
    await rig.idle()
    assert rig.status().state == "ready" and not (rig.data / "basemap.pmtiles.part").exists()


# ---- cancel, one at a time

async def test_a_cancel_ends_the_cut_removes_the_part_and_keeps_the_map(rig: Rig) -> None:
    rig.data.mkdir(exist_ok=True)
    (rig.data / DETAIL).write_bytes(b"the old map")
    (rig.data / WORLD).write_bytes(b"the world")
    rig.hold_tiles()
    rig.service.begin("fetch")
    await until_started(lambda: rig.server.holding > 0)
    assert (rig.data / "basemap.pmtiles.part").exists() and rig.service.cancel()
    await rig.idle()
    status = rig.status()
    assert status.state == "ready" and status.problem == "" and status.step == "" and status.percent is None
    await until_started(lambda: rig.server.holding == 0)                  # (the connection that waited for the server was shut)
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and not list(rig.data.glob("*.part"))


async def test_a_part_file_that_cannot_be_deleted_does_not_keep_the_job_busy(rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    real, deleted = Path.unlink, []

    def held(path: Path, missing_ok: bool = False) -> None:
        if path.name.endswith(".part") and deleted:                          # (the clean-up after the job, not the one before it)
            raise PermissionError("[WinError 32] in use by another process")
        if path.name.endswith(".part"):
            deleted.append(path)
        real(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", held)
    rig.server.mode = "missing"
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert not rig.service.busy and status.state == "error" and status.blocked == "" and rig.seen[-1].state == "error"
    assert "could not be deleted" in caplog.text
    monkeypatch.setattr(Path, "unlink", real)
    rig.server.mode = "ranges"
    await rig.service.fetch()                                                # (a new job is accepted)
    assert rig.status().state == "ready"


async def test_one_job_at_a_time(rig: Rig) -> None:
    rig.hold_tiles()
    rig.service.begin("fetch")
    await until_started(lambda: rig.server.holding > 0)
    assert rig.status().blocked == "a map job is running"
    for job in JOBS:
        with pytest.raises(MapError, match="running already"):
            rig.service.begin(job)
    with pytest.raises(MapError, match="running already"):
        await rig.service.estimate()
    assert rig.service.cancel()
    await rig.idle()
    assert not rig.service.cancel(), "nothing is running to be cancelled"


async def test_stopping_the_service_ends_the_cut_and_the_thread_of_it(rig: Rig) -> None:
    rig.hold_tiles()
    rig.service.begin("fetch")
    await until_started(lambda: rig.server.holding > 0)
    await rig.service.stop()
    assert rig.status().state == "none" and not list(rig.data.glob("*.part"))
    await until_started(lambda: rig.server.holding == 0)


# ---- the sources and the old program

async def test_a_source_that_names_a_file_is_cut_from_the_file(rig: Rig, tmp_path: Path) -> None:
    (tmp_path / "planet.pmtiles").write_bytes(planet())
    rig.config = replace(rig.config, map_source=str(tmp_path / "planet.pmtiles"))
    await rig.service.estimate()
    assert rig.status().estimate is not None and rig.status().estimate.build == "" and rig.server.asked == []      # type: ignore[union-attr]
    await rig.service.fetch()
    assert tiles_in(rig.data / DETAIL) == expected(box_around(60.17, 24.94, 150), ZOOMS)


async def test_a_source_that_is_not_a_map_is_told_in_words(rig: Rig, tmp_path: Path) -> None:
    (tmp_path / "text.pmtiles").write_bytes(b"not an archive" * 20)
    rig.config = replace(rig.config, map_source=str(tmp_path / "text.pmtiles"))
    rig.service.begin("estimate")
    await rig.idle()
    assert rig.status().state == "error" and rig.status().problem == "the map source cannot be cut: the file is not a PMTiles archive"


async def test_an_old_pmtiles_program_in_the_data_folder_is_left_alone_and_nothing_is_said(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    program = rig.data / "bin" / "pmtiles"
    program.parent.mkdir(parents=True)
    program.write_bytes(b"#!/bin/sh\nexit 1\n")
    program.chmod(0o755)
    await rig.service.fetch()
    assert rig.status().state == "ready" and program.read_bytes() == b"#!/bin/sh\nexit 1\n" and sorted(p.name for p in program.parent.iterdir()) == ["pmtiles"]
    assert "pmtiles program" not in caplog.text and not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]


async def test_a_failure_of_the_daemons_own_is_told_in_words_and_the_detail_goes_to_the_log(rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """The page never shows a Python exception name; a file that could not be written says what the system said."""
    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("an invariant of the cut")

    async def no_room(*args: object, **kwargs: object) -> None:
        raise OSError(28, "No space left on device")
    for cut, problem in ((broken, FAILED), (no_room, f"{FAILED}: No space left on device")):
        monkeypatch.setattr(mapfetch, "extract", cut)
        rig.service.begin("fetch")
        await rig.idle()
        assert rig.status().state == "error" and rig.status().problem == problem
    assert "an invariant of the cut" in caplog.text and "RuntimeError" not in rig.status().problem


