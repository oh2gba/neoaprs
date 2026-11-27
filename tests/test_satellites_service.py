"""The satellites layer's service (neoaprs/services/satellites.py) on a fixed clock with a stand-in
fetch: the file is fetched while a page looks, when it is missing or a day old, at most once a day,
kept in the data folder and used while the server is away; nothing is fetched or computed while no
page looks."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import utc
from neoaprs.satelliteview import View
from neoaprs.services.satellites import ENV_URL, FETCH_EVERY_SEC, RETRY_SEC, SATELLITES_URL, Satellites
from neoaprs.services import satellites as satellites_service
from neoaprs.services.updatecheck import ENV_SWITCH
from tests.support.clock import FixedClock
from tests.support.fakelayers import satellites_file

HELSINKI = (60.17, 24.94)
DURING_PASS = utc(2026, 11, 28, 12, 5, 0)  # the ISS is up over Helsinki: 12:03:44 to 12:13:06


class Server:
    def __init__(self, status: int = 200, body: bytes | None = None) -> None:
        self.status, self.body = status, satellites_file() if body is None else body
        self.asked: list[str] = []

    async def __call__(self, url: str, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
        self.asked.append(url)
        return None if self.status == 0 else (self.status, self.body if self.status == 200 else b"")


def made(
    tmp_path: Path,
    server: Server,
    clock: FixedClock,
    where: tuple[float, float] | None = HELSINKI,
    environ: dict[str, str] | None = None,
) -> Satellites:
    return Satellites(tmp_path, lambda: where, "0.26.0", "linux", server, clock, environ or {}, clock.monotonic)


async def test_a_round_fetches_the_missing_file_keeps_it_and_tells_every_mark_and_the_open_card(tmp_path: Path) -> None:
    server, clock = Server(), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    seen: list[View] = []
    service.told.connect(seen.append)
    service.look(True, frozenset({25544}))
    await service.round()
    assert server.asked == [SATELLITES_URL] and (tmp_path / "satellites.json").read_bytes() == server.body
    (view,) = seen
    assert len(view.marks) == 10 and [one.id for one in view.cards] == [25544]
    iss = view.cards[0]
    assert iss.next_pass is not None and iss.next_pass.rise < DURING_PASS < iss.next_pass.set
    assert iss.path == "" and iss.mode == "afsk1200" and [one.hz for one in iss.downlinks] == [437825000]
    assert iss.looks and 0 < iss.looks[0].down_hz[0] < 11000 and iss.looks[0].up_hz[0] < 0
    assert 400 < iss.alt_km < 440 and 2200 < iss.footprint_km < 2300 and len(iss.track) == 93


async def test_within_a_day_it_is_not_fetched_again_and_after_one_it_is_once(tmp_path: Path) -> None:
    server, clock = Server(), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    await service.round()
    clock.advance(FETCH_EVERY_SEC - 60)
    await service.round()
    assert len(server.asked) == 1
    clock.advance(120)
    await service.round()
    assert len(server.asked) == 2


async def test_a_failed_fetch_keeps_the_last_file_and_is_tried_again_only_after_the_pause(tmp_path: Path) -> None:
    (tmp_path / "satellites.json").write_bytes(satellites_file(made="2026-11-26T10:00:00Z"))
    server, clock = Server(status=0), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    seen: list[View] = []
    service.told.connect(seen.append)
    await service.round()
    assert len(server.asked) == 1 and len(seen[-1].marks) == 10, "the file of the data folder is used"
    clock.advance(RETRY_SEC - 1)
    await service.round()
    assert len(server.asked) == 1
    clock.advance(2)
    server.status = 503
    await service.round()
    assert len(server.asked) == 2 and len(seen[-1].marks) == 10


async def test_a_file_of_today_in_the_data_folder_is_used_without_asking(tmp_path: Path) -> None:
    (tmp_path / "satellites.json").write_bytes(satellites_file(made="2026-11-28T06:00:00Z"))
    server, clock = Server(), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    await service.round()
    assert server.asked == [] and service.view is not None and len(service.view.marks) == 10


async def test_elements_older_than_fourteen_days_are_not_shown_and_no_position_means_no_pass(tmp_path: Path) -> None:
    server, clock = Server(), FixedClock(utc(2026, 12, 11, 12, 0, 0))
    service = made(tmp_path, server, clock, where=None)
    service.look(True, frozenset({25544}))
    await service.round()
    assert service.view is not None
    shown = {one.id for one in service.view.marks}
    assert 25544 not in shown, "the ISS's elements are of 27 Nov"
    clock.now = DURING_PASS
    await service.round()
    (iss,) = service.view.cards
    assert iss.next_pass is None and iss.looks == () and iss.downlinks[0].rise_hz is None


async def test_with_the_update_check_off_nothing_is_fetched_unless_a_server_of_this_computer_is_named(
    tmp_path: Path,
) -> None:
    server, clock = Server(), FixedClock(DURING_PASS)
    off = made(tmp_path, server, clock, environ={ENV_SWITCH: "0"})
    await off.round()
    assert server.asked == [] and off.view is not None and off.view.marks == ()
    far = made(tmp_path, server, clock, environ={ENV_SWITCH: "0", ENV_URL: "https://example.org/s.json"})
    await far.round()
    assert server.asked == []
    local = made(tmp_path, server, clock, environ={ENV_SWITCH: "0", ENV_URL: "http://127.0.0.1:9/s.json"})
    await local.round()
    assert server.asked == ["http://127.0.0.1:9/s.json"]


async def test_nothing_runs_while_no_page_looks_and_the_rounds_stop_when_the_last_one_leaves(tmp_path: Path) -> None:
    server, clock = Server(), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    seen: list[View] = []
    service.told.connect(seen.append)
    await service.start()
    for _ in range(5):
        await asyncio.sleep(0)
    assert server.asked == [] and seen == []
    service.look(True, frozenset())
    while not seen:
        await asyncio.sleep(0.01)
    service.look(False, frozenset())
    told = len(seen)
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(seen) == told and len(server.asked) == 1
    await service.stop()


def test_the_iss_moves_along_its_points_by_a_few_degrees_a_minute() -> None:
    from neoaprs.satellitelist import read_file
    from neoaprs.satelliteview import mark

    read = read_file(satellites_file(only={25544}))
    assert read is not None
    (iss,) = read.satellites
    assert iss.orbit is not None
    got = mark(iss, iss.orbit, DURING_PASS)
    assert got is not None and len(got.points) == 12
    assert got.points[1][0] == DURING_PASS and got.points[0][0] == DURING_PASS - timedelta(seconds=30)
    assert all(0.5 < b[2] - a[2] < 3.0 for a, b in zip(got.points, got.points[1:], strict=False))


async def test_a_file_that_raises_in_reading_costs_a_failed_fetch_not_a_fetch_every_round(tmp_path: Path) -> None:
    server = Server(body=b'{"v": 1, "satellites": [{"id": 25544, "name": "ISS", "downlink": ["x"]}]}')
    clock = FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    await service.round()
    clock.advance(60)
    await service.round()
    assert len(server.asked) == 1, "the server is not asked every round"


async def test_an_answer_with_too_few_satellites_to_draw_never_replaces_a_good_kept_file_and_is_asked_again_soon(
    tmp_path: Path,
) -> None:
    kept = satellites_file(made="2026-11-26T10:00:00Z")
    (tmp_path / "satellites.json").write_bytes(kept)
    server, clock = (
        Server(body=satellites_file(made="2026-11-28T11:00:00Z", only=(25544, 7530))),
        FixedClock(DURING_PASS),
    )
    service = made(tmp_path, server, clock)
    await service.round()
    assert len(server.asked) == 1 and (tmp_path / "satellites.json").read_bytes() == kept
    assert service.view is not None and len(service.view.marks) == 10
    clock.advance(RETRY_SEC + 1)
    server.body = satellites_file(made="2026-11-28T12:00:00Z")
    await service.round()
    assert len(server.asked) == 2 and (tmp_path / "satellites.json").read_bytes() == server.body


async def test_with_no_file_kept_a_thin_answer_is_used_and_asked_for_again_after_the_pause(tmp_path: Path) -> None:
    server, clock = Server(body=satellites_file(made="2026-11-28T11:00:00Z", only=(25544,))), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    await service.round()
    assert service.view is not None and len(service.view.marks) == 1
    clock.advance(RETRY_SEC + 1)
    await service.round()
    assert len(server.asked) == 2, "a thin file is not kept for a day"


async def test_a_page_that_comes_back_is_not_handed_the_view_of_the_last_look(tmp_path: Path) -> None:
    server, clock = Server(), FixedClock(DURING_PASS)
    service = made(tmp_path, server, clock)
    service.look(True, frozenset())
    await service.round()
    assert service.view is not None
    service.look(False, frozenset())
    assert service.view is None


async def test_a_satellite_that_never_rises_is_not_searched_again_every_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    searched: list[int] = []

    def none(*args: object) -> list[object]:
        searched.append(1)
        return []

    monkeypatch.setattr(satellites_service, "passes", none)
    server, clock = Server(), FixedClock(DURING_PASS)
    moving = [60.17, 24.94]
    service = Satellites(
        tmp_path, lambda: (moving[0], moving[1]), "0.26.0", "linux", server, clock, {}, clock.monotonic
    )
    service.look(True, frozenset({25544}))
    for _ in range(4):
        await service.round()
        clock.advance(30)
        moving[0] += 0.001  # a GPS that drifts a little
    assert len(searched) == 1
