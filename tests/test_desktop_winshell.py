"""The Windows shell against stand-ins for pywebview, pystray and Pillow (`sys.modules` gets them, so this runs on any system and CI): what the shell asks of each toolkit, the closing of the window that
hides it, the tray menu made from the data of the actions, the page's script that sends other sites to the browser, and the way on without a window when WebView2 cannot start. What the real toolkits do with
those calls is what only a Windows desktop can say."""
import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from neoaprs.desktop import appstate, winshell
from neoaprs.desktop.menu import AUTOSTART, OPEN, QUIT
from neoaprs.desktop.session import Session
from neoaprs.desktop.shell import ShellContext
from neoaprs.desktop.single import SingleApp
from tests.test_desktop_logic import PAGE, FakeAutoStart, FakeDaemon


class Hook:
    """pywebview's event: `+=` adds a handler."""

    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "Hook":
        self.handlers.append(handler)
        return self


class FakeWindow:
    def __init__(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.args, self.kwargs = args, kwargs
        self.events = types.SimpleNamespace(closing=Hook(), resized=Hook(), loaded=Hook())
        self.calls: list[str] = []
        self.scripts: list[str] = []
        self.destroyed = threading.Event()

    def hide(self) -> None:
        self.calls.append("hide")

    def show(self) -> None:
        self.calls.append("show")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")
        self.destroyed.set()

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)


class FakeIcon:
    def __init__(self, name: str, image: object, title: str, menu: object) -> None:
        self.name, self.image, self.title, self.menu = name, image, title, menu
        self.calls: list[str] = []
        self.notes: list[tuple[str, str]] = []

    def run_detached(self) -> None:
        self.calls.append("run_detached")

    def stop(self) -> None:
        self.calls.append("stop")

    def update_menu(self) -> None:
        self.calls.append("update_menu")

    def notify(self, message: str, title: str) -> None:
        self.notes.append((message, title))


class FakeMenu:
    SEPARATOR = "---"

    def __init__(self, source: Any) -> None:
        self.source = source

    def items(self) -> list[Any]:
        return list(self.source())


class FakeMenuItem:
    def __init__(self, text: str, action: Any, checked: Any = None, default: bool = False) -> None:
        self.text, self.action, self.checked, self.default = text, action, checked, default


class Toolkits:
    """The three modules, and what the shell did to them."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, start_fails: bool = False) -> None:
        self.windows: list[FakeWindow] = []
        self.icons: list[FakeIcon] = []
        self.started: list[dict[str, Any]] = []
        self.settings: dict[str, Any] = {}
        self.start_fails = start_fails
        self.on_started: list[Any] = []
        webview = types.ModuleType("webview")
        webview.settings = self.settings  # type: ignore[attr-defined]
        webview.create_window = self.create_window  # type: ignore[attr-defined]
        webview.start = self.start  # type: ignore[attr-defined]
        pystray = types.ModuleType("pystray")
        pystray.Icon = self.make_icon  # type: ignore[attr-defined]
        pystray.Menu = FakeMenu  # type: ignore[attr-defined]
        pystray.MenuItem = FakeMenuItem  # type: ignore[attr-defined]
        pil = types.ModuleType("PIL")
        image = types.ModuleType("PIL.Image")
        image.open = lambda path: ("image", str(path))  # type: ignore[attr-defined]
        pil.Image = image  # type: ignore[attr-defined]
        for name, module in (("webview", webview), ("pystray", pystray), ("PIL", pil), ("PIL.Image", image)):
            monkeypatch.setitem(sys.modules, name, module)

    def create_window(self, *args: Any, **kwargs: Any) -> FakeWindow:
        window = FakeWindow(args, kwargs)
        self.windows.append(window)
        return window

    def make_icon(self, name: str, image: object, title: str, menu: object) -> FakeIcon:
        icon = FakeIcon(name, image, title, menu)
        self.icons.append(icon)
        return icon

    def start(self, func: Any = None, **kwargs: Any) -> None:
        self.started.append(kwargs)
        if self.start_fails:
            raise RuntimeError("WebView2 initialization failed")
        func()
        assert self.windows[0].destroyed.wait(10), "the window loop runs until the window is destroyed"


class Rig:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hidden: bool = False, window: bool = True, start_fails: bool = False, autostart: bool = True) -> None:
        self.toolkits = Toolkits(monkeypatch, start_fails)
        self.browser: list[str] = []
        monkeypatch.setattr(winshell.webbrowser, "open", lambda url: self.browser.append(url) or True)
        self.data = tmp_path / "data"
        self.data.mkdir()
        self.single = SingleApp(self.data)
        self.daemon = FakeDaemon(up=True)
        self.auto = FakeAutoStart() if autostart else None
        self.ctx = ShellContext(Session(self.data, PAGE, owned=False), hidden, window, self.auto, self.single, self.daemon)

    def run(self) -> int:
        return winshell.run(self.ctx)


def until(condition: Any, seconds: float = 10.0) -> None:
    deadline = threading.Event()
    for _ in range(int(seconds / 0.02)):
        if condition():
            return
        deadline.wait(0.02)
    raise AssertionError("the condition did not come true")


def launch(rig: Rig) -> threading.Thread:
    """Runs the shell in a thread (it blocks until Quit, as the toolkit's loop does) and returns when the window loop or the tray has started."""
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.toolkits.started or rig.toolkits.icons and "run_detached" in rig.toolkits.icons[0].calls and rig.ctx.watch is not None)
    until(lambda: rig.ctx.watch is not None)
    return thread


def menu_item(rig: Rig, text: str) -> FakeMenuItem:
    (icon,) = rig.toolkits.icons
    return next(item for item in icon.menu.items() if item != FakeMenu.SEPARATOR and item.text.startswith(text))  # type: ignore[attr-defined]


def quit_through_the_menu(rig: Rig, thread: threading.Thread) -> None:
    item = menu_item(rig, "Quit")
    item.action(rig.toolkits.icons[0], item)
    thread.join(10)
    assert not thread.is_alive()
    rig.ctx.close()


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    return Rig(tmp_path, monkeypatch)


def test_the_window_has_the_size_it_had_is_hidden_in_the_tray_and_starts_on_edge_with_its_storage_in_the_data_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, hidden=True)
    appstate.save_size(rig.data, 1000, 700)
    thread = launch(rig)
    (window,) = rig.toolkits.windows
    assert window.args == ("NeoAPRS", PAGE + "#app") and (window.kwargs["width"], window.kwargs["height"]) == (1000, 700) and window.kwargs["hidden"] is True and window.kwargs["text_select"] is True
    assert isinstance(window.kwargs["js_api"], winshell.LinkApi)
    assert rig.toolkits.started == [{"gui": "edgechromium", "private_mode": False, "storage_path": str(rig.data / "webview")}]
    assert rig.toolkits.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True and rig.browser == []
    icon = rig.toolkits.icons[0]
    assert (icon.name, icon.title, icon.image[0]) == ("NeoAPRS", "NeoAPRS", "image") and icon.image[1].endswith("icon.png") and icon.calls == ["run_detached"]
    quit_through_the_menu(rig, thread)
    assert icon.calls[-1] == "stop" and window.calls[-1] == "destroy"


def test_the_close_button_hides_the_window_and_only_quit_lets_it_close(rig: Rig) -> None:
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    (closing,) = window.events.closing.handlers
    assert closing() is False and window.calls == ["hide"], "False cancels the close"
    item = menu_item(rig, "Quit")
    item.action(rig.toolkits.icons[0], item)
    thread.join(10)
    assert closing() is True and window.calls[-1] == "destroy"
    rig.ctx.close()


def test_the_tray_menu_is_made_from_the_data_of_the_actions(rig: Rig) -> None:
    thread = launch(rig)
    icon = rig.toolkits.icons[0]
    items = icon.menu.items()  # type: ignore[attr-defined]
    assert [i if i == FakeMenu.SEPARATOR else i.text for i in items] == ["Open NeoAPRS", "Open in browser", "Start at sign-in", "Collect support logs", FakeMenu.SEPARATOR, "Quit (NeoAPRS keeps running as a service)"]
    opening, browser, auto = items[0], items[1], items[2]
    assert opening.default and not browser.default and opening.checked is None and auto.checked(auto) is False
    opening.action(icon, opening)
    assert rig.toolkits.windows[0].calls == ["show", "restore"]
    browser.action(icon, browser)
    assert rig.browser == [PAGE]
    auto.action(icon, auto)
    assert rig.auto is not None and rig.auto.on and "update_menu" in icon.calls
    assert menu_item(rig, "Start at sign-in").checked(auto) is True      # type: ignore[misc]
    quit_through_the_menu(rig, thread)


def test_a_resize_is_remembered_when_it_has_stopped(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(winshell, "SAVE_SIZE_SEC", 0.05)
    thread = launch(rig)
    (resized,) = rig.toolkits.windows[0].events.resized.handlers
    for width in (1010, 1020, 1030, 1100):
        resized(width, 750)
    until(lambda: appstate.load_size(rig.data) == (1100, 750))
    quit_through_the_menu(rig, thread)


def test_the_page_is_given_a_script_that_hands_other_sites_to_the_browser(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    (loaded,) = window.events.loaded.handlers
    loaded()
    assert window.scripts == [winshell.LINK_SCRIPT] and "pywebview.api.open_external" in winshell.LINK_SCRIPT and "location.origin" in winshell.LINK_SCRIPT
    opened: list[str] = []
    monkeypatch.setattr("neoaprs.desktop.links.webbrowser.open", lambda url: opened.append(url) or True)
    api = window.kwargs["js_api"]
    assert api.open_external("https://www.qrz.com/db/OH2GBA") and not api.open_external(PAGE) and not api.open_external("file:///c:/windows/system32/cmd.exe")
    assert opened == ["https://www.qrz.com/db/OH2GBA"]
    quit_through_the_menu(rig, thread)


@pytest.mark.expects_errors
def test_when_the_window_cannot_start_the_app_goes_on_in_the_tray_with_the_page_in_the_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, start_fails=True)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.browser == [PAGE] and rig.ctx.watch is not None)
    assert [i if i == FakeMenu.SEPARATOR else i.text for i in rig.toolkits.icons[0].menu.items()][:2] == ["Open NeoAPRS", "Start at sign-in"], "no window: no 'Open in browser'"  # type: ignore[attr-defined]
    item = menu_item(rig, "Open NeoAPRS")
    item.action(rig.toolkits.icons[0], item)
    assert rig.browser == [PAGE, PAGE], "Open is the browser now"
    quit_through_the_menu(rig, thread)


def test_with_no_web_engine_it_is_the_tray_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, window=False, autostart=False)
    thread = launch(rig)
    assert rig.toolkits.windows == [] and rig.toolkits.started == [] and rig.browser == [PAGE]
    assert [i if i == FakeMenu.SEPARATOR else i.text for i in rig.toolkits.icons[0].menu.items()] == ["Open NeoAPRS", "Collect support logs", FakeMenu.SEPARATOR, "Quit (NeoAPRS keeps running as a service)"]  # type: ignore[attr-defined]
    quit_through_the_menu(rig, thread)


def test_started_in_the_tray_without_a_window_it_opens_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, window=False, hidden=True)
    thread = launch(rig)
    assert rig.browser == []
    quit_through_the_menu(rig, thread)


def test_the_menu_item_constants_are_the_keys_the_actions_know() -> None:
    assert (OPEN, AUTOSTART, QUIT) == ("open", "autostart", "quit")


# ---- the edges: a frame before it has a window or an icon, a message to the tray, a window that cannot start when the app starts hidden

def test_a_frame_that_has_no_window_and_no_icon_yet_has_nothing_to_show_or_to_refresh_and_a_message_goes_to_the_log(caplog: pytest.LogCaptureFixture) -> None:
    frame = winshell.WinFrame(True)
    frame.show_window()
    frame.refresh()
    with caplog.at_level("WARNING", "neoaprs.desktop"):
        frame.tell("the daemon was started")
    assert [r.getMessage() for r in caplog.records] == ["the daemon was started"]


def test_a_message_is_a_notification_of_the_icon_where_there_is_one_and_quit_with_no_window_only_ends_the_wait() -> None:
    frame = winshell.WinFrame(False)
    notes: list[tuple[str, str]] = []
    updates: list[bool] = []
    frame.icon = types.SimpleNamespace(notify=lambda text, title: notes.append((text, title)), update_menu=lambda: updates.append(True))
    frame.tell("the daemon was started")
    frame.refresh()
    frame.quit()
    assert notes == [("the daemon was started", "NeoAPRS")] and updates == [True] and frame.quitting.is_set() and frame.done.is_set()


@pytest.mark.expects_errors
def test_a_window_that_cannot_start_when_the_app_starts_hidden_opens_no_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, start_fails=True, hidden=True)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.ctx.watch is not None and rig.toolkits.icons)
    assert rig.browser == []
    quit_through_the_menu(rig, thread)
