"""A map download that stands still (neoaprs/services/mapfetch.py, `Patience`) with the fake pmtiles program: the tool is ended and begun again, the status says so and what has been downloaded, after the last try the job fails
with a plain text, a download that moves only in the size of its file is not a stall, and the map that was there is never touched."""
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.services.mapfetch import DETAIL, SLOW, WORLD, MapFetch, Patience
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until
from tests.support.maprig import MapRig
from tests.support.fakepmtiles import FakePmtiles, alive, install_fake

FAST = Patience(stall_sec=0.4, tries=3, pause_sec=0.05, poll_sec=0.05)


class Rig(MapRig):
    def __init__(self, data: Path, fake: FakePmtiles, patience: Patience = FAST) -> None:
        super().__init__(data, fake, lambda: replace(ON_AIR, map_source="https://build.example/20261020.pmtiles"), patience, idle_sec=10)

    def old_map(self) -> None:
        self.data.mkdir(exist_ok=True)
        (self.data / DETAIL).write_bytes(b"the old map")
        (self.data / WORLD).write_bytes(b"the old world")

    def notes(self) -> list[str]:
        return [s.note for s in self.seen if s.note]


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    monkeypatch.setenv("PATH", "")
    return Rig(tmp_path / "data", install_fake(tmp_path / "data" / "bin"))


async def test_a_download_that_stands_still_is_ended_and_begun_again_and_the_page_is_told(rig: Rig) -> None:
    rig.fake.mode("stall-once")
    first_pid = 0

    def watch() -> None:
        nonlocal first_pid
        if rig.fake.calls() and not first_pid:
            first_pid = rig.fake.pid()
    rig.service.changed.connect(watch)
    await rig.service.fetch()
    assert rig.notes()[0] == "no progress: trying again (2 of 3)" and len(set(rig.notes())) == 1
    assert [c[2].rsplit("/", 1)[1] for c in rig.fake.calls()] == ["basemap-world.pmtiles.part", "basemap-world.pmtiles.part", "basemap.pmtiles.part"]
    assert first_pid and not alive(first_pid), "the program that stood still was ended"
    status = rig.status()
    assert status.state == "ready" and status.problem == "" and status.note == "" and status.downloaded is None
    noted = next(s for s in rig.seen if s.note)
    assert noted.state == "downloading" and noted.step == "world" and noted.percent is None, "the bar begins again"
    assert not [s for s in rig.seen if s.note and s.percent is not None], "the note goes when the download moves"
    assert sorted(p.name for p in rig.data.glob("*.pmtiles*")) == ["basemap-world.pmtiles", "basemap.pmtiles"]


async def test_after_the_last_try_the_job_fails_with_a_plain_text_and_the_old_map_stays(rig: Rig) -> None:
    rig.old_map()
    rig.fake.mode("slow")
    rig.service.begin("fetch")
    await rig.idle()
    status = rig.status()
    assert status.state == "error" and status.problem == SLOW == "the map server is too slow now; try again later"
    assert rig.notes()[:2] == ["no progress: trying again (2 of 3)", "no progress: trying again (3 of 3)"] and set(rig.notes()) <= set(rig.notes()[:2])
    assert len(rig.fake.calls()) == 3, "three runs in all"
    assert status.note == "" and status.downloaded is None and status.percent is None
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and (rig.data / WORLD).read_bytes() == b"the old world"
    assert not list(rig.data.glob("*.part")) and not alive(rig.fake.pid())


async def test_a_failure_of_the_tool_is_not_retried(rig: Rig) -> None:
    rig.fake.mode("fail")
    rig.service.begin("fetch")
    await rig.idle()
    assert rig.status().state == "error" and "connection refused" in rig.status().problem and len(rig.fake.calls()) == 1 and rig.notes() == []


async def test_the_size_of_the_part_file_is_told_with_the_percent(rig: Rig) -> None:
    rig.fake.mode("grow")
    await rig.service.fetch()
    sizes = [s.downloaded for s in rig.seen if s.step == "area" and s.downloaded is not None]
    assert sizes and sizes == sorted(sizes) and sizes[-1] > sizes[0] >= 0     # (the first report may come before the first bytes)
    percents = [s.percent for s in rig.seen if s.step == "area" and s.percent is not None]
    assert percents[0] == 10 and rig.status().downloaded is None


async def test_a_download_that_moves_only_in_the_size_of_its_file_is_not_a_stall(rig: Rig) -> None:
    rig.service = MapFetch(rig.data, lambda: replace(ON_AIR, map_source="https://build.example/20261020.pmtiles"), FixedClock(), patience=Patience(0.5, 1, 0.05, 0.05))
    remember_stop(rig.service.stop)
    rig.fake.mode("grow")
    await rig.service.fetch()                       # (1.2 s of a bar that stays at 10% while the file grows, with a patience of 0.5 s and no second try)
    assert rig.status().state == "ready" and len(rig.fake.calls()) == 2


async def test_a_cancel_while_the_job_waits_to_try_again_keeps_the_map_and_removes_the_part(rig: Rig) -> None:
    rig.service = MapFetch(rig.data, lambda: replace(ON_AIR, map_source="https://build.example/20261020.pmtiles"), FixedClock(), patience=Patience(0.3, 3, 30.0, 0.05))
    remember_stop(rig.service.stop)
    rig.old_map()
    rig.fake.mode("slow")
    rig.service.begin("fetch")
    await until(lambda: rig.service.status().note != "")
    assert rig.service.cancel()
    await rig.idle()
    status = rig.status()
    assert status.state == "ready" and status.problem == "" and status.note == "" and len(rig.fake.calls()) == 1
    assert (rig.data / DETAIL).read_bytes() == b"the old map" and not list(rig.data.glob("*.part")) and not alive(rig.fake.pid())


async def test_a_cancel_of_a_running_download_still_ends_the_program(rig: Rig) -> None:
    rig.old_map()
    rig.fake.mode("slow")
    rig.service.begin("fetch")
    await until(lambda: rig.status().percent == 10)
    pid = rig.fake.pid()
    assert rig.service.cancel()
    await rig.idle()
    assert not alive(pid) and rig.status().note == "" and (rig.data / DETAIL).read_bytes() == b"the old map" and len(rig.fake.calls()) == 1
