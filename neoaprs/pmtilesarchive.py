"""PMTiles archive helpers: read a header, move a file into place, find the latest daily build."""
import asyncio
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs.mapstate import MapError
from . import nodevices
from .httpstrust import USER_AGENT, NotDowngraded, https_handler
from .pmtilesformat import HEADER_LENGTH, MAGIC, VERSION, unpack_header

UNREACHABLE = "the map server could not be reached; is there a connection?"
REPLACE_TRIES = 8
DOWNLOAD_THREADS = 8                        # parallel requests of a cut
BUILDS = "https://build.protomaps.com"
BUILD_DAYS = 8                              # today and the seven days before it


class Redirected(NotDowngraded):
    """With the no-devices switch on, a redirect may not leave this computer."""

    def check(self, newurl: str) -> None:
        nodevices.check_url(newurl, "the map")


@dataclass(frozen=True)
class Header:
    min_zoom: int
    max_zoom: int
    bbox: tuple[float, float, float, float]          # west, south, east, north


def read_header(path: Path) -> Header | None:
    """Return the zooms and bounding box of a PMTiles v3 archive, or None if not one."""
    try:
        with path.open("rb") as f:
            data = f.read(HEADER_LENGTH)
    except OSError:
        return None
    if len(data) < HEADER_LENGTH or data[:7] != MAGIC or data[7] != VERSION:
        return None
    fields = unpack_header(data)
    west, south, east, north = fields.bounds_e7
    return Header(fields.min_zoom, fields.max_zoom, (west / 1e7, south / 1e7, east / 1e7, north / 1e7))


def replace_file(source: Path, target: Path) -> None:
    """Atomically replace `target` with `source`. Windows refuses while it is open, so retry."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(0.25)


def url_exists(url: str) -> bool:
    """Return whether a HEAD request succeeds; any connection failure is False. Blocks."""
    try:
        nodevices.check_url(url)
        with urllib.request.build_opener(https_handler(), Redirected, *nodevices.direct()).open(urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT}), timeout=20) as response:  # noqa: S310  (only BUILDS, https)
            return bool(200 <= response.status < 300)
    except (OSError, ValueError):
        return False


async def latest_build(now: datetime, probe: Callable[[str], bool] = url_exists) -> tuple[str, str]:
    """Return the URL and day of the newest daily build; raise MapError if none is found."""
    for back in range(BUILD_DAYS):
        day = (now - timedelta(days=back)).strftime("%Y%m%d")
        url = f"{BUILDS}/{day}.pmtiles"
        if await asyncio.to_thread(probe, url):
            return url, day
    raise MapError(f"no daily build was found at {BUILDS} in the last {BUILD_DAYS} days (is there a connection?)", problem="no_build", days=BUILD_DAYS)
