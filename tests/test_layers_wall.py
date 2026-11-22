"""Tests for the wall round the traffic layers on a whole daemon: aircraft reach the page and appear
nowhere in the station book, packets, `stations` topic or database.
"""

import sqlite3
from pathlib import Path

import pytest

from neoaprs import nodevices
from neoaprs.store import DB_NAME
from tests.support.env import Env
from tests.support.fakelayers import layers_server
from tests.test_layers import plane, sky
from tests.test_layers_radarcape import PLACE, cape, cape_row

IDS = ("4a0b1c", "4a0b1d", "~2f0c1a")


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for
    every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")


def readsb_file() -> tuple[str, bytes]:
    return "/tar1090/data/aircraft.json", sky(
        plane(IDS[0], flight="FIN7AB"),
        plane(IDS[1], r="OH-LZA", lat=60.18, lon=24.95),
        plane(IDS[2], lat=59.0, lon=20.0),
    )


def radarcape_list() -> tuple[str, bytes]:
    return PLACE, cape(
        cape_row(IDS[0], fli="FIN7AB"),
        cape_row(IDS[1], fli=None, reg="OH-LZA", lat=60.18, lon=24.95),
        cape_row(IDS[2], fli=None, lat=59.0, lon=20.0),
    )


@pytest.mark.parametrize("source", ["receiver", "radarcape"])
async def test_the_aircraft_of_a_receiver_reach_the_page_and_nothing_else(
    source: str, tmp_path: Path, under_the_switch: None
) -> None:
    receiver = await layers_server()
    path, body = readsb_file() if source == "receiver" else radarcape_list()
    receiver.route(path, body=body)
    e = Env(tmp_path / "data", web=True, settings={"map/aircraft": source, "map/aircraft_host": receiver.address})
    await e.start()
    tab = await e.ws()
    await tab.expect("state", "stations")
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    await tab.until(lambda: any(m["type"] == "layer_things" and len(m["things"]) == 3 for m in tab.messages), 10.0)
    await tab.quiet(0.5)
    assert {t["id"] for m in tab.messages if m["type"] == "layer_things" for t in m["things"]} == set(IDS)
    # (compared case-blind: a leak may well write a hex in capitals, as a call is written)
    names = {name.lower() for name in ("FIN7AB", "OH-LZA", *IDS)}

    def leaks(text: str) -> bool:
        return any(name in text.lower() for name in names)

    assert not any(leaks(station.call) for station in e.ctl.stationbook.stations()), "the station book"
    assert not leaks(repr(tab.topics["stations"])) and not leaks(repr(tab.topics["packets"])), (
        "the topics stations and packets"
    )
    assert e.server is not None and not leaks(repr(e.server.api.topics.window.whole())), "the page's packets"
    assert await e.ctl.packetlog.count() == 0
    await e.settled()
    await e.stop()
    db = sqlite3.connect(tmp_path / "data" / DB_NAME)
    try:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        assert tables
        for table in tables:
            for row in db.execute(f'SELECT * FROM "{table}"'):
                assert not leaks(repr(row)), f"the table {table}: {row!r}"
    finally:
        db.close()
