"""What the app keeps in the data folder, beside the database and not in it: the window's geometry (`neoaprs-app.json`: its size, its place and whether it is maximized, and on Windows the placement Windows itself keeps), the log of the app (`neoaprs-app.log`) and the folder
where the web engine keeps what the page stores (`webview/`: localStorage, so the page's panel width, map view and read messages survive a restart). A file that cannot be read is the default, never an error: the window must open."""
import json
import logging
import logging.handlers
from dataclasses import dataclass
from pathlib import Path

STATE_NAME = "neoaprs-app.json"
LOG_NAME = "neoaprs-app.log"
PROFILE_NAME = "webview"
DEFAULT_SIZE = (1280, 800)
MIN_SIZE = (480, 320)
MAX_SIZE = (16000, 16000)
MAX_PLACE = 30_000                              # a place further out than this is nonsense (Windows puts a minimised window at -32000; three 4K monitors side by side end short of this)


@dataclass(frozen=True)
class WindowState:
    """The window as it was left: the size and place it has when it is not maximized (the place is the top left corner of its frame, in the toolkit's logical pixels; None when it has never been told), and whether it
    is maximized, in which case the size and place are the ones it goes back to. On Windows `normal` is the rectangle Windows keeps for the window when it is not maximized (left, top, right, bottom of the
    WINDOWPLACEMENT's rcNormalPosition: in Windows' own pixels and workspace coordinates, which only SetWindowPlacement reads back), and then it is what counts; the Qt shell has None there."""
    width: int
    height: int
    x: int | None = None
    y: int | None = None
    maximized: bool = False
    normal: tuple[int, int, int, int] | None = None


DEFAULT_WINDOW = WindowState(*DEFAULT_SIZE)


def profile_dir(data: Path) -> Path:
    """The web engine's storage folder (made if it is not there)."""
    folder = data / PROFILE_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def clamp(width: object, height: object) -> tuple[int, int]:
    """A remembered size that is a number within sane limits, else the default (a hand-edited or damaged file, a monitor that is gone)."""
    if isinstance(width, int) and isinstance(height, int) and not isinstance(width, bool) and not isinstance(height, bool):
        if MIN_SIZE[0] <= width <= MAX_SIZE[0] and MIN_SIZE[1] <= height <= MAX_SIZE[1]:
            return width, height
    return DEFAULT_SIZE


def place(x: object, y: object) -> tuple[int | None, int | None]:
    """A remembered place that is two numbers within sane limits (a second monitor to the left is negative), else none."""
    if isinstance(x, int) and isinstance(y, int) and not isinstance(x, bool) and not isinstance(y, bool) and abs(x) <= MAX_PLACE and abs(y) <= MAX_PLACE:
        return x, y
    return None, None


def rect(value: object) -> tuple[int, int, int, int] | None:
    """A remembered Windows rectangle that is four numbers, its corners within sane limits and its size a sane one, else none (a file of an earlier version has none, and a hand-edited one may have anything)."""
    if not isinstance(value, list) or len(value) != 4 or not all(isinstance(v, int) and not isinstance(v, bool) and abs(v) <= MAX_PLACE for v in value):
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
    """Remembers the window (when its size is a real one: a hidden or minimised window reports nonsense; a place that is nonsense is left out); a folder that cannot be written is not worth a crash."""
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
    """The app's log, a rotating file of its own (the daemon's log is another process's file; on Windows two programs cannot rotate one)."""
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.handlers.RotatingFileHandler(data / LOG_NAME, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(fmt)
    root.addHandler(handler)
