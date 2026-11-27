"""The satellites layer on a whole daemon with a fixed clock and the fake server's satellites file:
a page that looks gets the marks, the pass and the Doppler of the card it has open; a page that does
not look makes the daemon ask and send nothing."""

from pathlib import Path
from typing import Any

import pytest

from neoaprs.clock import utc
from neoaprs.services.satellites import ENV_URL
from tests.support.clock import FixedClock
from tests.support.env import Env
from tests.support.fakelayers import SATELLITES_PATH, layers_server, satellites_file

DURING_PASS = utc(2026, 11, 28, 12, 5, 0)  # the ISS is up over Helsinki: 12:03:44 to 12:13:06
HELSINKI = {"station/lat": "60.17", "station/lon": "24.94"}


def told(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in messages if m["type"] == "satellites"]


async def test_a_page_that_looks_gets_every_mark_and_its_card_with_the_pass_and_the_doppler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await layers_server()
    server.route(SATELLITES_PATH, body=satellites_file())
    monkeypatch.setenv(ENV_URL, server.url + SATELLITES_PATH)
    e = Env(tmp_path / "data", clock=FixedClock(DURING_PASS), web=True, settings=HELSINKI)
    await e.start()
    tab = await e.ws()
    await tab.expect("state", "stations")
    await tab.send({"cmd": "satellite_look", "on": True, "cards": [25544]})
    await tab.until(lambda: any(m["cards"] for m in told(tab.messages)), 10.0)
    message = next(m for m in told(tab.messages) if m["cards"])
    assert message["at"] == "2026-11-28T12:05:00Z" and len(message["satellites"]) == 10
    iss = next(one for one in message["satellites"] if one["id"] == 25544)
    assert iss["name"] == "ISS" and len(iss["points"]) == 12
    (card,) = message["cards"]
    assert card["next_pass"]["rise"] == "2026-11-28T12:03:44Z" and card["next_pass"]["set"] == "2026-11-28T12:13:06Z"
    assert 14 < card["next_pass"]["max_el_deg"] < 16
    down = card["looks"][0]["down_hz"][0]
    assert card["looks"][0]["at"] == "2026-11-28T12:05:00Z" and 5000 < down < 10000, "approaching, heard above"
    tune = card["downlinks"][0]
    assert tune["hz"] == 437825000 and tune["rise_hz"] > tune["hz"] > tune["set_hz"]
    assert card["path"] == "" and card["mode"] == "afsk1200"
    assert server.paths() == [SATELLITES_PATH] and (tmp_path / "data" / "satellites.json").exists()
    await tab.send({"cmd": "satellite_look", "on": True, "cards": []})
    await tab.until(lambda: told(tab.messages)[-1]["cards"] == [], 10.0)
    await e.stop()


async def test_with_the_layer_off_nothing_is_asked_or_sent_and_switching_it_off_stops_the_rounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await layers_server()
    server.route(SATELLITES_PATH, body=satellites_file())
    monkeypatch.setenv(ENV_URL, server.url + SATELLITES_PATH)
    e = Env(tmp_path / "data", clock=FixedClock(DURING_PASS), web=True, settings=HELSINKI)
    await e.start()
    tab = await e.ws()
    await tab.expect("state", "stations")
    await tab.quiet(0.5)
    assert server.paths() == [] and told(tab.messages) == []
    await tab.send({"cmd": "satellite_look", "on": True, "cards": []})
    await tab.until(lambda: len(told(tab.messages)) >= 1, 10.0)
    await tab.send({"cmd": "satellite_look", "on": False, "cards": []})
    await tab.until(lambda: e.ctl.satellites.view is not None and not e.server.api.topics.satellites.pages(), 10.0)
    sent = len(told(tab.messages))
    assert e.server is not None
    await tab.quiet(0.5)
    assert len(told(tab.messages)) == sent and server.paths() == [SATELLITES_PATH]
    await e.stop()
