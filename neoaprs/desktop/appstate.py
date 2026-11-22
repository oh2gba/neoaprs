"""What the app keeps in the data folder, beside the database.

The window geometry, the app log and the web engine's storage folders. A file that cannot be
read gives the default, never an error: the window must open."""

import json
import logging
import logging.handlers
from dataclasses import dataclass
from pathlib import Path

from neoaprs.cli.logfile import APP_LOG_NAME

STATE_NAME = "neoaprs-app.json"
LOG_NAME = APP_LOG_NAME
PROFILE_NAME = "webview"
WEBKIT_NAME = "webkit"
DEFAULT_SIZE = (1280, 800)
MIN_SIZE = (480, 320)
MAX_SIZE = (16000, 16000)
# A window whose title bar shows on a screen at this point (from the frame's corner) can be grabbed.
TITLE_POINT = (64, 16)
# Windows puts a minimised window at -32000.
MAX_PLACE = 30_000


@dataclass(frozen=True)
class WindowState:
    """The window as it was left: size and place when not maximized, in logical pixels.

    On Windows `normal` is the rcNormalPosition rectangle and takes precedence; Qt has None."""

    width: int
    height: int
    x: int | None = None
    y: int | None = None
    maximized: bool = False
    normal: tuple[int, int, int, int] | None = None


DEFAULT_WINDOW = WindowState(*DEFAULT_SIZE)


def profile_dir(data: Path) -> Path:
    """Return the web engine's storage folder, creating it."""
    folder = data / PROFILE_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def webkit_dir(data: Path) -> Path:
    """Return WebKitGTK's storage folder, creating it."""
    folder = data / WEBKIT_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def clamp(width: object, height: object) -> tuple[int, int]:
    if (
        isinstance(width, int)
        and isinstance(height, int)
        and not isinstance(width, bool)
        and not isinstance(height, bool)
    ):
        if MIN_SIZE[0] <= width <= MAX_SIZE[0] and MIN_SIZE[1] <= height <= MAX_SIZE[1]:
            return width, height
    return DEFAULT_SIZE


def place(x: object, y: object) -> tuple[int | None, int | None]:
    """Return the place if both are sane integers (negative is valid), else Nones."""
    if (
        isinstance(x, int)
        and isinstance(y, int)
        and not isinstance(x, bool)
        and not isinstance(y, bool)
        and abs(x) <= MAX_PLACE
        and abs(y) <= MAX_PLACE
    ):
        return x, y
    return None, None


def rect(value: object) -> tuple[int, int, int, int] | None:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(isinstance(v, int) and not isinstance(v, bool) and abs(v) <= MAX_PLACE for v in value)
    ):
        return None
    left, top, right, bottom = value
    if clamp(right - left, bottom - top) != (right - left, bottom - top):
        return None
    return left, top, right, bottom


def load_window(data: Path) -> WindowState:
    try:
        saved = json.loads((data / STATE_NAME).read_text(encoding="utf-8"))
        width, height = clamp(saved["width"], saved["height"])
        x, y = place(saved.get("x"), saved.get("y"))
        return WindowState(width, height, x, y, saved.get("maximized") is True, rect(saved.get("normal")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return DEFAULT_WINDOW


def save_window(data: Path, state: WindowState) -> None:
    """Save the window state; a failed write is only logged. A nonsense size is not saved."""
    if clamp(state.width, state.height) != (state.width, state.height):
        return
    x, y = place(state.x, state.y)
    kept: dict[str, object] = {"width": state.width, "height": state.height, "maximized": state.maximized}
    if x is not None and y is not None:
        kept["x"], kept["y"] = x, y
    normal = rect(list(state.normal)) if state.normal is not None else None
    if normal is not None:
        kept["normal"] = list(normal)
    try:
        (data / STATE_NAME).write_text(json.dumps(kept) + "\n", encoding="utf-8")
    except OSError:
        logging.getLogger("neoaprs.desktop").debug("the window's size and place could not be saved", exc_info=True)


def setup_logging(data: Path, debug: bool = False) -> None:
    """Log to a rotating file of its own; Windows could not share the daemon's."""
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.handlers.RotatingFileHandler(data / LOG_NAME, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(fmt)
    root.addHandler(handler)
