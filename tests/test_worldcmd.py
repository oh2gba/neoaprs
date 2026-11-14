"""`neoaprs map --world` (neoaprs/cli/worldcmd.py, reached through neoaprs/cli/mapcmd.py): the world map that ships with the program, cut from the made-up planet of tests/support/madepmtiles.py (a range server on the
loopback plays build.protomaps.com, a file plays a source of the operator's) into a folder of the test. What it writes, the size it refuses before a tile is fetched, and the words of a failure. Nothing is written to the
package's own `maps/`."""
import asyncio
import json
from pathlib import Path

import pytest
import pytest_asyncio

from neoaprs.cli import mapcmd, worldcmd
from neoaprs.worldmap import MAPS_DIR, SHIPPED_ZOOM, WORLD_FILE
from tests.support.madepmtiles import every_tile, planet, tile_id
from tests.support.maprig import data_offset
from tests.support.rangeserver import RangeServer, range_server


class Cut:
    """The command's folder and the server of the daily builds."""

    def __init__(self, tmp_path: Path, server: RangeServer, monkeypatch: pytest.MonkeyPatch) -> None:
        self.out, self.server = tmp_path / "out", server
        monkeypatch.setattr(worldcmd, "BUILDS", f"http://127.0.0.1:{server.port}")

    async def run(self, *args: str) -> int:
        return await asyncio.to_thread(worldcmd.main, ["--out", str(self.out), *args])


@pytest_asyncio.fixture
async def cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Cut:
    return Cut(tmp_path, await range_server(planet()), monkeypatch)


async def test_the_world_is_cut_from_a_daily_build_into_the_folder_with_the_build_beside_it(cut: Cut, capsys: pytest.CaptureFixture[str]) -> None:
    assert await cut.run("--build", "20261020") == 0
    final = cut.out / WORLD_FILE
    assert final.is_file() and json.loads(final.with_suffix(".json").read_text()) == {"build": "20261020"}
    assert not list(cut.out.glob("*.part")), "(the part is gone whole or not)"
    stored = every_tile(planet())
    assert every_tile(final.read_bytes()) == {tile_id(z, x, y): stored[tile_id(z, x, y)] for z in range(SHIPPED_ZOOM + 1) for x in range(1 << z) for y in range(1 << z)}, "the whole world, to the shipped zoom"
    captured = capsys.readouterr()
    assert "fetching 100%" in captured.out and f"{final}:" in captured.out and f"zoom 0 to {SHIPPED_ZOOM}" in captured.out


async def test_a_source_of_the_operators_is_cut_from_as_it_is_and_the_zoom_can_be_lower(cut: Cut, tmp_path: Path) -> None:
    (tmp_path / "world.pmtiles").write_bytes(planet())
    assert await cut.run("--source", str(tmp_path / "world.pmtiles"), "--zoom", "3") == 0
    assert len(every_tile((cut.out / WORLD_FILE).read_bytes())) == 85 and cut.server.asked == []
    assert json.loads((cut.out / "basemap-world.json").read_text()) == {"build": ""}


async def test_without_a_build_or_a_source_the_latest_daily_build_is_cut_from(cut: Cut, monkeypatch: pytest.MonkeyPatch) -> None:
    async def latest(now: object) -> tuple[str, str]:
        return cut.server.url, "20261025"

    monkeypatch.setattr(worldcmd, "latest_build", latest)
    assert await cut.run() == 0
    assert cut.server.cuts == 2, "one look at the sizes, one cut"
    assert json.loads((cut.out / "basemap-world.json").read_text()) == {"build": "20261025"}


async def test_a_world_over_the_size_the_program_may_carry_is_refused_before_a_tile_is_fetched(cut: Cut, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(worldcmd, "MAX_BYTES", 100)
    assert await cut.run("--build", "20261020") == 1
    assert "use a lower --zoom" in capsys.readouterr().err
    assert all(last < data_offset(planet()) for _, last in cut.server.asked), "no tile data was fetched"
    assert not (cut.out / WORLD_FILE).exists() and not list(cut.out.glob("*.part")) and not (cut.out / "basemap-world.json").exists()


async def test_a_world_that_is_made_again_replaces_the_one_before_it(cut: Cut) -> None:
    cut.out.mkdir()
    (cut.out / WORLD_FILE).write_bytes(b"old")
    (cut.out / f"{WORLD_FILE}.part").write_bytes(b"left over from a run that was killed")
    assert await cut.run("--build", "20261020") == 0
    assert (cut.out / WORLD_FILE).read_bytes().startswith(b"PMTiles") and not list(cut.out.glob("*.part"))


async def test_a_server_that_fails_is_said_in_words_and_nothing_is_left(cut: Cut, capsys: pytest.CaptureFixture[str]) -> None:
    cut.server.mode = "missing"
    assert await cut.run("--build", "20261020") == 1
    assert "worldmap: the map server answered 404 Not Found" in capsys.readouterr().err and not (cut.out / WORLD_FILE).exists()


def test_the_defaults_are_the_package_maps_folder_and_the_shipped_zoom() -> None:
    args = worldcmd.parse([])
    assert Path(args.out).name == MAPS_DIR and args.zoom == SHIPPED_ZOOM and args.build is None and args.source is None


def test_a_build_and_a_source_together_are_refused() -> None:
    with pytest.raises(SystemExit):
        worldcmd.parse(["--build", "20261020", "--source", "x.pmtiles"])


def test_the_map_command_hands_world_to_this_command_and_the_rest_to_the_base_map(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(worldcmd, "main", lambda argv: seen.append(argv) or 0)
    assert mapcmd.main(["--world", "--build", "20261020"]) == 0 and seen == [["--build", "20261020"]]
    monkeypatch.setattr(mapcmd, "map_main", lambda argv, prog: seen.append([prog, *argv]) or 0)
    assert mapcmd.main(["--dry-run"]) == 0 and seen[-1] == ["neoaprs map", "--dry-run"]
