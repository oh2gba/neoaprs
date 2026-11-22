"""What the daemon writes into its data folder so that a command can find it again, and the words it writes: the log, `neoaprs.log`, with its start line (`NeoAPRS 0.14.0 starting, data in ...`) and its
page line (`web page at http://127.0.0.1:7303/`), and the file `neoaprs-web.url` that holds the page's address while the page is served. The daemon (neoaprs/daemon.py, neoaprs/web/server.py) writes them, the commands
(neoaprs/cli/daemonstate.py, the support bundle) read them, and this module is the one place that knows how they look."""
import os
import re
from pathlib import Path

from neoaprs.instancelock import is_file

LOG_NAME = "neoaprs.log"
APP_LOG_NAME = "neoaprs-app.log"
LAUNCH_NAME = "launch.log"                                  # what a daemon that was started by a command says before it has a log: a traceback
START_LINE = " starting, data in "
START_FORMAT = "%s %s" + START_LINE + "%s"                  # program, version, data folder (a logging format)
PAGE_FORMAT = "web page at %s"                              # the page's address (a logging format)
PAGE_LINE = re.compile(r"web page at (http://\S+?/)(?:\s|$)")
PAGE_FILE = "neoaprs-web.url"
NETWORK_FILE = "neoaprs-web.network"                        # there while the page is served to the network too (`web/network` on and bound): the app's tray reads it to know whether the browser is a way in
PAGE_URL = re.compile(r"http://\S+?/")
LOG_SCAN_BYTES = 20_000_000                                # the end of the log that is read for the run before: a whole file of it (neoaprs/daemon.py setup_logging)
_OWN_LINE = rb"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\dZ  INFO  "        # how a line the daemon says at INFO begins (the format of neoaprs/daemon.py setup_logging): words inside another line, a packet's text, are not such a line
RUN_START = re.compile(_OWN_LINE + rb"\S+ \S+" + re.escape(START_LINE.encode()), re.MULTILINE)
RUN_PAGE = re.compile(_OWN_LINE + rb"web page at (http://127\.0\.0\.1:\d{1,5}/)\r?$", re.MULTILINE)      # (the page's own address on this computer: neoaprs/web/server.py `url`)


def write_page(data_dir: Path, url: str) -> None:
    """Says where the page is: the file is written whole under another name and then renamed, so that a command that reads it never sees half of it."""
    scratch = data_dir / (PAGE_FILE + ".new")
    scratch.write_text(url + "\n", encoding="ascii")
    os.replace(scratch, data_dir / PAGE_FILE)


def remove_page(data_dir: Path) -> None:
    """The page is not served (any more): its address is taken away, and the note that it was served to the network."""
    for name in (PAGE_FILE, NETWORK_FILE):
        try:
            (data_dir / name).unlink(missing_ok=True)
        except OSError:
            pass


def write_network(data_dir: Path, on: bool) -> None:
    """Says whether the page is served to the network: the file is there while it is, and gone while it is not."""
    if on:
        (data_dir / NETWORK_FILE).write_text("on\n", encoding="ascii")
    else:
        (data_dir / NETWORK_FILE).unlink(missing_ok=True)


def network_is_on(data_dir: Path) -> bool:
    """Whether the daemon says its page is served to the network (a daemon that does not say, an older one or none, is taken as not serving it)."""
    return is_file(data_dir / NETWORK_FILE)


def page_of_the_run_before(data_dir: Path) -> str | None:
    """The page's address of the run before the one that has just written its start line, from the log: the last page line before the last start line, when no other start is between them. None when
    that run had no page, or the log has been rotated since it said so. (The daemon that starts again in the place of one of 0.20.1 or before finds its port this way: that one's note names none.)
    Only whole lines the daemon said itself count, and only the page's address on this computer: the words of a page line inside another line (the text of a packet that was logged) name no port."""
    try:
        with (data_dir / LOG_NAME).open("rb") as f:
            f.seek(0, 2)
            cut = max(0, f.tell() - LOG_SCAN_BYTES)
            f.seek(cut)
            text = f.read()
    except OSError:
        return None
    if cut:
        text = text[text.find(b"\n") + 1:]                   # (the first line of a cut is the end of one)
    starts = [found.start() for found in RUN_START.finditer(text)]
    if not starts:
        return None
    pages = RUN_PAGE.findall(text, starts[-2] if len(starts) > 1 else 0, starts[-1])
    return pages[-1].decode("ascii") if pages else None


def read_page(data_dir: Path) -> str | None:
    """The address the daemon wrote, or None (no file, or not an address)."""
    try:
        text = (data_dir / PAGE_FILE).read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return text if PAGE_URL.fullmatch(text) else None
