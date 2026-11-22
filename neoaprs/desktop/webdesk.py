"""What the web shell (webshell.py) asks of the desktop on Linux and macOS (NEOAPRS_WINDOW=web).

Tray presence, colour scheme, screens, close button and tray loop. Toolkits are imported inside
each function; what cannot be asked gets the answer that keeps the window usable."""

import importlib
import logging
import os
import threading
from collections.abc import Callable
from typing import Any, Protocol

from . import appstate, splash
from .menu import QUIT, AppActions
from .shell import TRAY_POLL_SEC, TRAY_WAIT_SEC
from .sizekeep import SizeKeeper

log = logging.getLogger("neoaprs.desktop")

# The bus name a tray host owns (KDE, GNOME's AppIndicator extension, Xfce, ...); Qt asks the same.
TRAY_WATCHER = "org.kde.StatusNotifierWatcher"
BUS_WAIT_MS = 1000


class WebFrame(Protocol):
    """What this file needs of the web shell's frame (webshell.WebFrame)."""

    icon: Any
    sizes: SizeKeeper | None
    actions: AppActions | None
    quitting: threading.Event
    done: threading.Event
    closed: bool
    lock: threading.Lock
    stop_loop: Callable[[], None] | None

    def tray_shows(self) -> bool: ...
    def show_window(self) -> None: ...


def on_main(system: str, call: Callable[[], object]) -> None:
    """Call the tray toolkit from any thread: queued to the main thread on macOS, direct elsewhere."""
    if system == "darwin":
        importlib.import_module("PyObjCTools.AppHelper").callAfter(call)
    else:
        call()


def gio_and_glib() -> tuple[Any, Any]:
    return importlib.import_module("gi.repository.Gio"), importlib.import_module("gi.repository.GLib")


def tray_host(system: str) -> bool:
    """Return whether the desktop shows tray icons (Linux: a tray host on the session bus)."""
    if system != "linux":
        return True
    try:
        gio, glib = gio_and_glib()
        bus = gio.bus_get_sync(gio.BusType.SESSION, None)
        reply = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            glib.Variant("(s)", (TRAY_WATCHER,)),
            glib.VariantType.new("(b)"),
            gio.DBusCallFlags.NONE,
            BUS_WAIT_MS,
            None,
        )
        return bool(reply.unpack()[0])
    except Exception:
        log.debug("the tray host could not be asked for", exc_info=True)
        return False


def portal_dark() -> bool:
    """Return whether the settings portal reports the dark scheme (1); False if unreadable."""
    try:
        gio, glib = gio_and_glib()
        bus = gio.bus_get_sync(gio.BusType.SESSION, None)
        reply = bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "Read",
            glib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
            None,
            gio.DBusCallFlags.NONE,
            BUS_WAIT_MS,
            None,
        )
        return bool(int(reply.unpack()[0]) == 1)
    except Exception:
        log.debug("the desktop's colour scheme could not be read", exc_info=True)
        return False


def mac_dark() -> bool:
    """Return whether `AppleInterfaceStyle` is Dark; False if unreadable."""
    try:
        defaults = importlib.import_module("Foundation").NSUserDefaults.standardUserDefaults()
        return bool(defaults.stringForKey_("AppleInterfaceStyle") == "Dark")
    except Exception:
        log.debug("the colour scheme of macOS could not be read", exc_info=True)
        return False


def on_a_screen(system: str, x: int, y: int) -> bool:
    """Return whether the title bar of a frame at (x, y) is on a screen (only Linux checks)."""
    if system != "linux":
        return True
    try:
        gdk = importlib.import_module("gi.repository.Gdk")
        px, py = x + appstate.TITLE_POINT[0], y + appstate.TITLE_POINT[1]
        area = gdk.Display.get_default().get_monitor_at_point(px, py).get_geometry()
        return bool(area.x <= px < area.x + area.width and area.y <= py < area.y + area.height)
    except Exception:
        log.debug("the screens could not be asked for", exc_info=True)
        return False


def screen_origin(system: str) -> tuple[int, int]:
    """Return the first monitor's top left corner, which pywebview's GTK window adds to a place."""
    if system != "linux":
        return 0, 0
    try:
        area = importlib.import_module("gi.repository.Gdk").Display.get_default().get_monitor(0).get_geometry()
        return int(area.x), int(area.y)
    except Exception:
        log.debug("the first monitor could not be asked for", exc_info=True)
        return 0, 0


def frame_moved(window: Any, sizes: SizeKeeper) -> Callable[..., None]:
    """Return the Linux move handler: pywebview reports the inside's place, GTK places by the frame."""
    glib = importlib.import_module("gi.repository.GLib")

    def read() -> bool:
        try:
            x, y = window.native.get_position()
        except Exception:
            log.debug("the window's place could not be asked for", exc_info=True)
            return False
        sizes.event("moved", x, y)
        # GLib repeats an idle function while it returns True; this must run once.
        return False

    def handler(*args: object) -> None:
        glib.idle_add(read)

    return handler


def wayland(environ: Any = os.environ) -> bool:
    """Return whether GTK draws on Wayland, where apps cannot learn or set their place."""
    return bool(environ.get("WAYLAND_DISPLAY")) and environ.get("GDK_BACKEND", "") != "x11"


def keep_size(frame: WebFrame, window: Any, sizes: SizeKeeper, system: str) -> None:
    """Connect the window's events to the size keeper.

    Close hides the window while a tray can restore it, else quits; the close itself is always cancelled."""
    frame.sizes = sizes

    def closing() -> bool:
        log.debug("window: event closing [%s]", threading.current_thread().name)
        if frame.quitting.is_set():
            return True
        sizes.save()
        window.hide()
        if frame.tray_shows():
            return False
        with frame.lock:
            actions = frame.actions
            frame.closed = actions is None
        if actions is None:
            log.info(
                "the window was closed before the page came and this desktop has no tray: the app ends when the page is there"
            )
        else:
            log.info("the window was closed and this desktop has no tray: the app ends")
            actions.run(QUIT)
        return False

    window.events.closing += closing
    window.events.shown += splash.done
    for name in ("maximized", "minimized", "restored", "resized", "moved"):
        hook = getattr(window.events, name)
        hook += (
            frame_moved(window, sizes)
            if name == "moved" and system == "linux" and sizes.keep_place
            else sizes.told(name)
        )


def await_tray(frame: WebFrame) -> None:
    """Wait up to TRAY_WAIT_SEC for a tray host (the panel may start late), else show the window."""
    if frame.icon is not None:
        waited, wait_sec, poll_sec = 0.0, TRAY_WAIT_SEC, TRAY_POLL_SEC
        while not frame.tray_shows():
            if waited >= wait_sec:
                log.warning("this desktop has no system tray: the window stays")
                break
            if frame.done.wait(poll_sec):
                return
            waited += poll_sec
        else:
            return
    else:
        log.info("no tray icon: the window is shown")
    frame.show_window()


def tray_loop(system: str, frame: WebFrame) -> None:
    """Run the tray on the main thread until Quit when there is no window loop (`frame.stop_loop` ends it)."""
    if system == "win32":
        frame.done.wait()
        return
    if system == "darwin":
        helper = importlib.import_module("PyObjCTools.AppHelper")
        frame.stop_loop = lambda: helper.callAfter(helper.stopEventLoop)
        if not frame.done.is_set():
            helper.runEventLoop()
        return
    glib = importlib.import_module("gi.repository.GLib")
    loop = glib.MainLoop.new(None, False)
    frame.stop_loop = lambda: glib.idle_add(loop.quit)
    if not frame.done.is_set():
        loop.run()
