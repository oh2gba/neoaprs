"""The window of the Qt shell: a QWebEngineView on a profile that keeps what the page stores in the data folder (so the page's panel width, map view and read messages survive a restart), a page that sends every
address that is not the daemon's page to the system's browser (the new window a `target="_blank"` asks for included), and a close button that hides the window instead of ending the app. This is the module that
needs the web engine (PySide6-WebEngine); the tray (qtshell.py) needs only QtWidgets."""
import logging
from collections.abc import Callable
from pathlib import Path

from shiboken6 import delete
from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QIcon, QResizeEvent
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineProfileBuilder
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from . import appstate
from .links import open_external, route

log = logging.getLogger("neoaprs.desktop")

SAVE_SIZE_MS = 500                       # a resize is remembered when it has stopped for this long


def make_profile(data: Path, parent: QObject | None = None) -> QWebEngineProfile:
    """The web engine's profile with its storage in the data folder, made with the builder, which touches no default folder of the system: the cookies and the local storage are kept in `webview/`, the cache beside them."""
    folder = appstate.profile_dir(data)
    builder = QWebEngineProfileBuilder()
    builder.setPersistentStoragePath(str(folder))
    builder.setCachePath(str(folder / "cache"))
    builder.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
    return builder.createProfile("neoaprs", parent)


class AppPage(QWebEnginePage):
    """The page of the window: it follows the daemon's own address and hands every other one to the browser. The page the engine makes for a new window (a link with `target="_blank"`) is an `AppPage` too, which
    never shows: the first thing it is asked to load is routed and the page is dropped."""

    def __init__(self, profile: QWebEngineProfile, page_url: str, parent: QObject | None = None, opener_of: "AppPage | None" = None) -> None:
        super().__init__(profile, parent)
        self.page_url = page_url
        self._main = opener_of

    def acceptNavigationRequest(self, url: QUrl | str, type: QWebEnginePage.NavigationType, isMainFrame: bool) -> bool:  # noqa: A002  (Qt's names)
        address = url.toString() if isinstance(url, QUrl) else str(url)
        where = route(address, self.page_url)
        if where == "window":
            if self._main is not None:
                self._main.setUrl(QUrl(address))                   # a new window for our own page: it is the window we have
                return False
            return True
        if where == "browser" and not open_external(address, self.page_url):
            log.warning("no browser could be started for %s", address)
        elif where == "block":
            log.info("not opened: %s", address)
        return False

    def createWindow(self, type: QWebEnginePage.WebWindowType) -> QWebEnginePage:  # noqa: A002
        return AppPage(self.profile(), self.page_url, self, opener_of=self._main or self)


class AppWindow(QMainWindow):
    """Title "NeoAPRS", the page, the size it had last time. `on_close` is asked when the close button is used: it says whether the window should be hidden (True: NeoAPRS goes on in the tray) or the app ends."""

    def __init__(self, data: Path, url: str, icon: QIcon, on_close: Callable[[], bool]) -> None:
        super().__init__()
        self.data = data
        self.url = url
        self.on_close = on_close
        self.setWindowTitle("NeoAPRS")
        self.setWindowIcon(icon)
        self.resize(*appstate.load_size(data))
        self.profile = make_profile(data, self)
        self.page = AppPage(self.profile, url, self)
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self._saver = QTimer(self)
        self._saver.setSingleShot(True)
        self._saver.setInterval(SAVE_SIZE_MS)
        self._saver.timeout.connect(self.remember_size)

    def load(self) -> None:
        self.view.setUrl(QUrl(self.url))

    def dispose(self) -> None:
        """Takes the page down before the profile it is made on, which the engine insists on (the other order is a crash at exit); the window is not used after this. (The stub wants a page for `setPage`; None lets go of it.)"""
        self.view.setPage(None)  # type: ignore[arg-type]
        delete(self.page)
        delete(self.profile)

    def raise_up(self) -> None:
        """Shows the window and brings it to the front, out of the minimised state if it was there."""
        self.setWindowState(self.windowState() & ~self.windowState().WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def remember_size(self) -> None:
        if not self.isMaximized() and not self.isFullScreen() and self.isVisible():
            appstate.save_size(self.data, self.width(), self.height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._saver.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.remember_size()
        if self.on_close():
            event.ignore()
            self.hide()
        else:
            event.accept()
