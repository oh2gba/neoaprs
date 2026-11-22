"""Choose which shell this computer can run.

A shell is `webshell` (pywebview and pystray) or `qtshell` (Qt); `choose` probes by importing.
With no toolkit the app only opens the page in the browser."""

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

# How long to look for a tray when the desktop has none yet (the panel may start later).
TRAY_WAIT_SEC = 60.0
TRAY_POLL_SEC = 2.0
WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"),
    ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"),
)
Importer = Callable[[str], Any]
# "web" selects the web shell on Linux and macOS instead of Qt; anything else means Qt.
WINDOW_SWITCH = "NEOAPRS_WINDOW"
WEB_SHELL = "neoaprs.desktop.webshell"
# The GLib program name: Wayland matches it to neoaprs.desktop to find the window's icon.
PROGRAM = "neoaprs"


@dataclass(frozen=True)
class Choice:
    """The chosen shell: its `module` (None: none can run), whether it has a `window` or a `tray`, and `why` for the log."""

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
    """Return None if every module imports, else what failed (any exception counts, not only ImportError)."""
    for name in names:
        try:
            importer(name)
        except Exception as e:
            return f"{name}: {type(e).__name__}: {e}"
    return None


def webview2_runtime(registry: Any = None) -> bool:
    """Return True if the WebView2 runtime is installed (a version in its registry keys)."""
    winreg = registry if registry is not None else importlib.import_module("winreg")
    for root, path in WEBVIEW2_KEYS:
        try:
            with winreg.OpenKey(getattr(winreg, root), path + "\\" + WEBVIEW2_CLIENT) as key:
                version, _kind = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if str(version).strip() not in ("", "0.0.0.0"):  # noqa: S104  (a version number meaning "not installed", not an address)
            return True
    return False


# WebKit2 with the Soup it is built on, in the order pywebview prefers them.
WEBKIT_APIS = (("4.1", "3.0"), ("4.0", "2.4"))


def webkit_api(gi: Any) -> tuple[str, str]:
    """Return the WebKit2 and Soup versions whose typelibs both exist; raise ValueError if none.

    Both are checked before either is required: gi keeps the first version required of a namespace."""
    repository = gi.Repository.get_default()
    for webkit, soup in WEBKIT_APIS:
        if webkit in repository.enumerate_versions("WebKit2") and soup in repository.enumerate_versions("Soup"):
            return webkit, soup
    raise ValueError("no typelibs of WebKit2 4.1 with Soup 3.0, nor of WebKit2 4.0 with Soup 2.4")


def gtk_window_problem(importer: Importer) -> str | None:
    """Return None if gi, GTK 3, WebKitGTK and pywebview load, else what is missing; sets GLib's program name."""
    # Imported only for the web window, so the Qt window's start loads none of it.
    from . import gtkenv

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
    """Choose the web shell on Linux or macOS; its window and its tray are each present or not."""
    if platform == "darwin":
        window_problem = _can_import(importer, "webview", "WebKit")
        tray_problem = _can_import(importer, "pystray", "PIL.Image", "PyObjCTools.AppHelper")
    else:
        # Imported only for the web window, so Qt's start loads none of it (ctypes included).
        from . import gtkenv

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


def choose(
    platform: str | None = None,
    importer: Importer = importlib.import_module,
    runtime: Callable[[], bool] = webview2_runtime,
    environ: Any = None,
) -> Choice:
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
    """What a shell is given to run; `ready(actions)` connects the app lock and the daemon watch to the actions."""

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
        self.watch = DaemonWatch(
            self.session,
            actions.daemon_gone,
            self.daemon,
            moved=actions.page_moved,
            app_file=self.app_file,
            renewed=actions.renew,
            network_moved=actions.network_moved,
        )
        self.watch.start()

    def renewing(self) -> bool:
        """Return True if the app ended to restart as the new version (renew.py)."""
        return self.actions is not None and self.actions.renewing

    def close(self) -> None:
        if self.watch is not None:
            self.watch.cancel()
        self.single.close()


@dataclass
class Launch:
    """What a shell starts with before the daemon's page is there.

    The shell shows its window at once and asks `context(session)` once `opening` has the session."""

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
        """Return the launch for a context whose session is already there."""
        return cls(
            ctx.session.data,
            Opening.opened(ctx.session),
            ctx.hidden,
            ctx.window,
            ctx.autostart,
            ctx.single,
            ctx.daemon,
            ctx=ctx,
        )

    def context(self, session: Session) -> ShellContext:
        if self.ctx is None:
            log.info(
                "NeoAPRS app on %s, page %s, %s daemon; %s",
                self.data,
                session.url,
                "its own" if session.owned else "a running",
                self.describe,
            )
            self.ctx = ShellContext(
                session, self.hidden, self.window, self.autostart, self.single, self.daemon, app_file=self.app_file
            )
        return self.ctx

    def no_page(self, error: NoPage) -> int:
        """Release the data folder and report that no page came; return exit code 1."""
        self.single.close()
        splash.done()
        opencmd.tell_the_user(f"app: NeoAPRS did not come up: {error}. The log is {self.data / LOG_NAME}")
        return 1

    def close(self) -> None:
        if self.ctx is not None:
            self.ctx.close()
        else:
            self.single.close()
