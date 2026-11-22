"""The tray menu as data, and what its items do.

Both shells draw `items()` with their toolkit and call `run(key)` when one is chosen, so the menu
is the same everywhere and testable without a tray.
"""

import logging
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from neoaprs.cli.supportmake import Made, make_for_the_user

from .autostart import AutoStart, AutoStartError
from .session import Daemon, Session, stop_owned

log = logging.getLogger("neoaprs.desktop")

OPEN, BROWSER, AUTOSTART, SUPPORT, QUIT = "open", "browser", "autostart", "support", "quit"
KEEPS_RUNNING = "NeoAPRS keeps running as a service"
OPEN_LABEL = "Open NeoAPRS"


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    checked: bool | None = None  # None: not a checkbox
    separator: bool = False


class Frame(Protocol):
    """What the app's logic needs of a toolkit (qtshell.py, webshell.py; a fake in the tests).

    Every method may be called from any thread."""

    has_window: bool

    def show_window(self) -> None: ...
    def quit(self) -> None: ...
    def refresh(self) -> None: ...
    def tell(self, text: str) -> None: ...
    # The daemon's page is at `url` now; a toolkit with no window does nothing.
    def load(self, url: str) -> None: ...


class AppActions:
    def __init__(
        self,
        session: Session,
        frame: Frame,
        autostart: AutoStart | None,
        daemon: Daemon | None = None,
        open_browser: Callable[[str], object] | None = None,
        support: Callable[[Path], Made] = make_for_the_user,
    ) -> None:
        self.session = session
        self.frame = frame
        self.autostart = autostart
        self.daemon = daemon or Daemon()
        self.open_browser = open_browser or (lambda url: webbrowser.open(url))
        self.support = support
        self.quitting = False
        # The app ends to restart as the new version (renew.py); the daemon is left running.
        self.renewing = False
        self.thread: threading.Thread | None = None
        self.support_thread: threading.Thread | None = None

    def items(self) -> list[Item]:
        owned = self.session.owned
        items = [Item(OPEN, OPEN_LABEL)]
        if self.frame.has_window and self.daemon.network(self.session.data):
            items.append(Item(BROWSER, "Open in browser"))
        if self.autostart is not None:
            items.append(Item(AUTOSTART, "Start at sign-in", checked=self.autostart.enabled()))
        items.append(Item(SUPPORT, "Collect support logs"))
        items.append(Item("-", "-", separator=True))
        items.append(Item(QUIT, "Stop and quit" if owned else f"Quit ({KEEPS_RUNNING})"))
        return items

    def run(self, key: str) -> None:
        """Run the item `key`. Quit runs in a thread so the toolkit loop keeps drawing."""
        if key == OPEN:
            self.show()
        elif key == BROWSER:
            self.open_browser(self.session.url)
        elif key == AUTOSTART:
            self.toggle_autostart()
        elif key == SUPPORT:
            self.support_thread = threading.Thread(target=self.collect_support, name="neoaprs-app-support", daemon=True)
            self.support_thread.start()
        elif key == QUIT:
            self.thread = threading.Thread(target=self.quit_now, name="neoaprs-app-quit", daemon=True)
            self.thread.start()
        else:
            log.warning("no such menu item: %s", key)

    def show(self) -> None:
        """Show the window, or the page in the browser when there is no window."""
        if self.frame.has_window:
            self.frame.show_window()
        else:
            self.open_browser(self.session.url)

    def collect_support(self) -> None:
        """Make the support bundle, show it in the file manager and tell the user the result."""
        try:
            made = self.support(self.session.data)
        except Exception:
            log.exception("the support bundle could not be made")
            self.frame.tell("The support file could not be made; see neoaprs-app.log")
            return
        self.frame.tell(f"Support file saved: {made.path}")

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
        """Stop the daemon if the app owns it, then end the app; runs once whoever asks first."""
        if self.quitting:
            return
        self.quitting = True
        try:
            if not self.session.owned:
                log.info("quitting; %s", KEEPS_RUNNING)
            elif not stop_owned(self.session, self.daemon):
                self.frame.tell("The NeoAPRS daemon did not stop; see neoaprs.log")
        except Exception:
            log.exception("the daemon could not be stopped")
        finally:
            self.frame.quit()

    def network_moved(self) -> None:
        """The page's network exposure changed: redraw the menu."""
        self.frame.refresh()

    def page_moved(self, url: str) -> None:
        """The daemon serves its page at another address: load it and use it for the browser."""
        self.session = replace(self.session, url=url)
        if not self.quitting:
            self.frame.load(url)

    def renew(self) -> None:
        """End the app as Quit would but leave the daemon running, for cmd.py to restart the app."""
        if self.quitting:
            return
        self.quitting = True
        self.renewing = True
        self.frame.quit()

    def daemon_gone(self) -> None:
        """The owned daemon ended by itself: end the app."""
        if not self.quitting:
            self.quitting = True
            self.frame.quit()
