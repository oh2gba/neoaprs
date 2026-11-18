"""The wall round the map's layers of traffic, for the ships, held on a whole daemon (the architecture test holds it on the imports): under the no-devices switch, with a fake AIS receiver on the loopback and then
with a fake Fintraffic on it, and a page that looks at the ships, the ships reach the page, and none of them (their MMSI, their name) is in the station book, the page's packets, the topic `stations`, or any
table of the database."""
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from neoaprs import nodevices
from neoaprs.store import DB_NAME
from tests.support import aissentences as ais
from tests.support.env import Env
from tests.support.fakeais import ais_receiver
from tests.support.fakelayers import layers_server
from tests.test_layerships import feature, locations, vessels

@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")


MMSIS = ("230111000", "230222000", "230333000")
NAMES = ("AURA", "SEA LARK", "BOTNIA")


async def assert_walled(e: Env, tab: Any, tmp_path: Path) -> None:
    names = {name.lower() for name in (*MMSIS, *NAMES)}                          # (compared case-blind: a leak may well write a name in small letters)

    def leaks(text: str) -> bool:
        return any(name in text.lower() for name in names)
    assert not any(leaks(station.call) for station in e.ctl.stationbook.stations()), "the station book"
    assert not leaks(repr(tab.topics["stations"])) and not leaks(repr(tab.topics["packets"])), "the topics stations and packets"
    assert e.server is not None and not leaks(repr(e.server.api.topics.window.whole())), "the page's packets"
    assert await e.ctl.packetlog.count() == 0
    await e.settled()
    await e.stop()
    db = sqlite3.connect(tmp_path / "data" / DB_NAME)
    try:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        assert tables
        for table in tables:
            for row in db.execute(f'SELECT * FROM "{table}"'):          # noqa: S608  (the names of the database's own tables)
                assert not leaks(repr(row)), f"the table {table}: {row!r}"
    finally:
        db.close()


async def test_the_ships_of_an_own_receiver_reach_the_page_and_nothing_else(tmp_path: Path, under_the_switch: None) -> None:
    receiver = await ais_receiver()
    e = Env(tmp_path / "data", web=True, settings={"map/ships": "receiver", "map/ships_host": receiver.address})
    await e.start()
    tab = await e.ws()
    await tab.expect("state", "stations")
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await receiver.until_connected()
    receiver.send(*ais.sentences(ais.class_a(230111000, 60.1, 24.9, sog=9.0, cog=80.0, heading=80)), *ais.sentences(ais.static_a(230111000, "AURA", 70, "ROSTOCK")),
                  *ais.sentences(ais.class_b(230222000, 60.2, 25.0)), *ais.sentences(ais.static_b(230222000, 0, "SEA LARK")), *ais.sentences(ais.class_a(230333000, 59.0, 20.0)),
                  *ais.sentences(ais.static_a(230333000, "BOTNIA", 60, "HELSINKI")))
    await tab.until(lambda: any(m["type"] == "layer_things" and m["layer"] == "ships" and len(m["things"]) == 3 and all(t["name"] for t in m["things"]) for m in tab.messages), 15.0)
    await tab.quiet(0.5)
    assert {t["id"] for m in tab.messages if m["type"] == "layer_things" and m["layer"] == "ships" for t in m["things"]} == set(MMSIS)
    await assert_walled(e, tab, tmp_path)


async def test_the_ships_of_fintraffic_reach_the_page_and_nothing_else(tmp_path: Path, under_the_switch: None, monkeypatch: pytest.MonkeyPatch) -> None:
    internet = await layers_server()
    monkeypatch.setenv("NEOAPRS_LAYERS_URL", internet.url)
    e = Env(tmp_path / "data", web=True, settings={"map/ships": "fintraffic"})
    now = e.now()
    internet.route("/api/ais/v1/locations", body=locations(feature(230111000, 60.1, 24.9, now=now), feature(230222000, 60.2, 25.0, now=now), feature(230333000, 59.9, 24.0, now=now)))
    internet.route("/api/ais/v1/vessels", body=vessels((230111000, "AURA", 70, "ROSTOCK"), (230222000, "SEA LARK", 37, ""), (230333000, "BOTNIA", 60, "HELSINKI")))
    await e.start()
    tab = await e.ws()
    await tab.expect("state", "stations")
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await tab.until(lambda: any(m["type"] == "layer_things" and m["layer"] == "ships" and m["source"] == "fintraffic" and len(m["things"]) == 3 and all(t["name"] for t in m["things"]) for m in tab.messages), 15.0)
    await tab.quiet(0.5)
    assert {t["id"] for m in tab.messages if m["type"] == "layer_things" and m["layer"] == "ships" for t in m["things"]} == set(MMSIS)
    assert json.dumps(internet.requests).count("OH2GBA") == 0, "nothing of the station was asked"
    await assert_walled(e, tab, tmp_path)
