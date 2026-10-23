"""Which shell this computer can run. A shell is the code that owns the toolkit's loop, the window and the tray icon: `qtshell` (Qt: Linux, macOS) or `winshell` (pywebview and pystray: Windows). The toolkits are
the app's optional dependencies, so what is installed decides: a window needs a web engine, a tray icon needs a toolkit, and when there is neither the app can only open the page in the browser. `choose` looks
(importing is the look; it runs no toolkit) and says what it found, for the log: the fallbacks are "no window: the tray and the browser" and "nothing: the browser only", never a failure.

Windows has one more condition: pywebview, asked for no particular engine, falls back to the old Internet Explorer engine when WebView2 is missing, which cannot show the page. WebView2's runtime is part of
Windows 11 and of every current Windows 10; `webview2_runtime` looks for it in the registry, where its updater writes it, and without it the window is not offered."""
import importlib
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .autostart import AutoStart
from .menu import QUIT, AppActions, Frame
from .session import Daemon, DaemonWatch, Session
from .single import SingleApp

log = logging.getLogger("neoaprs.desktop")

WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_KEYS = (("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"), ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"), ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"))
Importer = Callable[[str], Any]


@dataclass(frozen=True)
class Choice:
    """`module`: the shell's module (None: no shell can run); `window`: whether it can show the page in a window (else it keeps the tray and opens the browser); `why`: what was missing, for the log."""
    module: str | None
    window: bool
    why: tuple[str, ...] = ()

    def describe(self) -> str:
        if self.module is None:
            what = "no window and no tray icon: the page is opened in the browser"
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
        if str(version).strip() not in ("", "0.0.0.0"):
            return True
    return False


def choose(platform: str | None = None, importer: Importer = importlib.import_module, runtime: Callable[[], bool] = webview2_runtime) -> Choice:
    platform = sys.platform if platform is None else platform
    why: list[str] = []
    if platform == "win32":
        module = "neoaprs.desktop.winshell"
        tray_problem = _can_import(importer, "pystray", "PIL.Image")
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
    window and tray exist: from then on a second app's `show` and `quit` and the end of the daemon reach the actions."""
    session: Session
    hidden: bool
    window: bool
    autostart: AutoStart | None
    single: SingleApp
    daemon: Daemon = field(default_factory=Daemon)
    watch: DaemonWatch | None = None

    def actions_for(self, frame: Frame) -> AppActions:
        return AppActions(self.session, frame, self.autostart, self.daemon)

    def ready(self, actions: AppActions) -> None:
        self.single.handle(lambda command: actions.show() if command == "show" else actions.run(QUIT))
        self.watch = DaemonWatch(self.session, actions.daemon_gone, self.daemon)
        self.watch.start()

    def close(self) -> None:
        if self.watch is not None:
            self.watch.cancel()
        self.single.close()
