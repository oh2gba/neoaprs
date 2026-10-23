"""The shell of Linux and macOS: Qt for both the window and the tray icon, so there is one event loop and nothing to marry. QSystemTrayIcon is the tray (the StatusNotifier of KDE and of GNOME with its extension; the
menu bar on macOS), QWebEngineView in qtwindow.py the window. Without the web engine (no PySide6-WebEngine installed) it is the tray alone and the page goes to the browser. Closing the window hides it;
with no tray to bring it back from (a desktop that has none), closing it quits, as the menu's Quit would. Other threads (a second app's `show`, the end of the daemon, the quit that runs while the daemon
stops) reach the toolkit through the signals of `QtFrame`, which Qt queues to the main thread.
`build(ctx)` makes everything and `run(ctx)` runs it; the headless test and the screenshot use `build`."""
import logging
import webbrowser
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .menu import AppActions
from .shell import ShellContext

if TYPE_CHECKING:
    from .qtwindow import AppWindow

log = logging.getLogger("neoaprs.desktop")

TRAY_WAIT_SEC = 60                              # a desktop that starts the app at sign-in may not have its panel up yet: the tray is looked for this long before the window is shown for want of one
TRAY_POLL_MS = 2000


def icon_path() -> Path:
    return Path(str(resources.files("neoaprs.desktop").joinpath("icon.png")))


class QtFrame(QObject):
    """The `Frame` of the Qt shell. The signals are how another thread asks the main one: Qt delivers a signal to an object of the main thread there, in order."""
    show_requested = Signal()
    quit_requested = Signal()
    tell_requested = Signal(str)

    def __init__(self, with_window: bool) -> None:
        super().__init__()
        self.has_window = with_window
        self.window: AppWindow | None = None
        self.tray: QSystemTrayIcon | None = None
        self.show_requested.connect(self._show)
        self.quit_requested.connect(self._quit)
        self.tell_requested.connect(self._tell)

    def show_window(self) -> None:
        self.show_requested.emit()

    def quit(self) -> None:
        self.quit_requested.emit()

    def refresh(self) -> None:
        """Nothing to do: the tray menu is made again each time it is about to show."""

    def tell(self, text: str) -> None:
        self.tell_requested.emit(text)

    @Slot()
    def _show(self) -> None:
        if self.window is not None:
            self.window.raise_up()

    @Slot()
    def _quit(self) -> None:
        if self.window is not None:
            self.window.remember_size()
        QApplication.quit()

    @Slot(str)
    def _tell(self, text: str) -> None:
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage("NeoAPRS", text, QSystemTrayIcon.MessageIcon.Information, 8000)
        else:
            log.warning("%s", text)


class Built:
    """Everything `build` makes, kept alive for as long as the app runs (Qt drops what Python does not hold)."""

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
    """The tray menu from the data of `actions.items()`; made again each time it is about to show, so that the checkbox is what the system says now."""
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
    tray.activated.connect(lambda reason: built.actions.show() if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    built.frame.tray = tray
    fill_menu(built)
    return tray


def await_tray(built: Built, tray: QSystemTrayIcon) -> None:
    """The tray is shown at once when the desktop has one. When it has none yet (the panel starts after the app at sign-in) it is looked for for a minute; if it never comes the window, which had nothing to be brought back from, is shown."""
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
    """The QApplication that runs, or a new one."""
    existing = QApplication.instance()
    if existing is None:
        return QApplication([])
    assert isinstance(existing, QApplication)
    return existing


def build(ctx: ShellContext, app: QApplication | None = None) -> Built:
    """The window, the tray and their wiring, nothing shown yet and nothing started: the app is `app` or the one that is running or a new one."""
    app = app or application()
    app.setApplicationName("NeoAPRS")
    app.setQuitOnLastWindowClosed(False)
    icon = QIcon(str(icon_path()))
    frame = QtFrame(ctx.window)
    actions = ctx.actions_for(frame)
    built = Built(app, frame, actions)
    tray = make_tray(built, icon)
    if ctx.window:
        from .qtwindow import AppWindow
        frame.window = AppWindow(ctx.session.data, ctx.session.url, icon, lambda: close_hides(tray, actions))
    return built


def close_hides(tray: QSystemTrayIcon, actions: AppActions) -> bool:
    """The close button: hide the window while there is a tray icon to bring it back from; else it is the end of the app (the daemon too, if the app started it: nothing would be left to reach it)."""
    if tray.isVisible():
        return True
    actions.run("quit")
    return False


def run(ctx: ShellContext) -> int:
    built = build(ctx)
    window = built.window
    if built.tray is None or (window is None and not QSystemTrayIcon.isSystemTrayAvailable()):
        raise RuntimeError("this desktop has no system tray and the web engine is not installed: there is nothing to show")
    await_tray(built, built.tray)
    ctx.ready(built.actions)
    if window is not None:
        window.load()
        if not ctx.hidden:
            window.raise_up()
    elif not ctx.hidden:
        webbrowser.open(ctx.session.url)
    log.info("the Qt shell runs (%s)", "window and tray" if window is not None else "tray only")
    code = int(built.app.exec())
    if window is not None:
        window.dispose()
    return code
