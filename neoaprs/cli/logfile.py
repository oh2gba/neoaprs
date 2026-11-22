"""The log lines and files the daemon writes so that commands can find it, and their formats.

The daemon writes them, commands read them, and only this module knows their format."""
import os
import re
from pathlib import Path

from neoaprs.instancelock import is_file

LOG_NAME = "neoaprs.log"
APP_LOG_NAME = "neoaprs-app.log"
LAUNCH_NAME = "launch.log"  # a traceback from a daemon that failed before logging
START_LINE = " starting, data in "
START_FORMAT = "%s %s" + START_LINE + "%s"  # program, version, data folder
PAGE_FORMAT = "web page at %s"
PAGE_LINE = re.compile(r"web page at (http://\S+?/)(?:\s|$)")
PAGE_FILE = "neoaprs-web.url"
# Present while the page is also served to the network; the tray reads it.
NETWORK_FILE = "neoaprs-web.network"
PAGE_URL = re.compile(r"http://\S+?/")
LOG_SCAN_BYTES = 20_000_000  # tail of the log read for the previous run
# Anchoring on the daemon's own INFO prefix keeps text inside another line (a packet) from matching.
_OWN_LINE = rb"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\dZ  INFO  "
RUN_START = re.compile(_OWN_LINE + rb"\S+ \S+" + re.escape(START_LINE.encode()), re.MULTILINE)
# Only the local address counts.
RUN_PAGE = re.compile(_OWN_LINE + rb"web page at (http://127\.0\.0\.1:\d{1,5}/)\r?$", re.MULTILINE)


def write_page(data_dir: Path, url: str) -> None:
    """Write the page address atomically, so readers never see half of it."""
    scratch = data_dir / (PAGE_FILE + ".new")
    scratch.write_text(url + "\n", encoding="ascii")
    os.replace(scratch, data_dir / PAGE_FILE)


def remove_page(data_dir: Path) -> None:
    """Remove the page address file and the network note."""
    for name in (PAGE_FILE, NETWORK_FILE):
        try:
            (data_dir / name).unlink(missing_ok=True)
        except OSError:
            pass


def write_network(data_dir: Path, on: bool) -> None:
    """Create or remove the network note according to whether the page is served to the network."""
    if on:
        (data_dir / NETWORK_FILE).write_text("on\n", encoding="ascii")
    else:
        (data_dir / NETWORK_FILE).unlink(missing_ok=True)


def network_is_on(data_dir: Path) -> bool:
    """Return whether the daemon serves its page to the network."""
    return is_file(data_dir / NETWORK_FILE)


def page_of_the_run_before(data_dir: Path) -> str | None:
    """Return the page address logged by the run before the latest start line, or None."""
    try:
        with (data_dir / LOG_NAME).open("rb") as f:
            f.seek(0, 2)
            cut = max(0, f.tell() - LOG_SCAN_BYTES)
            f.seek(cut)
            text = f.read()
    except OSError:
        return None
    if cut:
        text = text[text.find(b"\n") + 1:]                   # drop the partial first line
    starts = [found.start() for found in RUN_START.finditer(text)]
    if not starts:
        return None
    pages = RUN_PAGE.findall(text, starts[-2] if len(starts) > 1 else 0, starts[-1])
    return pages[-1].decode("ascii") if pages else None


def read_page(data_dir: Path) -> str | None:
    """Return the address the daemon wrote, or None if the file is missing or invalid."""
    try:
        text = (data_dir / PAGE_FILE).read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return text if PAGE_URL.fullmatch(text) else None
