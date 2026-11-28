"""Ships from AISStream on a whole daemon, against the stand-in of tests/support/fakeaisstream.py:
the subscription, ships on the wire, a refused key, the layer switched off, a new Radius, a lost
or stalled connection, and the key kept from the page, the log and the support file."""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from neoaprs import nodevices
from neoaprs.aisstream import boxes
from neoaprs.config import Config
from neoaprs.configlayers import MASK
from neoaprs.services import layeraisstream
from neoaprs.services.layerasked import SourceContext
from tests.support.env import Env, until
from tests.support.fakeaisstream import KEY, FakeAisStream, aisstream, position, static
from tests.test_scripts import load_script

WRONG_KEY = "ffffeeeeddddccccbbbbaaaa9999888877776666"  # made up as well


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(nodevices.ENV, "1")


async def started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str = KEY, **more: str
) -> tuple[Env, Any, FakeAisStream]:
    server = await aisstream()
    monkeypatch.setenv("NEOAPRS_AISSTREAM_URL", server.url)
    e = Env(tmp_path / "data", web=True, settings={"map/ships": "aisstream", "map/ships_key": key, **more})
    await e.start()
    tab = await e.ws()
    await tab.expect("state", "map")
    return e, tab, server


def ships(tab: Any) -> list[dict[str, Any]]:
    told = [m for m in tab.messages if m["type"] == "layer_things" and m["layer"] == "ships"]
    return told[-1]["things"] if told else []


def at(e: Env) -> str:
    return e.now().strftime("%Y-%m-%d %H:%M:%S")


async def test_a_page_that_looks_gets_the_ships_of_the_box_round_the_radius(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    e, tab, server = await started(tmp_path, monkeypatch, **{"map/radius_km": "100"})
    assert server.connections == 0, "nothing is asked while no page looks"
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await until(lambda: server.subscriptions, 15.0)
    first = server.subscriptions[0]
    assert first.key == KEY and first.after_sec < 3.0
    assert [[tuple(c) for c in box] for box in first.boxes] == [list(box) for box in boxes(60.17, 24.94, 100)]
    assert "PositionReport" in first.types and "ShipStaticData" in first.types
    assert server.compressed, "permessage-deflate was asked for"
    server.send(
        static(230111000, "AURA", 70, "ROSTOCK", at(e)),
        position(230111000, 60.1, 24.9, at(e), sog=10.0, cog=80.0, heading=79),
        position(230222000, 60.3, 25.1, at(e), sog=0.0, cog=360.0),
        position(230333000, 58.0, 20.0, at(e)),  # outside the Radius
    )
    await tab.until(lambda: len(ships(tab)) == 2, 15.0)
    aura = next(t for t in ships(tab) if t["id"] == "230111000")
    assert (aura["name"], aura["destination"], aura["ship_type"]) == ("AURA", "ROSTOCK", 70)
    assert (aura["course_deg"], aura["heading_deg"], round(aura["speed_kmh"], 1)) == (80, 79, 18.5)
    told = [m for m in tab.messages if m["type"] == "layer_things" and m["things"]][-1]
    assert (told["source"], told["away"]) == ("aisstream", False)
    assert server.connections == 1
    await e.stop()


async def test_a_wrong_key_shows_the_refused_state_and_is_not_tried_again_soon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(layeraisstream, "AIS_RETRY_SEC", (0.2, 1.0))
    e, tab, server = await started(tmp_path, monkeypatch, key=WRONG_KEY)
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await tab.until(lambda: tab.topics["map"]["layers"][1]["problem"] == "key_refused", 15.0)
    await tab.until(lambda: any(m["type"] == "layer_things" and m["away"] for m in tab.messages))
    await tab.quiet(1.5)
    assert server.connections == layeraisstream.SILENT_CLOSES, "closed at once without a word, then not again soon"
    assert WRONG_KEY not in caplog.text
    await tab.send({"cmd": "set_config", "values": {"map/ships_key": KEY}})
    await tab.until(lambda: tab.topics["map"]["layers"][1]["problem"] == "", 10.0)
    await until(
        lambda: server.connections == layeraisstream.SILENT_CLOSES + 1 and server.subscriptions[-1].key == KEY, 15.0
    )
    assert KEY not in caplog.text
    await e.stop()


async def test_a_refusal_in_words_is_taken_at_once_and_its_words_are_logged_without_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None, caplog: pytest.LogCaptureFixture
) -> None:
    e, tab, server = await started(tmp_path, monkeypatch, key=WRONG_KEY)
    server.refusal = {"error": f"Api Key {WRONG_KEY} Is Not Valid"}
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await tab.until(lambda: tab.topics["map"]["layers"][1]["problem"] == "key_refused", 15.0)
    assert server.connections == 1
    assert "refused the key" in caplog.text and WRONG_KEY not in caplog.text
    await e.stop()


def problem(tab: Any) -> str:
    return str(tab.topics["map"]["layers"][1]["problem"])


async def test_a_refused_key_is_tried_again_by_itself_and_a_connection_that_is_taken_clears_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    monkeypatch.setattr(layeraisstream, "AIS_RETRY_SEC", (0.2, 1.0))
    monkeypatch.setattr(layeraisstream, "REFUSED_RETRY_SEC", (0.5, 1.0))
    e, tab, server = await started(tmp_path, monkeypatch, key=WRONG_KEY)
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await tab.until(lambda: problem(tab) == "key_refused", 15.0)
    await until(lambda: server.connections > layeraisstream.SILENT_CLOSES, 15.0)
    assert problem(tab) == "key_refused", "still refused while the server refuses"
    server.key = WRONG_KEY  # the service now takes it
    await tab.until(lambda: problem(tab) == "", 15.0)
    await e.stop()


async def test_saving_the_same_key_again_tries_it_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    monkeypatch.setattr(layeraisstream, "AIS_RETRY_SEC", (0.2, 1.0))
    e, tab, server = await started(tmp_path, monkeypatch, key=WRONG_KEY)
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await tab.until(lambda: problem(tab) == "key_refused", 15.0)
    server.key = WRONG_KEY
    await tab.send({"cmd": "set_config", "values": {"map/ships_key": WRONG_KEY}})
    await tab.until(lambda: problem(tab) == "", 15.0)
    await until(lambda: server.subscriptions[-1].key == WRONG_KEY and server.open == 1, 15.0)
    await e.stop()


async def test_connections_reset_or_stalled_before_the_confirmation_are_an_outage_not_a_refused_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    monkeypatch.setattr(layeraisstream, "AIS_RETRY_SEC", (0.1, 0.2))
    monkeypatch.setattr(layeraisstream, "STALL_SEC", 1.0)
    monkeypatch.setattr(layeraisstream, "PING_SEC", 0.5)
    e, tab, server = await started(tmp_path, monkeypatch)
    server.reset = True
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await until(lambda: server.connections >= 2 * layeraisstream.SILENT_CLOSES, 30.0)
    assert problem(tab) == ""
    server.reset, server.stalled = False, True
    seen = server.connections
    await until(lambda: server.connections >= seen + layeraisstream.SILENT_CLOSES + 1, 40.0)
    assert problem(tab) == ""
    server.stalled = False
    await until(lambda: server.open == 1 and server.subscriptions[-1].key == KEY, 15.0)
    await e.stop()


async def test_the_connection_is_closed_when_the_page_stops_looking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    e, tab, server = await started(tmp_path, monkeypatch)
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await until(lambda: server.open == 1 and server.subscriptions, 15.0)
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": False})
    await until(lambda: server.open == 0, 15.0)
    await tab.quiet(1.0)
    assert server.connections == 1, "nothing is asked while the layer is off"
    await e.stop()


async def test_a_new_radius_is_one_new_subscription_on_the_same_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    e, tab, server = await started(tmp_path, monkeypatch, **{"map/radius_km": "100"})
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await until(lambda: len(server.subscriptions) == 1, 15.0)
    await tab.send({"cmd": "set_config", "values": {"map/radius_km": "250"}})
    await until(lambda: len(server.subscriptions) == 2, 15.0)
    await tab.quiet(2.5)
    assert len(server.subscriptions) == 2 and server.connections == 1
    assert [[tuple(c) for c in box] for box in server.subscriptions[1].boxes] == [
        list(box) for box in boxes(60.17, 24.94, 250)
    ]
    await e.stop()


async def test_a_lost_or_stalled_connection_is_made_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    monkeypatch.setattr(layeraisstream, "STALL_SEC", 2.0)
    monkeypatch.setattr(layeraisstream, "PING_SEC", 0.5)
    monkeypatch.setattr(layeraisstream, "AIS_RETRY_SEC", (0.2, 1.0))
    e, tab, server = await started(tmp_path, monkeypatch)
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await until(lambda: server.open == 1 and server.subscriptions, 15.0)
    server.drop()
    await until(lambda: server.connections == 2 and server.open == 1, 15.0)
    server.stalled = True
    await until(lambda: server.closed >= 2 and server.connections >= 3, 20.0)
    await e.stop()


async def test_the_key_never_reaches_the_page_and_the_mask_sent_back_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    e, tab, _server = await started(tmp_path, monkeypatch)
    config = tab.topics["config"]
    assert config["values"]["map/ships_key"] == MASK
    assert KEY not in json.dumps(tab.messages)
    await tab.send({"cmd": "set_config", "values": {"map/ships_key": MASK, "map/radius_km": "200"}})
    await until(lambda: e.ctl.config.map_radius_km == 200, 10.0)
    assert e.ctl.config.map_ships_key == KEY, "the mask sent back keeps the key"
    await e.stop()


async def test_without_a_local_stand_in_nothing_goes_to_aisstream(
    tmp_path: Path, under_the_switch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEOAPRS_AISSTREAM_URL", "wss://stream.aisstream.io/v0/stream")
    e = Env(tmp_path / "data", web=True, settings={"map/ships": "aisstream", "map/ships_key": KEY})
    await e.start()
    tab = await e.ws()
    await tab.send({"cmd": "layer_look", "layer": "ships", "on": True})
    await tab.until(lambda: any(m["type"] == "layer_things" for m in tab.messages), 10.0)
    await tab.quiet(1.0)
    assert e.ctl.layers.stream == "" and not e.ctl.layers.stream_on
    assert all(m["away"] for m in tab.messages if m["type"] == "layer_things")
    await e.stop()


async def test_the_probe_runs_the_product_source_and_never_prints_the_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = await aisstream()
    probe = load_script("aisstream-probe")

    async def feed() -> None:
        await until(lambda: server.subscriptions and server.open, 10.0)
        server.send(
            static(230111000, "AURA", 70, "ROSTOCK", "2026-11-27 12:00:00"),
            position(230111000, 60.1, 24.9, datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")),
        )

    feeding = asyncio.create_task(feed())
    assert await probe.probe(KEY, 60.17, 24.94, 100, 2.0, server.url) == 0
    await feeding
    out = capsys.readouterr().out
    assert "position reports: 1" in out and "230111000 AURA" in out and "key refused: no" in out
    assert KEY not in out


# ---- the source alone


def source(url: str = "wss://stream.aisstream.io/v0/stream") -> layeraisstream.AisStreamShips:
    ctx = SourceContext(
        "ships",
        "aisstream",
        lambda: Config(),
        lambda: (60.17, 24.94),
        None,  # type: ignore[arg-type]  # never fetches
        "1.0",
        "linux",
        lambda: datetime(2026, 11, 27, 12, 0, tzinfo=UTC),
        time.monotonic,
        True,
        "",
        None,  # type: ignore[arg-type]
        lambda: None,
        lambda: None,
        url,
    )
    return layeraisstream.AisStreamShips(ctx, KEY, url)


async def test_under_the_switch_no_connection_to_aisstream_is_even_tried(
    under_the_switch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tried: list[str] = []

    async def connect(host: str, *args: Any, **kwargs: Any) -> None:
        tried.append(host)
        raise OSError("not here")

    monkeypatch.setattr(layeraisstream.WebSocketClient, "connect", connect)
    ships = source()
    assert await ships.ask() and tried == []
    assert not ships.refused


async def test_one_ship_on_a_short_connection_does_not_reset_the_back_off(monkeypatch: pytest.MonkeyPatch) -> None:
    ships = source()

    async def short() -> bool:
        return True  # a ship came, then the server closed at once

    monkeypatch.setattr(ships, "_connection", short)
    for _ in range(3):
        await ships.ask()
    assert ships._failures == 3
