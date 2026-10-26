"""The world map that ships with the program (neoaprs/worldmap.py): where it is on each kind of install (a clone, a wheel, the Windows app's frozen folder, an AppImage, a .deb), that a file that is no PMTiles archive is not taken,
that the data folder's own world map wins, what the real package holds, and that the daemon serves it when the data folder has none."""
import re
import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.pmtilestool import read_header
from neoaprs.worldmap import MAPS_DIR, SHIPPED_ZOOM, WORLD_FILE, search_folders, shipped_world, usable, world_file
from tests.conftest import ROOT
from tests.support.env import Env

HEADER = b"PMTiles" + bytes([3]) + bytes(92) + struct.pack("<BB4i", 0, SHIPPED_ZOOM, -1800000000, -850000000, 1800000000, 850000000) + bytes(9)


def put(folder: Path, content: bytes = HEADER + b"tiles") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / WORLD_FILE).write_bytes(content)
    return folder / WORLD_FILE


# ---- where it is, on each install

@pytest.mark.parametrize("layout", [
    "clone/neoaprs",                                                                    # a clone: the package is a folder of it (and the venv has it editable)
    "venv/lib/python3.13/site-packages/neoaprs",                                         # a wheel installed (uv tool install, pip, the install script)
    "venv/Lib/site-packages/neoaprs",                                                    # ... on Windows
    "mount/usr/lib/python3.13/site-packages/neoaprs",                                    # an AppImage: the wheel in the image's own Python
    "opt/neoaprs/lib/python3.13/site-packages/neoaprs",                                  # a .deb: the wheel in /opt/neoaprs
])
def test_the_world_map_is_in_the_package_beside_the_code_on_every_kind_of_install(layout: str, tmp_path: Path) -> None:
    package = tmp_path / layout
    shipped = put(package / MAPS_DIR)
    assert search_folders(code_dir=package) == [package / MAPS_DIR]
    assert shipped_world(search_folders(code_dir=package)) == shipped


def test_the_frozen_windows_app_has_it_in_the_internal_folder_where_pyinstaller_puts_the_packages_files(tmp_path: Path) -> None:
    app = tmp_path / "AppData" / "Local" / "Programs" / "NeoAPRS"
    internal = app / "_internal"
    shipped = put(internal / "neoaprs" / MAPS_DIR)
    # the code is in the bundle's archive, so a module's own folder has no maps/ ...
    folders = search_folders(code_dir=internal / "neoaprs" / "nowhere", frozen=True, bundle=str(internal), executable=str(app / "neoaprs.exe"))
    assert shipped_world(folders) == shipped
    # ... and with no bundle folder told (a PyInstaller that does not set it), the one beside the executable is found
    folders = search_folders(code_dir=tmp_path / "nowhere", frozen=True, bundle=None, executable=str(app / "neoaprsw.exe"))
    assert internal / "neoaprs" / MAPS_DIR in folders and shipped_world(folders) == shipped


def test_a_frozen_program_looks_where_python_says_it_is_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = tmp_path / "NeoAPRS"
    shipped = put(app / "_internal" / "neoaprs" / MAPS_DIR)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(app / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "neoaprs-app.exe"))
    assert shipped.parent in search_folders()
    monkeypatch.delattr(sys, "frozen")
    assert shipped.parent not in search_folders(), "a program run from Python does not look in a bundle"


def test_a_program_that_is_not_frozen_looks_in_its_own_package_only(tmp_path: Path) -> None:
    assert search_folders(code_dir=tmp_path / "neoaprs", frozen=False) == [tmp_path / "neoaprs" / MAPS_DIR]


# ---- which file counts

def test_a_file_that_is_not_a_pmtiles_archive_is_not_taken_and_the_next_folder_is_looked_in(tmp_path: Path) -> None:
    broken = put(tmp_path / "a", b"<html>")
    good = put(tmp_path / "b")
    assert not usable(broken) and usable(good)
    assert shipped_world([tmp_path / "a", tmp_path / "b"]) == good
    assert shipped_world([tmp_path / "a"]) is None and shipped_world([]) is None and shipped_world([tmp_path / "gone"]) is None
    assert not usable(put(tmp_path / "c", HEADER[:60])), "cut short"


def test_the_data_folders_own_world_map_is_the_one_when_it_is_good_else_the_shipped_one(tmp_path: Path) -> None:
    shipped = put(tmp_path / "package" / MAPS_DIR)
    folders = [shipped.parent]
    data = tmp_path / "data"
    assert world_file(data, folders) == shipped, "none in the data folder"
    own = put(data)
    assert world_file(data, folders) == own, "the data folder's own, which the daemon made to zoom 5"
    own.write_bytes(b"half")
    assert world_file(data, folders) == shipped, "a broken one of its own is not drawn: the shipped one is"
    assert world_file(data, []) is None, "and with neither there is no world map"


# ---- the package

def test_the_package_ships_a_small_world_map_to_zoom_4_with_its_build_beside_it() -> None:
    path = ROOT / "neoaprs" / MAPS_DIR / WORLD_FILE
    assert shipped_world() == path, "the program finds its own world map"
    header = read_header(path)
    assert header is not None and (header.min_zoom, header.max_zoom) == (0, SHIPPED_ZOOM) and header.bbox[0] == -180.0 and header.bbox[2] == 180.0
    assert path.stat().st_size <= 8_000_000, "the program carries it in every package"
    assert re.fullmatch(r'\{"build": "\d{8}"\}\n?', path.with_suffix(".json").read_text(encoding="utf-8"))


def test_the_windows_app_is_built_with_every_data_file_of_the_package_and_the_map_is_not_left_out() -> None:
    spec = (ROOT / "packaging" / "windows" / "neoaprs.spec").read_text(encoding="utf-8")
    excludes = re.search(r'collect_data_files\("neoaprs", excludes=\[([^\]]*)\]', spec)
    assert excludes is not None and "pmtiles" not in excludes.group(1) and "maps" not in excludes.group(1) and "json" not in excludes.group(1)


def test_the_release_workflow_looks_for_the_world_map_in_the_frozen_app_and_in_the_installed_one_and_the_smoke_test_asks_for_it() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "test -f dist/NeoAPRS/_internal/neoaprs/maps/basemap-world.pmtiles" in workflow
    assert "'_internal\\neoaprs\\maps\\basemap-world.pmtiles'" in workflow
    assert "check_the_world_map(base)" in (ROOT / "scripts" / "smoke.py").read_text(encoding="utf-8")


# ---- served by the daemon

@pytest.fixture
def shipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = put(tmp_path / "package" / MAPS_DIR, HEADER + b"shipped")
    monkeypatch.setattr("neoaprs.worldmap.search_folders", lambda *args, **kwargs: [path.parent])
    return path


async def test_the_daemon_serves_the_world_map_that_ships_when_the_data_folder_has_none(tmp_path: Path, shipped: Path) -> None:
    e = Env(tmp_path, web=True, radio=False)
    await e.start(connected=False)
    whole = await e.fetch("/basemap-world.pmtiles")
    assert whole.code == 200 and whole.body == shipped.read_bytes()
    part = await e.fetch("/basemap-world.pmtiles?v=1", headers={"Range": "bytes=0-7"})
    assert part.code == 206 and part.body == b"PMTiles\x03"
    assert (await e.fetch("/basemap-world.pmtiles", method="HEAD")).code == 200
    assert (await e.fetch("/basemap.pmtiles")).code == 404, "the detailed map is the data folder's and nobody else's"


async def test_the_daemon_serves_the_data_folders_own_world_map_when_it_has_one(tmp_path: Path, shipped: Path) -> None:
    e = Env(tmp_path, web=True, radio=False)
    own = put(tmp_path, HEADER + b"made by the daemon, zoom five")
    await e.start(connected=False)
    assert (await e.fetch("/basemap-world.pmtiles")).body == own.read_bytes()
    own.write_bytes(b"half a file")
    assert (await e.fetch("/basemap-world.pmtiles")).body == shipped.read_bytes(), "a broken file of its own is not served"


async def test_with_no_world_map_at_all_the_page_is_told_so_by_a_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.worldmap.search_folders", lambda *args, **kwargs: [])
    e = Env(tmp_path, web=True, radio=False)
    await e.start(connected=False)
    assert (await e.fetch("/basemap-world.pmtiles")).code == 404
    page = await e.ws()
    value = (await page.expect("state", "map"))["value"]
    assert value["world"] is None and value["detail"] is None


async def test_the_page_is_told_the_world_map_that_ships_is_there_from_the_start(tmp_path: Path, shipped: Path) -> None:
    e = Env(tmp_path, web=True, radio=False, operator=False)
    await e.start(connected=False)
    page = await e.ws()
    value = (await page.expect("state", "map"))["value"]
    assert value["state"] == "none" and value["world"]["name"] == WORLD_FILE and value["world"]["max_zoom"] == SHIPPED_ZOOM and value["detail"] is None and value["later"] is False
    assert replace(e.ctl.config).station_position is None
