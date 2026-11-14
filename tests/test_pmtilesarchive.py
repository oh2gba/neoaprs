"""The PMTiles archives of the base map outside the format (neoaprs/pmtilesarchive.py): the zooms and the box read from a header, a file moved into place (a target that Windows holds open is tried again), and the
question whether a daily build is there, asked of a range server on the loopback."""
import asyncio
import os
from pathlib import Path

import pytest

from neoaprs import pmtilesarchive
from neoaprs.pmtilesarchive import read_header, replace_file, url_exists
from tests.support.madepmtiles import archive, planet
from tests.support.rangeserver import range_server


def test_the_zooms_and_the_box_are_read_from_the_header_of_an_archive(tmp_path: Path) -> None:
    assert read_header(tmp_path / "none.pmtiles") is None
    (tmp_path / "text").write_text("not an archive")
    assert read_header(tmp_path / "text") is None
    (tmp_path / "v2").write_bytes(b"PMTiles" + bytes([2]) + bytes(200))
    assert read_header(tmp_path / "v2") is None
    (tmp_path / "short").write_bytes(planet()[:126])
    assert read_header(tmp_path / "short") is None
    (tmp_path / "planet").write_bytes(planet())
    header = read_header(tmp_path / "planet")
    assert header is not None and (header.min_zoom, header.max_zoom) == (0, 6) and header.bbox == pytest.approx((-180.0, -85.0511287, 180.0, 85.0511287))
    (tmp_path / "small").write_bytes(archive({(3, 4, 5): b"x"}, bounds=(240000000, 590000000, 250000000, 600000000)))  # type: ignore[arg-type]
    small = read_header(tmp_path / "small")
    assert small is not None and (small.min_zoom, small.max_zoom, small.bbox) == (3, 3, (24.0, 59.0, 25.0, 60.0))


def test_a_file_replaces_the_one_before_it(tmp_path: Path) -> None:
    (tmp_path / "new").write_bytes(b"new")
    (tmp_path / "old").write_bytes(b"old")
    replace_file(tmp_path / "new", tmp_path / "old")
    assert (tmp_path / "old").read_bytes() == b"new" and not (tmp_path / "new").exists()


def test_a_target_that_another_program_holds_is_tried_again_and_then_given_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real, slept, refusals = os.replace, [], [0]
    monkeypatch.setattr(pmtilesarchive.time, "sleep", slept.append)

    def busy(source: Path, target: Path) -> None:
        refusals[0] += 1
        if refusals[0] <= 3:
            raise PermissionError("[WinError 32] in use by another process")
        real(source, target)
    monkeypatch.setattr(pmtilesarchive.os, "replace", busy)
    (tmp_path / "new").write_bytes(b"new")
    replace_file(tmp_path / "new", tmp_path / "old")
    assert (tmp_path / "old").read_bytes() == b"new" and len(slept) == 3
    refusals[0] = -1000
    with pytest.raises(PermissionError):
        replace_file(tmp_path / "old", tmp_path / "again")
    assert len(slept) == 3 + pmtilesarchive.REPLACE_TRIES - 1


async def test_a_head_request_says_whether_a_build_is_there() -> None:
    server = await range_server(planet())
    assert await asyncio.to_thread(url_exists, server.url)
    server.mode = "missing"
    assert not await asyncio.to_thread(url_exists, server.url)
    assert not await asyncio.to_thread(url_exists, "not an address")
