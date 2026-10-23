"""The shell of Windows: pywebview for the window (it is the system's WebView2, the Edge engine that Windows 11 and every current Windows 10 have; nothing of a browser is shipped) and pystray for the tray icon, which
draws it from a Pillow image. pywebview must own the main thread, so the tray runs in a thread of its own (`run_detached`). Closing the window hides it (the `closing` event is cancelled and the window hidden);
Quit destroys it. When the window cannot be had (WebView2 is missing, pywebview fails to start) the app goes on as a tray icon and the page is in the browser, and the log says so; with no web engine at all the
tray runs on the main thread. The toolkits are imported inside the functions that use them, by name (they are not installed on the other systems, and the tests put fakes in `sys.modules`); nothing but this file imports them.
The toolkits' own pieces, which only Windows has, are the part no CI of ours can see: what the code asks of them is exactly what is in tests/test_desktop_winshell.py."""
import contextlib
import importlib
import logging
import threading
import webbrowser
from importlib import resources
from pathlib import Path
from typing import Any

from . import appstate
from .links import open_external
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


class LinkApi:
    """What the page's script may call: only this, and it only opens what links.route sends to the browser."""

    def __init__(self, page_url: str) -> None:
        self.page_url = page_url

    def open_external(self, url: str) -> bool:
        return open_external(str(url), self.page_url)


class SizeSaver:
    """Remembers the window's size when it has stopped changing (pywebview says so for every pixel of a drag)."""

    def __init__(self, data: Path) -> None:
        self.data = data
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def changed(self, width: int, height: int) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(SAVE_SIZE_SEC, appstate.save_size, (self.data, width, height))
            self._timer.daemon = True
            self._timer.start()


def icon_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.png")))


class WinFrame:
    """The `Frame` of the Windows shell. pywebview's calls and pystray's may be made from any thread."""

    def __init__(self, with_window: bool) -> None:
        self.has_window = with_window
        self.window: Any = None
        self.icon: Any = None
        self.quitting = threading.Event()
        self.done = threading.Event()               # set when the app is to end: the main thread waits for it when there is no window to wait for

    def show_window(self) -> None:
        if self.window is not None:
            self.window.show()
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
    """The pywebview window: the size it had, hidden when the app starts in the tray; closing it only hides it, unless the app is quitting. Text selection is allowed (pywebview switches it off unless asked)."""
    webview = importlib.import_module("webview")
    width, height = appstate.load_size(ctx.session.data)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    window = webview.create_window("NeoAPRS", ctx.session.url, width=width, height=height, hidden=ctx.hidden, text_select=True, js_api=LinkApi(ctx.session.url))
    frame.window = window
    saver = SizeSaver(ctx.session.data)

    def closing() -> bool:
        if frame.quitting.is_set():
            return True
        window.hide()
        return False                                 # False cancels the close

    window.events.closing += closing
    window.events.resized += saver.changed
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
