"""`neoaprs app` end to end with the shell and the daemon replaced (tests/support/fakeshell.py, a scripted `open_session`): the second app, the fallbacks when no window can be had, a page that does not come up, a shell that
fails to start, and `--quit`. The real daemon is tests/test_desktop_session.py, the real toolkits are tests/test_desktop_qt.py and tests/test_desktop_winshell.py."""
import sys
import threading
import types
from pathlib import Path

import pytest

from neoaprs.desktop import cmd
from neoaprs.desktop.session import NoPage, Session
from neoaprs.desktop.shell import Choice
from neoaprs.desktop.single import SingleApp
from tests.support import fakeshell

PAGE = "http://127.0.0.1:7303/"
FAKE = Choice("tests.support.fakeshell", True)


class World:
    """What the app was asked to do outside itself: the browser, the messages for the user, the daemons it opened a session on."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.data = tmp_path / "data"
        self.data.mkdir()
        self.browser: list[str] = []
        self.said: list[str] = []
        self.sessions: list[Path] = []
        self.owned = True
        self.page_fails = False
        self.choice = FAKE
        fakeshell.FRAMES.clear()
        fakeshell.STEPS.clear()
        monkeypatch.setattr(cmd.webbrowser, "open", lambda url: self.browser.append(url) or True)
        monkeypatch.setattr(cmd, "open_session", self.open_session)
        monkeypatch.setattr(cmd.shell, "choose", lambda: self.choice)
        monkeypatch.setattr(cmd, "autostart_for", lambda data: None)
        monkeypatch.setattr(cmd.opencmd, "tell_the_user", self.said.append)
        monkeypatch.setattr(cmd, "say", self.said.append)

    def open_session(self, data: Path, timeout: float = 60.0) -> Session:
        self.sessions.append(data)
        if self.page_fails:
            raise NoPage("no page came up")
        return Session(data, PAGE, self.owned)

    def run(self, *flags: str) -> int:
        return cmd.run(cmd.parser().parse_args(["--data", str(self.data), *flags]))


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, monkeypatch)


def test_with_no_shell_the_page_goes_to_the_browser_and_the_daemon_is_left_running(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.choice = Choice(None, False, ("PySide6: ModuleNotFoundError: No module named 'PySide6'",))
    assert world.run() == 0
    assert world.browser == [PAGE] and capsys.readouterr().out.strip() == PAGE
    assert any("neoaprs stop" in line for line in world.said), "the app started the daemon and is about to be gone: it says how to end it"
    assert any("neoaprs[app]" in line and "PySide6" in line for line in world.said), "it says what is missing and how to get it"
    assert not SingleApp(world.data).running(), "the app lets go of the folder"


def test_in_the_tray_the_browser_is_not_opened_at_start(world: World) -> None:
    world.choice = Choice(None, False)
    world.owned = False
    assert world.run("--tray") == 0
    assert world.browser == [] and world.said == []


def test_a_page_that_does_not_come_up_is_said_and_is_exit_code_1(world: World) -> None:
    world.page_fails = True
    assert world.run() == 1
    assert "did not come up" in world.said[0] and "neoaprs.log" in world.said[0]
    assert not SingleApp(world.data).running()


def test_the_shell_is_given_the_session_and_runs_until_it_is_quit_through_a_second_app(world: World) -> None:
    told: list[bool] = []

    def second_app(frame: fakeshell.FakeFrame) -> None:
        assert SingleApp(world.data).tell_the_other("show")
        for _ in range(500):
            if frame.shown:
                break
            threading.Event().wait(0.02)
        told.append(frame.shown == 1)
        assert SingleApp(world.data).tell_the_other("quit")

    fakeshell.STEPS.append(second_app)
    assert world.run() == 0
    frame = fakeshell.FRAMES[-1]
    assert told == [True] and frame.quits == 1 and frame.has_window
    assert not SingleApp(world.data).running()


def test_a_shell_without_a_window_is_told_so(world: World) -> None:
    world.choice = Choice("tests.support.fakeshell", False)
    fakeshell.STEPS.append(lambda frame: SingleApp(world.data).tell_the_other("quit"))
    assert world.run("--tray") == 0
    assert not fakeshell.FRAMES[-1].has_window


def test_a_second_app_raises_the_first_ones_window_and_starts_nothing(world: World) -> None:
    first = SingleApp(world.data)
    assert first.acquire()
    heard: list[str] = []
    got = threading.Event()
    first.handle(lambda command: (heard.append(command), got.set()))
    assert world.run() == 0
    assert got.wait(10) and heard == ["show"] and world.sessions == [], "no second daemon, no second window"
    first.close()


def test_a_second_app_that_is_the_one_of_start_at_sign_in_does_not_raise_the_window(world: World) -> None:
    first = SingleApp(world.data)
    assert first.acquire()
    heard: list[str] = []
    first.handle(heard.append)
    assert world.run("--tray") == 0
    threading.Event().wait(0.3)
    assert heard == [] and world.sessions == []
    first.close()


@pytest.mark.expects_errors
def test_a_shell_that_cannot_start_is_said_and_the_page_goes_to_the_browser(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    broken = types.ModuleType("neoaprs_test_broken_shell")

    def run(ctx: object) -> int:
        raise RuntimeError("qt.qpa.plugin: could not connect to any display")

    broken.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "neoaprs_test_broken_shell", broken)
    world.choice = Choice("neoaprs_test_broken_shell", True)
    assert world.run() == 1
    assert world.browser == [PAGE] and any("window could not be started" in line for line in world.said)
    assert not SingleApp(world.data).running()


def test_quit_with_no_app_running_is_fine(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cmd.main(["--quit", "--data", str(tmp_path / "never-made")]) == 0
    assert "not running" in capsys.readouterr().err


def test_quit_tells_the_app_and_waits_until_it_has_let_go_of_the_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    app = SingleApp(tmp_path)
    assert app.acquire()
    app.handle(lambda command: threading.Timer(0.3, app.close).start() if command == "quit" else None)
    assert cmd.main(["--quit", "--data", str(tmp_path)]) == 0
    assert "has ended" in capsys.readouterr().err and not app.running()


def test_quit_that_is_not_obeyed_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cmd, "QUIT_WAIT_SEC", 0.5)
    app = SingleApp(tmp_path)
    assert app.acquire()
    assert cmd.main(["--quit", "--data", str(tmp_path)]) == 1
    assert "did not end" in capsys.readouterr().err
    app.close()


def test_the_command_is_neoaprs_app_and_neoaprs_app_runs_the_same(capsys: pytest.CaptureFixture[str]) -> None:
    from neoaprs import cli
    assert "app" in cli.COMMANDS and cli.HANDLERS["app"] is cli._app
    with pytest.raises(SystemExit) as stop:
        cli.main(["app", "--help"])
    assert stop.value.code == 0 and "--tray" in capsys.readouterr().out
