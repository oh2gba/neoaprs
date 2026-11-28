"""NeoAPRS in a container image (packaging/container/): the install kind `container`, which the image
says by NEOAPRS_CONTAINER=1; the page always on the network with its access key, the key told once on
stderr, the host names of NEOAPRS_ALLOWED_HOSTS, no service, and its own platform in the count."""

import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.cli import servicecmd
from neoaprs.cli.installkind import DEB_PREFIX, container_environment, detect, simulated
from neoaprs.controller import Controller
from neoaprs.services.selfinstall import installer_for
from neoaprs.updateasset import asset_name
from neoaprs.versions import InstallInfo, install_kind, platform_name
from neoaprs.web import access as web_access
from tests.support.env import Env

CONTAINER = InstallInfo("container")
KEY_LINE = "the access key of the page is"


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: ["172.17.0.2"])
    monkeypatch.setattr("neoaprs.web.server.name_loopbacks", lambda: [])


def test_the_image_says_container_and_that_wins_over_the_package_it_was_made_from() -> None:
    assert container_environment({"NEOAPRS_CONTAINER": "1"})
    for value in ("", "0", "yes", "true"):
        assert not container_environment({"NEOAPRS_CONTAINER": value}), value
    assert not container_environment({})
    assert install_kind(False, None, True, False, False, container=True) == "container"
    assert detect(False, None, DEB_PREFIX, None, False, {"NEOAPRS_CONTAINER": "1"}, "aarch64") == CONTAINER
    assert detect(False, None, DEB_PREFIX, None, False, {}, "aarch64") == InstallInfo("deb", "", False, "arm64")
    assert simulated("container") == CONTAINER


def test_a_container_is_counted_as_its_own_platform() -> None:
    assert platform_name("linux", "x86_64", False, container=True) == "linux-container"
    assert platform_name("linux", "aarch64", False, container=True) == "linux-container"
    assert platform_name("linux", "aarch64", False) == "linux-arm"


def test_a_daemon_in_a_container_asks_the_version_page_as_linux_container_and_is_an_installation(
    tmp_path: Path,
) -> None:
    ctl = Controller(tmp_path, install=CONTAINER)
    assert ctl.updatecheck.platform == "linux-container" and ctl.updatecheck.developer is False


def test_an_image_is_never_updated_in_place() -> None:
    assert asset_name("container", "0.28.0", "amd64") is None
    assert installer_for(CONTAINER, Path("/data"), lambda argv: None, {}, platform="linux") is None


def test_service_install_is_refused_in_a_container_with_one_plain_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEOAPRS_CONTAINER", "1")
    for action in ("install", "remove", "status"):
        assert servicecmd.main([action, "--data", str(tmp_path)], platform="linux") == 1
        said = capsys.readouterr()
        assert said.out == "" and said.err.count("\n") == 1 and "container" in said.err, said
    assert not (tmp_path / ".config").exists()


async def test_in_a_container_the_page_is_on_the_network_with_a_key_told_once_and_the_switch_cannot_close_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)
    e = Env(tmp_path, web=True, install=CONTAINER)
    await e.start()
    assert e.server is not None and e.server.address == "" and e.ctl.config.web_network is True
    key = e.ctl.config.web_key
    assert key and await e.ctl.store.setting("web/key") == key
    told = capsys.readouterr().err
    assert told.count(KEY_LINE) == 1 and key in told
    assert key not in caplog.text, "the key stays out of the log, which Send logs hands on"
    assert (await e.fetch("/access")).code == 401, "a device of the network logs in with the key"
    assert await e.ctl.change_config(lambda c: replace(c, web_network=False))
    assert e.ctl.config.web_network is True and e.server.address == ""
    await e.stop()
    again = Env(tmp_path, web=True, install=CONTAINER)
    await again.start()
    assert again.ctl.config.web_key == key and KEY_LINE not in capsys.readouterr().err, "told at the first start only"


async def test_the_names_of_neoaprs_allowed_hosts_open_the_page_in_a_container_and_nowhere_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("NEOAPRS_ALLOWED_HOSTS", "mynas.local, radio.example.org")
    e = Env(tmp_path / "in", web=True, install=CONTAINER)
    await e.start()
    for host in ("mynas.local", "mynas.local:7303", "radio.example.org"):
        assert (await e.fetch("/", headers={"Host": host})).code == 200, host
    assert (await e.fetch("/", headers={"Host": "evil.example"})).code == 403
    await e.stop()
    native = Env(tmp_path / "out", web=True, settings={"web/network": "true", "web/key": "k7m2-x9pq-4hrt"})
    await native.start()
    assert (await native.fetch("/", headers={"Host": "mynas.local"})).code == 403
