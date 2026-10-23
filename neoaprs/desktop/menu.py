"""The tray menu, as data, and what its items do. Both shells draw `items()` with their toolkit and call `run(key)` when one is chosen, so what the menu says and does is the same on every system and is
tested with no tray: the toolkits are fakes of `Frame` there.

    Open NeoAPRS          shows the window (with no web engine to show one: the page in the browser)
    Open in browser      the page in the system's browser (left out when that is what Open does)
    Start at sign-in     a checkbox: the app, in the tray, starts when the user signs in (left out where the system has none)
    Stop and quit        stops the daemon if the app started it, and ends the app; for a daemon that was already running (a service) it is "Quit (NeoAPRS keeps running as a service)" and only ends the app
"""
import logging
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .autostart import AutoStart, AutoStartError
from .session import Daemon, Session, stop_owned

log = logging.getLogger("neoaprs.desktop")

OPEN, BROWSER, AUTOSTART, QUIT = "open", "browser", "autostart", "quit"
KEEPS_RUNNING = "NeoAPRS keeps running as a service"


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    checked: bool | None = None                     # None: not a checkbox
    separator: bool = False


class Frame(Protocol):
    """What the app's logic needs of a toolkit (qtshell.py, winshell.py; a fake in the tests). every method may be called from any thread (a second app's `show` arrives in a thread of its own, Quit runs in one)."""
    has_window: bool

    def show_window(self) -> None: ...
    def quit(self) -> None: ...
    def refresh(self) -> None: ...
    def tell(self, text: str) -> None: ...


class AppActions:
    def __init__(self, session: Session, frame: Frame, autostart: AutoStart | None, daemon: Daemon | None = None, open_browser: Callable[[str], object] | None = None) -> None:
        self.session = session
        self.frame = frame
        self.autostart = autostart
        self.daemon = daemon or Daemon()
        self.open_browser = open_browser or (lambda url: webbrowser.open(url))          # (looked up when it is used)
        self.quitting = False
        self.thread: threading.Thread | None = None

    def items(self) -> list[Item]:
        owned = self.session.owned
        items = [Item(OPEN, "Open NeoAPRS")]
        if self.frame.has_window:
            items.append(Item(BROWSER, "Open in browser"))
        if self.autostart is not None:
            items.append(Item(AUTOSTART, "Start at sign-in", checked=self.autostart.enabled()))
        items.append(Item("-", "-", separator=True))
        items.append(Item(QUIT, "Stop and quit" if owned else f"Quit ({KEEPS_RUNNING})"))
        return items

    def run(self, key: str) -> None:
        """What the item `key` does. Quit is done in a thread of its own: the daemon takes a moment to end, and the toolkit's loop must go on drawing meanwhile."""
        if key == OPEN:
            self.show()
        elif key == BROWSER:
            self.open_browser(self.session.url)
        elif key == AUTOSTART:
            self.toggle_autostart()
        elif key == QUIT:
            self.thread = threading.Thread(target=self.quit_now, name="neoaprs-app-quit", daemon=True)
            self.thread.start()
        else:
            log.warning("no such menu item: %s", key)

    def show(self) -> None:
        """Brings the window up, or, with no window to bring, the page in the browser."""
        if self.frame.has_window:
            self.frame.show_window()
        else:
            self.open_browser(self.session.url)

    def toggle_autostart(self) -> None:
        if self.autostart is None:
            return
        try:
            self.autostart.disable() if self.autostart.enabled() else self.autostart.enable()
        except AutoStartError as e:
            log.warning("start at sign-in: %s", e)
            self.frame.tell(str(e))
        self.frame.refresh()

    def quit_now(self) -> None:
        """Stops the daemon if it is the app's own, then ends the app. Said once, whoever asks first: the menu, the second app's `--quit`, the end of the daemon."""
        if self.quitting:
            return
        self.quitting = True
        if not self.session.owned:
            log.info("quitting; %s", KEEPS_RUNNING)
        elif not stop_owned(self.session, self.daemon):
            self.frame.tell("The NeoAPRS daemon did not stop; see neoaprs.log")
        self.frame.quit()

    def daemon_gone(self) -> None:
        """The daemon the app owns ended by itself: nothing is left to stop, the app ends."""
        if not self.quitting:
            self.quitting = True
            self.frame.quit()
