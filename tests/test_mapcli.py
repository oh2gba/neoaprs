"""The command line of the base map (`python -m neoaprs.services.mapfetch`, `scripts/fetch-basemap`) as a process, with the fake pmtiles program first on the PATH: the same jobs as the page's buttons, the flags over
the settings of the data folder, the settings read from its database, and the way it fails."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs.config import Config
from tests.conftest import ROOT
from tests.support.fakepmtiles import FakePmtiles, install_fake
from tests.support.storedb import store_at

SOURCE = "https://build.example/20261020.pmtiles"


@pytest.fixture
def fake(tmp_path: Path) -> FakePmtiles:
    return install_fake(tmp_path / "tools")


def mapfetch(tmp_path: Path, fake: FakePmtiles, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    env["PATH"] = str(fake.path.parent)
    return subprocess.run([sys.executable, "-m", "neoaprs.services.mapfetch", "--data", str(tmp_path / "data"), "--source", SOURCE, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_a_dry_run_says_the_size_for_the_flags_and_makes_no_file(tmp_path: Path, fake: FakePmtiles) -> None:
    done = mapfetch(tmp_path, fake, "--lat", "60.17", "--lon", "24.94", "--radius", "40", "--maxzoom", "14", "--dry-run")
    assert done.returncode == 0, done.stderr
    assert "493 MB for 40 km round us to zoom 14 (41233 tiles)" in done.stdout
    assert not list((tmp_path / "data").glob("*.pmtiles*"))
    assert "--maxzoom=14" in fake.calls()[0] and "--dry-run" in fake.calls()[0]


def test_a_download_makes_the_area_only_because_the_world_ships_with_the_program_and_says_how_far_it_is(tmp_path: Path, fake: FakePmtiles) -> None:
    fake.mode("linger")
    done = mapfetch(tmp_path, fake, "--lat", "60.17", "--lon", "24.94")
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in (tmp_path / "data").glob("*.pmtiles*")) == ["basemap.pmtiles"]
    assert done.stdout.strip().splitlines()[-1].startswith("basemap.pmtiles: ")
    assert "area: 75%" in done.stdout and "world" not in done.stdout


async def test_the_position_and_the_map_settings_are_read_from_the_database_of_the_data_folder(tmp_path: Path, fake: FakePmtiles) -> None:
    (tmp_path / "data").mkdir()
    store = await store_at(tmp_path / "data" / "neoaprs.sqlite")
    await store.put_settings(Config.checked(Config(), {"station/lat": "64.5", "station/lon": "26.0", "map/radius_km": "30", "map/maxzoom": "10"}).to_data())
    done = await asyncio.to_thread(mapfetch, tmp_path, fake, "--dry-run")
    assert done.returncode == 0, done.stderr
    assert "for 30 km round us to zoom 10" in done.stdout


def test_no_position_is_said_with_exit_1_and_nothing_is_run(tmp_path: Path, fake: FakePmtiles) -> None:
    done = mapfetch(tmp_path, fake, "--dry-run")
    assert done.returncode == 1 and "no position" in done.stderr and fake.calls() == []


def test_a_wrong_flag_is_refused_with_the_key_and_exit_2(tmp_path: Path, fake: FakePmtiles) -> None:
    done = mapfetch(tmp_path, fake, "--lat", "60", "--lon", "24", "--radius", "5000", "--dry-run")
    assert done.returncode == 2 and "map/radius_km" in done.stderr and fake.calls() == []


def test_a_program_that_fails_is_said_with_exit_1(tmp_path: Path, fake: FakePmtiles) -> None:
    fake.mode("fail")
    done = mapfetch(tmp_path, fake, "--lat", "60", "--lon", "24")
    assert done.returncode == 1 and "connection refused" in done.stderr
    assert not list((tmp_path / "data").glob("*.pmtiles*"))
