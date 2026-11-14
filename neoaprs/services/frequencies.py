"""The frequencies the project suggests for the HF radio: a small file on the project's server (`FREQUENCIES_URL`, site/frequencies.json: bands and dials, edited by hand and uploaded with the site, no release) that the daemon asks for a minute after
its start and whenever a page shows the HF radio's box (`wanted`), and never more often than every FREQUENCIES_EVERY_SEC however many pages ask. Every entry is checked (the band `40 m`, the dial `7.0541 MHz USB`, at most four), the last good list is
kept in the settings table (the row FREQUENCIES_ROW) and told at the start before the server is asked, and a file that is not a list, or cannot be fetched, leaves it as it was. The box shows this list, else the dial the version page names (the daily check:
services/updatecheck.py), else the built-in three (`neoaprs/mercury.py` SUGGESTED). It is part of the update check's kind of traffic and goes off with it: `NEOAPRS_UPDATE_CHECK=0` in the environment (the tests, the demo) asks nothing, and a test or a bench that
needs a server names one on this computer with `NEOAPRS_FREQUENCIES_URL`."""
import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping

from neoaprs.services.memory import Memory
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.updatefetch import fetch_url
from neoaprs.versions import FREQUENCIES_ROW, FREQUENCIES_URL, Frequency, frequencies_text, on_this_computer, parse_frequencies

log = logging.getLogger("neoaprs.update")

FIRST_SEC = 60.0
FREQUENCIES_EVERY_SEC = 15 * 60.0              # the least time between two questions to the server, whoever asks
MAX_BYTES = 8192                                # the file is a few hundred bytes
ENV_SWITCH = "NEOAPRS_UPDATE_CHECK"
ENV_URL = "NEOAPRS_FREQUENCIES_URL"             # development and tests: a server on this computer, instead of FREQUENCIES_URL
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
        self.listed: list[Frequency] = []                        # the project's list as last understood (the kept one until the server has answered)
        self.changed: Signal[[]] = Signal("frequencies.changed")
        self.asked = 0                                           # how many times the server was asked
        self._last: float | None = None                          # when it was last asked, by `clock`
        self._tasks = TaskSet(log, "frequencies")

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    @property
    def url(self) -> str:
        """The server's file: the project's, or, for development and tests, the one of `NEOAPRS_FREQUENCIES_URL` when it is a server on this computer."""
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
        await self.ask()                                         # (after that, when a page shows the HF box: `wanted`)

    async def _kept(self) -> None:
        """The list kept by an earlier run, told before the server is asked (inside the task: the start of the daemon does not wait for the database)."""
        if self._memory is not None and not self.listed and (kept := await self._memory.setting(FREQUENCIES_ROW)) and (found := parse_frequencies(kept)):
            self.listed = found
            self.changed.emit()

    def wanted(self) -> None:
        """A page shows the HF radio's box: the server is asked now, unless it was asked less than every_sec ago or the check is off."""
        if self._begin():
            self._tasks.spawn(self._take(), "frequencies-ask")

    def _begin(self) -> bool:
        """Whether the server is to be asked now (the check is on and it was not asked less than every_sec ago); if so, now is the time it was asked, so that two pages at once ask once."""
        if not self.enabled or (self._last is not None and self._clock() - self._last < self.every_sec):
            return False
        self._last = self._clock()
        self.asked += 1
        return True

    async def ask(self) -> None:
        """Asks the server, with the same rule as `wanted`; the list in the file, when it is one, is the project's list from now on."""
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
