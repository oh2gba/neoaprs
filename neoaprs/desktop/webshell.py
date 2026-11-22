"""The web shell: a pywebview window on the system's web engine, plus a pystray tray icon.

Windows always uses it (WebView2); Linux and macOS use it when NEOAPRS_WINDOW=web asks for it.
pywebview owns the main thread; the toolkits are imported inside functions (tests fake them).
"""

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
    """The tray icon image for pystray on Windows: the bytes of icon.ico, written as they are.

    The file is read at construction, so a missing file fails here, not in pystray's thread."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = ico_path() if path is None else path
        self.data = self.path.read_bytes()

    def save(self, fp: Any, format: str | None = None) -> None:
        if format is not None and format.upper() != "ICO":
            raise ValueError(f"the tray icon is an ICO file and cannot be written as {format}")
        fp.write(self.data)


class WebFrame:
    """The `Frame` of the web shell. pystray's calls go through `webdesk.on_main`."""

    def __init__(self, with_window: bool) -> None:
        self.has_window = with_window
        self.window: Any = None
        self.keeper: WindowKeeper | None = None  # Windows: the placement
        self.sizes: SizeKeeper | None = None  # Linux and macOS: the size keeper
        self.icon: Any = None
        self.actions: AppActions | None = None  # set once the session is there
        self.api = LinkApi()
        self.quitting = threading.Event()
        # Set when the app is to end; the main thread waits on it without a window.
        self.done = threading.Event()
        # Close used before the session existed with no tray to hide into: the app ends then.
        self.closed = False
        # Guards `actions` and `closed` (close button thread vs. session thread).
        self.lock = threading.Lock()
        self.stop_loop: Callable[[], None] | None = None  # ends the tray's own loop (no window)

    def show_window(self) -> None:
        """Show the window, un-minimised, and maximized if it was left so.

        On Linux restore is always called: GTK's show does not raise a minimised window."""
        if self.window is None or (self.keeper is not None and self.keeper.open()):
            return
        self.window.show()
        maximized = (self.keeper is not None and self.keeper.maximized) or (
            self.sizes is not None and self.sizes.maximized
        )
        if SYSTEM == "linux" or not maximized:
            self.window.restore()
        if maximized:
            self.window.maximize()

    def tray_shows(self) -> bool:
        """Return whether a tray icon is on show."""
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
            self.window.destroy()  # `run` stops the icon afterwards
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

    def load(self, url: str) -> None:
        """Record `url` as the page address, against which links are judged, and load it."""
        self.api.page_url = url
        if self.window is not None and not self.quitting.is_set():
            load_page(self.window, window_url(url))


def tray_menu(pystray: Any, frame: WebFrame) -> Any:
    """Return the tray menu, rebuilt from `frame.actions.items()` each time pystray asks.

    pystray counts parameters with defaults, so each action is its own closure."""

    def entries() -> Any:
        actions = frame.actions
        if actions is None:
            yield pystray.MenuItem(OPEN_LABEL, _show(frame), default=True)
            return
        for item in actions.items():
            if item.separator:
                yield pystray.Menu.SEPARATOR
                continue
            yield pystray.MenuItem(
                item.label,
                _run(actions, item.key),
                checked=None if item.checked is None else _shows(item.checked),
                default=item.key == OPEN,
            )

    return pystray.Menu(entries)


def _run(actions: AppActions, key: str) -> Callable[[Any, Any], None]:
    """Return the item's action in pystray's calling form (icon, item)."""
    return lambda _icon, _item: actions.run(key)


def _show(frame: WebFrame) -> Callable[[Any, Any], None]:
    return lambda _icon, _item: frame.show_window()


def _shows(state: bool) -> Callable[[Any], bool]:
    """Return the item's check mark in pystray's calling form (item)."""
    return lambda _item: state


def tray_image() -> Any:
    """Return icon.ico as is on Windows (no Pillow there), else a Pillow image of icon.png."""
    if SYSTEM == "win32":
        return IcoFile()
    return importlib.import_module("PIL.Image").open(icon_path())


def make_icon(frame: WebFrame) -> Any:
    pystray = importlib.import_module("pystray")
    icon = pystray.Icon("NeoAPRS", tray_image(), "NeoAPRS", tray_menu(pystray, frame))
    frame.icon = icon
    return icon


def new_icon(frame: WebFrame, launch: Launch) -> Any:
    """Return the tray icon, or None on Linux and macOS if it cannot be made; Windows raises."""
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
    """Create the pywebview window showing the loading page, hidden when the app starts in the tray.

    On Windows the saved placement is also passed as a first guess, so the form does not centre."""
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
        log.info(
            "window: file: no placement (old: %dx%d at %s,%s maximized=%s): the default size in the middle of the screen",
            state.width,
            state.height,
            state.x,
            state.y,
            state.maximized,
        )
        width, height = appstate.DEFAULT_SIZE
    else:
        width, height = state.width, state.height
        if keep_place and state.x is not None and state.y is not None and webdesk.on_a_screen(SYSTEM, state.x, state.y):
            # Saved in desktop coordinates; pywebview's GTK window adds the monitor corner.
            origin_x, origin_y = webdesk.screen_origin(SYSTEM)
            where = {"x": state.x - origin_x, "y": state.y - origin_y}
        log.info(
            "window: file: %dx%d at %s maximized=%s",
            width,
            height,
            where or "the middle of the screen",
            state.maximized,
        )
    window = webview.create_window(
        "NeoAPRS",
        html=loading.HTML,
        width=width,
        height=height,
        **where,
        maximized=state.maximized,
        hidden=launch.hidden,
        text_select=True,
        js_api=frame.api,
        background_color=loading.background(system_dark()),
    )
    frame.window = window
    if SYSTEM == "win32":
        keep_placement(frame, window, WindowKeeper(launch.data, state, window))
    else:
        webdesk.keep_size(frame, window, SizeKeeper(launch.data, state, keep_place), SYSTEM)
    window.events.loaded += lambda: window.evaluate_js(LINK_SCRIPT)
    return window


def keep_placement(frame: WebFrame, window: Any, keeper: WindowKeeper) -> None:
    """Windows: save the placement when the window hides or settles, restore it before showing.

    The close button always hides, as the notification area is always there."""
    frame.keeper = keeper

    def closing() -> bool:
        log.debug("window: event closing [%s]", threading.current_thread().name)
        if frame.quitting.is_set():
            return True  # Quit already saved the placement
        keeper.save("hide")
        window.hide()
        return False  # False cancels the close

    def shown() -> None:
        splash.done()  # the window is visible, so the start splash can go
        keeper.shown()

    window.events.closing += closing
    window.events.before_show += keeper.before_show
    window.events.shown += shown
    for name in ("maximized", "minimized", "restored", "resized", "moved"):
        hook = getattr(window.events, name)
        hook += keeper.told(name)


def dark_scheme(registry: Any = None) -> bool:
    """Return whether Windows apps use the dark scheme; False if unreadable."""
    try:
        winreg = registry if registry is not None else importlib.import_module("winreg")
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            light, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except (ImportError, OSError):
        return False
    return bool(light == 0)


def system_dark() -> bool:
    """Return the system's dark scheme, for the window background before the page paints."""
    if SYSTEM == "linux":
        return webdesk.portal_dark()
    if SYSTEM == "darwin":
        return webdesk.mac_dark()
    return dark_scheme()


def attach(frame: WebFrame, ctx: ShellContext) -> AppActions:
    """Give the tray its menu and the page's script its address once the session exists."""
    actions = ctx.actions_for(frame)
    with frame.lock:
        frame.actions = actions
    frame.api.page_url = ctx.session.url
    return actions


def load_page(window: Any, url: str) -> None:
    """Load the daemon's page in the window, or at the next `shown` if load_url times out."""
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
    """Return the folder for the web engine's page storage, or None on macOS."""
    if SYSTEM == "win32":
        return str(appstate.profile_dir(data))
    if SYSTEM == "darwin":
        return None
    return str(appstate.webkit_dir(data))


def start_options(launch: Launch) -> dict[str, Any]:
    """Return the options for `webview.start`.

    The engine is named because pywebview's own pick varies with the environment."""
    options: dict[str, Any] = {"gui": GUI.get(SYSTEM, "gtk"), "private_mode": False}
    storage = store_dir(launch.data)
    if storage is not None:
        options["storage_path"] = storage
    if SYSTEM == "linux":
        options["icon"] = str(icon_path())
    return options


def run_window(frame: WebFrame, launch: Launch, failed: list[NoPage]) -> None:
    """Run pywebview on the main thread until the last window is destroyed.

    If the engine cannot start, go on as a tray icon; with no tray either the failure propagates."""
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
