"""The Windows shell against stand-ins for pywebview, pystray and Pillow (`sys.modules` gets them, so this runs on any system and CI): what the shell asks of each toolkit, the closing of the window that
hides it, the tray menu made from the data of the actions, the page's script that sends other sites to the browser, and the way on without a window when WebView2 cannot start. What the real toolkits do with
those calls is what only a Windows desktop can say."""
import ctypes
import logging
import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from neoaprs.desktop import appstate, winplace, winshell
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
        self.destroyed = threading.Event()
        self.user32 = user32
        self.native = types.SimpleNamespace(Handle=types.SimpleNamespace(ToInt64=lambda: FakeUser32.hwnd))      # (pywebview's WinForms Form, with its HWND)

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

    def __init__(self, monkeypatch: pytest.MonkeyPatch, start_fails: bool = False, user32: FakeUser32 | None = None) -> None:
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
        pil = types.ModuleType("PIL")
        image = types.ModuleType("PIL.Image")
        image.open = lambda path: ("image", str(path))  # type: ignore[attr-defined]
        pil.Image = image  # type: ignore[attr-defined]
        for name, module in (("webview", webview), ("pystray", pystray), ("PIL", pil), ("PIL.Image", image)):
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
                 windll: bool = True) -> None:
        """`user32`: the window's Win32 side, which is `ctypes.windll.user32` unless `windll` is False (then the window has it and the shell cannot reach it, as on any system but Windows)."""
        self.toolkits = Toolkits(monkeypatch, start_fails, user32)
        if user32 is not None and windll:
            monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)
        self.browser: list[str] = []
        monkeypatch.setattr(winshell.webbrowser, "open", lambda url: self.browser.append(url) or True)
        self.data = tmp_path / "data"
        self.data.mkdir(parents=True)
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
    appstate.save_window(rig.data, kept(False))
    thread = launch(rig)
    (window,) = rig.toolkits.windows
    assert window.args == ("NeoAPRS", PAGE + "#app") and (window.kwargs["width"], window.kwargs["height"]) == (1000, 700) and window.kwargs["hidden"] is True and window.kwargs["text_select"] is True
    assert (window.kwargs["x"], window.kwargs["y"], window.kwargs["maximized"]) == (100, 60, False), "the placement's rectangle, as a first guess"
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


def test_where_there_is_no_win32_no_call_is_made_and_open_is_pywebviews(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not hasattr(ctypes, "windll"), "(this runs where ctypes has no windll)"
    user32 = FakeUser32(show_cmd=winplace.SW_SHOWMAXIMIZED)
    rig = Rig(tmp_path, monkeypatch, user32=user32, windll=False)
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
