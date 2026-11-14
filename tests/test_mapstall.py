"""A map download that stands still (neoaprs/services/mapfetch.py, `Patience`) with the range server of tests/support/rangeserver.py holding its answers for tile data: the cut is ended and begun again, the status says
so and what has been downloaded, after the last try the job fails with a plain text, a download that moves only in the size of what has come is not a stall, and the map that was there is never touched."""
import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio

import neoaprs.services.mapfetch as mapfetch
from neoaprs.mapstate import Box
from neoaprs.pmtilescut import part_of
from neoaprs.services.mapfetch import DETAIL, SLOW, WORLD, MapFetch, Patience
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until_started
from tests.support.madepmtiles import planet
from tests.support.maprig import MapRig, data_offset, own_world
from tests.support.rangeserver import RangeServer, range_server

FAST = Patience(stall_sec=0.5, tries=3, pause_sec=0.05, poll_sec=0.05)


class Rig(MapRig):
    def __init__(self, data: Path, server: RangeServer, patience: Patience = FAST) -> None:
        super().__init__(data, server, lambda: replace(ON_AIR, map_source=server.url), patience)
        server.hold_from = data_offset(planet())               # (every answer for tile data is held, the directories come)

    def old_map(self) -> None:
        self.data.mkdir(exist_ok=True)
        (self.data / DETAIL).write_bytes(b"the old map")
        (self.data / WORLD).write_bytes(b"the old world")

    def notes(self) -> list[str]:
        return [s.note for s in self.seen if s.note]

    def tries(self) -> int:
        """The cuts begun: each reads the header first."""
        return self.server.asked.count((0, 126))

    def with_patience(self, patience: Patience) -> None:
        self.service = MapFetch(self.data, lambda: replace(ON_AIR, map_source=self.server.url), FixedClock(), patience=patience, world=own_world)
        remember_stop(self.service.stop)
        self.service.changed.connect(lambda: self.seen.append(self.service.status()))


@pytest_asyncio.fixture
async def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path / "data", await range_server(planet()))


async def test_a_download_that_stands_still_is_ended_and_begun_again_and_the_page_is_told(rig: Rig) -> None:
    def let_the_next_try_through() -> None:
        if rig.service.status().note:
            rig.server.hold_from = None
    rig.service.changed.connect(let_the_next_try_through)
    await rig.service.fetch()
    assert rig.notes()[0] == "no progress: trying again (2 of 3)" and len(set(rig.notes())) == 1
    assert rig.tries() == 3, "the world map twice, the area once"
    status = rig.status()
    assert status.state == "ready" and status.problem == "" and status.note == "" and status.downloaded is None
    noted = next(s for s in rig.seen if s.note)
    assert noted.state == "downloading" and noted.step == "world" and noted.percent is None, "the bar begins again"
    assert not [s for s in rig.seen if s.note and s.percent is not None], "the note goes when the download moves"
    assert sorted(p.name for p in rig.data.glob("*.pmtiles*")) == ["basemap-world.pmtiles", "basemap.pmtiles"]
    await until_started(lambda: rig.server.holding == 0)       # (the connections of the try that stood still were shut)


async def test_after_the_last_try_the_job_fails_with_a_plain_text_and_the_old_map_stays(rig: Rig) -> None:
    rig.old_map()
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert status.state == "error" and status.problem == SLOW == "the map server is too slow now; try again later"
    assert rig.notes()[:2] == ["no progress: trying again (2 of 3)", "no progress: trying again (3 of 3)"] and set(rig.notes()) <= set(rig.notes()[:2])
    assert rig.tries() == 3, "three cuts in all"
    assert status.note == "" and status.downloaded is None and status.percent is None
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and (rig.data / WORLD).read_bytes() == b"the old world"
    assert not list(rig.data.glob("*.part"))
    await until_started(lambda: rig.server.holding == 0)


async def test_a_failure_of_the_server_that_cannot_get_better_is_not_retried(rig: Rig) -> None:
    rig.server.mode = "missing"
    rig.service.begin("fetch")
    await rig.idle()
    assert rig.status().state == "error" and rig.status().problem == "the map server answered 404 Not Found" and rig.tries() == 1 and rig.notes() == []


async def test_the_size_of_what_has_come_is_told_while_the_download_moves(rig: Rig) -> None:
    rig.old_map()
    rig.server.hold_from = data_offset(planet()) + 3000        # (the tiles before it come, the others are held)
    rig.service.begin("fetch")
    await until_started(lambda: (rig.status().downloaded or 0) > 0)
    assert rig.status().step == "area" and rig.status().note == ""
    assert part_of(rig.data / DETAIL).exists()
    assert rig.service.cancel()
    await rig.idle()
    assert rig.status().downloaded is None


async def test_a_download_that_moves_only_in_the_size_of_what_has_come_is_not_a_stall(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cut that tells no percent for longer than the patience, while the size of what has come grows, goes on: the size is a sign of life as well."""
    rig.old_map()
    (rig.data / DETAIL).unlink()
    rig.with_patience(Patience(0.5, 1, 0.05, 0.05))
    runs: list[Path] = []

    async def growing(source: str, final: Path, box: Box | None, maxzoom: int, dry_run: bool = False, on_percent: Callable[[int], None] | None = None,
                      on_size: Callable[[int], None] | None = None) -> None:
        runs.append(final)
        assert on_size is not None
        for step in range(1, 13):                                   # (1.2 s of a size that grows and a bar that does not move, with a patience of 0.5 s and no second try)
            part_of(final).write_bytes(b"tiles" * 100 * step)
            on_size(500 * step)
            await asyncio.sleep(0.1)
        part_of(final).replace(final)
    monkeypatch.setattr(mapfetch, "extract", growing)
    await rig.service.fetch()
    assert rig.status().state == "ready" and runs == [rig.data / DETAIL] and rig.notes() == []


async def test_a_cancel_while_the_job_waits_to_try_again_keeps_the_map_and_removes_the_part(rig: Rig) -> None:
    rig.with_patience(Patience(0.3, 3, 30.0, 0.05))
    rig.old_map()
    rig.service.begin("fetch")
    await until_started(lambda: rig.service.status().note != "")
    assert rig.service.cancel()
    await rig.idle()
    status = rig.status()
    assert status.state == "ready" and status.problem == "" and status.note == "" and rig.tries() == 1
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and not list(rig.data.glob("*.part"))
    await until_started(lambda: rig.server.holding == 0)


async def test_a_cancel_of_a_running_download_still_ends_the_cut(rig: Rig) -> None:
    rig.old_map()
    rig.service.begin("fetch")
    await until_started(lambda: rig.server.holding > 0)
    assert rig.service.cancel()
    await rig.idle()
    assert rig.status().note == "" and (rig.data / DETAIL).read_bytes() == b"the old map" and rig.tries() == 1
    await until_started(lambda: rig.server.holding == 0)
