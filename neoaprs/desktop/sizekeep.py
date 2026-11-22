"""Keep the web window's size, place and maximized state on Linux and macOS.

Tracked from pywebview's events and saved shortly after they stop. The saved size and place are
those of the unmaximized window; Wayland gives no place (`keep_place`). Events arrive on any thread."""

import threading
from collections.abc import Callable
from pathlib import Path

from . import appstate

# Quiet time before a resize or move is saved.
SAVE_AFTER_SEC = 0.5


class SizeKeeper:
    def __init__(self, data: Path, state: appstate.WindowState, keep_place: bool = True) -> None:
        self.data = data
        self.keep_place = keep_place
        self.size = (state.width, state.height)
        self.place: tuple[int | None, int | None] = (state.x, state.y) if keep_place else (None, None)
        self.maximized = state.maximized
        self.minimized = False
        # Geometry before the latest burst of events; a maximize's own resize and move revert to it.
        self._settled = (self.size, self.place)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._stopped = False

    def told(self, name: str) -> Callable[..., None]:
        """Return the handler for pywebview's event `name` (resized and moved carry two numbers)."""

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
        """Record the current geometry as the one a later maximize reverts to, and save it."""
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
    """Return the two numbers an event carries, or None for any other payload."""
    if len(args) < 2:
        return None
    first, second = args[0], args[1]
    if (
        isinstance(first, bool)
        or isinstance(second, bool)
        or not isinstance(first, int | float)
        or not isinstance(second, int | float)
    ):
        return None
    return int(first), int(second)
