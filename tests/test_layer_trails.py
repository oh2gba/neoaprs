"""The way the map's aircraft and ships went, kept by the daemon for a page that starts to look
(neoaprs/layerthing.py TrailBook), and the short grace after the last look (neoaprs/services/layers.py
LOOK_GRACE_SEC): a page that comes back from another tab, is reloaded or opened on a second device
starts with the trail."""

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from neoaprs import layerthing
from neoaprs.layerthing import LIMIT, TRAIL_MAX_AGE_SEC, TRAIL_MAX_POINTS, Thing, TrailBook
from neoaprs.services import layers
from tests.support.env import Env, until
from tests.support.fakelayers import layers_server
from tests.test_layers import plane, sky

T0 = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def thing(id: str, lon: float, at: datetime, lat: float = 60.3) -> Thing:
    return Thing(id=id, lat=lat, lon=lon, at=at, heading_deg=90, speed_kmh=500.0)


def test_a_trail_gets_a_point_when_the_place_changes_and_none_for_the_same_place_or_an_older_report() -> None:
    book = TrailBook()
    book.grow([thing("a", 24.9, T0)], T0)
    book.grow([thing("a", 24.9, T0 + timedelta(seconds=5))], T0)
    book.grow([thing("a", 25.0, T0 + timedelta(seconds=10))], T0)
    book.grow([thing("a", 25.5, T0 - timedelta(seconds=10))], T0)
    [trail] = book.trails()
    assert (trail.id, [p[0] for p in trail.points]) == ("a", [24.9, 25.0])


def test_old_points_go_a_thing_keeps_its_last_400_and_the_book_its_newest_things() -> None:
    book = TrailBook()
    for i in range(TRAIL_MAX_POINTS + 50):
        book.grow([thing("a", 20 + i / 1000, T0 + timedelta(seconds=i))], T0 + timedelta(seconds=i))
    assert len(book.trails()[0].points) == TRAIL_MAX_POINTS
    later = T0 + timedelta(seconds=TRAIL_MAX_POINTS + 50 + TRAIL_MAX_AGE_SEC + 1)
    book.grow([], later)
    assert book.trails() == ()
    many = TrailBook()
    many.grow(
        [thing(f"t{i}", 20.0, T0 + timedelta(seconds=i)) for i in range(LIMIT + 20)], T0 + timedelta(seconds=LIMIT + 20)
    )
    kept = {trail.id for trail in many.trails()}
    assert len(kept) == LIMIT and "t0" not in kept and f"t{LIMIT + 19}" in kept
    many.clear()
    assert many.trails() == ()


@pytest.fixture
def look_grace(monkeypatch: pytest.MonkeyPatch) -> float:
    """A grace short enough for a test (tests/conftest.py gives every other test none)."""
    monkeypatch.setattr(layers, "LOOK_GRACE_SEC", 1.5)
    monkeypatch.setitem(layerthing.EVERY_SEC, "aircraft_receiver", 0.3)
    return 1.5


def trails_of(message: dict[str, Any]) -> dict[str, list[list[Any]]]:
    return {trail["id"]: trail["points"] for trail in message["trails"]}


@pytest.mark.slow("serves made-up feeds on the loopback through the layer's rounds")
async def test_a_page_that_comes_back_within_the_grace_starts_with_the_trail_and_after_it_with_none(
    tmp_path: Path, look_grace: float
) -> None:
    receiver = await layers_server()
    receiver.route("/tar1090/data/aircraft.json", body=sky(plane("461f2a", lon=24.90)))
    e = Env(tmp_path / "data", web=True, settings={"map/aircraft": "receiver", "map/aircraft_host": receiver.address})
    await e.start()
    tab = await e.ws()
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    first = await tab.expect("layer_things")
    assert first["trails"] == [] or len(trails_of(first)["461f2a"]) <= 1
    for lon in (24.95, 25.00):
        receiver.route("/tar1090/data/aircraft.json", body=sky(plane("461f2a", lon=lon)))
        await tab.until(lambda lon=lon: any(t["lon"] == lon for m in tab.of("layer_things") for t in m["things"]), 10.0)
    assert all(m["trails"] == [] for m in tab.of("layer_things")[1:]), "the trails come with the first table only"
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": False})
    asked = len(receiver.paths())
    await until(lambda: len(receiver.paths()) > asked + 1)  # asked on through the grace
    back = await e.ws()
    await back.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    table = await back.expect("layer_things")
    points = trails_of(table)["461f2a"]
    # (the first place may have been asked before the look began, and so be the page's own)
    assert [p[0] for p in points][-2:] == [24.95, 25.00]
    assert all(isinstance(p[2], str) and p[2].endswith("Z") for p in points)
    await back.send({"cmd": "layer_look", "layer": "aircraft", "on": False})
    await e.settled()
    await until(lambda: "aircraft" not in e.ctl.layers._watched, 10.0)
    quiet = len(receiver.paths())
    late = await e.ws()
    await late.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    table = await late.expect("layer_things")
    assert len(trails_of(table).get("461f2a", [])) <= 1, "after the grace the trails were dropped"
    assert len(receiver.paths()) >= quiet
    await e.stop()


@pytest.mark.slow("serves made-up feeds on the loopback through the layer's rounds")
async def test_nothing_is_asked_once_the_grace_has_passed(tmp_path: Path, look_grace: float) -> None:
    receiver = await layers_server()
    receiver.route("/tar1090/data/aircraft.json", body=sky(plane("461f2a")))
    e = Env(tmp_path / "data", web=True, settings={"map/aircraft": "receiver", "map/aircraft_host": receiver.address})
    await e.start()
    tab = await e.ws()
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    await tab.expect("layer_things")
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": False})
    await until(lambda: "aircraft" not in e.ctl.layers._watched, 10.0)
    await tab.quiet(1.0)  # a request already on its way when the look ended still arrives
    asked = len(receiver.paths())
    await tab.quiet(1.0)
    assert len(receiver.paths()) == asked
    await e.stop()


def test_a_page_is_handed_only_the_trails_of_the_things_in_its_table_thinned_where_the_way_is_straight() -> None:
    book = TrailBook()
    now = T0 + timedelta(seconds=1795)
    for i in range(360):  # every 5 s for half an hour: straight east, then a turn north at the end
        at = T0 + timedelta(seconds=5 * i)
        lat = 60.3 + (0.0 if i < 300 else (i - 300) * 0.002)
        book.grow([thing("a", 24.0 + i * 0.002, at, lat), thing("gone", 20.0 + i * 0.002, at)], at)
    [trail] = book.trails(["a"], now)
    assert trail.id == "a"
    whole = [p for p in trail.points if (now - p[2]).total_seconds() <= layerthing.TRAIL_WHOLE_SEC]
    assert len(whole) == 13, "the last minute whole"
    older = trail.points[: len(trail.points) - len(whole)]
    assert len(older) <= 4, "a straight leg is its two ends and the bend"
    assert older[0][2] == T0, "the trail still begins where it began"


@pytest.mark.slow("serves made-up feeds on the loopback through the layer's rounds")
def test_the_first_table_for_three_hundred_aircraft_after_half_an_hour_is_bounded() -> None:
    import json

    from neoaprs.web.layerfeed import table_message

    book = TrailBook()
    now = T0 + timedelta(seconds=1795)
    for i in range(360):
        at = T0 + timedelta(seconds=5 * i)
        # every aircraft circling: the worst case for the bends
        book.grow(
            [
                thing(f"{n:06x}", 24.0 + 0.2 * math.cos(i / 20 + n), at, 60.0 + 0.1 * math.sin(i / 20 + n))
                for n in range(LIMIT)
            ],
            at,
        )
    things = tuple(thing(f"{n:06x}", 24.0, now) for n in range(LIMIT))
    table = layerthing.LayerTable("aircraft", "receiver", False, things, book.trails([t.id for t in things], now))
    size = len(json.dumps(table_message(table, now)))
    assert size < 750_000, size
