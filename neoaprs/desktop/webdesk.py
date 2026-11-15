"""What the web shell (webshell.py) asks of the desktop on Linux and macOS, where it runs as the trial of NEOAPRS_WINDOW=web: whether there is a tray to hide into (on Linux, a tray host that owns its name on the
session bus; the menu bar of macOS is always there), the desktop's light or dark scheme (the settings portal of Linux, the user's defaults of macOS), whether a remembered place is on a screen still, the tray
calls that AppKit wants on the main thread, the close button of a window with no tray, the minute's wait for the tray host of an app started in the tray, and the tray's own loop when there is no window. Each
toolkit (gi's Gio, GLib and Gdk, pyobjc's Foundation and PyObjCTools) is imported by name inside the function that uses it; what cannot be asked is the answer that keeps the window usable, never an error."""
import importlib
import logging
import os
import threading
from collections.abc import Callable
from typing import Any, Protocol

from . import splash
from .menu import QUIT, AppActions
from .sizekeep import SizeKeeper

log = logging.getLogger("neoaprs.desktop")

TRAY_WAIT_SEC = 60.0                            # a desktop that starts the app at sign-in may not have its panel up yet: the tray is looked for this long before the window is shown for want of one
TRAY_POLL_SEC = 2.0
TRAY_WATCHER = "org.kde.StatusNotifierWatcher"   # the bus name a desktop's tray host owns (KDE, GNOME's AppIndicator extension, Xfce's and others' panels): the same question Qt asks
BUS_WAIT_MS = 1000
TITLE_POINT = (64, 16)                          # a point of the title bar, from the top left corner of the frame: where it is on a screen, the window can be taken hold of


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
    """A call of the tray's toolkit from any thread: on macOS queued to the main thread, where AppKit's objects live; elsewhere made at once (pystray queues its own calls to GTK's loop, and Windows' backend is thread-safe)."""
    if system == "darwin":
        importlib.import_module("PyObjCTools.AppHelper").callAfter(call)
    else:
        call()


def gio_and_glib() -> tuple[Any, Any]:
    return importlib.import_module("gi.repository.Gio"), importlib.import_module("gi.repository.GLib")


def tray_host(system: str) -> bool:
    """Whether the desktop shows tray icons: on Linux, whether a tray host owns its name on the session bus (False when it cannot be asked); macOS's menu bar and Windows' notification area are always there."""
    if system != "linux":
        return True
    try:
        gio, glib = gio_and_glib()
        bus = gio.bus_get_sync(gio.BusType.SESSION, None)
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner", glib.Variant("(s)", (TRAY_WATCHER,)), glib.VariantType.new("(b)"),
                              gio.DBusCallFlags.NONE, BUS_WAIT_MS, None)
        return bool(reply.unpack()[0])
    except Exception:
        log.debug("the tray host could not be asked for", exc_info=True)
        return False


def portal_dark() -> bool:
    """Whether the Linux desktop is in the dark scheme, as its settings portal tells it (`org.freedesktop.appearance` `color-scheme`, 1 = dark); light where it cannot be read."""
    try:
        gio, glib = gio_and_glib()
        bus = gio.bus_get_sync(gio.BusType.SESSION, None)
        reply = bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop", "org.freedesktop.portal.Settings", "Read",
                              glib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")), None, gio.DBusCallFlags.NONE, BUS_WAIT_MS, None)
        return bool(int(reply.unpack()[0]) == 1)
    except Exception:
        log.debug("the desktop's colour scheme could not be read", exc_info=True)
        return False


def mac_dark() -> bool:
    """Whether macOS is in the dark appearance (`AppleInterfaceStyle` of the user's defaults); light where it cannot be read."""
    try:
        defaults = importlib.import_module("Foundation").NSUserDefaults.standardUserDefaults()
        return bool(defaults.stringForKey_("AppleInterfaceStyle") == "Dark")
    except Exception:
        log.debug("the colour scheme of macOS could not be read", exc_info=True)
        return False


def on_a_screen(system: str, x: int, y: int) -> bool:
    """Whether the title bar of a window whose frame has its top left corner at (x, y) is on a screen now (a monitor may be gone since): on Linux as GDK sees the monitors; elsewhere it is taken that it is."""
    if system != "linux":
        return True
    try:
        gdk = importlib.import_module("gi.repository.Gdk")
        px, py = x + TITLE_POINT[0], y + TITLE_POINT[1]
        area = gdk.Display.get_default().get_monitor_at_point(px, py).get_geometry()
        return bool(area.x <= px < area.x + area.width and area.y <= py < area.y + area.height)
    except Exception:
        log.debug("the screens could not be asked for", exc_info=True)
        return False


def screen_origin(system: str) -> tuple[int, int]:
    """Where the first monitor's top left corner is: pywebview's GTK window adds it to the place it is given (on Linux; (0, 0) elsewhere, and when the screens cannot be asked)."""
    if system != "linux":
        return 0, 0
    try:
        area = importlib.import_module("gi.repository.Gdk").Display.get_default().get_monitor(0).get_geometry()
        return int(area.x), int(area.y)
    except Exception:
        log.debug("the first monitor could not be asked for", exc_info=True)
        return 0, 0


def frame_moved(window: Any, sizes: SizeKeeper) -> Callable[..., None]:
    """The handler of a move on Linux: pywebview tells the place of the window's inside, and GTK puts a window by its frame (the title bar too), so the place kept is the frame's, asked of the GTK window itself
    on GTK's own loop (`get_position`, which is what `move` sets)."""
    glib = importlib.import_module("gi.repository.GLib")

    def read() -> bool:
        try:
            x, y = window.native.get_position()
        except Exception:
            log.debug("the window's place could not be asked for", exc_info=True)
            return False
        sizes.event("moved", x, y)
        return False                                    # (once: GLib calls an idle function again while it returns True)

    def handler(*args: object) -> None:
        glib.idle_add(read)
    return handler


def wayland(environ: Any = os.environ) -> bool:
    """Whether GTK draws on Wayland, where no app is told its place or given one (Qt's neither): only the size is kept there."""
    return bool(environ.get("WAYLAND_DISPLAY")) and environ.get("GDK_BACKEND", "") != "x11"


def keep_size(frame: WebFrame, window: Any, sizes: SizeKeeper, system: str) -> None:
    """The size keeper hears the window's events. The close button hides the window while a tray icon is on show to bring it back from; with none it ends the app (the daemon too, if the app started it), as
    Quit would: at once when the session is there, else as soon as it comes. The close itself is always cancelled, so that the window loop runs until Quit has stopped the daemon."""
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
            log.info("the window was closed before the page came and this desktop has no tray: the app ends when the page is there")
        else:
            log.info("the window was closed and this desktop has no tray: the app ends")
            actions.run(QUIT)
        return False

    window.events.closing += closing
    window.events.shown += splash.done
    for name in ("maximized", "minimized", "restored", "resized", "moved"):
        hook = getattr(window.events, name)
        hook += frame_moved(window, sizes) if name == "moved" and system == "linux" and sizes.keep_place else sizes.told(name)


def await_tray(frame: WebFrame) -> None:
    """An app that started in the tray: the tray host is looked for for a minute (the panel may come up after the app at sign-in); if it never comes, or there is no tray icon at all, the window, which had
    nothing to be brought back from, is shown. Runs in the thread pywebview started, which has nothing else to do."""
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
    """With no window loop to ride on, the main thread runs the tray until Quit: on Windows pystray's thread draws it and the main thread only waits; on Linux it is a GLib loop and on macOS the
    application's event loop, which Quit ends (`frame.stop_loop`)."""
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
