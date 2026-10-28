"""The shell of Windows: pywebview for the window (it is the system's WebView2, the Edge engine that Windows 11 and every current Windows 10 have; nothing of a browser is shipped) and pystray for the tray icon, which
draws it from a Pillow image. pywebview must own the main thread, so the tray runs in a thread of its own (`run_detached`). Closing the window hides it (the `closing` event is cancelled and the window hidden);
Quit destroys it. When the window cannot be had (WebView2 is missing, pywebview fails to start) the app goes on as a tray icon and the page is in the browser, and the log says so; with no web engine at all the
tray runs on the main thread. The toolkits are imported inside the functions that use them, by name (they are not installed on the other systems, and the tests put fakes in `sys.modules`); nothing but this file imports them.
The toolkits' own pieces, which only Windows has, are the part no CI of ours can see: what the code asks of them is exactly what is in tests/test_desktop_winshell.py."""
import contextlib
import ctypes
import importlib
import logging
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from importlib import resources
from pathlib import Path
from typing import Any

from . import appstate
from .links import open_external, window_url
from .menu import OPEN, AppActions
from .shell import ShellContext

log = logging.getLogger("neoaprs.desktop")


# Runs in the page after it has loaded: a click on a link to another site is not followed inside the window but handed to Python, which routes it (links.py). (pywebview already sends the new windows that
# `target="_blank"` asks for to the browser; this is for a link that has no target.)
LINK_SCRIPT = """(function () {
  if (window.__neoaprsLinks) { return; }
  window.__neoaprsLinks = true;
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || new URL(a.href, location.href).origin === location.origin) { return; }
    e.preventDefault();
    e.stopPropagation();
    if (window.pywebview && window.pywebview.api) { window.pywebview.api.open_external(a.href); }
  }, true);
})();"""
SAVE_SIZE_SEC = 0.5
TITLE_POINT = (64, 16)                          # a point of the title bar, from the top left corner of the frame: where it is, the window can be taken hold of


class LinkApi:
    """What the page's script may call: only this, and it only opens what links.route sends to the browser."""

    def __init__(self, page_url: str) -> None:
        self.page_url = page_url

    def open_external(self, url: str) -> bool:
        return open_external(str(url), self.page_url)


class WindowSaver:
    """Remembers the window's size and place when they have stopped changing (pywebview says so for every pixel of a drag), and whether it is maximized. The size and place that are kept are the ones of the window
    when it is not maximized: pywebview tells the maximized window's own (the whole screen, a corner off it) after it has said `maximized`, and a minimised window's nonsense after `minimized`, and those are
    not looked at; what comes after `restored` is. So a window that is left maximized comes back maximized, and restored to where it was before."""

    def __init__(self, data: Path, state: appstate.WindowState) -> None:
        self.data = data
        self.state = state                      # as the file has it
        self.maximized = state.maximized
        self._minimized = False
        self._size: tuple[int, int] | None = None       # the latest pywebview told, while not maximized
        self._place: tuple[int, int] | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def resized(self, width: int, height: int) -> None:
        if not self.maximized and not self._minimized:
            self._size = (width, height)
        self._later()

    def moved(self, x: int, y: int) -> None:
        if not self.maximized and not self._minimized:
            self._place = (x, y)
        self._later()

    def maximize_told(self) -> None:
        self.maximized, self._minimized = True, False
        self._place = None                      # (the move pywebview told just before was the window going to its corner off the screen)
        self._later()

    def minimize_told(self) -> None:
        self._minimized = True
        self._place = None

    def restore_told(self) -> None:
        self.maximized, self._minimized = False, False
        self._later()

    def _later(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(SAVE_SIZE_SEC, self.save)
            self._timer.daemon = True
            self._timer.start()

    def save(self) -> None:
        """Writes the file when the window is other than it says (a minimised window changes nothing: it goes back to what it was)."""
        if self._minimized:
            return
        size = self._size if self._size is not None else (self.state.width, self.state.height)
        x, y = self._place if self._place is not None else (self.state.x, self.state.y)
        state = replace(self.state, maximized=True) if self.maximized else appstate.WindowState(size[0], size[1], x, y, False)
        if state != self.state:
            appstate.save_window(self.data, state)
            self.state = state


class _Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


def on_a_monitor(x: int, y: int) -> bool:
    """Whether a window whose frame's top left corner is at (x, y) has the start of its title bar on one of the monitors there are now (the system's MonitorFromPoint; a monitor that was unplugged leaves a remembered
    place nowhere, and a window there could never be taken hold of). True where it cannot be asked."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return True
    try:
        return bool(windll.user32.MonitorFromPoint(_Point(x + TITLE_POINT[0], y + TITLE_POINT[1]), 0))      # (0: MONITOR_DEFAULTTONULL)
    except (AttributeError, OSError, ctypes.ArgumentError):
        return True


def placed(state: appstate.WindowState, on_screen: Callable[[int, int], bool] | None = None) -> appstate.WindowState:
    """The state with the place left out when no monitor has it (`on_a_monitor` asks the system; the tests pass their own)."""
    if state.x is None or state.y is None or (on_screen or on_a_monitor)(state.x, state.y):
        return state
    log.info("the window's place (%d, %d) is on no monitor: it opens in the middle of the screen", state.x, state.y)
    return replace(state, x=None, y=None)


def icon_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.png")))


class WinFrame:
    """The `Frame` of the Windows shell. pywebview's calls and pystray's may be made from any thread."""

    def __init__(self, with_window: bool) -> None:
        self.has_window = with_window
        self.window: Any = None
        self.saver: WindowSaver | None = None
        self.icon: Any = None
        self.quitting = threading.Event()
        self.done = threading.Event()               # set when the app is to end: the main thread waits for it when there is no window to wait for

    def show_window(self) -> None:
        """Shows the window, out of the minimised state if it was there, maximized if that is how it was left (pywebview's restore would make it a normal window)."""
        if self.window is not None:
            self.window.show()
            if self.saver is not None and self.saver.maximized:
                self.window.maximize()
            else:
                self.window.restore()

    def quit(self) -> None:
        self.quitting.set()
        self.done.set()
        if self.window is not None:
            self.window.destroy()                   # (the icon is stopped by `run`, when the window loop or the wait is over)

    def refresh(self) -> None:
        if self.icon is not None:
            self.icon.update_menu()

    def tell(self, text: str) -> None:
        if self.icon is not None:
            self.icon.notify(text, "NeoAPRS")
        else:
            log.warning("%s", text)


def tray_menu(pystray: Any, actions: AppActions) -> Any:
    """The tray menu from the data of `actions.items()`, made again whenever pystray asks for the items; the Open item is the default one (the click on the icon)."""
    def entries() -> Any:
        for item in actions.items():
            if item.separator:
                yield pystray.Menu.SEPARATOR
                continue
            checked = None if item.checked is None else (lambda _menu_item, state=item.checked: state)
            yield pystray.MenuItem(item.label, lambda _icon, _item, key=item.key: actions.run(key), checked=checked, default=item.key == OPEN)
    return pystray.Menu(entries)


def make_icon(frame: WinFrame, actions: AppActions) -> Any:
    pystray = importlib.import_module("pystray")
    image = importlib.import_module("PIL.Image")
    icon = pystray.Icon("NeoAPRS", image.open(icon_path()), "NeoAPRS", tray_menu(pystray, actions))
    frame.icon = icon
    return icon


def make_window(frame: WinFrame, ctx: ShellContext) -> Any:
    """The pywebview window: the size and place it had (in the middle of the screen the first time, and when the place is on no monitor now) and maximized if it was left so, hidden when the app starts in the tray;
    closing it only hides it, unless the app is quitting. Text selection is allowed (pywebview switches it off unless asked)."""
    webview = importlib.import_module("webview")
    state = placed(appstate.load_window(ctx.session.data))
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    where = {"x": state.x, "y": state.y} if state.x is not None and state.y is not None else {}
    window = webview.create_window("NeoAPRS", window_url(ctx.session.url), width=state.width, height=state.height, **where, maximized=state.maximized, hidden=ctx.hidden, text_select=True,
                                   js_api=LinkApi(ctx.session.url))
    frame.window = window
    saver = WindowSaver(ctx.session.data, state)
    frame.saver = saver

    def closing() -> bool:
        if frame.quitting.is_set():
            return True
        window.hide()
        return False                                 # False cancels the close

    window.events.closing += closing
    window.events.resized += saver.resized
    window.events.moved += saver.moved
    window.events.maximized += saver.maximize_told
    window.events.minimized += saver.minimize_told
    window.events.restored += saver.restore_told
    window.events.loaded += lambda: window.evaluate_js(LINK_SCRIPT)
    return window


def run_window(frame: WinFrame, ctx: ShellContext, actions: AppActions) -> None:
    """The main thread is pywebview's until the last window is destroyed (Quit). If the engine cannot start, the app goes on without a window."""
    webview = importlib.import_module("webview")
    storage = str(appstate.profile_dir(ctx.session.data))
    try:
        webview.start(lambda: ctx.ready(actions), gui="edgechromium", private_mode=False, storage_path=storage)
    except Exception:
        log.exception("the WebView2 window could not start: going on in the tray, with the page in the browser")
        frame.window = None
        frame.has_window = False
        if not ctx.hidden:
            webbrowser.open(ctx.session.url)
        ctx.ready(actions)
        frame.done.wait()


def run(ctx: ShellContext) -> int:
    frame = WinFrame(ctx.window)
    actions = ctx.actions_for(frame)
    icon = make_icon(frame, actions)
    try:
        if ctx.window:
            make_window(frame, ctx)
            icon.run_detached()
            run_window(frame, ctx, actions)
        else:
            log.info("no window: the tray, and the page in the browser")
            if not ctx.hidden:
                webbrowser.open(ctx.session.url)
            ctx.ready(actions)
            icon.run_detached()
            frame.done.wait()
    finally:
        with contextlib.suppress(Exception):
            icon.stop()
    return 0
