"""The detailed map without a click (neoaprs/services/mapauto.py) on the map service with the fake pmtiles program: the first place starts it, once for an installation; a failed job (no connection) waits for the next start
and says so; the operator's cancel and a stop of the daemon are different things; a place far from the area being made starts it again; and where the process does not ask for it (the tests', the scripts') nothing starts."""
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.config import MAP_AUTO
from neoaprs.geo import box_around
from neoaprs.services.mapauto import MapAuto, inside
from neoaprs.services.mapfetch import DETAIL, WORLD, MapFetch
from tests.support.clock import FixedClock
from neoaprs.config import DEFAULTS
from tests.support.env import Env, remember_stop, until
from tests.support.wsclient import WsClient
from tests.support.fakepmtiles import FakePmtiles, install_fake

SOURCE = "https://build.example/20261020.pmtiles"
HELSINKI, TURKU, ROME = (60.17, 24.94), (60.45, 22.27), (41.9, 12.5)


class Rows:
    """The settings table as far as the map's memory goes: a dict."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    async def setting(self, key: str) -> str | None:
        return self.rows.get(key)

    async def put_settings(self, data: dict[str, str]) -> bool:
        self.rows.update(data)
        return True


class Rig:
    def __init__(self, tmp_path: Path, fake: FakePmtiles, rows: Rows, enabled: bool = True, place: tuple[float, float] | None = None) -> None:
        self.data, self.fake, self.rows = tmp_path / "data", fake, rows
        self.config = replace(DEFAULTS, map_source=SOURCE, station_lat=place[0] if place else None, station_lon=place[1] if place else None)
        self.world = tmp_path / "shipped" / WORLD
        self.world.parent.mkdir(exist_ok=True)
        self.world.write_bytes(b"PMTiles" + bytes([3]) + bytes(92) + struct.pack("<BB4i", 0, 4, -1800000000, -850000000, 1800000000, 850000000) + bytes(9))      # the world map the program ships: a header is all it needs here
        self.fetch = MapFetch(self.data, lambda: self.config, FixedClock(), world=lambda data: self.world)
        self.auto = MapAuto(self.fetch, lambda: self.config, rows, enabled)
        self.fetch.changed.connect(self.auto.fetch_changed)
        remember_stop(self.auto.stop)
        remember_stop(self.fetch.stop)

    async def move(self, place: tuple[float, float]) -> None:
        before, self.config = self.config, replace(self.config, station_lat=place[0], station_lon=place[1])
        self.auto.settings_changed(before)

    async def idle(self) -> None:
        await until(lambda: not self.fetch.busy, 5)

    async def row(self, value: str | None) -> None:
        """Waits until the row `map/auto` is this (None: not there); the memory is written in a task."""
        await until(lambda: self.rows.rows.get(MAP_AUTO) == value, 5)

    def targets(self) -> list[str]:
        return [call[2].rsplit("/", 1)[1] for call in self.fake.calls()]


@pytest.fixture
def make(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PATH", "")                                         # (a pmtiles on this machine is not the one to run)

    def build(rows: Rows | None = None, **options: object) -> Rig:
        fake = install_fake(tmp_path / "data" / "bin")
        return Rig(tmp_path, fake, rows if rows is not None else Rows(), **options)                    # type: ignore[arg-type]
    return build


async def test_the_first_place_makes_the_detailed_map_and_the_world_that_ships_is_not_made_again(make) -> None:
    rig = make()
    await rig.auto.start()
    await rig.move(HELSINKI)
    await until(lambda: rig.fetch.status().state == "ready", 5)
    assert rig.targets() == [DETAIL + ".part"], "one run: the world under it is the one that ships with the program"
    await rig.row("done")
    assert not rig.fetch.status().later
    assert not (rig.data / WORLD).exists() and rig.fetch.status().world is not None


async def test_it_is_once_for_an_installation_whatever_becomes_of_the_files_or_the_place(make) -> None:
    rig = make()
    await rig.auto.start()
    await rig.move(HELSINKI)
    await until(lambda: rig.fetch.status().state == "ready", 5)
    (rig.data / DETAIL).unlink()
    await rig.move(ROME)
    await rig.idle()
    assert len(rig.fake.calls()) == 1
    again = make(rig.rows)                                                  # a start of the daemon on the same rows
    await again.auto.start()
    await again.move(TURKU)
    await again.idle()
    assert len(again.fake.calls()) == 1, "done stays done (the one call is the first start's: the program and its log are the same)"


async def test_a_station_that_has_a_place_and_no_map_is_not_given_a_download_at_its_start(make) -> None:
    rig = make(place=HELSINKI)
    await rig.auto.start()
    await rig.idle()
    assert rig.fake.calls() == [] and MAP_AUTO not in rig.rows.rows


async def test_a_place_that_is_not_new_or_not_there_starts_nothing(make) -> None:
    rig = make(place=HELSINKI)
    await rig.auto.start()
    rig.auto.settings_changed(rig.config)                                   # saved again, the same
    rig.config = replace(rig.config, station_lat=None, station_lon=None)
    rig.auto.settings_changed(replace(rig.config, station_lat=60.0, station_lon=25.0))      # the place was taken away
    await rig.idle()
    assert rig.fake.calls() == []


async def test_a_detailed_map_that_is_there_means_done_and_nothing_is_made(make) -> None:
    rig = make()
    rig.data.mkdir(parents=True, exist_ok=True)
    (rig.data / DETAIL).write_bytes(rig.world.read_bytes())
    await rig.auto.start()
    await rig.move(HELSINKI)
    await rig.idle()
    assert rig.fake.calls() == []
    await rig.row("done")


async def test_without_a_connection_the_world_stays_the_page_is_told_it_will_come_later_and_the_next_start_tries_again(make) -> None:
    rig = make()
    rig.fake.mode("fail")
    await rig.auto.start()
    await rig.move(HELSINKI)
    await until(lambda: rig.fetch.status().later, 5)
    status = rig.fetch.status()
    assert status.state == "error" and "connection refused" in status.problem and status.detail is None and status.world is not None
    await rig.row("wanted")
    await rig.move(TURKU)                                                   # (the place changed again: tried again at once, and failing again)
    await until(lambda: rig.fetch.status().later and len(rig.fake.calls()) == 2, 5)
    rig.fake.mode("ok")
    start = make(rig.rows, place=HELSINKI)                                  # the next start of the daemon
    await start.auto.start()
    await until(lambda: start.fetch.status().state == "ready", 5)
    await start.row("done")
    assert not start.fetch.status().later
    assert (start.data / DETAIL).is_file()


async def test_a_job_started_by_hand_that_makes_the_map_counts_as_done_and_a_new_job_takes_the_later_note_back(make) -> None:
    rig = make(place=HELSINKI)
    rig.rows.rows[MAP_AUTO] = "wanted"
    rig.fake.mode("fail")
    await rig.auto.start()
    await until(lambda: rig.fetch.status().later, 5)
    rig.fake.mode("ok")
    await rig.fetch.fetch()                                                 # Settings, Map, Download
    assert not rig.fetch.status().later
    await until(lambda: rig.rows.rows[MAP_AUTO] == "done", 5)


async def test_the_operators_cancel_ends_it_for_good_and_a_stop_of_the_daemon_does_not(make) -> None:
    rig = make()
    rig.fake.mode("slow")
    await rig.auto.start()
    await rig.move(HELSINKI)
    await until(lambda: rig.fetch.status().percent == 10, 5)
    assert rig.fetch.cancel()
    await rig.idle()
    await rig.row("done")
    assert not rig.fetch.status().later
    stopped = make()
    stopped.fake.mode("slow")
    await stopped.auto.start()
    await stopped.move(HELSINKI)
    await until(lambda: stopped.fetch.status().percent == 10, 5)
    await stopped.auto.stop()
    await stopped.fetch.stop()
    await stopped.row("wanted")                                             # (the daemon endedthe job is still wanted at the next start)


async def test_a_place_outside_the_area_that_is_being_made_starts_it_again_for_that_place_and_one_inside_does_not(make) -> None:
    rig = make()
    rig.fake.mode("slow")
    await rig.auto.start()
    await rig.move(HELSINKI)
    await until(lambda: rig.fetch.status().percent == 10, 5)
    await rig.move((60.3, 25.1))                                            # a few km: inside
    assert len(rig.fake.calls()) == 1
    await rig.move(ROME)
    await until(lambda: len(rig.fake.calls()) == 2 and rig.fetch.status().percent == 10, 5)
    west, south, east, north = (float(v) for v in next(a for a in rig.fake.calls()[1] if a.startswith("--bbox=")).split("=")[1].split(","))
    assert south < ROME[0] < north and west < ROME[1] < east
    await rig.row("wanted")                                                 # (the job that was ended to make the new one is not the operator's cancel)
    assert rig.fetch.busy


async def test_where_the_process_does_not_ask_for_it_nothing_starts_and_nothing_is_remembered(make) -> None:
    rig = make(enabled=False)
    await rig.auto.start()
    await rig.move(HELSINKI)
    await rig.fetch.fetch()
    await rig.idle()
    assert len(rig.fake.calls()) == 1 and rig.rows.rows == {}


def test_a_place_is_inside_a_box_with_its_edges() -> None:
    box = box_around(*HELSINKI, 150)
    assert inside(box, *HELSINKI) and not inside(box, *ROME) and inside(box, box[1], box[0])


# ---- in the whole daemon: the place the setup sends

async def daemon(tmp_path: Path, mode: str) -> tuple[Env, WsClient, FakePmtiles]:
    fake = install_fake(tmp_path / "bin")
    fake.mode(mode)
    e = Env(tmp_path, web=True, radio=False, operator=False, auto_map=True)
    await e.start(connected=False)
    await e.ctl.save_config(replace(e.ctl.config, map_source=SOURCE))
    page = await e.ws()
    await page.until(lambda: "map" in page.topics)
    return e, page, fake


async def test_the_place_the_setup_sends_makes_the_map_round_it_and_the_page_is_told(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    e, page, fake = await daemon(tmp_path, "ok")
    assert page.topics["map"]["state"] == "none" and page.topics["map"]["world"] is not None, "the world map is there from the first second"
    await page.send({"cmd": "set_config", "values": {"station/lat": "60.17", "station/lon": "24.94"}})
    await page.until(lambda: page.topics["map"]["state"] == "ready", 10)
    value = page.topics["map"]
    assert value["detail"]["name"] == "basemap.pmtiles" and value["later"] is False
    assert len(fake.calls()) == 1
    await page.send({"cmd": "set_config", "values": {"station/lat": "48.85", "station/lon": "2.35"}})
    await e.settled()
    assert len(fake.calls()) == 1, "once for the installation"


async def test_without_a_connection_the_page_is_told_the_detailed_map_will_come_when_online(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    e, page, fake = await daemon(tmp_path, "fail")
    await page.send({"cmd": "set_config", "values": {"station/lat": "60.17", "station/lon": "24.94"}})
    await page.until(lambda: page.topics["map"]["later"], 10)
    value = page.topics["map"]
    assert value["state"] == "error" and value["detail"] is None and value["world"] is not None
