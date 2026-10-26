"""`neoaprs map --world` (neoaprs/cli/worldcmd.py, reached through neoaprs/cli/mapcmd.py): the world map that ships with the program, cut with the pinned pmtiles tool (a stand-in, tests/support/fakepmtiles.py) into a folder of the
test. What it writes, the file it refuses (too big, no PMTiles file), the tool that is not the pinned one, and the words of a failure. Nothing is fetched and nothing is written to the package's own `maps/`."""
import json
from pathlib import Path

import pytest

from neoaprs.cli import mapcmd, worldcmd
from neoaprs.worldmap import MAPS_DIR, SHIPPED_ZOOM, WORLD_FILE
from tests.support.fakepmtiles import FakePmtiles, install_fake

class Cut:
    """The command's folders and its tool."""

    def __init__(self, tmp_path: Path) -> None:
        self.data, self.out = tmp_path / "data", tmp_path / "out"
        self.fake: FakePmtiles = install_fake(self.data / "bin")

    def run(self, *args: str) -> int:
        return worldcmd.main(["--data", str(self.data), "--out", str(self.out), *args])

@pytest.fixture
def cut(tmp_path: Path) -> Cut:
    return Cut(tmp_path)

def test_the_world_is_cut_from_a_daily_build_into_the_folder_with_the_build_beside_it(cut: Cut, capsys: pytest.CaptureFixture[str]) -> None:
    assert cut.run("--build", "20261020") == 0
    final = cut.out / WORLD_FILE
    assert final.is_file() and json.loads(final.with_suffix(".json").read_text()) == {"build": "20261020"}
    assert not list(cut.out.glob("*.part")), "(the part is gone whole or not)"
    [call] = cut.fake.calls()
    assert call[0] == "extract" and call[1].endswith("/20261020.pmtiles") and f"--maxzoom={SHIPPED_ZOOM}" in call and "--bbox" not in " ".join(call), "the whole world, to the shipped zoom"
    captured = capsys.readouterr()
    assert "fetching 75%" in captured.out and f"{final}:" in captured.out and f"zoom 0 to {SHIPPED_ZOOM}" in captured.out

def test_a_source_of_the_operators_is_cut_from_as_it_is_and_the_zoom_can_be_lower(cut: Cut) -> None:
    assert cut.run("--source", "/somewhere/world.pmtiles", "--zoom", "3") == 0
    [call] = cut.fake.calls()
    assert call[1] == "/somewhere/world.pmtiles" and "--maxzoom=3" in call
    assert json.loads((cut.out / "basemap-world.json").read_text()) == {"build": ""}

def test_without_a_build_or_a_source_the_latest_daily_build_is_cut_from(cut: Cut, monkeypatch: pytest.MonkeyPatch) -> None:
    async def latest(now: object) -> tuple[str, str]:
        return "https://builds.example/20261025.pmtiles", "20261025"

    monkeypatch.setattr(worldcmd, "latest_build", latest)
    assert cut.run() == 0
    assert cut.fake.calls()[0][1] == "https://builds.example/20261025.pmtiles"
    assert json.loads((cut.out / "basemap-world.json").read_text()) == {"build": "20261025"}

def test_a_file_over_the_size_the_program_may_carry_is_refused_and_nothing_is_left(cut: Cut, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(worldcmd, "MAX_BYTES", 100)
    assert cut.run("--build", "20261020") == 1
    assert "use a lower --zoom" in capsys.readouterr().err
    assert not (cut.out / WORLD_FILE).exists() and not list(cut.out.glob("*.part")) and not (cut.out / "basemap-world.json").exists()

def test_a_file_that_is_no_pmtiles_archive_is_refused(cut: Cut, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(worldcmd, "read_header", lambda path: None)
    assert cut.run("--build", "20261020") == 1
    assert f"{WORLD_FILE}.part is not a PMTiles file" in capsys.readouterr().err
    assert not (cut.out / WORLD_FILE).exists()

def test_a_world_that_is_made_again_replaces_the_one_before_it(cut: Cut) -> None:
    cut.out.mkdir()
    (cut.out / WORLD_FILE).write_bytes(b"old")
    (cut.out / f"{WORLD_FILE}.part").write_bytes(b"left over from a run that was killed")
    assert cut.run("--build", "20261020") == 0
    assert (cut.out / WORLD_FILE).read_bytes().startswith(b"PMTiles")

def test_a_tool_that_fails_is_said_in_its_own_words(cut: Cut, capsys: pytest.CaptureFixture[str]) -> None:
    cut.fake.mode("fail")
    assert cut.run("--build", "20261020") == 1
    assert "worldmap: " in capsys.readouterr().err and not (cut.out / WORLD_FILE).exists()

def test_a_tool_that_is_not_the_pinned_version_is_not_used(cut: Cut, capsys: pytest.CaptureFixture[str]) -> None:
    cut.fake.mode("wrongversion")
    assert cut.run("--build", "20261020") == 1
    assert "is not go-pmtiles" in capsys.readouterr().err and cut.fake.calls() == []

def test_the_defaults_are_the_package_maps_folder_and_the_shipped_zoom() -> None:
    args = worldcmd.parse([])
    assert Path(args.out).name == MAPS_DIR and args.zoom == SHIPPED_ZOOM and args.build is None and args.source is None

def test_a_build_and_a_source_together_are_refused() -> None:
    with pytest.raises(SystemExit):
        worldcmd.parse(["--build", "20261020", "--source", "x.pmtiles"])

def test_the_map_command_hands_world_to_this_command_and_the_rest_to_the_base_map(cut: Cut, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(worldcmd, "main", lambda argv: seen.append(argv) or 0)
    assert mapcmd.main(["--world", "--build", "20261020"]) == 0 and seen == [["--build", "20261020"]]
    monkeypatch.setattr(mapcmd, "map_main", lambda argv, prog: seen.append([prog, *argv]) or 0)
    assert mapcmd.main(["--dry-run"]) == 0 and seen[-1] == ["neoaprs map", "--dry-run"]
