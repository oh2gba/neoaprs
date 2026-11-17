"""Which shell this computer can run. A shell is the code that owns the toolkit's loop, the window and the tray icon: `webshell` (pywebview and pystray: Windows, and Linux and macOS when NEOAPRS_WINDOW=web asks
for it) or `qtshell` (Qt: Linux, macOS). The toolkits are the app's optional dependencies, so what is installed decides: a window needs a web engine, a tray icon needs a toolkit, and when there is neither the app
can only open the page in the browser. `choose` looks (importing is the look; it runs no toolkit, and on Linux the web shell's GTK ground is laid first, gtkenv.py) and says what it found, for the log: the
fallbacks are "no window: the tray and the browser" and "nothing: the browser only", never a failure; the web shell on Linux and macOS may also have a window and no tray ("window, no tray icon").

Windows has one more condition: pywebview, asked for no particular engine, falls back to the old Internet Explorer engine when WebView2 is missing, which cannot show the page. WebView2's runtime is part of
Windows 11 and of every current Windows 10; `webview2_runtime` looks for it in the registry, where its updater writes it, and without it the window is not offered.

The web window on Linux and macOS is a trial (aprs-reference/window-plan.md): NEOAPRS_WINDOW=web chooses it in place of Qt's, which stays the window when the variable is not set. On Linux the window needs
GTK 3 and WebKitGTK (the 4.1 API, else 4.0) with their typelibs and pywebview; the tray needs pystray on its appindicator backend, forced (`PYSTRAY_BACKEND`), whose library and typelib the AppImage carries:
any failure of its import is no tray (pystray ends its whole import with the ValueError of a missing typelib). The program's name is given to GLib before GTK starts, so that the desktop finds the window's icon
by the name of neoaprs.desktop."""
import importlib
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neoaprs.cli import opencmd
from neoaprs.cli.logfile import LOG_NAME

from . import splash
from .autostart import AutoStart
from .menu import QUIT, AppActions, Frame
from .renew import AppFile
from .session import Daemon, DaemonWatch, NoPage, Opening, Session
from .single import SingleApp

log = logging.getLogger("neoaprs.desktop")

WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_KEYS = (("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"), ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"), ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"))
Importer = Callable[[str], Any]
WINDOW_SWITCH = "NEOAPRS_WINDOW"                 # "web": the web shell on Linux and macOS in place of Qt's (the trial); anything else or nothing: Qt
WEB_SHELL = "neoaprs.desktop.webshell"
PROGRAM = "neoaprs"                              # the name GLib gives the program: the desktop matches it to neoaprs.desktop for the window's icon on Wayland


@dataclass(frozen=True)
class Choice:
    """`module`: the shell's module (None: no shell can run); `window`: whether it can show the page in a window (else it keeps the tray and opens the browser); `why`: what was missing, for the log;
    `tray`: whether it can have a tray icon (only the web shell on Linux and macOS can have a window without one)."""
    module: str | None
    window: bool
    why: tuple[str, ...] = ()
    tray: bool = True

    def describe(self) -> str:
        if self.module is None:
            what = "no window and no tray icon: the page is opened in the browser"
        elif self.window and not self.tray:
            what = f"window, no tray icon: closing the window quits ({self.module})"
        elif self.window:
            what = f"window and tray ({self.module})"
        else:
            what = f"no window, the tray and the browser ({self.module})"
        return what + (f" [{'; '.join(self.why)}]" if self.why else "")


def _can_import(importer: Importer, *names: str) -> str | None:
    """None when every module imports, else what failed (the toolkit that is not installed, or installed and broken: a library that cannot be loaded raises more than ImportError)."""
    for name in names:
        try:
            importer(name)
        except Exception as e:
            return f"{name}: {type(e).__name__}: {e}"
    return None


def webview2_runtime(registry: Any = None) -> bool:
    """Whether the WebView2 runtime is installed (a version in the keys its updater keeps, for all users or the current one)."""
    winreg = registry if registry is not None else importlib.import_module("winreg")
    for root, path in WEBVIEW2_KEYS:
        try:
            with winreg.OpenKey(getattr(winreg, root), path + "\\" + WEBVIEW2_CLIENT) as key:
                version, _kind = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if str(version).strip() not in ("", "0.0.0.0"):  # noqa: S104  (a version number, which in this key says that the runtime is not installed; no address)
            return True
    return False


WEBKIT_APIS = (("4.1", "3.0"), ("4.0", "2.4"))     # WebKit2 with the Soup it is built on, in the order pywebview takes them


def webkit_api(gi: Any) -> tuple[str, str]:
    """The WebKit2 and Soup versions whose typelibs are both there, looked up before either is required: gi keeps the first version required of a namespace, so a WebKit2 4.1 required before its Soup 3.0
    turned out missing would refuse the 4.0 after it. ValueError when neither pair is there."""
    repository = gi.Repository.get_default()
    for webkit, soup in WEBKIT_APIS:
        if webkit in repository.enumerate_versions("WebKit2") and soup in repository.enumerate_versions("Soup"):
            return webkit, soup
    raise ValueError("no typelibs of WebKit2 4.1 with Soup 3.0, nor of WebKit2 4.0 with Soup 2.4")


def gtk_window_problem(importer: Importer) -> str | None:
    """None when the web window can be had on Linux, else what is missing: gi, GTK 3, WebKitGTK (the 4.1 API with Soup 3, else 4.0 with Soup 2.4, as pywebview asks for them) and pywebview. The program is named
    before GTK is (it is GLib's)."""
    from . import gtkenv                        # (imported only for the web window: the Qt window's start loads nothing of it)
    try:
        gi = importer("gi")
    except Exception as e:
        return f"gi: {type(e).__name__}: {e}"
    try:
        importer("gi.repository.GLib").set_prgname(PROGRAM)
        gi.require_version("Gtk", "3.0")
        webkit, soup = webkit_api(gi)
        gi.require_version("Soup", soup)
        gi.require_version("WebKit2", webkit)
        importer("gi.repository.Gtk")
        importer("gi.repository.WebKit2")
    except Exception as e:
        return f"no WebKitGTK: {type(e).__name__}: {e} (the window needs the system's; Debian and Ubuntu: {gtkenv.WEBKIT_PACKAGE})"
    return _can_import(importer, "webview")


def choose_web(platform: str, importer: Importer, environ: Any) -> Choice:
    """The web shell on Linux or macOS: its window and its tray are each had or not, and a window without a tray is a choice of its own."""
    if platform == "darwin":
        window_problem = _can_import(importer, "webview", "WebKit")
        tray_problem = _can_import(importer, "pystray", "PIL.Image", "PyObjCTools.AppHelper")
    else:
        from . import gtkenv                    # (imported only for the web window: the Qt window's start loads nothing of it, ctypes included)
        ground = gtkenv.prepare()
        if ground:
            log.info("the web window's ground: %s", "; ".join(ground))
        window_problem = gtk_window_problem(importer)
        environ["PYSTRAY_BACKEND"] = "appindicator"
        tray_problem = _can_import(importer, "pystray", "PIL.Image")
    why = tuple(p for p in (window_problem, tray_problem) if p)
    if window_problem is not None and tray_problem is not None:
        return Choice(None, False, why, tray=False)
    return Choice(WEB_SHELL, window_problem is None, why, tray=tray_problem is None)


def choose(platform: str | None = None, importer: Importer = importlib.import_module, runtime: Callable[[], bool] = webview2_runtime, environ: Any = None) -> Choice:
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    why: list[str] = []
    if platform != "win32" and environ.get(WINDOW_SWITCH) == "web":
        return choose_web(platform, importer, environ)
    if platform == "win32":
        module = WEB_SHELL
        tray_problem = _can_import(importer, "pystray")
        window_problem = _can_import(importer, "webview")
        if window_problem is None and not runtime():
            window_problem = "the WebView2 runtime is not installed"
    else:
        module = "neoaprs.desktop.qtshell"
        window_problem = _can_import(importer, "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore")
        tray_problem = None if window_problem is None else _can_import(importer, "PySide6.QtWidgets")
    why.extend(p for p in (window_problem, tray_problem) if p)
    if tray_problem is not None:
        return Choice(None, False, tuple(why))
    return Choice(module, window_problem is None, tuple(why))


@dataclass
class ShellContext:
    """What a shell is given to run: the daemon's session, whether to start with the window hidden, the start at sign-in of this system, and the app's one-app lock. `ready(actions)` is the shell telling the app that its
    window and tray exist: from then on a second app's `show` and `quit`, the end of the daemon, a new address of its page and a new version of the app's own file (`app_file`, renew.py) reach the actions."""
    session: Session
    hidden: bool
    window: bool
    autostart: AutoStart | None
    single: SingleApp
    daemon: Daemon = field(default_factory=Daemon)
    watch: DaemonWatch | None = None
    app_file: AppFile | None = None
    actions: AppActions | None = None

    def actions_for(self, frame: Frame) -> AppActions:
        return AppActions(self.session, frame, self.autostart, self.daemon)

    def ready(self, actions: AppActions) -> None:
        self.actions = actions
        self.single.handle(lambda command: actions.show() if command == "show" else actions.run(QUIT))
        self.watch = DaemonWatch(self.session, actions.daemon_gone, self.daemon, moved=actions.page_moved, app_file=self.app_file, renewed=actions.renew)
        self.watch.start()

    def renewing(self) -> bool:
        """Whether the app ended to start again as the new version (renew.py)."""
        return self.actions is not None and self.actions.renewing

    def close(self) -> None:
        if self.watch is not None:
            self.watch.cancel()
        self.single.close()


@dataclass
class Launch:
    """What a shell starts with, before the daemon's page is there: the data folder, the session on its way, whether to start with the window hidden, whether a window can be had, the start at sign-in and the
    one-app lock. The shell makes its window at once (with the page of loading.py in it) and asks `context(session)` for its ShellContext once `opening` has the session; when it never comes, `no_page` is
    the end, in the words the app has always said it with. `describe` is what the shell can do, for the log line of the session; `tray`, whether its tray's toolkit loaded (Choice.tray); `app_file`, the
    AppImage file the app runs from, as it was at the start (renew.py)."""
    data: Path
    opening: Opening
    hidden: bool
    window: bool
    autostart: AutoStart | None
    single: SingleApp
    daemon: Daemon = field(default_factory=Daemon)
    describe: str = ""
    ctx: ShellContext | None = None
    tray: bool = True
    app_file: AppFile | None = None

    @classmethod
    def of(cls, ctx: ShellContext) -> "Launch":
        """The launch of a context whose session is there already."""
        return cls(ctx.session.data, Opening.opened(ctx.session), ctx.hidden, ctx.window, ctx.autostart, ctx.single, ctx.daemon, ctx=ctx)

    def context(self, session: Session) -> ShellContext:
        if self.ctx is None:
            log.info("NeoAPRS app on %s, page %s, %s daemon; %s", self.data, session.url, "its own" if session.owned else "a running", self.describe)
            self.ctx = ShellContext(session, self.hidden, self.window, self.autostart, self.single, self.daemon, app_file=self.app_file)
        return self.ctx

    def no_page(self, error: NoPage) -> int:
        """No page came: the app lets go of the folder and says so (a message box too, where there is no console, with the splash taken away first: it is on top of everything); exit code 1."""
        self.single.close()
        splash.done()
        opencmd.tell_the_user(f"app: NeoAPRS did not come up: {error}. The log is {self.data / LOG_NAME}")
        return 1

    def close(self) -> None:
        if self.ctx is not None:
            self.ctx.close()
        else:
            self.single.close()
