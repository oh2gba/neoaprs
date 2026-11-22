"""The shell for Linux and macOS: Qt provides the window (qtwindow.py) and the tray icon.

Without the web engine only the tray runs and the page opens in the browser. The window is made
first, showing the loading page, while the daemon comes up; `build(ctx)` makes the rest."""

import logging
import webbrowser
from importlib import resources
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .menu import QUIT, AppActions
from .session import NoPage
from .shell import TRAY_POLL_SEC, TRAY_WAIT_SEC, Launch, ShellContext

if TYPE_CHECKING:
    from .qtwindow import AppWindow

log = logging.getLogger("neoaprs.desktop")

TRAY_POLL_MS = int(TRAY_POLL_SEC * 1000)


def icon_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.png")))


class QtFrame(QObject):
    """The `Frame` of the Qt shell. Other threads use the signals to reach the main thread, in order."""

    show_requested = Signal()
    quit_requested = Signal()
    tell_requested = Signal(str)
    load_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self, with_window: bool) -> None:
        super().__init__()
        self.has_window = with_window
        self.window: AppWindow | None = None
        self.tray: QSystemTrayIcon | None = None
        self.show_requested.connect(self._show)
        self.quit_requested.connect(self._quit)
        self.tell_requested.connect(self._tell)
        self.load_requested.connect(self._load)
        self.refresh_requested.connect(self._refresh)
        self.rebuild: Callable[[], None] | None = None  # rebuilds the tray menu (set once it exists)

    def show_window(self) -> None:
        self.show_requested.emit()

    def quit(self) -> None:
        self.quit_requested.emit()

    def refresh(self) -> None:
        """Rebuild the tray menu on the main thread, for trays that do not signal when the menu opens."""
        self.refresh_requested.emit()

    @Slot()
    def _refresh(self) -> None:
        if self.rebuild is not None:
            self.rebuild()

    def tell(self, text: str) -> None:
        self.tell_requested.emit(text)

    def load(self, url: str) -> None:
        self.load_requested.emit(url)

    @Slot()
    def _show(self) -> None:
        if self.window is not None:
            self.window.raise_up()

    @Slot()
    def _quit(self) -> None:
        if self.window is not None:
            self.window.remember_geometry()
        QApplication.quit()

    @Slot(str)
    def _load(self, url: str) -> None:
        if self.window is not None:
            self.window.load(url)

    @Slot(str)
    def _tell(self, text: str) -> None:
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage("NeoAPRS", text, QSystemTrayIcon.MessageIcon.Information, 8000)
        else:
            log.warning("%s", text)


class Built:
    """Everything `build` makes, held so Qt does not drop it while the app runs."""

    def __init__(self, app: QApplication, frame: QtFrame, actions: AppActions) -> None:
        self.app, self.frame, self.actions = app, frame, actions
        self.menu = QMenu()
        self.entries: list[QAction] = []
        self.tray: QSystemTrayIcon | None = None
        self.tray_timer: QTimer | None = None

    @property
    def window(self) -> "AppWindow | None":
        return self.frame.window


def fill_menu(built: Built) -> None:
    """Fill the tray menu from `actions.items()`; rebuilt before each show so checkboxes are current."""
    built.menu.clear()
    built.entries.clear()
    for item in built.actions.items():
        if item.separator:
            built.menu.addSeparator()
            continue
        action = QAction(item.label, built.menu)
        if item.checked is not None:
            action.setCheckable(True)
            action.setChecked(item.checked)
        action.triggered.connect(lambda _checked=False, key=item.key: built.actions.run(key))
        built.menu.addAction(action)
        built.entries.append(action)


def make_tray(built: Built, icon: QIcon) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(icon, built.frame)
    built.tray = tray
    tray.setToolTip("NeoAPRS")
    tray.setContextMenu(built.menu)
    built.menu.aboutToShow.connect(lambda: fill_menu(built))
    tray.activated.connect(
        lambda reason: (
            built.actions.show()
            if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick)
            else None
        )
    )
    built.frame.tray = tray
    built.frame.rebuild = lambda: fill_menu(built)
    fill_menu(built)
    return tray


def await_tray(built: Built, tray: QSystemTrayIcon) -> None:
    """Show the tray, polling for TRAY_WAIT_SEC while the panel starts; if none comes, show the window."""
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
        return
    left = [TRAY_WAIT_SEC * 1000 // TRAY_POLL_MS]
    timer = QTimer(built.frame)
    built.tray_timer = timer

    def look() -> None:
        left[0] -= 1
        if QSystemTrayIcon.isSystemTrayAvailable():
            timer.stop()
            tray.show()
        elif left[0] <= 0:
            timer.stop()
            log.warning("this desktop has no system tray: the window stays")
            built.actions.show()

    timer.timeout.connect(look)
    timer.start(TRAY_POLL_MS)


def application() -> QApplication:
    """Return the running QApplication, or a new one."""
    existing = QApplication.instance()
    if existing is None:
        return QApplication([])
    assert isinstance(existing, QApplication)
    return existing


def prepared(app: QApplication | None = None) -> QApplication:
    """Return the app (`app`, the running one, or a new one), set to keep running when its last window closes."""
    app = app or application()
    app.setApplicationName("NeoAPRS")
    app.setQuitOnLastWindowClosed(False)
    return app


def build(ctx: ShellContext, app: QApplication | None = None, window: "AppWindow | None" = None) -> Built:
    """Make the window (`window`, the loading one, or a new one), the tray and their wiring, showing and starting nothing."""
    app = prepared(app)
    icon = QIcon(str(icon_path()))
    frame = QtFrame(ctx.window)
    actions = ctx.actions_for(frame)
    built = Built(app, frame, actions)
    tray = make_tray(built, icon)
    if ctx.window:
        from .qtwindow import AppWindow

        window = window or AppWindow(ctx.session.data, ctx.session.url, icon, lambda: True)
        window.on_close = lambda: close_hides(tray, actions)
        frame.window = window
    return built


def close_hides(tray: QSystemTrayIcon, actions: AppActions) -> bool:
    """Handle the close button: hide the window while a tray icon can restore it, else quit."""
    if tray.isVisible():
        return True
    actions.run("quit")
    return False


class Opened(QObject):
    """Carries the session's arrival to the main thread; queued, so it is heard once the loop runs."""

    arrived = Signal()


def start(built: Built, ctx: ShellContext) -> None:
    """Start the tray, end the wait for the session, and load the page in the window (or the browser)."""
    window = built.window
    if built.tray is None or (window is None and not QSystemTrayIcon.isSystemTrayAvailable()):
        raise RuntimeError(
            "this desktop has no system tray and the web engine is not installed: there is nothing to show"
        )
    await_tray(built, built.tray)
    ctx.ready(built.actions)
    if window is not None:
        window.load(ctx.session.url)
    elif not ctx.hidden:
        webbrowser.open(ctx.session.url)
    log.info("the Qt shell runs (%s)", "window and tray" if window is not None else "tray only")


def loading_window(launch: Launch) -> "AppWindow":
    """Return the startup window with the loading page, raised unless starting in the tray."""
    from .qtwindow import AppWindow

    window = AppWindow(launch.data, None, QIcon(str(icon_path())), lambda: True)
    window.show_loading()
    if not launch.hidden:
        window.raise_up()
    return window


def close_while_loading(closed: list[bool]) -> bool:
    """Handle the close button before the session exists: hide with a tray, else close and note it in `closed`."""
    if QSystemTrayIcon.isSystemTrayAvailable():
        return True
    closed.append(True)
    return False


def run(launch: Launch) -> int:
    app = prepared()
    if not launch.window:
        try:
            ctx = launch.context(launch.opening.result())
        except NoPage as e:
            return launch.no_page(e)
        built = build(ctx, app)
        start(built, ctx)
        return int(built.app.exec())
    window = loading_window(launch)
    closed: list[bool] = []
    window.on_close = lambda: close_while_loading(closed)
    failed: list[NoPage] = []
    kept: list[Built] = []

    def arrived() -> None:
        try:
            ctx = launch.context(launch.opening.result())
        except NoPage as e:
            failed.append(e)
            window.hide()
            QApplication.exit(1)  # ends the loop without asking a window to close
            return
        kept.append(build(ctx, app, window))
        if closed:
            log.info("the window was closed before the page came and this desktop has no tray: the app ends")
            kept[0].actions.run(QUIT)
            return
        start(kept[0], ctx)

    opened = Opened()
    opened.arrived.connect(arrived, Qt.ConnectionType.QueuedConnection)
    launch.opening.when_done(opened.arrived.emit)
    code = int(app.exec())
    window.dispose()
    return launch.no_page(failed[0]) if failed else code
