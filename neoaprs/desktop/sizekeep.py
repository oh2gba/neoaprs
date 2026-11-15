"""The web window's size, place and whether it is maximized on Linux and macOS, kept from pywebview's events and saved in the app's file (appstate.py) once they have stopped for half a second, as the Qt window
does (Windows keeps its own placement, which winplace.py reads and gives back). The size and place are the ones the window goes back to when it is not maximized: what a maximize does to them is not kept,
and a minimise and the restore that ends it change nothing. The place is the frame's top left corner, on Linux asked of GTK's window at each move (webdesk.frame_moved). Wayland tells no app its place,
so there the place is not kept (`keep_place`). Every event may come from any thread; this file imports no toolkit."""
import threading
from collections.abc import Callable
from pathlib import Path

from . import appstate

SAVE_AFTER_SEC = 0.5                     # a resize or a move is saved when it has stopped for this long


class SizeKeeper:
    def __init__(self, data: Path, state: appstate.WindowState, keep_place: bool = True) -> None:
        self.data = data
        self.keep_place = keep_place
        self.size = (state.width, state.height)
        self.place: tuple[int | None, int | None] = (state.x, state.y) if keep_place else (None, None)
        self.maximized = state.maximized
        self.minimized = False
        self._settled = (self.size, self.place)            # what the window had before the latest burst of events: a maximize's own resize and move are undone to it
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._stopped = False

    def told(self, name: str) -> Callable[..., None]:
        """The handler of pywebview's event `name` (resized and moved carry two numbers; maximized, minimized and restored none)."""
        def handler(*args: object) -> None:
            self.event(name, *args)
        return handler

    def event(self, name: str, *args: object) -> None:
        with self._lock:
            normal = not self.maximized and not self.minimized
            pair = _pair(args)
            if name == "resized" and normal and pair is not None:
                self.size = pair
            elif name == "moved" and normal and self.keep_place and pair is not None:
                self.place = pair
            elif name == "maximized":
                self.maximized = True
                self.size, self.place = self._settled
            elif name == "minimized":
                self.minimized = True
            elif name == "restored" and self.minimized:
                self.minimized = False
            elif name == "restored":
                self.maximized = False
            else:
                return
            self._restart()

    def _restart(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        if self._stopped:
            return
        self._timer = threading.Timer(SAVE_AFTER_SEC, self.settle)
        self._timer.daemon = True
        self._timer.start()

    def settle(self) -> None:
        """The events have stopped: what the window has now is what a later maximize goes back to, and it is saved."""
        with self._lock:
            if not self.maximized and not self.minimized:
                self._settled = (self.size, self.place)
        self.save()

    def save(self) -> None:
        with self._lock:
            (width, height), (x, y), maximized = self.size, self.place, self.maximized
        appstate.save_window(self.data, appstate.WindowState(width, height, x, y, maximized))

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()


def _pair(args: tuple[object, ...]) -> tuple[int, int] | None:
    """The two numbers an event carries, or None (an event of another kind, or a payload pywebview may change)."""
    if len(args) < 2:
        return None
    first, second = args[0], args[1]
    if isinstance(first, bool) or isinstance(second, bool) or not isinstance(first, int | float) or not isinstance(second, int | float):
        return None
    return int(first), int(second)
