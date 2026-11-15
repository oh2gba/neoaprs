"""The web shell: pywebview for the window, on the system's own web engine (nothing of a browser is shipped), and pystray for the tray icon. Windows always runs it, on WebView2,
the Edge engine of Windows 11 and every current Windows 10; Linux (WebKitGTK) and macOS (WKWebView) run it when the switch NEOAPRS_WINDOW=web asks for it (shell.py), the trial of the window that is to take the
place of Qt's there (aprs-reference/window-plan.md). pywebview must own the main thread, so the tray runs beside its loop: on Windows in a thread of its own, on Linux in GTK's loop (which pywebview runs), on
macOS in the one NSApplication. The tray's image on Windows is icon.ico as it is (IcoFile: pystray there only asks its image to write itself as an ICO, so no imaging library is shipped); on Linux
and macOS it is a Pillow image of icon.png, which pystray's backends there write as a PNG or scale. Closing the window hides it (the `closing` event is cancelled and the window hidden); Quit destroys it.
Windows: the window's size, its place and whether it is maximized are Windows' own window placement, read and given back through user32 (winplace.py); a splash covers the start (splash.py). Linux and macOS:
the size keeper (sizekeep.py) saves them from pywebview's events, and webdesk.py asks the desktop the rest. On Linux the tray icon is the StatusNotifier of the desktop (pystray's appindicator backend, forced: its other backends show nothing on Wayland);
a desktop with no tray host (GNOME without its extension) has none, and there the close button quits, since nothing would be left to bring the window back from. The app that starts in the tray (`--tray`, the
start at sign-in) looks for the tray host for a minute, as the panel may come up after it, and shows the window if none comes. AppKit's objects belong to the main thread, so on macOS the tray's calls are queued
there (`PyObjCTools.AppHelper.callAfter`).
When the window cannot be had (no web engine, pywebview fails to start) the app goes on as a tray icon and the page is in the browser, and the log says so; with no window loop the tray runs on a loop of its own.
The window and the tray icon are made at once, the window with the loading page (loading.py) and the tray with Open alone; the thread that pywebview starts once its loop runs waits for the session, then
gives the tray its menu and the window the daemon's page (`load_url`), and when no page comes it ends the loop and the app says why. The toolkits are imported inside the functions that use them, by name (each
system has only its own, and the tests put fakes in `sys.modules`); nothing but this file and webdesk.py imports them. `SYSTEM` is the system the shell runs as (the tests set it).
The toolkits' own pieces are the part no CI of ours can see: what the code asks of them is exactly what is in tests/test_desktop_webshell.py."""
import contextlib
import importlib
import logging
import sys
import threading
import webbrowser
from importlib import resources
from pathlib import Path
from collections.abc import Callable
from typing import Any

from . import appstate, loading, splash, webdesk
from .links import LINK_SCRIPT, LinkApi, window_url
from .sizekeep import SizeKeeper
from .winplace import WindowKeeper
from .menu import OPEN, OPEN_LABEL, QUIT, AppActions
from .session import NoPage
from .shell import Launch, ShellContext

log = logging.getLogger("neoaprs.desktop")

SYSTEM = sys.platform
GUI = {"win32": "edgechromium", "linux": "gtk", "darwin": "cocoa"}


def icon_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.png")))


def ico_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.ico")))


class IcoFile:
    """The tray icon's image as pystray takes it on Windows: its backend writes the image to a file as an ICO (`image.save(file, format="ICO")`) and has Windows load that file, which picks the frame of
    the display's scaling; so the image is the bytes of icon.ico, its frames 16 to 256 px, written as they are. tests/test_desktop_webshell.py reads pystray's own code for that call. The file is read here,
    on the thread that makes the icon: pystray asks for it later, in its own thread, where a missing file would leave the app without its tray and with only a line in the log."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = ico_path() if path is None else path
        self.data = self.path.read_bytes()

    def save(self, fp: Any, format: str | None = None) -> None:
        if format is not None and format.upper() != "ICO":
            raise ValueError(f"the tray icon is an ICO file and cannot be written as {format}")
        fp.write(self.data)


class WebFrame:
    """The `Frame` of the web shell. pywebview's calls may be made from any thread; pystray's go through `webdesk.on_main`."""

    def __init__(self, with_window: bool) -> None:
        self.has_window = with_window
        self.window: Any = None
        self.keeper: WindowKeeper | None = None      # Windows: the placement
        self.sizes: SizeKeeper | None = None          # Linux and macOS: the size keeper
        self.icon: Any = None
        self.actions: AppActions | None = None      # the menu's, once the session is there
        self.api = LinkApi()
        self.quitting = threading.Event()
        self.done = threading.Event()               # set when the app is to end: the main thread waits for it when there is no window to wait for
        self.closed = False                          # the close button was used before the session was there, with no tray to hide into: the app ends as soon as it comes
        self.lock = threading.Lock()                 # (the close button's thread and the session's: `actions` and `closed` are read and set under it)
        self.stop_loop: Callable[[], None] | None = None   # ends the tray's own loop, when it runs one (no window)

    def show_window(self) -> None:
        """Shows the window, out of the minimised state if it was there, maximized if that is how it was left: on Windows with the placement it was hidden with (`WindowKeeper.open`); where Win32 cannot be had,
        with pywebview's maximize or restore (its restore alone would make a maximized window a normal one on Windows and macOS). On Linux GTK's show does nothing to a window that is there already, minimised
        or behind others, and its maximize does not bring one back from the taskbar: pywebview's restore there only brings it back and raises it, and leaves a maximized window maximized, so it is always made."""
        if self.window is None or (self.keeper is not None and self.keeper.open()):
            return
        self.window.show()
        maximized = (self.keeper is not None and self.keeper.maximized) or (self.sizes is not None and self.sizes.maximized)
        if SYSTEM == "linux" or not maximized:
            self.window.restore()
        if maximized:
            self.window.maximize()

    def tray_shows(self) -> bool:
        """Whether there is a tray icon on show to bring the window back from."""
        return self.icon is not None and webdesk.tray_host(SYSTEM)

    def quit(self) -> None:
        self.quitting.set()
        self.done.set()
        if self.keeper is not None:
            self.keeper.stop()
            self.keeper.save("quit")
        if self.sizes is not None:
            self.sizes.stop()
            self.sizes.save()
        if self.window is not None:
            self.window.destroy()                   # (the icon is stopped by `run`, when the window loop or the wait is over)
        if self.stop_loop is not None:
            self.stop_loop()

    def refresh(self) -> None:
        icon = self.icon
        if icon is not None:
            webdesk.on_main(SYSTEM, icon.update_menu)

    def tell(self, text: str) -> None:
        icon = self.icon
        if icon is not None:
            webdesk.on_main(SYSTEM, lambda: icon.notify(text, "NeoAPRS"))
        else:
            log.warning("%s", text)


def tray_menu(pystray: Any, frame: WebFrame) -> Any:
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


def _show(frame: WebFrame) -> Callable[[Any, Any], None]:
    return lambda _icon, _item: frame.show_window()


def _shows(state: bool) -> Callable[[Any], bool]:
    """The check mark of an item, as pystray asks for it: with the item."""
    return lambda _item: state


def tray_image() -> Any:
    """The tray's image: icon.ico as it is on Windows, where the app ships no Pillow; a Pillow image of icon.png on Linux and macOS."""
    if SYSTEM == "win32":
        return IcoFile()
    return importlib.import_module("PIL.Image").open(icon_path())


def make_icon(frame: WebFrame) -> Any:
    pystray = importlib.import_module("pystray")
    icon = pystray.Icon("NeoAPRS", tray_image(), "NeoAPRS", tray_menu(pystray, frame))
    frame.icon = icon
    return icon


def new_icon(frame: WebFrame, launch: Launch) -> Any:
    """The tray icon, or None: on Linux and macOS when the tray's toolkit did not load (`launch.tray`) or the icon cannot be made, which leaves the window without one; on Windows a failure is the shell's."""
    if SYSTEM == "win32":
        return make_icon(frame)
    if not launch.tray:
        return None
    try:
        return make_icon(frame)
    except Exception:
        log.exception("the tray icon could not be made: the window goes on without it")
        frame.icon = None
        return None


def make_window(frame: WebFrame, launch: Launch) -> Any:
    """The pywebview window with the loading page, hidden when the app starts in the tray; closing it only hides it, unless the app is quitting (or, on Linux and macOS, there is no tray to hide into: then it
    quits). Text selection is allowed (pywebview switches it off unless asked), and so are downloads (the HTTPS guide's certificate: a save dialog). On Windows its size and place are the placement Windows
    had for it (winplace.py), which is put on the form before it is shown; create_window is given the same rectangle as a first guess (exact at 100 % display scaling, and it makes the form's start position
    manual, so the form does not centre itself over it) and whether it is maximized. A file of 0.12.0 or earlier has no placement: its size and place are what the bug of 0.12.0 wrote, so the window opens at the
    default size in the middle of the screen, maximized if the file says so, and from then on it is the placement. On Linux and macOS it is the size and place the size keeper saved (the place only where a
    screen has it still, and not on Wayland)."""
    webview = importlib.import_module("webview")
    state = appstate.load_window(launch.data)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_DOWNLOADS"] = True
    where: dict[str, int] = {}
    keep_place = SYSTEM != "win32" and not webdesk.wayland()
    if SYSTEM == "win32" and state.normal is not None:
        left, top, right, bottom = state.normal
        log.info("window: file: maximized=%s normal=%s", state.maximized, state.normal)
        width, height = appstate.clamp(right - left, bottom - top)
        where = {"x": left, "y": top}
    elif SYSTEM == "win32":
        log.info("window: file: no placement (old: %dx%d at %s,%s maximized=%s): the default size in the middle of the screen", state.width, state.height, state.x, state.y, state.maximized)
        width, height = appstate.DEFAULT_SIZE
    else:
        width, height = state.width, state.height
        if keep_place and state.x is not None and state.y is not None and webdesk.on_a_screen(SYSTEM, state.x, state.y):
            origin_x, origin_y = webdesk.screen_origin(SYSTEM)          # (the place kept is the desktop's; pywebview's GTK window adds the first monitor's corner to the one it is given)
            where = {"x": state.x - origin_x, "y": state.y - origin_y}
        log.info("window: file: %dx%d at %s maximized=%s", width, height, where or "the middle of the screen", state.maximized)
    window = webview.create_window("NeoAPRS", html=loading.HTML, width=width, height=height, **where, maximized=state.maximized, hidden=launch.hidden, text_select=True, js_api=frame.api,
                                   background_color=loading.background(system_dark()))
    frame.window = window
    if SYSTEM == "win32":
        keep_placement(frame, window, WindowKeeper(launch.data, state, window))
    else:
        webdesk.keep_size(frame, window, SizeKeeper(launch.data, state, keep_place), SYSTEM)
    window.events.loaded += lambda: window.evaluate_js(LINK_SCRIPT)
    return window


def keep_placement(frame: WebFrame, window: Any, keeper: WindowKeeper) -> None:
    """Windows: the placement is saved when the window is hidden and settles after a change, and given back before it is shown; the close button always hides (the notification area is always there)."""
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


def dark_scheme(registry: Any = None) -> bool:
    """Whether the apps of this Windows are in the dark scheme (what WebView2 tells the page as prefers-color-scheme); light where it cannot be read."""
    try:
        winreg = registry if registry is not None else importlib.import_module("winreg")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            light, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except (ImportError, OSError):
        return False
    return bool(light == 0)


def system_dark() -> bool:
    """The system's scheme, for the background the window paints before the page has painted."""
    if SYSTEM == "linux":
        return webdesk.portal_dark()
    if SYSTEM == "darwin":
        return webdesk.mac_dark()
    return dark_scheme()


def attach(frame: WebFrame, ctx: ShellContext) -> AppActions:
    """The session is there: the tray gets its menu, the page's script its address."""
    actions = ctx.actions_for(frame)
    with frame.lock:
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


def store_dir(data: Path) -> str | None:
    """Where the web engine keeps what the page stores: WebView2's in `webview/`, WebKitGTK's in `webkit/` (a store of its own: the Qt window's Chromium profile stays in `webview/`); macOS's WKWebView
    keeps it in the system's place for the app and is given none."""
    if SYSTEM == "win32":
        return str(appstate.profile_dir(data))
    if SYSTEM == "darwin":
        return None
    return str(appstate.webkit_dir(data))


def start_options(launch: Launch) -> dict[str, Any]:
    """What `webview.start` is given besides the function it runs: the engine by name (never pywebview's own pick, which an outside variable or a KDE session would change), the storage, and on Linux the
    window's icon."""
    options: dict[str, Any] = {"gui": GUI.get(SYSTEM, "gtk"), "private_mode": False}
    storage = store_dir(launch.data)
    if storage is not None:
        options["storage_path"] = storage
    if SYSTEM == "linux":
        options["icon"] = str(icon_path())
    return options


def run_window(frame: WebFrame, launch: Launch, failed: list[NoPage]) -> None:
    """The main thread is pywebview's until the last window is destroyed (Quit, or no page coming: `failed` says so). If the engine cannot start, the app goes on without a window, in the tray; with no tray
    icon either, the failure is the shell's (the app then opens the page in the browser)."""
    webview = importlib.import_module("webview")

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
        if frame.closed:
            actions.run(QUIT)
            return
        load_page(frame.window, window_url(ctx.session.url))
        log.info("the web shell runs (%s)", "window and tray" if frame.icon is not None else "window, no tray icon")
        if SYSTEM != "win32" and ctx.hidden:
            webdesk.await_tray(frame)

    try:
        webview.start(started, **start_options(launch))
    except Exception:
        if frame.icon is None:
            raise
        log.exception("the window could not start: going on in the tray, with the page in the browser")
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
        webdesk.tray_loop(SYSTEM, frame)


def run(launch: Launch) -> int:
    frame = WebFrame(launch.window)
    icon = new_icon(frame, launch)
    if icon is None and not launch.window:
        raise RuntimeError("no tray icon and no window: there is nothing to show")
    failed: list[NoPage] = []
    try:
        if launch.window:
            make_window(frame, launch)
            if icon is not None:
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
            log.info("the web shell runs (tray only)")
            webdesk.tray_loop(SYSTEM, frame)
    finally:
        if icon is not None:
            with contextlib.suppress(Exception):
                icon.stop()
    return launch.no_page(failed[0]) if failed else 0
