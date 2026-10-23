"""The Qt shell with the real toolkit, headless (QT_QPA_PLATFORM=offscreen; PySide6-WebEngine from the extra `app`, the whole module skipped without it): the window is made with its title and size and shows a page
served on the loopback, remembers its size, hides when it is closed, keeps what the page stores in the data folder, sends the links to other sites (and the new windows `target="_blank"` asks for) to the browser
and never shows them, and the tray menu is made from the data of the actions. There is no tray in the offscreen platform, so the tray itself is what only a real desktop can say."""
import http.server
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")         # (the sandbox of Chromium needs what a container or a test runner may not give; this is a test of ours)
pytest.importorskip("PySide6.QtWebEngineWidgets")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from neoaprs.desktop import appstate, qtshell  # noqa: E402
from neoaprs.desktop.menu import AUTOSTART, QUIT  # noqa: E402
from neoaprs.desktop.session import Session  # noqa: E402
from neoaprs.desktop.shell import ShellContext  # noqa: E402
from neoaprs.desktop.single import SingleApp  # noqa: E402
from tests.test_desktop_logic import FakeAutoStart, FakeDaemon  # noqa: E402

HTML = b"""<!doctype html><html><head><title>fake page</title></head><body>
<a id="ext" href="https://www.qrz.com/db/OH2GBA" target="_blank">QRZ</a>
<a id="plain" href="https://www.openstreetmap.org/copyright">OSM</a>
<a id="same" href="/elsewhere">same site</a>
<script>localStorage.setItem("panel", "320");</script></body></html>"""


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return None


@pytest.fixture(scope="module")
def page_url() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return qtshell.application()


def spin(condition: Any, seconds: float = 20.0) -> None:
    """Runs Qt's event loop until the condition holds."""
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(20)
    poll.timeout.connect(lambda: loop.quit() if condition() else None)
    poll.start()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()
    poll.stop()
    assert condition(), "the condition did not come true"


def reload(window: Any) -> None:
    loaded: list[bool] = []
    window.view.loadFinished.connect(loaded.append)
    window.load()
    spin(lambda: loaded)
    window.view.loadFinished.disconnect(loaded.append)


def evaluate(window: Any, script: str) -> Any:
    got: list[Any] = []
    window.page.runJavaScript(script, 0, got.append)
    spin(lambda: got)
    return got[0]


class Rig:
    def __init__(self, data: Path, url: str, app: QApplication) -> None:
        self.data = data
        self.auto = FakeAutoStart()
        self.ctx = ShellContext(Session(data, url, owned=False), False, True, self.auto, SingleApp(data), FakeDaemon(up=True))
        self.built = qtshell.build(self.ctx, app)
        window = self.built.window
        assert window is not None
        self.window = window


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory, page_url: str, qapp: QApplication) -> Iterator[Rig]:
    data = tmp_path_factory.mktemp("appdata")
    rig = Rig(data, page_url, qapp)
    loaded: list[bool] = []
    rig.window.view.loadFinished.connect(loaded.append)
    rig.window.load()
    spin(lambda: loaded)
    yield rig
    rig.window.on_close = lambda: False
    rig.window.close()
    rig.window.dispose()
    rig.window.deleteLater()
    qapp.processEvents()


def test_the_window_has_its_title_the_default_size_and_shows_the_page(rig: Rig) -> None:
    assert rig.window.windowTitle() == "NeoAPRS" and (rig.window.width(), rig.window.height()) == appstate.DEFAULT_SIZE
    assert evaluate(rig.window, "document.title") == "fake page"
    image = rig.window.view.grab().toImage()
    assert image.width() > 0 and len({image.pixel(x, y) for x in range(0, image.width(), 40) for y in range(0, image.height(), 40)}) > 1, "something is drawn"


def test_the_page_keeps_what_it_stores_in_a_folder_of_the_data_folder(rig: Rig) -> None:
    assert evaluate(rig.window, "localStorage.getItem('panel')") == "320"
    profile = rig.window.profile
    assert profile.persistentStoragePath() == str(rig.data / "webview") and not profile.isOffTheRecord()
    assert (rig.data / "webview").is_dir()


def test_a_navigation_to_the_page_stays_and_one_to_another_site_goes_to_the_browser(rig: Rig, page_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("neoaprs.desktop.links.webbrowser.open", lambda url: opened.append(url) or True)
    page, link = rig.window.page, QWebEnginePage.NavigationType.NavigationTypeLinkClicked
    assert page.acceptNavigationRequest(QUrl(page_url + "elsewhere"), link, True) is True
    assert page.acceptNavigationRequest(QUrl("https://www.openstreetmap.org/copyright"), link, True) is False
    assert page.acceptNavigationRequest(QUrl("file:///etc/passwd"), link, True) is False
    assert page.acceptNavigationRequest(QUrl("javascript:alert(1)"), link, True) is False
    assert opened == ["https://www.openstreetmap.org/copyright"]


def test_a_link_with_a_target_blank_opens_the_browser_and_no_window(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("neoaprs.desktop.links.webbrowser.open", lambda url: opened.append(url) or True)
    new_page = rig.window.page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab)
    assert new_page.acceptNavigationRequest(QUrl("https://www.qrz.com/db/OH2GBA"), QWebEnginePage.NavigationType.NavigationTypeTyped, True) is False
    assert opened == ["https://www.qrz.com/db/OH2GBA"]
    assert new_page.acceptNavigationRequest(QUrl(rig.window.url + "x"), QWebEnginePage.NavigationType.NavigationTypeTyped, True) is False, "our own page in a new window is the window we have"
    assert rig.window.page.url().toString().startswith(rig.window.url)


def test_a_click_on_the_links_of_the_page_reaches_the_browser_and_the_window_stays_where_it_is(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("neoaprs.desktop.links.webbrowser.open", lambda url: opened.append(url) or True)
    reload(rig.window)
    before = rig.window.page.url().toString()
    assert evaluate(rig.window, "document.getElementById('plain').click(); true") is True
    spin(lambda: opened)
    assert opened == ["https://www.openstreetmap.org/copyright"] and rig.window.page.url().toString() == before


def test_closing_hides_the_window_and_remembers_its_size(rig: Rig) -> None:
    rig.window.resize(1000, 700)
    rig.window.show()
    rig.window.on_close = lambda: True
    assert rig.window.close() is False and not rig.window.isVisible(), "the close was refused and the window is hidden"
    assert appstate.load_size(rig.data) == (1000, 700)


def test_closing_with_no_tray_to_bring_it_back_from_quits_the_app(rig: Rig) -> None:
    class NoTray:
        def isVisible(self) -> bool:
            return False

    class Tray(NoTray):
        def isVisible(self) -> bool:
            return True

    quits: list[str] = []
    rig.built.actions.run = quits.append                                   # type: ignore[method-assign]
    assert qtshell.close_hides(Tray(), rig.built.actions) is True and quits == []      # type: ignore[arg-type]
    assert qtshell.close_hides(NoTray(), rig.built.actions) is False and quits == [QUIT]       # type: ignore[arg-type]


def test_the_window_is_raised_by_another_thread(rig: Rig) -> None:
    rig.window.hide()
    thread = threading.Thread(target=rig.built.frame.show_window)
    thread.start()
    spin(lambda: rig.window.isVisible())
    thread.join()
    rig.window.hide()


def test_the_tray_menu_is_made_from_the_actions_and_its_items_run_them(rig: Rig) -> None:
    ran: list[str] = []
    rig.built.actions.run = ran.append                                     # type: ignore[method-assign]
    qtshell.fill_menu(rig.built)
    assert [a.text() for a in rig.built.entries] == ["Open NeoAPRS", "Open in browser", "Start at sign-in", "Quit (NeoAPRS keeps running as a service)"]
    box = rig.built.entries[2]
    assert box.isCheckable() and not box.isChecked() and not rig.built.entries[0].isCheckable()
    rig.auto.on = True
    qtshell.fill_menu(rig.built)
    assert rig.built.entries[2].isChecked(), "the menu is made again when it is shown: the box is what the system says now"
    rig.built.entries[2].trigger()
    rig.built.entries[3].trigger()
    assert ran == [AUTOSTART, QUIT]


def test_without_the_web_engine_window_there_is_a_tray_and_no_window(tmp_path: Path, qapp: QApplication) -> None:
    ctx = ShellContext(Session(tmp_path, "http://127.0.0.1:7303/", owned=False), False, False, None, SingleApp(tmp_path), FakeDaemon(up=True))
    built = qtshell.build(ctx, qapp)
    assert built.window is None and not built.frame.has_window and built.tray is not None
    qtshell.fill_menu(built)
    assert [a.text() for a in built.entries] == ["Open NeoAPRS", "Quit (NeoAPRS keeps running as a service)"]
