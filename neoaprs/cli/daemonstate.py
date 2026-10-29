"""What a command can find out about a daemon without starting one or talking to its socket: whether one holds the lock of the data folder, where its page is (the file the daemon writes when it has bound
the port, and, for a daemon that did not write one, its log line "web page at ..."; neoaprs/cli/logfile.py), whether that page answers, and the end of its log."""
import urllib.error
import urllib.request
from pathlib import Path

from neoaprs.config import DEFAULTS
from neoaprs.dberror import SqlError
from neoaprs.instancelock import LOCK_NAME, is_held
from neoaprs.store import DB_NAME
from neoaprs.storesql import read_setting
from neoaprs.supportsql import open_readonly

from .logfile import LOG_NAME, PAGE_LINE, START_LINE, read_page

SCAN_BYTES = 256 * 1024                  # the end of the log that is looked at for the page's address
PROBE_SEC = 2.0
LOCAL_ONLY = urllib.request.build_opener(urllib.request.ProxyHandler({}))         # (the page is on this computer: a proxy of the environment has nothing to say about it)


def is_running(data_dir: Path) -> bool:
    """Whether a daemon holds the instance lock of the data folder."""
    return is_held(data_dir, LOCK_NAME)


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
    """The page address the daemon wrote into the data folder, or else the latest run's log line; None when there is neither (the latest run has no page: its ports were taken)."""
    written = read_page(data_dir)
    if written is not None:
        return written
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
        with LOCAL_ONLY.open(url, timeout=PROBE_SEC) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def page_address(data_dir: Path) -> str:
    """Where the page of a daemon on the data folder will be, by the web/port the folder's database stores (the default while it has none), as the daemon starts without a flag: the first free port after it
    is taken is the log's to say, and so is a port 0."""
    port = DEFAULTS.web_port
    try:
        conn = open_readonly(data_dir / DB_NAME)
        try:
            stored = read_setting(conn, "web/port")
        finally:
            conn.close()
        port = DEFAULTS.web_port if stored is None else int(stored)
    except (SqlError, OSError, ValueError):
        pass
    return f"http://127.0.0.1:{port}/" if port else "(a free port: the log says which)"


def describe(data_dir: Path) -> tuple[bool, str]:
    """(whether a daemon runs on the data folder, a line that says how it looks: running with its page and whether the page answers, or not running)."""
    if not is_running(data_dir):
        return False, "no daemon is running on this data folder"
    url = page_url(data_dir)
    if url is None:
        return True, "a daemon is running; its log does not say where its page is (is the page's port taken?)"
    return True, f"a daemon is running; its page {url} " + ("answers" if page_answers(url) else "does not answer")
