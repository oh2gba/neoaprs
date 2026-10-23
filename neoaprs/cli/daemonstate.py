"""What a command can find out about a daemon without starting one or talking to its socket: whether one holds the lock of the data folder, where its page is (the daemon logs "web page at ..."
when it has bound the port, which is also the only place the port that was free is written), whether that page answers, and the end of its log."""
import re
import urllib.error
import urllib.request
from pathlib import Path

from neoaprs.instancelock import LOCK_NAME, AlreadyRunning, InstanceLock

LOG_NAME = "neoaprs.log"
SCAN_BYTES = 256 * 1024                  # the end of the log that is looked at for the page's address
PAGE_LINE = re.compile(r"web page at (http://\S+?/)(?:\s|$)")
START_LINE = " starting, data in "
PROBE_SEC = 2.0


def is_running(data_dir: Path) -> bool:
    """Whether a daemon holds the instance lock of the data folder (the lock is taken for a moment, and let go, to find out; a folder with no lock file has no daemon)."""
    if not (data_dir / LOCK_NAME).is_file():
        return False
    lock = InstanceLock(data_dir)
    try:
        lock.acquire()
    except AlreadyRunning:
        return True
    except OSError:
        return False
    lock.release()
    return False


def tail(path: Path, lines: int = 50) -> list[str]:
    """The last `lines` lines of a text file (the whole file when it is short); [] when it cannot be read."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - SCAN_BYTES))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:] if size <= SCAN_BYTES else text.splitlines()[1:][-lines:]       # (the first line of a cut is the end of one)


def page_url(data_dir: Path) -> str | None:
    """The page address the latest run of the daemon logged, or None (no log, or the latest run has no page: its ports were taken)."""
    found: str | None = None
    for line in tail(data_dir / LOG_NAME, 100_000):
        if START_LINE in line:
            found = None                                   # a new run: what an earlier one said is over
        match = PAGE_LINE.search(line)
        if match:
            found = match.group(1)
    return found


def page_answers(url: str) -> bool:
    """Whether something answers the page's address with a page."""
    try:
        with urllib.request.urlopen(url, timeout=PROBE_SEC) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def describe(data_dir: Path) -> tuple[bool, str]:
    """(whether a daemon runs on the data folder, a line that says how it looks: running with its page and whether the page answers, or not running)."""
    if not is_running(data_dir):
        return False, "no daemon is running on this data folder"
    url = page_url(data_dir)
    if url is None:
        return True, "a daemon is running; its log does not say where its page is (is the page's port taken?)"
    return True, f"a daemon is running; its page {url} " + ("answers" if page_answers(url) else "does not answer")
