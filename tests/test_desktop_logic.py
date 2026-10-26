"""The desktop app's logic, with no window and no tray: which addresses stay in the window, the tray menu as data and what its items do, the decision to attach to a daemon or start one, what the app remembers, which shell
this computer can run and the fallbacks when none can show a window. The shells themselves are tests/test_desktop_qt.py and tests/test_desktop_winshell.py."""
import subprocess
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from neoaprs.desktop import appstate, links, shell
from neoaprs.desktop.autostart import AutoStartError
from neoaprs.desktop.menu import AUTOSTART, BROWSER, KEEPS_RUNNING, OPEN, QUIT, SUPPORT, AppActions, Item
from neoaprs.desktop.session import Daemon, DaemonWatch, NoPage, Session, open_session, stop_owned
from tests.support.fakeshell import FakeFrame

PAGE = "http://127.0.0.1:7303/"


# ---- which addresses stay in the window

@pytest.mark.parametrize("url, where", [
    (PAGE, "window"), ("http://127.0.0.1:7303/#/stations?x=1", "window"), ("http://127.0.0.1:7303/ws", "window"), ("HTTP://127.0.0.1:7303/", "window"),
    ("about:blank", "window"), ("blob:http://127.0.0.1:7303/3f6a", "window"),
    ("http://127.0.0.1:7304/", "browser"), ("https://127.0.0.1:7303/", "browser"), ("http://localhost:7303/", "browser"), ("http://127.0.0.1.example.org:7303/", "browser"),
    ("https://www.qrz.com/db/OH2GBA", "browser"), ("https://www.openstreetmap.org/copyright", "browser"), ("mailto:oh2gba@example.org", "browser"),
    ("blob:https://evil.example/3f6a", "block"), ("data:text/html,<b>x</b>", "block"), ("file:///etc/passwd", "block"), ("javascript:alert(1)", "block"), ("ftp://example.org/", "block"),
    ("", "block"), ("http://[::1", "block"), ("http://127.0.0.1:notaport/", "block"),
])
def test_links_stay_in_the_window_only_when_they_are_the_daemons_page(url: str, where: str) -> None:
    assert links.route(url, PAGE) == where


def test_the_port_the_page_was_found_on_is_the_one_that_counts() -> None:
    assert links.route("http://127.0.0.1:7304/", "http://127.0.0.1:7304/") == "window"
    assert links.route("http://127.0.0.1:7303/", "http://127.0.0.1:7304/") == "browser"
    assert links.route("http://127.0.0.1/", "http://127.0.0.1:80/") == "window", "the default port is the port"


def test_only_what_goes_to_the_browser_is_handed_to_it(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(links.webbrowser, "open", lambda url: opened.append(url) or True)
    assert links.open_external("https://www.qrz.com/db/OH2GBA", PAGE)
    assert not links.open_external(PAGE, PAGE) and not links.open_external("file:///etc/passwd", PAGE) and not links.open_external("javascript:alert(1)", PAGE)
    assert opened == ["https://www.qrz.com/db/OH2GBA"]
    monkeypatch.setattr(links.webbrowser, "open", lambda url: False)
    assert not links.open_external("https://example.org/", PAGE), "a browser that could not be started is a failure the caller can say"


# ---- the tray menu is data

class FakeAutoStart:
    def __init__(self, on: bool = False, fail: str = "") -> None:
        self.on, self.fail = on, fail

    def enabled(self) -> bool:
        return self.on

    def enable(self) -> None:
        if self.fail:
            raise AutoStartError(self.fail)
        self.on = True

    def disable(self) -> None:
        self.on = False


class FakeDaemon(Daemon):
    """The daemons of the app as a script: `up` is whether one holds the folder, `stops` what was asked to stop, `page` what the wait finds."""

    def __init__(self, up: bool = False, page: str | None = PAGE, child_alive: bool = True, stops: bool = True) -> None:
        self.up, self.page, self.child_alive, self.ends = up, page, child_alive, stops
        self.started: list[Path] = []
        self.stopped: list[Path] = []
        super().__init__(running=lambda data: self.up, start=self._start, wait=lambda data, child, seconds: self.page, stop=self._stop)

    def _start(self, data: Path) -> "subprocess.Popen[bytes]":
        self.started.append(data)
        self.up = True
        return types.SimpleNamespace(poll=lambda: None if self.child_alive else 2, returncode=2)       # type: ignore[return-value]

    def _stop(self, data: Path, seconds: float) -> bool:
        self.stopped.append(data)
        self.up = not self.ends
        return self.ends


def actions_for(owned: bool, window: bool = True, autostart: FakeAutoStart | None = None, daemon: FakeDaemon | None = None) -> tuple[AppActions, FakeFrame, FakeDaemon, list[str]]:
    frame, daemon = FakeFrame(window), daemon or FakeDaemon()
    opened: list[str] = []
    actions = AppActions(Session(Path("data"), PAGE, owned), frame, autostart, daemon, lambda url: opened.append(url))
    return actions, frame, daemon, opened


def labels(items: list[Item]) -> list[str]:
    return [i.label for i in items if not i.separator]


def test_the_menu_of_an_app_that_started_the_daemon() -> None:
    actions, *_ = actions_for(owned=True, autostart=FakeAutoStart(on=True))
    assert actions.items() == [Item(OPEN, "Open NeoAPRS"), Item(BROWSER, "Open in browser"), Item(AUTOSTART, "Start at sign-in", checked=True), Item(SUPPORT, "Collect support logs"), Item("-", "-", separator=True), Item(QUIT, "Stop and quit")]


def test_the_menu_of_an_app_attached_to_a_service_says_the_service_keeps_running() -> None:
    actions, *_ = actions_for(owned=False, autostart=FakeAutoStart())
    assert actions.items()[-1] == Item(QUIT, "Quit (NeoAPRS keeps running as a service)") and KEEPS_RUNNING in actions.items()[-1].label
    assert actions.items()[2] == Item(AUTOSTART, "Start at sign-in", checked=False)


def test_without_a_window_open_is_the_browser_and_without_autostart_there_is_no_checkbox() -> None:
    actions, frame, _, opened = actions_for(owned=True, window=False, autostart=None)
    assert labels(actions.items()) == ["Open NeoAPRS", "Collect support logs", "Stop and quit"], "Open in browser would only repeat Open"
    actions.run(OPEN)
    assert opened == [PAGE] and frame.shown == 0


def test_open_shows_the_window_and_open_in_browser_opens_the_browser() -> None:
    actions, frame, _, opened = actions_for(owned=True)
    actions.run(OPEN)
    actions.run(BROWSER)
    assert frame.shown == 1 and opened == [PAGE]


def test_the_checkbox_turns_start_at_sign_in_on_and_off_and_a_refusal_is_told() -> None:
    auto = FakeAutoStart()
    actions, frame, *_ = actions_for(owned=True, autostart=auto)
    actions.run(AUTOSTART)
    assert auto.on and frame.refreshed == 1
    actions.run(AUTOSTART)
    assert not auto.on and frame.refreshed == 2
    refusing = FakeAutoStart(fail="the Run entry NeoAPRS is not NeoAPRS's")
    actions, frame, *_ = actions_for(owned=True, autostart=refusing)
    actions.run(AUTOSTART)
    assert not refusing.on and frame.told == ["the Run entry NeoAPRS is not NeoAPRS's"] and frame.refreshed == 1


def test_stop_and_quit_stops_the_daemon_the_app_started_and_ends_the_app() -> None:
    actions, frame, daemon, _ = actions_for(owned=True)
    actions.run(QUIT)
    assert actions.thread is not None
    actions.thread.join(10)
    assert daemon.stopped == [Path("data")] and frame.quits == 1 and frame.told == []


def test_quit_leaves_a_daemon_that_was_already_running_alone() -> None:
    actions, frame, daemon, _ = actions_for(owned=False)
    actions.quit_now()
    assert daemon.stopped == [] and frame.quits == 1


def test_a_daemon_that_does_not_stop_is_told_and_the_app_ends_all_the_same() -> None:
    actions, frame, daemon, _ = actions_for(owned=True, daemon=FakeDaemon(stops=False))
    actions.quit_now()
    assert daemon.stopped and frame.quits == 1 and "did not stop" in frame.told[0]


def test_quit_is_done_once_whoever_asks() -> None:
    actions, frame, daemon, _ = actions_for(owned=True)
    actions.quit_now()
    actions.quit_now()
    actions.daemon_gone()
    assert frame.quits == 1 and len(daemon.stopped) == 1


def test_a_daemon_that_ended_by_itself_ends_the_app_without_a_stop() -> None:
    actions, frame, daemon, _ = actions_for(owned=True)
    actions.daemon_gone()
    assert frame.quits == 1 and daemon.stopped == []


# ---- attach or own

DATA = Path("somewhere")


def test_a_daemon_that_holds_the_folder_is_attached_to_and_not_owned() -> None:
    daemon = FakeDaemon(up=True)
    assert open_session(DATA, daemon) == Session(DATA, PAGE, owned=False)
    assert daemon.started == []


def test_with_no_daemon_one_is_started_and_owned() -> None:
    daemon = FakeDaemon(up=False)
    assert open_session(DATA, daemon) == Session(DATA, PAGE, owned=True)
    assert daemon.started == [DATA]


def test_a_daemon_that_started_first_wins_the_lock_and_the_one_we_started_is_not_ours() -> None:
    assert open_session(DATA, FakeDaemon(up=False, child_alive=False)).owned is False


def test_no_page_is_an_error_that_says_where_to_look() -> None:
    with pytest.raises(NoPage, match="neoaprs.log"):
        open_session(DATA, FakeDaemon(up=False, page=None), timeout=0.5)


def test_only_a_daemon_the_app_started_is_stopped() -> None:
    daemon = FakeDaemon(up=True)
    assert stop_owned(Session(DATA, PAGE, owned=False), daemon) and daemon.stopped == []
    assert stop_owned(Session(DATA, PAGE, owned=True), daemon) and daemon.stopped == [DATA]
    assert not stop_owned(Session(DATA, PAGE, owned=True), FakeDaemon(up=True, stops=False))


def test_the_watch_calls_when_the_owned_daemon_has_gone_twice_in_a_row_and_never_for_an_attached_one() -> None:
    gone = threading.Event()
    daemon = FakeDaemon(up=True)
    watch = DaemonWatch(Session(DATA, PAGE, owned=True), gone.set, daemon, every=0.02)
    watch.start()
    assert not gone.wait(0.2), "a daemon that is up is not gone"
    daemon.up = False
    assert gone.wait(5)
    attached = threading.Event()
    other = DaemonWatch(Session(DATA, PAGE, owned=False), attached.set, FakeDaemon(up=False), every=0.02)
    other.start()
    assert not attached.wait(0.3), "the daemon of a service is its manager's to stop and restart"
    other.cancel()


def test_a_daemon_that_blinks_once_is_not_gone() -> None:
    gone = threading.Event()
    daemon = FakeDaemon(up=True)
    answers = iter([False, True, True, True])
    daemon.running = lambda data: next(answers, True)
    watch = DaemonWatch(Session(DATA, PAGE, owned=True), gone.set, daemon, every=0.02)
    watch.start()
    assert not gone.wait(0.3)
    watch.cancel()


def test_a_daemon_that_restarts_as_a_new_version_is_waited_for_while_its_note_is_fresh() -> None:
    gone = threading.Event()
    daemon = FakeDaemon(up=False)
    note = [True]
    daemon.restarting = lambda data: note[0]
    watch = DaemonWatch(Session(DATA, PAGE, owned=True), gone.set, daemon, every=0.02)
    watch.start()
    assert not gone.wait(0.3), "Update now of an AppImage: the daemon ends and the new file starts"
    note[0] = False
    assert gone.wait(5), "a restart that did not come up is an end"


# ---- what the app remembers

def test_the_window_size_is_remembered_and_a_bad_file_gives_the_default(tmp_path: Path) -> None:
    assert appstate.load_size(tmp_path) == (1280, 800)
    appstate.save_size(tmp_path, 1000, 700)
    assert appstate.load_size(tmp_path) == (1000, 700)
    for text in ("", "not json", "[]", '{"width": "wide", "height": 5}', '{"width": 10, "height": 10}', '{"width": 1000}', '{"width": true, "height": true}', '{"width": 99999, "height": 700}'):
        (tmp_path / appstate.STATE_NAME).write_text(text, encoding="utf-8")
        assert appstate.load_size(tmp_path) == (1280, 800), text


def test_the_size_of_a_window_that_is_hidden_or_minimised_is_not_saved(tmp_path: Path) -> None:
    appstate.save_size(tmp_path, 1000, 700)
    appstate.save_size(tmp_path, 0, 0)
    appstate.save_size(tmp_path, 160, 28)
    assert appstate.load_size(tmp_path) == (1000, 700)


def test_the_web_engine_gets_its_storage_in_the_data_folder(tmp_path: Path) -> None:
    folder = appstate.profile_dir(tmp_path / "data")
    assert folder == tmp_path / "data" / "webview" and folder.is_dir()


# ---- which shell this computer can run

def importer(missing: set[str]) -> Any:
    def load(name: str) -> object:
        if name in missing or any(name.startswith(m + ".") for m in missing):
            raise ModuleNotFoundError(f"No module named {name!r}")
        return types.ModuleType(name)
    return load


def test_linux_with_the_web_engine_has_the_window_and_the_tray() -> None:
    choice = shell.choose("linux", importer(set()))
    assert choice == shell.Choice("neoaprs.desktop.qtshell", True) and "window and tray" in choice.describe()


def test_linux_without_the_web_engine_has_the_tray_and_the_browser() -> None:
    choice = shell.choose("linux", importer({"PySide6.QtWebEngineWidgets"}))
    assert choice.module == "neoaprs.desktop.qtshell" and not choice.window and "QtWebEngineWidgets" in choice.describe() and "no window" in choice.describe()


def test_linux_without_qt_has_the_browser_only() -> None:
    choice = shell.choose("linux", importer({"PySide6"}))
    assert choice.module is None and not choice.window and "browser" in choice.describe() and "PySide6" in choice.describe()


def test_a_toolkit_that_is_installed_and_broken_is_a_fallback_and_not_a_crash() -> None:
    def broken(name: str) -> object:
        raise OSError("libEGL.so.1: cannot open shared object file")
    choice = shell.choose("linux", broken)
    assert choice.module is None and "libEGL" in choice.describe()


def test_windows_has_the_window_and_the_tray_when_webview2_is_there() -> None:
    assert shell.choose("win32", importer(set()), lambda: True) == shell.Choice("neoaprs.desktop.winshell", True)


@pytest.mark.parametrize("missing, runtime, module, window", [
    (set(), False, "neoaprs.desktop.winshell", False),             # no WebView2 runtime: pywebview would fall back to the old Internet Explorer engine, which cannot show the page
    ({"webview"}, True, "neoaprs.desktop.winshell", False),        # pywebview is not installed
    ({"pystray"}, True, None, False), ({"PIL"}, True, None, False),
])
def test_windows_falls_back_to_the_tray_or_the_browser(missing: set[str], runtime: bool, module: str | None, window: bool) -> None:
    choice = shell.choose("win32", importer(missing), lambda: runtime)
    assert (choice.module, choice.window) == (module, window) and choice.why


def test_the_webview2_runtime_is_looked_for_where_its_updater_writes_it() -> None:
    keys: dict[tuple[str, str], str] = {}
    registry = types.ModuleType("winreg")
    registry.HKEY_LOCAL_MACHINE = "HKLM"  # type: ignore[attr-defined]
    registry.HKEY_CURRENT_USER = "HKCU"  # type: ignore[attr-defined]

    class Key:
        def __init__(self, version: str) -> None:
            self.version = version

        def __enter__(self) -> "Key":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def open_key(root: str, path: str) -> Key:
        if (root, path) not in keys:
            raise FileNotFoundError(path)
        return Key(keys[(root, path)])

    registry.OpenKey = open_key  # type: ignore[attr-defined]
    registry.QueryValueEx = lambda key, name: (key.version, 1)  # type: ignore[attr-defined]
    assert not shell.webview2_runtime(registry)
    clients = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients" + "\\" + shell.WEBVIEW2_CLIENT
    keys[("HKLM", clients)] = "0.0.0.0"
    assert not shell.webview2_runtime(registry), "a key with no version is not an installation"
    keys[("HKLM", clients)] = "126.0.2592.87"
    assert shell.webview2_runtime(registry)
    keys.clear()
    keys[("HKCU", r"SOFTWARE\Microsoft\EdgeUpdate\Clients" + "\\" + shell.WEBVIEW2_CLIENT)] = "126.0.2592.87"
    assert shell.webview2_runtime(registry), "a per-user install counts"
