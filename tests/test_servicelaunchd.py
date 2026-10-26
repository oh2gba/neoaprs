"""The macOS service (neoaprs/cli/servicelaunchd.py) where tests/test_service.py does not look: the agent's real place, a system with no launchctl, an agent that is there already, a launchd that will not load it, and a
remove with nothing to remove. `launchctl` is a record of what it was asked."""
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs.cli import servicecmd, servicelaunchd

PLAIST = "eu.oh2gba.neoaprs.plist"


class Launchctl:
    """`subprocess.run` as the module sees it: the program is there (or not), and answers with a code."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
        self.calls: list[list[str]] = []
        self.present = True
        self.code = 0
        self.home = home
        monkeypatch.setattr(servicelaunchd, "subprocess", SimpleNamespace(run=self.run))
        monkeypatch.setattr(servicelaunchd, "domain", lambda: "gui/501")
        monkeypatch.setattr(Path, "home", lambda: home)

    def run(self, argv: list[str], **kwargs: object) -> SimpleNamespace:
        if not self.present:
            raise FileNotFoundError("launchctl")
        self.calls.append(argv)
        return SimpleNamespace(returncode=self.code)

    @property
    def plist(self) -> Path:
        return self.home / "Library" / "LaunchAgents" / PLAIST


@pytest.fixture
def mac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Launchctl:
    return Launchctl(monkeypatch, tmp_path / "home")


def plan_in(tmp_path: Path) -> servicecmd.Plan:
    return servicecmd.Plan("/usr/bin/python3", tmp_path / "data")


def test_the_agent_lives_in_the_launch_agents_of_the_users_library(mac: Launchctl) -> None:
    assert servicelaunchd.plist_path() == mac.plist


def test_a_system_with_no_launchctl_is_told_it_is_not_macos_and_has_no_agent_loaded(mac: Launchctl, capsys: pytest.CaptureFixture[str]) -> None:
    mac.present = False
    assert servicelaunchd.launchctl("bootout", "gui/501/x") == -1 and "this is not macOS" in capsys.readouterr().out
    assert servicelaunchd.loaded() is False


def test_an_agent_that_is_there_with_the_same_content_is_not_written_again(mac: Launchctl, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = plan_in(tmp_path)
    assert servicelaunchd.install(plan) == 0 and "wrote" in capsys.readouterr().out
    before = mac.plist.stat().st_mtime_ns
    assert servicelaunchd.install(plan) == 0 and "wrote" not in capsys.readouterr().out
    assert mac.plist.stat().st_mtime_ns == before and not mac.plist.with_name(PLAIST + ".new").exists()
    assert plistlib.loads(mac.plist.read_bytes())["Label"] == servicelaunchd.LABEL


def test_a_launchd_that_does_not_load_the_agent_says_how_to_try_by_hand(mac: Launchctl, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mac.code = 5
    assert servicelaunchd.install(plan_in(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "launchctl did not load the agent; try: launchctl bootstrap gui/501 " + mac.plist.as_posix() in out and "runs and starts at login" not in out


def test_removing_what_was_never_installed_unloads_nothing_and_deletes_nothing_and_says_the_service_is_gone(mac: Launchctl, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert servicelaunchd.remove(plan_in(tmp_path)) == 0
    assert mac.calls == [["launchctl", "bootout", "gui/501/eu.oh2gba.neoaprs"]]
    out = capsys.readouterr().out
    assert "no longer a service" in out and "removed" not in out
