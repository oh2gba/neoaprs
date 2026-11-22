"""What a command can learn about a daemon without starting one or using its socket.

That is: whether one holds the data folder's lock, where its page is (the address file, else the
log line "web page at ..."), whether the page answers, and the end of its log."""
import http.client
import urllib.error
import urllib.request
from pathlib import Path

from neoaprs.config import DEFAULTS
from neoaprs.dberror import SqlError
from neoaprs.instancelock import LOCK_NAME, is_held
from neoaprs.stopfile import migrating
from neoaprs.store import DB_NAME
from neoaprs.storesql import read_setting
from neoaprs.supportsql import open_readonly

from .logfile import LOG_NAME, PAGE_LINE, START_LINE, read_page

SCAN_BYTES = 256 * 1024                  # tail of the log searched for the page address
PROBE_SEC = 2.0
# The page is local, so an environment proxy must not be used.
LOCAL_ONLY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def is_running(data_dir: Path) -> bool:
    """Whether a daemon holds the instance lock of the data folder."""
    return is_held(data_dir, LOCK_NAME)


def tail(path: Path, lines: int = 50) -> list[str]:
    """Return the last `lines` lines of a text file, or [] if it cannot be read."""
    if lines <= 0:
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - SCAN_BYTES))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    # After a cut the first line is partial, so it is dropped.
    return text.splitlines()[-lines:] if size <= SCAN_BYTES else text.splitlines()[1:][-lines:]


def page_url(data_dir: Path) -> str | None:
    """Return the page address from the address file, else from the latest run's log line, else None."""
    written = read_page(data_dir)
    if written is not None:
        return written
    found: str | None = None
    for line in tail(data_dir / LOG_NAME, 100_000):
        if START_LINE in line:
            found = None                                   # a new run supersedes earlier lines
        match = PAGE_LINE.search(line)
        if match:
            found = match.group(1)
    return found


def page_answers(url: str) -> bool:
    """Return whether the address answers with HTTP 200."""
    try:
        with LOCAL_ONLY.open(url, timeout=PROBE_SEC) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return False


def page_address(data_dir: Path) -> str:
    """Return where a daemon started without flags would serve its page, from the stored web/port.

    A fallback port (when the port is taken) or port 0 is only known from the log."""
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
    """Return (whether a daemon runs on the data folder, a one-line description of its state)."""
    if not is_running(data_dir):
        return False, "no daemon is running on this data folder"
    if migrating(data_dir):
        return True, "a daemon is running and is bringing its database up to date; its page comes when that is done"
    url = page_url(data_dir)
    if url is None:
        return True, "a daemon is running; its log does not say where its page is (is the page's port taken?)"
    return True, f"a daemon is running; its page {url} " + ("answers" if page_answers(url) else "does not answer")
