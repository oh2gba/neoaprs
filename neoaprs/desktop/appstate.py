"""What the app keeps in the data folder, beside the database and not in it: the size of the window (`neoaprs-app.json`), the log of the app (`neoaprs-app.log`) and the folder where the web engine keeps
what the page stores (`webview/`: localStorage, so the page's panel width, map view and read messages survive a restart). A file that cannot be read is the default, never an error: the window must open."""
import json
import logging
import logging.handlers
from pathlib import Path

STATE_NAME = "neoaprs-app.json"
LOG_NAME = "neoaprs-app.log"
PROFILE_NAME = "webview"
DEFAULT_SIZE = (1280, 800)
MIN_SIZE = (480, 320)
MAX_SIZE = (16000, 16000)


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


def load_size(data: Path) -> tuple[int, int]:
    try:
        saved = json.loads((data / STATE_NAME).read_text(encoding="utf-8"))
        return clamp(saved["width"], saved["height"])
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_SIZE


def save_size(data: Path, width: int, height: int) -> None:
    """Remembers the size (when it is a real one: a hidden or minimised window reports nonsense); a folder that cannot be written is not worth a crash."""
    if clamp(width, height) != (width, height):
        return
    try:
        (data / STATE_NAME).write_text(json.dumps({"width": width, "height": height}) + "\n", encoding="utf-8")
    except OSError:
        logging.getLogger("neoaprs.desktop").debug("the window size could not be saved", exc_info=True)


def setup_logging(data: Path, debug: bool = False) -> None:
    """The app's log, a rotating file of its own (the daemon's log is another process's file; on Windows two programs cannot rotate one)."""
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.handlers.RotatingFileHandler(data / LOG_NAME, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(fmt)
    root.addHandler(handler)
