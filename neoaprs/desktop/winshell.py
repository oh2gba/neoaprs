"""The shell of Windows: pywebview for the window (it is the system's WebView2, the Edge engine that Windows 11 and every current Windows 10 have; nothing of a browser is shipped) and pystray for the tray icon, which
draws it from a Pillow image. pywebview must own the main thread, so the tray runs in a thread of its own (`run_detached`). Closing the window hides it (the `closing` event is cancelled and the window hidden);
Quit destroys it. Its size, its place and whether it is maximized are Windows' own window placement, read and given back through user32 (winplace.py). When the window cannot be had (WebView2 is
missing, pywebview fails to start) the app goes on as a tray icon and the page is in the browser, and the log says so; with no web engine at all the tray runs on the main thread.
The window and the tray icon are made at once, the window with the loading page (loading.py) and the tray with Open alone; the thread that pywebview starts once its loop runs waits for the session, then
gives the tray its menu and the window the daemon's page (`load_url`), and when no page comes it ends the loop and the app says why. The toolkits are imported inside the functions that use them, by name (they are not installed on the other systems, and the tests put fakes in `sys.modules`); nothing but this file imports them.
The toolkits' own pieces, which only Windows has, are the part no CI of ours can see: what the code asks of them is exactly what is in tests/test_desktop_winshell.py."""
import contextlib
import importlib
import logging
import threading
import webbrowser
from importlib import resources
from pathlib import Path
from collections.abc import Callable
from typing import Any

from . import appstate, loading, splash
from .links import open_external, window_url
from .winplace import WindowKeeper
from .menu import OPEN, OPEN_LABEL, AppActions
from .session import NoPage
from .shell import Launch, ShellContext

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


class LinkApi:
    """What the page's script may call: only this, and it only opens what links.route sends to the browser (`page_url` is the daemon's page once it is there)."""

    def __init__(self, page_url: str = "") -> None:
        self.page_url = page_url

    def open_external(self, url: str) -> bool:
        return open_external(str(url), self.page_url)


def icon_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.png")))


class WinFrame:
    """The `Frame` of the Windows shell. pywebview's calls and pystray's may be made from any thread."""

    def __init__(self, with_window: bool) -> None:
        self.has_window = with_window
        self.window: Any = None
        self.keeper: WindowKeeper | None = None
        self.icon: Any = None
        self.actions: AppActions | None = None      # the menu's, once the session is there
        self.api = LinkApi()
        self.quitting = threading.Event()
        self.done = threading.Event()               # set when the app is to end: the main thread waits for it when there is no window to wait for

    def show_window(self) -> None:
        """Shows the window, out of the minimised state if it was there, maximized if that is how it was left: on Windows with the placement it was hidden with (`WindowKeeper.open`); where Win32 cannot be had,
        with pywebview's maximize or restore (its restore alone would make a maximized window a normal one)."""
        if self.window is None or (self.keeper is not None and self.keeper.open()):
            return
        self.window.show()
        if self.keeper is not None and self.keeper.maximized:
            self.window.maximize()
        else:
            self.window.restore()

    def quit(self) -> None:
        self.quitting.set()
        self.done.set()
        if self.keeper is not None:
            self.keeper.stop()
            self.keeper.save("quit")
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


def tray_menu(pystray: Any, frame: WinFrame) -> Any:
    """The tray menu from the data of `frame.actions.items()`, made again whenever pystray asks for the items; the Open item is the default one (the click on the icon). Until the session is there it is
    Open alone, which shows the window. pystray takes an action of at most two parameters, and counts one with a default too: each action and each check mark is a closure of its own (`_run`, `_shows`),
    not a lambda that keeps its key in a default."""
    def entries() -> Any:
        actions = frame.actions
        if actions is None:
            yield pystray.MenuItem(OPEN_LABEL, _show(frame), default=True)
            return
        for item in actions.items():
            if item.separator:
                yield pystray.Menu.SEPARATOR
                continue
            yield pystray.MenuItem(item.label, _run(actions, item.key), checked=None if item.checked is None else _shows(item.checked), default=item.key == OPEN)
    return pystray.Menu(entries)


def _run(actions: AppActions, key: str) -> Callable[[Any, Any], None]:
    """The action of the item `key`, as pystray calls it: with the icon and the item."""
    return lambda _icon, _item: actions.run(key)


def _show(frame: WinFrame) -> Callable[[Any, Any], None]:
    return lambda _icon, _item: frame.show_window()


def _shows(state: bool) -> Callable[[Any], bool]:
    """The check mark of an item, as pystray asks for it: with the item."""
    return lambda _item: state


def make_icon(frame: WinFrame) -> Any:
    pystray = importlib.import_module("pystray")
    image = importlib.import_module("PIL.Image")
    icon = pystray.Icon("NeoAPRS", image.open(icon_path()), "NeoAPRS", tray_menu(pystray, frame))
    frame.icon = icon
    return icon


def make_window(frame: WinFrame, launch: Launch) -> Any:
    """The pywebview window with the loading page, hidden when the app starts in the tray; closing it only hides it, unless the app is quitting. Text selection is allowed (pywebview switches it off unless asked).
    Its size and place are the placement Windows had for it (winplace.py), which is put on the form before it is shown; create_window is given the same rectangle as a first guess (exact at 100 % display
    scaling, and it makes the form's start position manual, so the form does not centre itself over it) and whether it is maximized. A file of 0.12.0 or earlier has no placement: its size and place are what
    the bug of 0.12.0 wrote, so the window opens at the default size in the middle of the screen, maximized if the file says so, and from then on it is the placement."""
    webview = importlib.import_module("webview")
    state = appstate.load_window(launch.data)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    if state.normal is not None:
        left, top, right, bottom = state.normal
        log.info("window: file: maximized=%s normal=%s", state.maximized, state.normal)
        width, height = appstate.clamp(right - left, bottom - top)
        where = {"x": left, "y": top}
    else:
        log.info("window: file: no placement (old: %dx%d at %s,%s maximized=%s): the default size in the middle of the screen", state.width, state.height, state.x, state.y, state.maximized)
        (width, height), where = appstate.DEFAULT_SIZE, {}
    window = webview.create_window("NeoAPRS", html=loading.HTML, width=width, height=height, **where, maximized=state.maximized, hidden=launch.hidden, text_select=True, js_api=frame.api,
                                   background_color=loading.background(dark_scheme()))
    frame.window = window
    keeper = WindowKeeper(launch.data, state, window)
    frame.keeper = keeper

    def closing() -> bool:
        log.debug("window: event closing [%s]", threading.current_thread().name)
        if frame.quitting.is_set():
            return True                             # (Quit saved it)
        keeper.save("hide")
        window.hide()
        return False                                 # False cancels the close

    def shown() -> None:
        splash.done()                               # (the window is on the screen: the splash of the start has done its part)
        keeper.shown()

    window.events.closing += closing
    window.events.before_show += keeper.before_show
    window.events.shown += shown
    for name in ("maximized", "minimized", "restored", "resized", "moved"):
        hook = getattr(window.events, name)
        hook += keeper.told(name)
    window.events.loaded += lambda: window.evaluate_js(LINK_SCRIPT)
    return window


def dark_scheme(registry: Any = None) -> bool:
    """Whether the apps of this Windows are in the dark scheme (what WebView2 tells the page as prefers-color-scheme); light where it cannot be read."""
    try:
        winreg = registry if registry is not None else importlib.import_module("winreg")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            light, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except (ImportError, OSError):
        return False
    return bool(light == 0)


def attach(frame: WinFrame, ctx: ShellContext) -> AppActions:
    """The session is there: the tray gets its menu, the page's script its address."""
    actions = ctx.actions_for(frame)
    frame.actions = actions
    frame.api.page_url = ctx.session.url
    return actions


def load_page(window: Any, url: str) -> None:
    """The daemon's page in the window, asked once the app has heard the session (the one-app lock and the tray work whatever the window does). pywebview's load_url waits for the window's `shown`; when it
    does not come in time (a window that has not been shown), the page is loaded at the window's next `shown`, once, and the log says so."""
    done = threading.Event()

    def load() -> None:
        if not done.is_set():
            done.set()
            window.load_url(url)

    try:
        window.load_url(url)
        done.set()
    except Exception as e:
        log.warning("window: the page is loaded when the window is shown (%s)", e)
        window.events.shown += load


def run_window(frame: WinFrame, launch: Launch, failed: list[NoPage]) -> None:
    """The main thread is pywebview's until the last window is destroyed (Quit, or no page coming: `failed` says so). If the engine cannot start, the app goes on without a window."""
    webview = importlib.import_module("webview")
    storage = str(appstate.profile_dir(launch.data))

    def started() -> None:
        try:
            ctx = launch.context(launch.opening.result())
        except NoPage as e:
            failed.append(e)
            frame.quit()
            return
        actions = attach(frame, ctx)
        ctx.ready(actions)
        frame.refresh()
        load_page(frame.window, window_url(ctx.session.url))

    try:
        webview.start(started, gui="edgechromium", private_mode=False, storage_path=storage)
    except Exception:
        log.exception("the WebView2 window could not start: going on in the tray, with the page in the browser")
        splash.done()
        frame.window = None
        frame.has_window = False
        try:
            ctx = launch.context(launch.opening.result())
        except NoPage as e:
            failed.append(e)
            return
        actions = attach(frame, ctx)
        frame.refresh()
        if not ctx.hidden:
            webbrowser.open(ctx.session.url)
        ctx.ready(actions)
        frame.done.wait()


def run(launch: Launch) -> int:
    frame = WinFrame(launch.window)
    icon = make_icon(frame)
    failed: list[NoPage] = []
    try:
        if launch.window:
            make_window(frame, launch)
            icon.run_detached()
            run_window(frame, launch, failed)
        else:
            splash.done()
            try:
                ctx = launch.context(launch.opening.result())
            except NoPage as e:
                return launch.no_page(e)
            log.info("no window: the tray, and the page in the browser")
            actions = attach(frame, ctx)
            if not ctx.hidden:
                webbrowser.open(ctx.session.url)
            ctx.ready(actions)
            icon.run_detached()
            frame.done.wait()
    finally:
        with contextlib.suppress(Exception):
            icon.stop()
    return launch.no_page(failed[0]) if failed else 0
