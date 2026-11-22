"""The note the daemon keeps in its data folder while it serves the page to the network
(neoaprs-web.network): the app's tray reads it to offer the browser only while "Allow access from
the network" is on."""
from pathlib import Path

import pytest

from neoaprs.cli.logfile import NETWORK_FILE, network_is_on
from tests.support.env import Env, until

KEY = "k7m2-x9pq-4hrt"


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    """The computer's addresses are made up: nothing is asked of its network."""
    for place in ("neoaprs.web.server.lan_addresses", "neoaprs.web.secureside.lan_addresses"):
        monkeypatch.setattr(place, lambda: ["192.168.1.20"])


async def test_the_note_is_there_while_the_page_is_served_to_the_network_and_follows_the_switch(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, settings={"web/network": "true", "web/key": KEY})
    await e.start()
    assert network_is_on(tmp_path), "written when the page starts"
    page = await e.ws()
    await page.until(lambda: "config" in page.topics)
    await page.send({"cmd": "set_config", "values": {"web/network": "false"}})
    await until(lambda: not network_is_on(tmp_path))
    await page.send({"cmd": "set_config", "values": {"web/network": "true"}})
    await until(lambda: network_is_on(tmp_path))


async def test_the_note_is_not_there_while_the_page_is_on_this_computer_only(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    assert not (tmp_path / NETWORK_FILE).exists()
