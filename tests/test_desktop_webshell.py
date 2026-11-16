"""The web shell against stand-ins for pywebview, pystray and Pillow (`sys.modules` gets them, so this runs on any system and CI). First as it runs on Windows (the rig sets `webshell.SYSTEM`): what the shell
asks of each toolkit, the closing of the window that hides it, the tray menu made from the data of the actions, the page's script that sends other sites to the browser, and the way on without a window when
WebView2 cannot start. The Windows tray's image is icon.ico written as it is (no imaging library: there an import of Pillow fails); where the real pystray is installed (the CI's Windows job), its own code
is read for the one call it makes of the image, and the image goes through it. Then as it runs on Linux and macOS (the trial of NEOAPRS_WINDOW=web), with stand-ins for gi and PyObjCTools too: the engine, the storage and the icon it starts with, the size keeper,
the window without a tray whose close button quits, the minute's wait for the tray host, the tray's own loop with no window, and gtkenv's rules on a fake /proc and fake folders. What the real toolkits do with
those calls is what only a desktop of each system can say."""
import ast
import inspect
import ctypes
import logging
import os
import re
import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from neoaprs.desktop import appstate, gtkenv, loading, sizekeep, webdesk, webshell, winplace
from neoaprs.desktop.menu import AUTOSTART, KEEPS_RUNNING, OPEN, OPEN_LABEL, QUIT
from neoaprs.desktop.session import Opening, Session
from neoaprs.desktop.shell import Launch, ShellContext
from neoaprs.desktop.single import SingleApp
from tests.test_desktop_logic import PAGE, FakeAutoStart, FakeDaemon


class Hook:
    """pywebview's event: `+=` adds a handler."""

    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "Hook":
        self.handlers.append(handler)
        return self


Rect = tuple[int, int, int, int]
SCREEN, WORK = (0, 0, 1366, 768), (0, 0, 1366, 728)        # the laptop of the report: 1366 x 768 at 100 %, the taskbar at the bottom
MAXIMIZED_FRAME = (-8, -8, 1374, 736)                       # (a maximized window's frame: its borders off the work area)
NORMAL = (100, 60, 1100, 760)


class FakeUser32:
    """Windows' user32 as far as the shell asks it, with the one window: its placement (show state, flags, normal rectangle) and whether it is visible, the placements it was given, and every call. The window's
    form (pywebview's) shows and hides it; with `form_bug` its Show makes a maximized window a normal one the size of the screen, as the laptop of the report showed it, and with `undo` SetWindowPlacement is
    answered and changes nothing."""
    hwnd = 0x2A0F44

    def __init__(self, show_cmd: int = winplace.SW_SHOWNORMAL, flags: int = 0, normal: Rect = NORMAL, visible: bool = True) -> None:
        self.show_cmd, self.flags, self.normal, self.visible = show_cmd, flags, normal, visible
        self.placed: list[tuple[int, Rect]] = []
        self.calls: list[str] = []
        self.form_bug = False
        self.undo = False

    def _window(self, name: str, handle: Any) -> None:
        assert handle.value == self.hwnd
        self.calls.append(name)

    def GetWindowPlacement(self, handle: Any, ref: Any) -> int:
        self._window("GetWindowPlacement", handle)
        wp = ref._obj
        assert wp.length == ctypes.sizeof(winplace._Placement)
        wp.showCmd, wp.flags, wp.rcNormalPosition = self.show_cmd, self.flags, winplace._Rect(*self.normal)
        return 1

    def SetWindowPlacement(self, handle: Any, ref: Any) -> int:
        self._window("SetWindowPlacement", handle)
        wp = ref._obj
        self.placed.append((wp.showCmd, wp.rcNormalPosition.corners()))
        if not self.undo:
            self.normal = wp.rcNormalPosition.corners()
            if wp.showCmd != winplace.SW_HIDE:
                self.show_cmd, self.visible = wp.showCmd, True
        return 1

    def IsWindowVisible(self, handle: Any) -> int:
        self._window("IsWindowVisible", handle)
        return int(self.visible)

    def IsZoomed(self, handle: Any) -> int:
        self._window("IsZoomed", handle)
        return int(self.show_cmd == winplace.SW_SHOWMAXIMIZED)

    def GetWindowRect(self, handle: Any, ref: Any) -> int:
        self._window("GetWindowRect", handle)
        ref._obj.left, ref._obj.top, ref._obj.right, ref._obj.bottom = MAXIMIZED_FRAME if self.show_cmd == winplace.SW_SHOWMAXIMIZED else self.normal
        return 1

    def MonitorFromRect(self, ref: Any, flags: int) -> int:
        self.calls.append("MonitorFromRect")
        assert flags == winplace.MONITOR_DEFAULTTONEAREST
        return 0x10001

    def GetMonitorInfoW(self, handle: Any, ref: Any) -> int:
        self.calls.append("GetMonitorInfoW")
        assert handle.value == 0x10001 and ref._obj.cbSize == ctypes.sizeof(winplace._MonitorInfo)
        ref._obj.rcMonitor, ref._obj.rcWork = winplace._Rect(*SCREEN), winplace._Rect(*WORK)
        return 1

    def GetDpiForWindow(self, handle: Any) -> int:
        self._window("GetDpiForWindow", handle)
        return 96

    def GetSystemMetrics(self, index: int) -> int:
        self.calls.append("GetSystemMetrics")
        return SCREEN[2:][index]

    def form_shows(self) -> None:
        self.visible = True
        if self.form_bug and self.show_cmd == winplace.SW_SHOWMAXIMIZED:
            self.show_cmd, self.normal = winplace.SW_SHOWNORMAL, MAXIMIZED_FRAME


class FakeWindow:
    def __init__(self, args: tuple[Any, ...], kwargs: dict[str, Any], user32: FakeUser32 | None = None) -> None:
        self.args, self.kwargs = args, kwargs
        self.events = types.SimpleNamespace(closing=Hook(), before_show=Hook(), shown=Hook(), resized=Hook(), moved=Hook(), maximized=Hook(), minimized=Hook(), restored=Hook(), loaded=Hook())
        self.calls: list[str] = []
        self.scripts: list[str] = []
        self.loaded: list[str] = []
        self.shown = True
        self.destroyed = threading.Event()
        self.user32 = user32
        self.frame_at = (0, 0)                                                                                      # where the frame is, title bar and all (GTK's get_position)
        self.native = types.SimpleNamespace(Handle=types.SimpleNamespace(ToInt64=lambda: FakeUser32.hwnd),      # (pywebview's WinForms Form, with its HWND;
                                            get_position=lambda: self.frame_at)                                  #  GTK's Window, with the place of its frame)

    def hide(self) -> None:
        self.calls.append("hide")
        if self.user32 is not None:
            self.user32.visible = False

    def show(self) -> None:
        self.calls.append("show")
        if self.user32 is not None:
            self.user32.form_shows()

    def restore(self) -> None:
        self.calls.append("restore")

    def maximize(self) -> None:
        self.calls.append("maximize")

    def destroy(self) -> None:
        self.calls.append("destroy")
        self.destroyed.set()

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)

    def load_url(self, url: str) -> None:
        if not self.shown:
            raise RuntimeError("Main window failed to start")            # (pywebview's load_url, when the window's `shown` does not come in time)
        self.loaded.append(url)


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
        # pystray 0.19.5 (MenuItem._assert_action) takes an action of 0, 1 or 2 parameters, counting those with a default, and refuses any other with ValueError: the tray menu of every Windows start
        # failed so from 26 Oct to 4 Nov 2026 (OH2GAX's app log), an action `lambda _icon, _item, key=...` having three.
        if callable(action) and action.__code__.co_argcount - (1 if inspect.ismethod(action) else 0) > 2:
            raise ValueError(action)
        self.text, self.action, self.checked, self.default = text, action, checked, default


class Toolkits:
    """The three modules, and what the shell did to them."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, start_fails: bool = False, user32: FakeUser32 | None = None, system: str = "win32") -> None:
        self.user32 = user32
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
        for name, module in (("webview", webview), ("pystray", pystray)):
            monkeypatch.setitem(sys.modules, name, module)
        if system == "win32":
            for name in ("PIL", "PIL.Image"):
                monkeypatch.setitem(sys.modules, name, None)        # (an import of Pillow fails: the Windows shell must not need it, the app does not ship it)
        else:
            pil = types.ModuleType("PIL")
            image = types.ModuleType("PIL.Image")
            image.open = lambda path: ("image", str(path))  # type: ignore[attr-defined]
            pil.Image = image  # type: ignore[attr-defined]
            for name, module in (("PIL", pil), ("PIL.Image", image)):
                monkeypatch.setitem(sys.modules, name, module)

    def create_window(self, *args: Any, **kwargs: Any) -> FakeWindow:
        window = FakeWindow(args, kwargs, self.user32)
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
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hidden: bool = False, window: bool = True, start_fails: bool = False, autostart: bool = True, user32: FakeUser32 | None = None,
                 windll: bool = True, system: str = "win32") -> None:
        """`user32`: the window's Win32 side, which is `ctypes.windll.user32` unless `windll` is False (then the window has it and the shell cannot reach it, as on any system but Windows). Without one the
        shell has no Win32 at all, on Windows too (CI runs these tests there): the real user32 is never called with a fake window, and no real WebView2 is started. `system`: the system the shell runs as."""
        monkeypatch.setattr(webshell, "SYSTEM", system)
        self.tray = True                                                    # whether the tray's toolkit loaded (Launch.tray)
        self.toolkits = Toolkits(monkeypatch, start_fails, user32, system)
        if user32 is not None and windll:
            monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)
        else:
            monkeypatch.delattr(ctypes, "windll", raising=False)
        self.browser: list[str] = []
        monkeypatch.setattr(webshell.webbrowser, "open", lambda url: self.browser.append(url) or True)
        self.data = tmp_path / "data"
        self.data.mkdir(parents=True)
        self.single = SingleApp(self.data)
        self.daemon = FakeDaemon(up=True)
        self.auto = FakeAutoStart() if autostart else None
        self.ctx = ShellContext(Session(self.data, PAGE, owned=False), hidden, window, self.auto, self.single, self.daemon)

    def run(self) -> int:
        launch = Launch.of(self.ctx)
        launch.tray = self.tray
        return webshell.run(launch)


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


def test_a_page_that_the_daemon_serves_at_another_address_is_loaded_there_and_the_links_are_judged_against_it(rig: Rig) -> None:
    """The daemon started again on another port (Update now on Windows: the installer starts it; the port it had may be taken by then): the watch tells the actions, the window loads the page there."""
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    assert rig.ctx.watch is not None and rig.ctx.watch.moved is not None
    rig.ctx.watch.moved("http://127.0.0.1:7310/")
    assert window.loaded == [PAGE + "#app", "http://127.0.0.1:7310/#app"]
    api = window.kwargs["js_api"]
    assert api.page_url == "http://127.0.0.1:7310/" and not api.open_external("http://127.0.0.1:7310/x") and rig.browser == []
    assert api.open_external(PAGE) and rig.browser == [PAGE], "the old address is another site's now"
    item = menu_item(rig, "Open in browser")
    item.action(rig.toolkits.icons[0], item)
    assert rig.browser == [PAGE, "http://127.0.0.1:7310/"]
    quit_through_the_menu(rig, thread)
    rig.ctx.watch.moved(PAGE)
    assert window.loaded[-1] == "http://127.0.0.1:7310/#app", "a window that Quit destroyed is given nothing to load"


def test_the_window_has_the_size_it_had_is_hidden_in_the_tray_and_starts_on_edge_with_its_storage_in_the_data_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, hidden=True)
    appstate.save_window(rig.data, kept(False))
    thread = launch(rig)
    (window,) = rig.toolkits.windows
    assert window.args == ("NeoAPRS",) and window.kwargs["html"] == loading.HTML and window.loaded == [PAGE + "#app"], "the loading page first, then the daemon's"
    assert (window.kwargs["width"], window.kwargs["height"]) == (1000, 700) and window.kwargs["hidden"] is True and window.kwargs["text_select"] is True
    assert window.kwargs["background_color"] == loading.background(webshell.dark_scheme()), "the page's background in the scheme of the system, before anything is painted"
    assert (window.kwargs["x"], window.kwargs["y"], window.kwargs["maximized"]) == (100, 60, False), "the placement's rectangle, as a first guess"
    assert isinstance(window.kwargs["js_api"], webshell.LinkApi)
    assert rig.toolkits.started == [{"gui": "edgechromium", "private_mode": False, "storage_path": str(rig.data / "webview")}]
    assert rig.toolkits.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True and rig.browser == []
    assert rig.toolkits.settings["ALLOW_DOWNLOADS"] is True, "the HTTPS guide's Download certificate: WebView2 cancels every download unless it is allowed"
    icon = rig.toolkits.icons[0]
    assert (icon.name, icon.title) == ("NeoAPRS", "NeoAPRS") and isinstance(icon.image, webshell.IcoFile) and icon.image.path.name == "icon.ico" and icon.calls == ["run_detached", "update_menu"]
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


# ---- the window's placement on Windows: read with GetWindowPlacement, given back with SetWindowPlacement (user32 is a fake: what Windows itself does with the calls only a Windows desktop can say)

def kept(maximized: bool, normal: Rect = NORMAL) -> appstate.WindowState:
    """The file as the Windows shell writes it."""
    return appstate.WindowState(normal[2] - normal[0], normal[3] - normal[1], None, None, maximized, normal)


def lines(caplog: pytest.LogCaptureFixture, level: int = logging.INFO) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level and r.getMessage().startswith("window:")]


def handler(hook: Hook) -> Any:
    (only,) = hook.handlers
    return only


def test_a_window_left_maximized_starts_maximized_on_the_normal_rectangle_it_had_even_when_the_form_shows_it_otherwise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    user32 = FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED, normal=(0, 0, 1280, 800), visible=False)     # the form as pywebview makes it: hidden, maximized as it was told, at its own rectangle
    rig = Rig(tmp_path, monkeypatch, user32=user32)
    appstate.save_window(rig.data, kept(True))
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    assert (window.kwargs["width"], window.kwargs["height"], window.kwargs["x"], window.kwargs["y"], window.kwargs["maximized"]) == (1000, 700, 100, 60, True)
    handler(window.events.before_show)()
    assert user32.placed == [(winplace.SW_HIDE, NORMAL)] and not user32.visible, "before it is shown: the rectangle, and still hidden"
    user32.form_bug = True                                              # the form shows it as the laptop did: a normal window the size of the screen
    user32.form_shows()
    handler(window.events.shown)()
    assert user32.placed[-1] == (winplace.SW_SHOWMAXIMIZED, NORMAL) and (user32.show_cmd, user32.normal) == (winplace.SW_SHOWMAXIMIZED, NORMAL)
    said = lines(caplog)
    assert said[0] == "window: file: maximized=True normal=(100, 60, 1100, 760)"
    assert "window: start: apply showCmd=3 normal=(100, 60, 1100, 760) monitor=(0, 0, 1366, 768) work=(0, 0, 1366, 728) dpi=96 screen=1366x768" in said
    assert "window: start: after showCmd=3 normal=(100, 60, 1100, 760) frame=(-8, -8, 1374, 736) zoomed=True" in said
    assert lines(caplog, logging.WARNING) == []
    quit_through_the_menu(rig, thread)
    assert "window: quit: read showCmd=3 flags=0 normal=(100, 60, 1100, 760), saved maximized=True" in lines(caplog)
    assert appstate.load_window(rig.data) == kept(True)


def test_the_close_button_saves_the_placement_before_it_hides_the_window_and_open_gives_it_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    user32 = FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED)
    rig = Rig(tmp_path, monkeypatch, user32=user32)
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    assert handler(window.events.closing)() is False and window.calls == ["hide"] and not user32.visible
    assert appstate.load_window(rig.data) == kept(True)
    assert "window: hide: read showCmd=3 flags=0 normal=(100, 60, 1100, 760), saved maximized=True" in lines(caplog)
    user32.form_bug = True
    menu_item(rig, "Open NeoAPRS").action(rig.toolkits.icons[0], menu_item(rig, "Open NeoAPRS"))
    assert window.calls == ["hide", "show"] and user32.placed == [(winplace.SW_SHOWMAXIMIZED, NORMAL)], "no maximize or restore of pywebview's: the placement"
    assert (user32.show_cmd, user32.normal, user32.visible) == (winplace.SW_SHOWMAXIMIZED, NORMAL, True)
    assert "window: open: the saved placement, maximized=True normal=(100, 60, 1100, 760)" in lines(caplog)
    user32.show_cmd = winplace.SW_SHOWNORMAL                            # the user restores it and moves it to a corner, and closes it again
    user32.normal = (0, 0, 1000, 700)
    handler(window.events.closing)()
    user32.form_bug = False
    menu_item(rig, "Open NeoAPRS").action(rig.toolkits.icons[0], menu_item(rig, "Open NeoAPRS"))
    assert user32.placed[-1] == (winplace.SW_SHOWNORMAL, (0, 0, 1000, 700)) and appstate.load_window(rig.data) == kept(False, (0, 0, 1000, 700))
    quit_through_the_menu(rig, thread)


def test_quit_saves_the_placement_and_the_next_start_is_given_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    rig = Rig(tmp_path, monkeypatch, user32=FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED, normal=(-1700, 100, -900, 700)))     # on a monitor to the left
    quit_through_the_menu(rig, launch(rig))
    assert appstate.load_window(rig.data) == kept(True, (-1700, 100, -900, 700))
    user32 = FakeUser32(visible=False)
    again = Rig(tmp_path / "again", monkeypatch, user32=user32)
    (again.data / appstate.STATE_NAME).write_bytes((rig.data / appstate.STATE_NAME).read_bytes())
    thread = launch(again)
    window = again.toolkits.windows[0]
    assert (window.kwargs["x"], window.kwargs["y"], window.kwargs["width"], window.kwargs["maximized"]) == (-1700, 100, 800, True)
    handler(window.events.before_show)()
    user32.form_shows()
    handler(window.events.shown)()
    assert user32.placed == [(winplace.SW_HIDE, (-1700, 100, -900, 700)), (winplace.SW_SHOWMAXIMIZED, (-1700, 100, -900, 700))]
    quit_through_the_menu(again, thread)


def test_quit_with_the_window_hidden_keeps_what_was_saved_when_it_was_hidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    user32 = FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED)
    rig = Rig(tmp_path, monkeypatch, user32=user32)
    thread = launch(rig)
    handler(rig.toolkits.windows[0].events.closing)()
    user32.normal = (0, 0, 640, 480)                                    # (what a hidden window says is not read)
    quit_through_the_menu(rig, thread)
    assert appstate.load_window(rig.data) == kept(True)
    assert "window: quit: the window is hidden, the placement saved when it was hidden stays" in lines(caplog)


def test_a_minimised_window_is_saved_as_what_it_goes_back_to_and_never_brought_back_minimised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for flags, maximized in ((0, False), (winplace.WPF_RESTORETOMAXIMIZED, True)):
        user32 = FakeUser32(show_cmd=winplace.SW_SHOWMINIMIZED, flags=flags)
        rig = Rig(tmp_path / str(flags), monkeypatch, user32=user32)
        thread = launch(rig)
        menu_item(rig, "Open NeoAPRS").action(rig.toolkits.icons[0], menu_item(rig, "Open NeoAPRS"))      # the window is on the taskbar: Open takes it back
        assert user32.placed == [(winplace.SW_SHOWMAXIMIZED if maximized else winplace.SW_SHOWNORMAL, NORMAL)]
        user32.show_cmd = winplace.SW_SHOWMINIMIZED
        quit_through_the_menu(rig, thread)
        assert appstate.load_window(rig.data) == kept(maximized)


def test_the_events_only_start_the_timer_and_what_is_saved_is_what_windows_says_then(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.desktop")
    monkeypatch.setattr(winplace, "SAVE_SIZE_SEC", 0.05)
    user32 = FakeUser32(normal=(10, 20, 1010, 720))
    rig = Rig(tmp_path / "w", monkeypatch, user32=user32)
    thread = launch(rig)
    e = rig.toolkits.windows[0].events
    handler(e.moved)(-8, -8)                                            # a maximize as pywebview tells it, in any order: the payloads are not used
    handler(e.resized)(1382, 744)
    handler(e.maximized)()
    user32.show_cmd = winplace.SW_SHOWMAXIMIZED
    until(lambda: appstate.load_window(rig.data) == kept(True, (10, 20, 1010, 720)))
    debug = lines(caplog, logging.DEBUG)
    assert any(m.startswith("window: event resized (1382, 744) [") for m in debug) and any(m.startswith("window: settled: read showCmd=3") for m in debug)
    quit_through_the_menu(rig, thread)


def test_a_file_of_an_earlier_version_opens_at_the_default_size_in_the_middle_and_keeps_only_maximized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    user32 = FakeUser32(normal=(43, 34, 1323, 834), visible=False)
    for maximized in (False, True):
        rig = Rig(tmp_path / str(maximized), monkeypatch, user32=user32)
        appstate.save_window(rig.data, appstate.WindowState(1382, 744, 0, 20, maximized))       # (what 0.12.0 wrote on the laptop: the size of the screen, a little down)
        thread = launch(rig)
        window = rig.toolkits.windows[0]
        assert (window.kwargs["width"], window.kwargs["height"], window.kwargs["maximized"]) == (*appstate.DEFAULT_SIZE, maximized) and "x" not in window.kwargs
        handler(window.events.before_show)()
        user32.form_shows()
        handler(window.events.shown)()
        assert user32.placed[-1] == (winplace.SW_SHOWMAXIMIZED if maximized else winplace.SW_SHOWNORMAL, (43, 34, 1323, 834)), "the rectangle the form opened with"
        quit_through_the_menu(rig, thread)
    assert any("no placement (old: 1382x744 at 0,20 maximized=False)" in m for m in lines(caplog))


def test_a_placement_that_does_not_hold_is_a_warning_in_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    user32 = FakeUser32(visible=False)
    rig = Rig(tmp_path, monkeypatch, user32=user32)
    appstate.save_window(rig.data, kept(True))
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    user32.undo = True
    user32.form_shows()
    handler(window.events.shown)()
    assert lines(caplog, logging.WARNING) == ["window: start: the window is not as applied (showCmd=3 normal=(100, 60, 1100, 760))"]
    assert "window: start: after showCmd=1 normal=(100, 60, 1100, 760) frame=(100, 60, 1100, 760) zoomed=False" in lines(caplog)
    quit_through_the_menu(rig, thread)


def test_a_window_started_in_the_tray_gets_its_placement_when_it_is_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.desktop")
    user32 = FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED, visible=False)
    rig = Rig(tmp_path, monkeypatch, hidden=True, user32=user32)
    appstate.save_window(rig.data, kept(True))
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    handler(window.events.before_show)()
    handler(window.events.shown)()                                      # (pywebview shows and hides it at once: the shown comes with the window hidden)
    assert user32.placed == [(winplace.SW_HIDE, NORMAL)] and "window: start: in the tray, the placement is applied when the window is opened" in lines(caplog)
    menu_item(rig, "Open NeoAPRS").action(rig.toolkits.icons[0], menu_item(rig, "Open NeoAPRS"))
    assert user32.placed[-1] == (winplace.SW_SHOWMAXIMIZED, NORMAL) and user32.visible
    quit_through_the_menu(rig, thread)


def test_a_window_in_the_tray_that_cannot_load_its_page_yet_leaves_the_app_listening_and_gets_the_page_when_it_is_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                                                       caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(tmp_path, monkeypatch, hidden=True)
    create = rig.toolkits.create_window

    def unshown(*args: Any, **kwargs: Any) -> FakeWindow:
        window = create(*args, **kwargs)
        window.shown = False
        return window

    monkeypatch.setattr(sys.modules["webview"], "create_window", unshown)
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    until(lambda: "window: the page is loaded when the window is shown (Main window failed to start)" in lines(caplog, logging.WARNING))
    assert rig.ctx.watch is not None and window.loaded == [], "the app heard the session (the daemon watched, the one-app lock answered) though the page waits"
    window.shown = True
    for shown in window.events.shown.handlers:
        shown()
    window.events.shown.handlers[-1]()
    assert window.loaded == [PAGE + "#app"], "the page once, at the first show"
    quit_through_the_menu(rig, thread)


def test_where_there_is_no_win32_no_call_is_made_and_open_is_pywebviews(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user32 = FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED)
    rig = Rig(tmp_path, monkeypatch, user32=user32, windll=False)
    assert not hasattr(ctypes, "windll"), "(the rig takes Windows' windll away, so that this runs as on any other system)"
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    assert winplace.Win32Window.of(window) is None and winplace.Win32Window.of(types.SimpleNamespace(native=None)) is None
    handler(window.events.before_show)()
    handler(window.events.shown)()
    handler(window.events.resized)(1382, 744)
    assert handler(window.events.closing)() is False
    menu_item(rig, "Open NeoAPRS").action(rig.toolkits.icons[0], menu_item(rig, "Open NeoAPRS"))
    assert window.calls == ["hide", "show", "restore"]
    quit_through_the_menu(rig, thread)
    assert user32.calls == [] and not (rig.data / appstate.STATE_NAME).exists()


def test_a_win32_that_fails_is_none_and_false_never_an_error() -> None:
    class Broken:
        def __getattr__(self, name: str) -> Any:
            if name == "GetDpiForWindow":
                raise AttributeError(name)                              # (Windows before 10 1607)

            def fails(*args: Any) -> int:
                raise OSError("the handle is gone")
            return fails
    win = winplace.Win32Window(Broken(), 1)
    assert (win.placement(), win.place(NORMAL, winplace.SW_SHOWNORMAL), win.visible(), win.zoomed(), win.frame(), win.monitor(NORMAL), win.dpi(), win.screen()) == (None, False, False, False, None, None, None, None)
    assert winplace.Placement(winplace.SW_SHOWMINIMIZED, 0, NORMAL).maximized is False and winplace.Placement(winplace.SW_SHOWMINIMIZED, 2, NORMAL).maximized is True
    assert ctypes.sizeof(winplace._Placement) == 44, "WINDOWPLACEMENT, as Windows has it"


def test_the_page_is_given_a_script_that_hands_other_sites_to_the_browser(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    (loaded,) = window.events.loaded.handlers
    loaded()
    assert window.scripts == [webshell.LINK_SCRIPT] and "pywebview.api.open_external" in webshell.LINK_SCRIPT and "location.origin" in webshell.LINK_SCRIPT
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
    frame = webshell.WebFrame(True)
    frame.show_window()
    frame.refresh()
    with caplog.at_level("WARNING", "neoaprs.desktop"):
        frame.tell("the daemon was started")
    assert [r.getMessage() for r in caplog.records] == ["the daemon was started"]


def test_a_message_is_a_notification_of_the_icon_where_there_is_one_and_quit_with_no_window_only_ends_the_wait() -> None:
    frame = webshell.WebFrame(False)
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



# ---- the Windows tray icon's image, without Pillow

def test_the_tray_image_writes_the_bytes_of_icon_ico_as_pystray_asks_for_an_ico() -> None:
    import io
    image = webshell.IcoFile()
    assert image.path == webshell.ico_path() and image.path.name == "icon.ico" and image.path.is_file()
    for format in ("ICO", "ico", None):
        out = io.BytesIO()
        image.save(out, format=format)
        assert out.getvalue() == image.path.read_bytes(), format
    data = image.path.read_bytes()
    assert data[:4] == b"\0\0\1\0", "an icon file"
    with pytest.raises(ValueError, match="PNG"):
        image.save(io.BytesIO(), format="PNG")


def test_a_missing_icon_file_fails_the_shell_where_it_starts_and_not_later_in_pystrays_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """pystray asks the image for its file in its own thread, when the icon is shown; a failure there is a line in the log and an app without a tray, whose window then hides into nothing. So icon.ico is
    read when the icon is made, on the thread that starts the shell, whose failure the app answers with the page in the browser."""
    gone = tmp_path / "icon.ico"
    with pytest.raises(FileNotFoundError):
        webshell.IcoFile(gone)
    Toolkits(monkeypatch)
    monkeypatch.setattr(webshell, "SYSTEM", "win32")
    monkeypatch.setattr(webshell, "ico_path", lambda: gone)
    with pytest.raises(FileNotFoundError):
        webshell.make_icon(webshell.WebFrame(True))
    gone.write_bytes(b"\0\0\1\0 made up")
    image = webshell.IcoFile(gone)
    gone.unlink()
    import io
    out = io.BytesIO()
    image.save(out, format="ICO")
    assert out.getvalue() == b"\0\0\1\0 made up", "what pystray is given later is what was read"


def test_the_real_pystray_asks_the_image_to_write_itself_as_an_ico_and_has_windows_load_that_file() -> None:
    """pystray 0.19.5 on Windows: `_assert_icon_handle` makes the file with `serialized_image(self.icon, 'ICO')` and loads it with LoadImage; `serialized_image` calls `image.save(f, format=format)`.
    A pystray whose code says otherwise fails here, on the CI's Windows job, and not in an operator's tray."""
    if sys.platform != "win32":
        pytest.skip("the real pystray is installed with the extra app on Windows only")
    util = pytest.importorskip("pystray._util")
    win32 = pytest.importorskip("pystray._win32")
    made = inspect.getsource(util.serialized_image)
    assert "image.save(f, format=format)" in made
    loaded = inspect.getsource(win32.Icon._assert_icon_handle)
    assert "serialized_image(self.icon, 'ICO')" in loaded and "LoadImage(" in loaded and "LR_LOADFROMFILE" in loaded
    with util.serialized_image(webshell.IcoFile(), "ICO") as path:
        assert Path(path).read_bytes() == webshell.ico_path().read_bytes(), "the file Windows loads is icon.ico"


# What the frozen app has on Windows: pystray and its Windows backend with no Pillow at all (the spec excludes PIL). Run in a Python of its own, in which any import of PIL fails.
WITHOUT_PILLOW = """
import sys
sys.modules["PIL"] = None
import pystray, pystray._win32, pystray._util, pystray._util.win32
from neoaprs.desktop import webshell
assert pystray.Icon is pystray._win32.Icon, pystray.Icon
with pystray._util.serialized_image(webshell.IcoFile(), "ICO") as path:
    with open(path, "rb") as made:
        assert made.read() == webshell.ico_path().read_bytes()
print("pystray without Pillow")
"""


def test_the_real_pystray_and_its_windows_backend_run_without_pillow() -> None:
    """The CI's Windows job has Pillow (the extra app installs it, as pystray asks), the frozen app has none. A pystray whose Windows modules or shared helpers import PIL fails here, and not in an
    operator's tray."""
    if sys.platform != "win32":
        pytest.skip("the real pystray is installed with the extra app on Windows only")
    pytest.importorskip("pystray._win32")
    import subprocess
    env = {name: value for name, value in os.environ.items() if name != "PYSTRAY_BACKEND"}
    done = subprocess.run([sys.executable, "-c", WITHOUT_PILLOW], capture_output=True, text=True, timeout=120, env=env, cwd=Path(__file__).resolve().parents[1])
    assert done.returncode == 0 and "pystray without Pillow" in done.stdout, done.stderr

# ---- Linux and macOS: the web window of the trial (NEOAPRS_WINDOW=web). The tray host, the desktop's scheme and the screens are stood in for here; their own calls of gi further down.

class Desk:
    """What a Linux desktop answers the shell: whether a tray host is there, whether the remembered place is on a screen, and where the first monitor is (GDK's); GLib's idle calls are made at once."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, host: bool = True, on_screen: bool = True, first_monitor: tuple[int, int] = (0, 0)) -> None:
        self.host = host
        self.on_screen = on_screen
        monkeypatch.setattr(webdesk, "tray_host", lambda system: self.host)
        monkeypatch.setattr(webdesk, "portal_dark", lambda: True)
        monkeypatch.setattr(webdesk, "on_a_screen", lambda system, x, y: self.on_screen)
        area = types.SimpleNamespace(x=first_monitor[0], y=first_monitor[1], width=1920, height=1080)
        gdk = types.ModuleType("gi.repository.Gdk")
        gdk.Display = types.SimpleNamespace(get_default=lambda: types.SimpleNamespace(get_monitor=lambda n: types.SimpleNamespace(get_geometry=lambda: area)))  # type: ignore[attr-defined]
        glib = types.ModuleType("gi.repository.GLib")
        glib.idle_add = lambda call: call()  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "gi.repository.Gdk", gdk)
        monkeypatch.setitem(sys.modules, "gi.repository.GLib", glib)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setattr("neoaprs.desktop.sizekeep.SAVE_AFTER_SEC", 0.05)


def linux_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Rig:
    return Rig(tmp_path, monkeypatch, system="linux", **kwargs)


def test_on_linux_the_window_is_gtks_with_its_own_store_the_icon_and_the_size_and_place_it_was_left_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch)
    user32 = FakeUser32()
    rig = Rig(tmp_path, monkeypatch, user32=user32, system="linux")
    appstate.save_window(rig.data, appstate.WindowState(1000, 700, 40, 30, False))
    thread = launch(rig)
    (window,) = rig.toolkits.windows
    assert (window.kwargs["width"], window.kwargs["height"], window.kwargs["x"], window.kwargs["y"], window.kwargs["maximized"]) == (1000, 700, 40, 30, False)
    assert window.kwargs["background_color"] == loading.background(True), "the desktop's dark scheme, before anything is painted"
    (started,) = rig.toolkits.started
    assert started == {"gui": "gtk", "private_mode": False, "storage_path": str(rig.data / "webkit"), "icon": str(webshell.icon_path())}
    assert (rig.data / "webkit").is_dir() and not (rig.data / "webview").exists(), "a store of its own: the Qt window's stays as it was"
    assert rig.toolkits.settings["ALLOW_DOWNLOADS"] is True and rig.toolkits.icons[0].calls == ["run_detached", "update_menu"]
    assert rig.toolkits.icons[0].image == ("image", str(webshell.icon_path())), "on Linux the tray's image is Pillow's of icon.png (pystray's appindicator writes it as a PNG)"
    e = window.events
    handler(e.resized)(1100, 750)
    window.frame_at = (50, 60)
    handler(e.moved)(52, 97)                                            # (what pywebview tells: the inside, below the title bar)
    until(lambda: appstate.load_window(rig.data) == appstate.WindowState(1100, 750, 50, 60, False))
    quit_through_the_menu(rig, thread)
    assert user32.calls == [], "no Win32 on Linux"


def test_on_x11_the_frames_place_is_kept_and_given_back_without_the_first_monitors_corner_which_pywebview_adds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch, first_monitor=(1920, 0))                          # (a screen to the left of the first one: the desktop's places of the first one start at 1920)
    rig = linux_rig(tmp_path, monkeypatch)
    appstate.save_window(rig.data, appstate.WindowState(1000, 700, 2000, 100, False))
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    assert (window.kwargs["x"], window.kwargs["y"]) == (80, 100), "pywebview moves it to 1920 + 80: where it was"
    window.frame_at = (2100, 120)
    handler(window.events.moved)(2102, 157)
    until(lambda: (appstate.load_window(rig.data).x, appstate.load_window(rig.data).y) == (2100, 120))
    quit_through_the_menu(rig, thread)
    assert webdesk.screen_origin("darwin") == (0, 0), "(macOS: not asked)"


def test_a_maximize_keeps_the_size_it_goes_back_to_and_a_minimise_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch)
    rig = linux_rig(tmp_path, monkeypatch)
    appstate.save_window(rig.data, appstate.WindowState(1000, 700, 40, 30, False))
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    e = window.events
    handler(e.resized)(1920, 1040)                                      # what GTK says of a maximize, the size before the state
    handler(e.moved)(0, 0)
    handler(e.maximized)()
    until(lambda: appstate.load_window(rig.data) == appstate.WindowState(1000, 700, 40, 30, True))
    handler(e.minimized)()
    handler(e.restored)()                                              # (out of the minimised state: still maximized)
    handler(e.closing)()
    assert appstate.load_window(rig.data) == appstate.WindowState(1000, 700, 40, 30, True)
    menu_item(rig, "Open NeoAPRS").action(rig.toolkits.icons[0], menu_item(rig, "Open NeoAPRS"))
    assert window.calls == ["hide", "show", "restore", "maximize"], "Open brings it back and gives it back maximized"
    handler(e.restored)()
    handler(e.resized)(1000, 700)
    until(lambda: appstate.load_window(rig.data) == appstate.WindowState(1000, 700, 40, 30, False))
    quit_through_the_menu(rig, thread)


@pytest.mark.parametrize("system, maximized, calls", [
    ("linux", True, ["show", "restore", "maximize"]),          # GTK: show and maximize leave a minimised window on the taskbar; its restore brings it back and keeps it maximized
    ("linux", False, ["show", "restore"]),
    ("darwin", True, ["show", "maximize"]),                    # (Cocoa's restore would make it a normal window)
    ("darwin", False, ["show", "restore"]),
])
def test_a_window_left_maximized_and_minimised_is_brought_back_maximized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, maximized: bool, calls: list[str]) -> None:
    monkeypatch.setattr(webshell, "SYSTEM", system)
    frame = webshell.WebFrame(True)
    frame.window = FakeWindow((), {})
    frame.sizes = sizekeep.SizeKeeper(tmp_path, appstate.WindowState(1000, 700, 40, 30, maximized))
    frame.sizes.event("minimized")
    frame.show_window()                                       # (a second start, or the tray's Open)
    frame.sizes.stop()
    assert frame.window.calls == calls


@pytest.mark.parametrize("wayland, on_screen", [(True, True), (False, False)])
def test_on_wayland_or_off_every_screen_the_window_opens_in_the_middle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wayland: bool, on_screen: bool) -> None:
    Desk(monkeypatch, on_screen=on_screen)
    if wayland:
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.delenv("GDK_BACKEND", raising=False)
    rig = linux_rig(tmp_path, monkeypatch)
    appstate.save_window(rig.data, appstate.WindowState(1000, 700, 40, 30, False))
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    assert "x" not in window.kwargs and (window.kwargs["width"], window.kwargs["height"]) == (1000, 700)
    window.frame_at = (10, 10)
    handler(window.events.moved)(12, 47)
    handler(window.events.resized)(900, 600)
    until(lambda: appstate.load_window(rig.data).width == 900)
    assert appstate.load_window(rig.data).x == (None if wayland else 10), "Wayland tells no place; X11 does"
    quit_through_the_menu(rig, thread)


def test_the_close_button_hides_the_window_while_the_desktop_has_a_tray_and_quits_when_it_has_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desk = Desk(monkeypatch)
    rig = linux_rig(tmp_path, monkeypatch)
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    closing = handler(window.events.closing)
    assert closing() is False and window.calls == ["hide"] and thread.is_alive()
    desk.host = False                                                   # the tray host went away (GNOME without its extension)
    assert closing() is False, "the close is cancelled: the loop runs on until Quit has done its part"
    thread.join(10)
    assert not thread.is_alive() and window.calls[-1] == "destroy" and closing() is True
    rig.ctx.close()


def test_a_window_without_a_tray_icon_is_a_window_whose_close_button_quits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch)
    rig = linux_rig(tmp_path, monkeypatch)
    rig.tray = False
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.ctx.watch is not None and bool(rig.toolkits.windows) and bool(rig.toolkits.windows[0].loaded))     # (the watch is there a moment before the window has loaded the page: under a full load the test was there first)
    window = rig.toolkits.windows[0]
    assert rig.toolkits.icons == [] and window.loaded == [PAGE + "#app"]
    assert handler(window.events.closing)() is False
    thread.join(10)
    assert not thread.is_alive() and window.calls[-1] == "destroy"
    rig.ctx.close()


@pytest.mark.expects_errors
def test_an_icon_that_cannot_be_made_leaves_the_window_without_one_and_with_no_window_the_failure_is_the_shells(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch)
    rig = linux_rig(tmp_path, monkeypatch)

    def refused(*args: Any) -> FakeIcon:
        raise RuntimeError("no StatusNotifier")
    monkeypatch.setattr(sys.modules["pystray"], "Icon", refused)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.ctx.watch is not None)
    assert handler(rig.toolkits.windows[0].events.closing)() is False
    thread.join(10)
    assert not thread.is_alive()
    rig.ctx.close()
    alone = linux_rig(tmp_path / "alone", monkeypatch, window=False)
    monkeypatch.setattr(sys.modules["pystray"], "Icon", refused)            # (the new rig's stand-ins)
    with pytest.raises(RuntimeError, match="nothing to show"):
        alone.run()
    alone.single.close()


def test_closed_before_the_page_came_with_no_tray_the_app_ends_when_it_comes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch, host=False)
    rig = linux_rig(tmp_path, monkeypatch)
    came = threading.Event()

    def slow() -> Session:
        assert came.wait(30)
        return Session(rig.data, PAGE, owned=False)
    assert rig.single.acquire()
    pending = Launch(rig.data, Opening(rig.data, slow).start(), False, True, rig.auto, rig.single, rig.daemon)
    thread = threading.Thread(target=lambda: webshell.run(pending), daemon=True)
    thread.start()
    until(lambda: rig.toolkits.started)
    window = rig.toolkits.windows[0]
    assert handler(window.events.closing)() is False and window.calls == ["hide"] and thread.is_alive()
    came.set()
    thread.join(10)
    assert not thread.is_alive() and window.loaded == [] and window.calls[-1] == "destroy"
    pending.close()


def test_started_in_the_tray_it_looks_for_the_tray_for_a_while_and_shows_the_window_if_none_comes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    desk = Desk(monkeypatch, host=False)
    monkeypatch.setattr(webdesk, "TRAY_WAIT_SEC", 0.2)
    monkeypatch.setattr(webdesk, "TRAY_POLL_SEC", 0.02)
    rig = linux_rig(tmp_path, monkeypatch, hidden=True)
    thread = launch(rig)
    window = rig.toolkits.windows[0]
    until(lambda: "show" in window.calls)
    assert window.kwargs["hidden"] is True and "this desktop has no system tray: the window stays" in caplog.text
    quit_through_the_menu(rig, thread)
    desk.host = True
    again = linux_rig(tmp_path / "again", monkeypatch, hidden=True)
    thread = launch(again)
    quit_through_the_menu(again, thread)
    assert again.toolkits.windows[0].calls == ["destroy"], "the tray was there: the window stays hidden"


def test_started_in_the_tray_with_no_tray_icon_at_all_the_window_is_shown_at_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch, host=False)
    rig = linux_rig(tmp_path, monkeypatch, hidden=True)
    rig.tray = False
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    window_calls = lambda: rig.toolkits.windows[0].calls if rig.toolkits.windows else []  # noqa: E731
    until(lambda: window_calls()[:2] == ["show", "restore"])
    assert handler(rig.toolkits.windows[0].events.closing)() is False
    thread.join(10)
    rig.ctx.close()


class FakeGLib(types.ModuleType):
    """gi's GLib as far as the tray's own loop asks it: a main loop that runs until it is told to quit, and idle_add, which calls at once."""

    def __init__(self) -> None:
        super().__init__("gi.repository.GLib")
        self.loops: list[Any] = []
        ended = threading.Event()

        class Loop:
            @staticmethod
            def new(_context: object, _running: bool) -> "Loop":
                loop = Loop()
                self.loops.append(loop)
                return loop

            def run(self) -> None:
                assert ended.wait(10)

            def quit(self) -> None:
                ended.set()

        self.MainLoop = Loop
        self.idle_add = lambda call, *args: call(*args)


def test_on_linux_without_a_window_the_tray_runs_on_a_glib_loop_of_its_own_until_quit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Desk(monkeypatch)
    glib = FakeGLib()
    monkeypatch.setitem(sys.modules, "gi.repository.GLib", glib)
    rig = linux_rig(tmp_path, monkeypatch, window=False)
    thread = launch(rig)
    until(lambda: glib.loops)
    assert rig.browser == [PAGE] and rig.toolkits.started == [] and rig.toolkits.icons[0].calls == ["run_detached"]
    quit_through_the_menu(rig, thread)


class FakeAppHelper(types.ModuleType):
    """PyObjCTools.AppHelper: callAfter queues a call to the main thread, here a list the test runs; the event loop runs until stopEventLoop."""

    def __init__(self) -> None:
        super().__init__("PyObjCTools.AppHelper")
        self.queued: list[Any] = []
        self.ended = threading.Event()
        self.callAfter = self.queued.append

    def runEventLoop(self) -> None:
        assert self.ended.wait(10)

    def stopEventLoop(self) -> None:
        self.ended.set()


def test_on_macos_the_window_is_wkwebviews_and_the_trays_calls_go_to_the_main_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    helper = FakeAppHelper()
    monkeypatch.setitem(sys.modules, "PyObjCTools", types.ModuleType("PyObjCTools"))
    monkeypatch.setitem(sys.modules, "PyObjCTools.AppHelper", helper)
    monkeypatch.setattr(webdesk, "mac_dark", lambda: False)
    rig = Rig(tmp_path, monkeypatch, system="darwin")
    thread = launch(rig)
    assert rig.toolkits.started == [{"gui": "cocoa", "private_mode": False}], "WKWebView keeps the page's store in the system's place for the app"
    icon = rig.toolkits.icons[0]
    until(lambda: helper.queued)
    assert icon.calls == ["run_detached"], "the menu's update is queued, not made from pywebview's thread"
    for call in list(helper.queued):
        call()
    assert icon.calls == ["run_detached", "update_menu"]
    window = rig.toolkits.windows[0]
    assert handler(window.events.closing)() is False and window.calls == ["hide"], "the menu bar is always there to bring it back from"
    quit_through_the_menu(rig, thread)


@pytest.mark.expects_errors
def test_a_window_that_cannot_start_on_macos_goes_on_in_the_menu_bar_on_the_event_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    helper = FakeAppHelper()
    monkeypatch.setitem(sys.modules, "PyObjCTools", types.ModuleType("PyObjCTools"))
    monkeypatch.setitem(sys.modules, "PyObjCTools.AppHelper", helper)
    monkeypatch.setattr(webdesk, "mac_dark", lambda: False)
    rig = Rig(tmp_path, monkeypatch, system="darwin", start_fails=True)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.browser == [PAGE] and rig.ctx.watch is not None)
    item = menu_item(rig, "Quit")
    item.action(rig.toolkits.icons[0], item)
    until(lambda: helper.stopEventLoop in helper.queued)
    for call in list(helper.queued):
        call()
    thread.join(10)
    assert not thread.is_alive()
    rig.ctx.close()


# ---- what the shell asks of gi and pyobjc itself: the tray host on the session bus, the desktop's scheme, the screens, macOS's appearance

class FakeBus:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[Any, ...]] = []

    def call_sync(self, name: str, path: str, interface: str, method: str, args: Any, reply: Any, flags: Any, timeout: int, cancel: Any) -> Any:
        self.calls.append((name, path, interface, method, args.value, timeout))
        answer = self.answers[method]
        if isinstance(answer, Exception):
            raise answer
        return types.SimpleNamespace(unpack=lambda: answer)


def fake_gio(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> FakeBus:
    bus = FakeBus(answers)
    gio = types.ModuleType("gi.repository.Gio")
    gio.BusType = types.SimpleNamespace(SESSION="session")  # type: ignore[attr-defined]
    gio.DBusCallFlags = types.SimpleNamespace(NONE=0)  # type: ignore[attr-defined]
    gio.bus_get_sync = lambda kind, cancel: bus  # type: ignore[attr-defined]
    glib = types.ModuleType("gi.repository.GLib")
    glib.Variant = lambda signature, value: types.SimpleNamespace(signature=signature, value=value)  # type: ignore[attr-defined]
    glib.VariantType = types.SimpleNamespace(new=lambda signature: signature)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gi.repository.Gio", gio)
    monkeypatch.setitem(sys.modules, "gi.repository.GLib", glib)
    return bus


def test_the_tray_host_is_the_owner_of_the_status_notifier_watcher_on_the_session_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = fake_gio(monkeypatch, {"NameHasOwner": (True,)})
    assert webdesk.tray_host("linux") is True
    assert bus.calls == [("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner", ("org.kde.StatusNotifierWatcher",), webdesk.BUS_WAIT_MS)]
    bus.answers["NameHasOwner"] = (False,)
    assert webdesk.tray_host("linux") is False
    bus.answers["NameHasOwner"] = RuntimeError("no session bus")
    assert webdesk.tray_host("linux") is False, "a bus that cannot be asked is no tray"
    assert webdesk.tray_host("darwin") is True, "the menu bar is always there"


def test_the_linux_scheme_is_the_settings_portals_color_scheme_and_light_where_it_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = fake_gio(monkeypatch, {"Read": (1,)})
    assert webdesk.portal_dark() is True and bus.calls[0][3:5] == ("Read", ("org.freedesktop.appearance", "color-scheme"))
    for answer in ((0,), (2,), RuntimeError("no portal")):                # no preference, light, no portal
        bus.answers["Read"] = answer
        assert webdesk.portal_dark() is False


def test_the_macos_scheme_is_the_users_interface_style(monkeypatch: pytest.MonkeyPatch) -> None:
    style: list[Any] = ["Dark"]
    foundation = types.ModuleType("Foundation")
    foundation.NSUserDefaults = types.SimpleNamespace(standardUserDefaults=lambda: types.SimpleNamespace(stringForKey_=lambda key: style[0] if key == "AppleInterfaceStyle" else None))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "Foundation", foundation)
    assert webdesk.mac_dark() is True
    style[0] = None
    assert webdesk.mac_dark() is False
    monkeypatch.delitem(sys.modules, "Foundation")
    monkeypatch.setattr(webdesk.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    assert webdesk.mac_dark() is False


def test_a_place_is_on_a_screen_when_gdks_nearest_monitor_holds_its_title_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[int, int]] = []
    area = types.SimpleNamespace(x=0, y=0, width=1920, height=1080)

    def monitor_at(x: int, y: int) -> Any:
        asked.append((x, y))
        return types.SimpleNamespace(get_geometry=lambda: area)
    gdk = types.ModuleType("gi.repository.Gdk")
    gdk.Display = types.SimpleNamespace(get_default=lambda: types.SimpleNamespace(get_monitor_at_point=monitor_at))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gi.repository.Gdk", gdk)
    assert webdesk.on_a_screen("linux", 40, 30) and asked == [(104, 46)]
    assert not webdesk.on_a_screen("linux", 2400, 30), "a monitor to the right that is gone"
    assert webdesk.on_a_screen("darwin", 2400, 30), "(macOS: not asked)"
    monkeypatch.delitem(sys.modules, "gi.repository.Gdk")
    monkeypatch.setattr(webdesk.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    assert not webdesk.on_a_screen("linux", 40, 30), "when the screens cannot be asked, the window opens in the middle"
    assert webdesk.screen_origin("linux") == (0, 0), "(and the first monitor is taken to be at the corner)"


# ---- the size keeper (sizekeep.py), alone

def test_the_size_keeper_saves_once_the_events_have_stopped_and_not_after_it_is_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sizekeep, "SAVE_AFTER_SEC", 0.05)
    keeper = sizekeep.SizeKeeper(tmp_path, appstate.WindowState(1000, 700, 40, 30, False))
    keeper.told("resized")(1200, 800)
    keeper.told("moved")(5, 6)
    keeper.told("shown")()                                               # (an event it does not keep)
    keeper.told("resized")("wide", None)                                 # (a payload it cannot read)
    until(lambda: appstate.load_window(tmp_path) == appstate.WindowState(1200, 800, 5, 6, False))
    keeper.stop()
    keeper.told("resized")(640, 480)
    threading.Event().wait(0.2)
    assert appstate.load_window(tmp_path).width == 1200, "stopped: Quit saved what it had"
    started_maximized = sizekeep.SizeKeeper(tmp_path, appstate.WindowState(1000, 700, None, None, True), keep_place=False)
    started_maximized.told("resized")(1920, 1040)
    started_maximized.told("moved")(0, 0)
    started_maximized.save()
    assert appstate.load_window(tmp_path) == appstate.WindowState(1000, 700, None, None, True), "a window that started maximized goes back to the size it had"
    started_maximized.stop()


# ---- gtkenv: the carried libraries and typelibs, and the sandbox, on fake folders and a fake /proc

@pytest.fixture
def fresh_ground(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gtkenv, "_done", None)


def carried(tmp_path: Path, libs: tuple[str, ...] = gtkenv.LIBRARIES, tray: bool = True, webkit: bool = True) -> Path:
    folder = tmp_path / "neoaprs-gtk"
    (folder / "lib").mkdir(parents=True)
    for name in libs:
        (folder / "lib" / name).write_bytes(b"\x7fELF")
    for kind, wanted, typelib in (("tray", tray, gtkenv.TRAY_TYPELIB), ("webkit", webkit, gtkenv.WEBKIT_TYPELIB)):
        if wanted:
            (folder / f"girepository-{kind}").mkdir()
            (folder / f"girepository-{kind}" / typelib).write_bytes(b"GOBJ")
    return folder


def proc(tmp_path: Path, restrict: str | None = "0", max_ns: str | None = "63000") -> Path:
    root = tmp_path / "proc"
    for path, value in (("sys/kernel/apparmor_restrict_unprivileged_userns", restrict), ("sys/user/max_user_namespaces", max_ns)):
        if value is not None:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(value + "\n", encoding="ascii")
    return root


def by_path(name: str) -> bool:
    """A load by a path, not by a name: str(Path) has the system's separator (a backslash where the suite runs on Windows)."""
    return "/" in name or os.sep in name


class Loader:
    """The dynamic linker as gtkenv asks it: the names the system can load, and every load, by name or by path."""

    def __init__(self, system: set[str]) -> None:
        self.system = system
        self.loaded: list[str] = []

    def __call__(self, name: str) -> object:
        if not by_path(name) and name not in self.system:
            raise OSError(f"{name}: cannot open shared object file")
        self.loaded.append(name)
        return object()


TOOLS = {"bwrap": "/usr/bin/bwrap", "xdg-dbus-proxy": "/usr/bin/xdg-dbus-proxy"}
RUNS = {"/usr/bin/bwrap"}.__contains__                                       # bubblewrap, tried, starts its program


def never(bwrap: str) -> bool:
    raise AssertionError("bubblewrap is not tried where the files already say no")


def test_a_carried_library_is_loaded_by_its_path_only_where_the_system_has_none_of_that_name(tmp_path: Path) -> None:
    folder = carried(tmp_path)
    load = Loader({"libdbusmenu-glib.so.4", "libdbusmenu-gtk3.so.4"})          # (Ubuntu's desktop: dbusmenu, not the AppIndicator)
    assert gtkenv.carry_libraries(folder / "lib", load) == ["libayatana-ido3-0.4.so.0", "libayatana-indicator3.so.7", "libayatana-appindicator3.so.1"]
    assert [n for n in load.loaded if by_path(n)] == [str(folder / "lib" / n) for n in ("libayatana-ido3-0.4.so.0", "libayatana-indicator3.so.7", "libayatana-appindicator3.so.1")], "in the order they need each other"
    assert gtkenv.carry_libraries(tmp_path / "none", Loader(set())) == []


def test_the_carried_typelibs_are_used_only_where_the_system_has_none_and_webkits_only_beside_its_library(tmp_path: Path) -> None:
    folder = carried(tmp_path)
    system = tmp_path / "girepository-1.0"
    system.mkdir()
    with_41 = Loader({gtkenv.WEBKIT_LIBRARY})
    assert gtkenv.typelib_path(folder, with_41, [system]) == [str(folder / "girepository-tray"), str(folder / "girepository-webkit")], "Debian 13 Xfce: the library, no typelib"
    assert gtkenv.typelib_path(folder, Loader(set()), [system]) == [str(folder / "girepository-tray")], "Ubuntu 22.04: no 4.1 library, so pywebview takes the system's 4.0"
    (system / gtkenv.WEBKIT_TYPELIB).write_bytes(b"GOBJ")
    (system / gtkenv.TRAY_TYPELIB).write_bytes(b"GOBJ")
    assert gtkenv.typelib_path(folder, with_41, [system]) == [], "the system's typelibs win: they match its own libraries"


def test_the_sandbox_is_asked_for_where_user_namespaces_and_bubblewrap_are_there_and_never_against_the_environment(tmp_path: Path, fresh_ground: None) -> None:
    assert gtkenv.sandbox_possible(proc(tmp_path), TOOLS.get, RUNS)
    assert gtkenv.sandbox_possible(proc(tmp_path / "old", None, None), TOOLS.get, RUNS), "a kernel without the AppArmor knob"
    assert not gtkenv.sandbox_possible(proc(tmp_path / "ubuntu", "1"), TOOLS.get, never), "Ubuntu 24.04's AppArmor rule"
    assert not gtkenv.sandbox_possible(proc(tmp_path / "none", "0", "0"), TOOLS.get, never), "a kernel with no user namespaces"
    debian = proc(tmp_path / "debian", None)
    (debian / "sys" / "kernel").mkdir(parents=True, exist_ok=True)
    (debian / "sys" / "kernel" / "unprivileged_userns_clone").write_text("0\n", encoding="ascii")
    assert not gtkenv.sandbox_possible(debian, TOOLS.get, never), "Debian's own switch, off"
    assert not gtkenv.sandbox_possible(proc(tmp_path), {"bwrap": "/usr/bin/bwrap"}.get, never), "WebKit's web process would not start without its D-Bus proxy"
    assert not gtkenv.sandbox_possible(proc(tmp_path), TOOLS.get, lambda bwrap: False), "a container whose seccomp refuses the namespaces: bubblewrap, tried, fails"
    environ: dict[str, str] = {}
    said = gtkenv.prepare(tmp_path / "nothing", environ, Loader(set()), [], proc(tmp_path), TOOLS.get, RUNS)
    assert environ == {"WEBKIT_FORCE_SANDBOX": "1"} and said == ["the web content in WebKit's sandbox"], "outside the AppImage only the sandbox"
    assert gtkenv.prepare(tmp_path / "nothing", environ, Loader(set()), [], proc(tmp_path), TOOLS.get, RUNS) == [], "once"


def test_the_ground_in_the_appimage_on_a_system_that_refuses_the_sandbox(tmp_path: Path, fresh_ground: None) -> None:
    folder = carried(tmp_path)
    environ = {"GI_TYPELIB_PATH": "/opt/own"}
    said = gtkenv.prepare(folder, environ, Loader({gtkenv.WEBKIT_LIBRARY}), [], proc(tmp_path, "1"), TOOLS.get, never)
    assert environ["GI_TYPELIB_PATH"] == os.pathsep.join([str(folder / "girepository-tray"), str(folder / "girepository-webkit"), "/opt/own"])
    assert "WEBKIT_FORCE_SANDBOX" not in environ and said[-1].startswith("the web content without WebKit's sandbox")
    assert said[0].startswith("the carried libdbusmenu-glib.so.4") and "girepository-tray, girepository-webkit" in said[1]


def test_a_sandbox_variable_of_the_users_own_is_left_as_it_is(tmp_path: Path, fresh_ground: None) -> None:
    environ = {"WEBKIT_FORCE_SANDBOX": "0"}
    assert gtkenv.prepare(tmp_path / "nothing", environ, Loader(set()), [], proc(tmp_path), TOOLS.get, never) == ["WEBKIT_FORCE_SANDBOX=0 as the environment has it"]
    assert environ == {"WEBKIT_FORCE_SANDBOX": "0"}


@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap is Linux's")
def test_the_try_of_bubblewrap_is_a_fixed_command_and_a_program_that_is_not_there_is_no_sandbox(tmp_path: Path) -> None:
    assert gtkenv.SANDBOX_TRY[-2:] == ("--", "true") and "--unshare-all" in gtkenv.SANDBOX_TRY
    assert gtkenv.bubblewrap_runs(str(tmp_path / "no-bwrap")) is False
    fake = tmp_path / "bwrap"
    fake.write_text('#!/bin/sh\n[ "$1" = --unshare-all ] && [ "$#" = 7 ]\n', encoding="ascii")
    fake.chmod(0o755)
    assert gtkenv.bubblewrap_runs(str(fake)) is True


def test_the_window_calls_the_program_by_its_one_name_in_every_word_it_shows() -> None:
    """The window's title, the loading page, the tray icon's name and its notices, and the tray's menu: NeoAPRS, never another spelling, the daemon or the server (as the page's catalogue: ui/src/i18n/words.test.ts)."""
    tree = ast.parse(Path(webshell.__file__).read_text(encoding="utf-8"))
    shown = [a.value for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("create_window", "Icon", "notify")
             for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    assert shown.count("NeoAPRS") >= 3, shown                                     # (the window's title, the icon's name and its title, the notices' title)
    page = re.sub(r"<[^>]+>", " ", loading.HTML.split("</style>", 1)[1])
    assert "<title>NeoAPRS</title>" in loading.HTML and "NeoAPRS" in page
    words = [*shown, page, OPEN_LABEL, KEEPS_RUNNING]
    assert [m for w in words for m in re.findall(r"neo[\s-]*aprs", w, re.I) if m != "NeoAPRS"] == []
    assert [w for w in words if re.search(r"daemon|server", w, re.I)] == []
