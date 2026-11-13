"""What a page of another device may not do (neoaprs/web/confighandlers.py, `LOCAL_ONLY` of neoaprs/web/access.py): change a setting that names a program or an address the daemon runs or fetches from,
and run the alert's Test. A session that left this computer works the radio, not the computer. As in tests/test_web_access.py, a request is made to look as if it came from another device by saying that
no address is the loopback (`away`); such a device logs in with the key, as a phone does."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.web import access as web_access
from neoaprs.web.access import LOCAL_ONLY
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.alertcmd import writing
from tests.support.env import Env, until
from tests.support.wsclient import WsClient

KEY = "k7m2-x9pq-4hrt"
NETWORK = {"web/network": "true", "web/key": KEY}
NEW_VALUES = {                                             # a value for each, other than the one in force, that the setting itself takes
    "messages/alert_command": "exit 0",
    "update/url": "https://updates.example.org/version.json",
    "map/source": "https://maps.example.org/planet.pmtiles",
    "web/allowed_hosts": "aprs.example.org",
}


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    """The address of this computer on the network is a made-up one: the system is not asked."""
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: ["192.168.1.20"])


@pytest.fixture
def away(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request comes from an address that is not this computer's."""
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


async def served(tmp_path: Path) -> Env:
    e = Env(tmp_path, web=True, settings=NETWORK)
    await e.start()
    return e


async def ready(page: WsClient) -> WsClient:
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return page


async def from_afar(e: Env) -> WsClient:
    """A page of another device that has logged in with the key."""
    answer = await e.fetch("/access", method="POST", body=json.dumps({"key": KEY}))
    assert answer.code == 204
    return await ready(await e.ws(cookie=answer.headers["Set-Cookie"].split(";", 1)[0]))


def test_the_list_is_the_settings_that_name_a_program_or_an_address() -> None:
    assert LOCAL_ONLY == NEW_VALUES.keys()


async def test_a_page_of_another_device_is_told_so_and_this_computer_is_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = await served(tmp_path)
    here = await e.ws()
    assert (await here.expect("hello"))["local"] is True
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)
    there = await from_afar(e)
    assert there.of("hello")[0]["local"] is False
    await e.stop()


@pytest.mark.parametrize("key", sorted(NEW_VALUES))
async def test_a_page_of_another_device_cannot_change_a_setting_that_names_a_program_or_an_address(tmp_path: Path, away: None, key: str) -> None:
    e = await served(tmp_path)
    page = await from_afar(e)
    before, stored = e.ctl.config, await e.ctl.store.settings()
    await page.send({"cmd": "set_config", "values": {key: NEW_VALUES[key], "map/radius_km": "200"}})
    error = await page.expect("error")
    assert (error["cmd"], error["key"], error["code"]) == ("set_config", key, "setting.local_only")
    assert error["text"] == f"set_config: {key}: only a page on the computer NeoAPRS runs on can do this"
    assert e.ctl.config == before and await e.ctl.store.settings() == stored, "nothing is stored, not even the other value of the same change"
    await e.stop()


async def test_a_page_of_another_device_cannot_run_the_alert_test(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path)
    out = tmp_path / "ran.txt"
    assert await e.ctl.save_config(replace(e.ctl.config, messages_alert_command=writing(out)))
    page = await from_afar(e)
    await page.send({"cmd": "alert_test"})
    error = await page.expect("error")
    assert (error["cmd"], error["key"], error["code"]) == ("alert_test", "messages/alert_command", "setting.local_only")
    await page.quiet(0.3)
    assert not out.exists() and page.of("alert_result") == [], "nothing ran"
    await e.stop()


async def test_a_page_of_another_device_changes_every_other_setting_and_switches_the_alert(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path)
    page = await from_afar(e)
    command = e.ctl.config.messages_alert_command
    await page.send({"cmd": "set_config", "values": {"map/radius_km": "200", "messages/alert": "false", "messages/alert_command": command}})
    await until(lambda: e.ctl.config.map_radius_km == 200 and e.ctl.config.messages_alert is False)
    assert e.ctl.config.messages_alert_command == command, "a value that is the one in force changes nothing and is let through"
    assert page.of("error") == []
    await e.stop()


async def test_this_computer_changes_them_and_runs_the_test(tmp_path: Path) -> None:
    e = await served(tmp_path)
    page = await ready(await e.ws())
    out = tmp_path / "ran.txt"
    await page.send({"cmd": "set_config", "values": {**NEW_VALUES, "messages/alert_command": writing(out)}})
    await until(lambda: e.ctl.config.to_data()["web/allowed_hosts"] == NEW_VALUES["web/allowed_hosts"])
    data = e.ctl.config.to_data()
    assert {key: data[key] for key in NEW_VALUES} == {**NEW_VALUES, "messages/alert_command": writing(out)}
    await page.send({"cmd": "alert_test"})
    assert (await page.expect("alert_result"))["ok"] is True
    assert out.exists() and page.of("error") == []
    await e.stop()
