"""The frequencies the project suggests for the HF radio, fetched from the project's server.

Fetched at most once per FREQUENCIES_EVERY_SEC; the last valid list is kept in the settings table.
It is switched off with the update check.
"""
import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping

from neoaprs.services.memory import Memory
from neoaprs.services.updatecheck import ENV_SWITCH, FIRST_SEC
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.updatefetch import fetch_url
from neoaprs.versions import FREQUENCIES_ROW, FREQUENCIES_URL, Frequency, frequencies_text, on_this_computer, parse_frequencies

log = logging.getLogger("neoaprs.update")

FREQUENCIES_EVERY_SEC = 15 * 60.0
MAX_BYTES = 8192
ENV_URL = "NEOAPRS_FREQUENCIES_URL"             # a local server instead of FREQUENCIES_URL, for tests
FetchUrl = Callable[[str, str, str, int], Awaitable[bytes | None]]


def words(frequencies: list[Frequency]) -> str:
    return ", ".join(f"{f.band} {f.dial}" for f in frequencies) or "none"


class Frequencies:
    def __init__(self, version: str, platform: str, fetch: FetchUrl = fetch_url, first_sec: float = FIRST_SEC, every_sec: float = FREQUENCIES_EVERY_SEC, environ: Mapping[str, str] = os.environ,
                 memory: Memory | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.version, self.platform = version, platform
        self._fetch = fetch
        self.first_sec, self.every_sec = first_sec, every_sec
        self._environ = environ
        self._memory = memory
        self._clock = clock
        self.listed: list[Frequency] = []
        self.changed: Signal[[]] = Signal("frequencies.changed")
        self.asked = 0
        self._last: float | None = None
        self._tasks = TaskSet(log, "frequencies")

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    @property
    def url(self) -> str:
        """The project's URL, or `NEOAPRS_FREQUENCIES_URL` when that is a local server."""
        given = self._environ.get(ENV_URL, "").strip()
        return given if on_this_computer(given) else FREQUENCIES_URL

    async def start(self) -> None:
        if not self._tasks:
            self._tasks.spawn(self._run(), "frequencies")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await self._kept()
        await asyncio.sleep(self.first_sec)
        await self.ask()

    async def _kept(self) -> None:
        """Load the list kept by an earlier run."""
        if self._memory is not None and not self.listed and (kept := await self._memory.setting(FREQUENCIES_ROW)) and (found := parse_frequencies(kept)):
            self.listed = found
            self.changed.emit()

    def wanted(self) -> None:
        """Ask the server now, unless asked less than `every_sec` ago or the check is off."""
        if self._begin():
            self._tasks.spawn(self._take(), "frequencies-ask")

    def _begin(self) -> bool:
        """Return whether to ask now, recording the time so concurrent callers ask once."""
        if not self.enabled or (self._last is not None and self._clock() - self._last < self.every_sec):
            return False
        self._last = self._clock()
        self.asked += 1
        return True

    async def ask(self) -> None:
        """Ask the server under the same rule as `wanted`."""
        if self._begin():
            await self._take()

    async def _take(self) -> None:
        body = await self._fetch(self.url, self.version, self.platform, MAX_BYTES)
        if body is None:
            log.debug("the project's frequencies could not be fetched from %s", self.url)
            return
        found = parse_frequencies(body)
        if found is None:
            log.debug("the project's file of frequencies at %s is not a list", self.url)
            return
        if found != self.listed:
            log.info("the project suggests the frequencies %s (was %s)", words(found), words(self.listed))
            self.listed = found
            if self._memory is not None:
                await self._memory.put_settings({FREQUENCIES_ROW: frequencies_text(found)})
            self.changed.emit()
