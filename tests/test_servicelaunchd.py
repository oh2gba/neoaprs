"""The macOS service (neoaprs/cli/servicelaunchd.py) beyond tests/test_service.py: the agent's real
place, no launchctl, an existing agent, a launchd that will not load it, a remove with nothing
to remove, and a daemon that refuses to start under launchd, which stays stopped.
"""

import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs.cli import servicecmd, servicelaunchd
from neoaprs.controller import Controller
from neoaprs.daemon import DATABASE_UNUSABLE
from neoaprs.instancelock import InstanceLock
from tests.support.daemonrun import InProcess, signals_restored as signals_restored

PLAIST = "eu.oh2gba.neoaprs.plist"


class Launchctl:
    """`subprocess.run` as the module sees it: the program is there (or not), and answers with a
    code."""

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


def test_a_system_with_no_launchctl_is_told_it_is_not_macos_and_has_no_agent_loaded(
    mac: Launchctl, capsys: pytest.CaptureFixture[str]
) -> None:
    mac.present = False
    assert servicelaunchd.launchctl("bootout", "gui/501/x") == -1 and "this is not macOS" in capsys.readouterr().out
    assert servicelaunchd.loaded() is False


def test_an_agent_that_is_there_with_the_same_content_is_not_written_again(
    mac: Launchctl, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = plan_in(tmp_path)
    assert servicelaunchd.install(plan) == 0 and "wrote" in capsys.readouterr().out
    before = mac.plist.stat().st_mtime_ns
    assert servicelaunchd.install(plan) == 0 and "wrote" not in capsys.readouterr().out
    assert mac.plist.stat().st_mtime_ns == before and not mac.plist.with_name(PLAIST + ".new").exists()
    assert plistlib.loads(mac.plist.read_bytes())["Label"] == servicelaunchd.LABEL


def test_a_launchd_that_does_not_load_the_agent_says_how_to_try_by_hand(
    mac: Launchctl, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mac.code = 5
    assert servicelaunchd.install(plan_in(tmp_path)) == 1
    out = capsys.readouterr().out
    assert (
        "launchctl did not load the agent; try: launchctl bootstrap gui/501 " + mac.plist.as_posix() in out
        and "runs and starts at login" not in out
    )


def test_removing_what_was_never_installed_unloads_nothing_and_deletes_nothing_and_says_the_service_is_gone(
    mac: Launchctl, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert servicelaunchd.remove(plan_in(tmp_path)) == 0
    assert mac.calls == [["launchctl", "bootout", "gui/501/eu.oh2gba.neoaprs"]]
    out = capsys.readouterr().out
    assert "no longer a service" in out and "removed" not in out


# ---- a refusal to start leaves the agent stopped; a crash is restarted


def test_the_agent_restarts_only_a_failure_and_tells_the_daemon_it_runs_under_launchd(tmp_path: Path) -> None:
    content = plistlib.loads(servicelaunchd.render(plan_in(tmp_path)))
    assert content["KeepAlive"] == {"SuccessfulExit": False}
    assert content["EnvironmentVariables"][servicelaunchd.UNDER_LAUNCHD] == "1"


@pytest.fixture
def launchd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(servicelaunchd.UNDER_LAUNCHD, "1")


async def test_another_copy_on_the_folder_ends_the_daemon_with_success_under_launchd_and_status_says_why(
    tmp_path: Path, mac: Launchctl, launchd: None, signals_restored: None, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    held = InstanceLock(data)
    held.acquire()
    try:
        assert await InProcess(data).ended() == 0, "launchd restarts every end that is not a success"
    finally:
        held.release()
    assert servicelaunchd.refusal(data) == "another NeoAPRS is running on this data folder"
    servicelaunchd.install(plan_in(tmp_path))
    capsys.readouterr()
    assert servicelaunchd.status(plan_in(tmp_path)) == 1
    assert (
        "the service is stopped because another NeoAPRS is running on this data folder; "
        "start it again with: neoaprs service install" in capsys.readouterr().out
    )
    second = InProcess(data)
    assert await second.running()
    assert servicelaunchd.refusal(data) is None, "a start that went through clears it"
    assert await second.stop() == 0


async def test_without_launchd_a_refusal_keeps_its_exit_code_and_leaves_no_note(
    tmp_path: Path, signals_restored: None
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    held = InstanceLock(data)
    held.acquire()
    try:
        assert await InProcess(data).ended() == DATABASE_UNUSABLE
    finally:
        held.release()
    assert not (data / servicelaunchd.REFUSAL_NAME).exists()


async def test_a_data_folder_that_cannot_be_made_is_a_refusal_under_launchd(
    tmp_path: Path, launchd: None, signals_restored: None
) -> None:
    (tmp_path / "file").write_text("")
    data = tmp_path / "file" / "data"
    assert await InProcess(data).ended() == 0
    assert servicelaunchd.refusal(data) == "the data folder cannot be made or used"


@pytest.mark.expects_errors
async def test_a_crash_under_launchd_is_still_a_failure_that_launchd_restarts(
    tmp_path: Path, launchd: None, signals_restored: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def crash(self: Controller) -> None:
        raise RuntimeError("a fault")

    monkeypatch.setattr(Controller, "start", crash)
    with pytest.raises(RuntimeError):
        await InProcess(tmp_path / "data").ended()
    assert not (tmp_path / "data" / servicelaunchd.REFUSAL_NAME).exists()
