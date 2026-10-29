"""What the daemon writes into its data folder so that a command can find it again, and the words it writes: the log, `neoaprs.log`, with its start line (`NeoAPRS 0.14.0 starting, data in ...`) and its
page line (`web page at http://127.0.0.1:7303/`), and the file `neoaprs-web.url` that holds the page's address while the page is served. The daemon (neoaprs/daemon.py, neoaprs/web/server.py) writes them, the commands
(neoaprs/cli/daemonstate.py, the support bundle) read them, and this module is the one place that knows how they look."""
import os
import re
from pathlib import Path

LOG_NAME = "neoaprs.log"
LAUNCH_NAME = "launch.log"                                  # what a daemon that was started by a command says before it has a log: a traceback
START_LINE = " starting, data in "
START_FORMAT = "%s %s" + START_LINE + "%s"                  # program, version, data folder (a logging format)
PAGE_FORMAT = "web page at %s"                              # the page's address (a logging format)
PAGE_LINE = re.compile(r"web page at (http://\S+?/)(?:\s|$)")
PAGE_FILE = "neoaprs-web.url"
PAGE_URL = re.compile(r"http://\S+?/")


def write_page(data_dir: Path, url: str) -> None:
    """Says where the page is: the file is written whole under another name and then renamed, so that a command that reads it never sees half of it."""
    scratch = data_dir / (PAGE_FILE + ".new")
    scratch.write_text(url + "\n", encoding="ascii")
    os.replace(scratch, data_dir / PAGE_FILE)


def remove_page(data_dir: Path) -> None:
    """The page is not served (any more): its address is taken away."""
    try:
        (data_dir / PAGE_FILE).unlink(missing_ok=True)
    except OSError:
        pass


def read_page(data_dir: Path) -> str | None:
    """The address the daemon wrote, or None (no file, or not an address)."""
    try:
        text = (data_dir / PAGE_FILE).read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return text if PAGE_URL.fullmatch(text) else None
