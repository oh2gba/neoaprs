"""The window of the Qt shell: a QWebEngineView with its own page and profile.

The profile keeps the page's storage in the data folder; other addresses go to the system
browser. This is the module that needs the web engine; the tray (qtshell.py) needs only QtWidgets."""
import logging
from collections.abc import Callable
from pathlib import Path

from shiboken6 import delete
from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QColor, QGuiApplication, QIcon, QMoveEvent, QResizeEvent
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineProfileBuilder
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from . import appstate, loading
from .links import open_external, route, window_url

log = logging.getLogger("neoaprs.desktop")

# A resize or move is saved once it has stopped for this long.
SAVE_SIZE_MS = 500


def make_profile(data: Path, parent: QObject | None = None) -> QWebEngineProfile:
    """Return a profile storing cookies and local storage under `webview/` in the data folder.

    The builder is used because it touches no default folder of the system.
    """
    folder = appstate.profile_dir(data)
    builder = QWebEngineProfileBuilder()
    builder.setPersistentStoragePath(str(folder))
    builder.setCachePath(str(folder / "cache"))
    builder.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
    return builder.createProfile("neoaprs", parent)


class AppPage(QWebEnginePage):
    """The window's page: follows the daemon's address and hands every other one to the browser.

    Until `page_url` is known it lets the loading page's `data:` address in, once."""

    def __init__(self, profile: QWebEngineProfile, page_url: str | None, parent: QObject | None = None, opener_of: "AppPage | None" = None) -> None:
        super().__init__(profile, parent)
        self.page_url = page_url
        self.loading = False
        self._main = opener_of

    def acceptNavigationRequest(self, url: QUrl | str, type: QWebEnginePage.NavigationType, isMainFrame: bool) -> bool:  # noqa: A002  (Qt's names)
        address = url.toString() if isinstance(url, QUrl) else str(url)
        if self.loading and isMainFrame and address.startswith("data:text/html"):
            self.loading = False
            return True
        where = route(address, self.page_url or "")
        if where == "window":
            if self._main is not None:
                # A new window for our own page: use the existing window.
                self._main.setUrl(QUrl(address))
                return False
            return True
        if where == "browser" and not open_external(address, self.page_url or ""):
            log.warning("no browser could be started for %s", address)
        elif where == "block":
            log.info("not opened: %s", address)
        return False

    def createWindow(self, type: QWebEnginePage.WebWindowType) -> QWebEnginePage:  # noqa: A002
        return AppPage(self.profile(), self.page_url, self, opener_of=self._main or self)


class AppWindow(QMainWindow):
    """The main window, restored to its saved size and place.

    `on_close` returns True to hide the window on close, False to end the app."""

    def __init__(self, data: Path, url: str | None, icon: QIcon, on_close: Callable[[], bool]) -> None:
        super().__init__()
        self.data = data
        self.url = url or ""
        self.on_close = on_close
        self.setWindowTitle("NeoAPRS")
        self.setWindowIcon(icon)
        state = appstate.load_window(data)
        self.resize(state.width, state.height)
        if state.x is not None and state.y is not None and QGuiApplication.screenAt(QPoint(state.x + appstate.TITLE_POINT[0], state.y + appstate.TITLE_POINT[1])) is not None:
            self.move(state.x, state.y)
        if state.maximized:
            self.setWindowState(Qt.WindowState.WindowMaximized)
        self.profile = make_profile(data, self)
        self.page = AppPage(self.profile, url, self)
        self.page.setBackgroundColor(QColor(loading.background(QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark)))
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self._saver = QTimer(self)
        self._saver.setSingleShot(True)
        self._saver.setInterval(SAVE_SIZE_MS)
        self._saver.timeout.connect(self.remember_geometry)

    def show_loading(self) -> None:
        self.page.loading = True
        self.page.setHtml(loading.HTML)

    def load(self, url: str | None = None) -> None:
        """Show the daemon's page (`url`, else the one the window was made with)."""
        if url is not None:
            self.url = self.page.page_url = url
        self.view.setUrl(QUrl(window_url(self.url)))

    def dispose(self) -> None:
        """Delete the page before its profile (the other order crashes at exit); unusable after."""
        self.view.setPage(None)  # type: ignore[arg-type]
        delete(self.page)
        delete(self.profile)

    def raise_up(self) -> None:
        """Show the window and bring it to the front, restoring it if minimised."""
        self.setWindowState(self.windowState() & ~self.windowState().WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def remember_geometry(self) -> None:
        """Save the normal size and place and the maximized state; a hidden window reports nonsense."""
        if self.isFullScreen() or not self.isVisible():
            return
        if self.isMaximized():
            # normalGeometry is the widget's; the frame's corner is up and left by the decorations.
            normal = self.normalGeometry()
            frame = self.geometry().topLeft() - self.frameGeometry().topLeft()
            state = appstate.WindowState(normal.width(), normal.height(), normal.x() - frame.x(), normal.y() - frame.y(), True)
        else:
            state = appstate.WindowState(self.width(), self.height(), self.pos().x(), self.pos().y(), False)
        appstate.save_window(self.data, state)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._saver.start()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._saver.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.remember_geometry()
        if self.on_close():
            event.ignore()
            self.hide()
        else:
            event.accept()
