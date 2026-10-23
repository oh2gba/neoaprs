"""How this copy was installed (neoaprs/versions.py `install_kind`, neoaprs/cli/installkind.py): the kind from what the process can see, with the facts faked in a folder of the test; and what the page is told of it in `hello`."""
import sys
from pathlib import Path

import pytest

from neoaprs.cli import installkind
from neoaprs.cli.installkind import DEB_PREFIX, deb_environment, detect, is_checkout, service_set, uv_tool_environment
from neoaprs.versions import INSTALL_KINDS, InstallInfo, install_kind
from tests.support.env import Env


@pytest.mark.parametrize("frozen, appimage, deb, checkout, uv_tool, kind", [
    (True, None, False, False, False, "windows-installer"),
    (True, "/x/NeoAPRS.AppImage", True, True, True, "windows-installer"),     # (a frozen program is the installer's whatever else holds)
    (False, "/home/u/NeoAPRS.AppImage", False, False, False, "appimage"),
    (False, "/home/u/NeoAPRS.AppImage", True, True, True, "appimage"),
    (False, None, True, False, False, "deb"),
    (False, None, True, True, True, "deb"),
    (False, None, False, True, False, "source"),
    (False, None, False, True, True, "source"),                               # (a clone made with `uv sync` has a uv environment too)
    (False, None, False, False, True, "uv-tool"),
    (False, None, False, False, False, "pip"),
])
def test_the_kind_follows_what_the_process_can_see_in_this_order(frozen: bool, appimage: str | None, deb: bool, checkout: bool, uv_tool: bool, kind: str) -> None:
    assert install_kind(frozen, appimage, deb, checkout, uv_tool) == kind
    assert kind in INSTALL_KINDS


def test_there_are_six_kinds() -> None:
    assert INSTALL_KINDS == ("windows-installer", "appimage", "deb", "uv-tool", "pip", "source")


def test_the_deb_is_the_python_of_opt_neoaprs(tmp_path: Path) -> None:
    assert DEB_PREFIX == "/opt/neoaprs"
    assert deb_environment("/opt/neoaprs")
    assert not deb_environment("/opt/neoaprs/lib")
    assert not deb_environment("/usr")
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    assert deb_environment(str(tmp_path / "link"), str(tmp_path / "real")), "a prefix that is a link to the folder is the folder"


def test_a_uv_tool_environment_has_the_receipt_or_is_in_the_tool_folder(tmp_path: Path) -> None:
    tool = tmp_path / "share" / "uv" / "tools" / "neoaprs"
    tool.mkdir(parents=True)
    assert uv_tool_environment(str(tool), {})
    plain = tmp_path / "venvs" / "neoaprs"
    plain.mkdir(parents=True)
    assert not uv_tool_environment(str(plain), {})
    (plain / "uv-receipt.toml").write_text("[tool]\n", encoding="utf-8")
    assert uv_tool_environment(str(plain), {})


def test_the_tool_folder_can_be_moved_with_uv_tool_dir(tmp_path: Path) -> None:
    moved = tmp_path / "mytools"
    env = moved / "neoaprs"
    env.mkdir(parents=True)
    assert uv_tool_environment(str(env), {"UV_TOOL_DIR": str(moved)})
    assert not uv_tool_environment(str(env), {"UV_TOOL_DIR": str(tmp_path / "elsewhere")})


def test_a_checkout_is_a_folder_with_a_git_folder_or_file(tmp_path: Path) -> None:
    assert not is_checkout(None)
    assert not is_checkout(tmp_path)
    (tmp_path / ".git").mkdir()
    assert is_checkout(tmp_path)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: ../.git/worktrees/wt\n", encoding="utf-8")
    assert is_checkout(worktree)


def test_detect_puts_the_facts_together_and_names_the_appimage_file_only_for_an_appimage(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    image = "/home/u/NeoAPRS-0.3.0-x86_64.AppImage"
    assert detect(False, image, str(tmp_path / "venv"), None, True, {}) == InstallInfo("appimage", image, True)
    assert detect(False, None, str(tmp_path / "venv"), tmp_path, False, {}) == InstallInfo("source", "", False)
    assert detect(True, None, "C:/NeoAPRS", None, True, {}) == InstallInfo("windows-installer", "", True)
    assert detect(False, None, str(tmp_path / "venv"), None, False, {}) == InstallInfo("pip", "", False)


@pytest.mark.parametrize("machine, arch", [("x86_64", "amd64"), ("AMD64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64"), ("armv7l", ""), ("riscv64", "")])
def test_a_deb_install_names_the_architecture_of_its_package_and_no_other_kind_does(machine: str, arch: str, tmp_path: Path) -> None:
    assert detect(False, None, DEB_PREFIX, None, True, {}, machine) == InstallInfo("deb", "", True, arch)
    assert detect(False, None, str(tmp_path / "venv"), None, True, {}, machine) == InstallInfo("pip", "", True, "")


def test_a_service_is_what_the_systems_own_backend_says(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Backend:
        answer: object = (True, "the user unit")

        def installed(self, plan: object) -> object:
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer

    backend = Backend()
    monkeypatch.setattr(installkind.servicecmd, "backend_for", lambda system: backend)
    assert service_set(tmp_path)
    backend.answer = (False, "no user unit")
    assert not service_set(tmp_path)
    backend.answer = OSError("the registry cannot be read")
    assert not service_set(tmp_path), "a service that cannot be looked at is no service"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the unit is a Linux thing")
def test_a_systemd_unit_the_install_wrote_is_a_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert not service_set(tmp_path)
    unit = tmp_path / "config" / "systemd" / "user" / "neoaprs.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("# Generated by `neoaprs service install`; changes are lost\n[Service]\n", encoding="utf-8")
    assert service_set(tmp_path)
    unit.write_text("[Service]\n", encoding="utf-8")
    assert not service_set(tmp_path), "a unit of somebody else's is not ours"


async def test_a_page_is_told_how_the_daemon_was_installed_in_hello(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.install = InstallInfo("appimage", "/home/u/NeoAPRS-0.3.0-x86_64.AppImage", True)
    await e.start()
    page = await e.ws()
    hello = await page.expect("hello")
    assert hello["install"] == {"kind": "appimage", "appimage": "/home/u/NeoAPRS-0.3.0-x86_64.AppImage", "service": True, "arch": ""}
    await e.stop()


async def test_the_architecture_of_a_deb_is_in_hello(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.install = InstallInfo("deb", "", True, "arm64")
    await e.start()
    hello = await (await e.ws()).expect("hello")
    assert hello["install"] == {"kind": "deb", "appimage": "", "service": True, "arch": "arm64"}
    await e.stop()


async def test_a_daemon_made_without_saying_is_a_plain_install(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    hello = await (await e.ws()).expect("hello")
    assert hello["install"] == {"kind": "pip", "appimage": "", "service": False, "arch": ""}
    await e.stop()
