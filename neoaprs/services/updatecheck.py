"""The daily update check: a minute after the start and then every 24 hours the daemon asks the version page (`update/url`) which version is the latest, sending its own version and platform and nothing else. When the answer is a
newer version, `latest` has it; the page is told in its next status and shows it beside the version. `update/check` switches it off (so does `NEOAPRS_UPDATE_CHECK=0` in the environment, which the tests set), and is looked at again an hour later while it is off.
A page that cannot be reached or understood is only a line in the debug log: the next try is the next day. Nothing is kept between runs.
"""
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Mapping

from neoaprs.config import Config
from neoaprs.tasks import TaskSet
from neoaprs.versions import Update, compare_versions, parse_update

log = logging.getLogger("neoaprs.update")

FIRST_SEC = 60.0
EVERY_SEC = 24 * 3600.0
WHILE_OFF_SEC = 3600.0
ENV_SWITCH = "NEOAPRS_UPDATE_CHECK"             # "0" is off for this run, whatever the setting says
Fetch = Callable[[str, str, str], Awaitable[bytes | None]]     # (address, version, platform) to the body of the answer


class UpdateCheck:
    def __init__(self, config: Callable[[], Config], version: str, platform: str, fetch: Fetch, first_sec: float = FIRST_SEC, every_sec: float = EVERY_SEC,
                 environ: Mapping[str, str] = os.environ) -> None:
        self._config = config
        self.version = version
        self.platform = platform
        self._fetch = fetch
        self.first_sec = first_sec
        self.every_sec = every_sec
        self._environ = environ
        self.latest: Update | None = None                       # the answer, while it names a version newer than ours
        self._tasks = TaskSet(self._task_failed)

    @property
    def enabled(self) -> bool:
        return self._config().update_check and self._environ.get(ENV_SWITCH) != "0"

    async def start(self) -> None:
        if not self._tasks:
            self._tasks.spawn(self._run(), "update-check")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    @staticmethod
    def _task_failed(task: "asyncio.Task[None]") -> None:
        log.error("update task %s failed: %r", task.get_name(), task.exception())

    async def _run(self) -> None:
        wait = self.first_sec
        while True:
            await asyncio.sleep(wait)
            wait = self.every_sec if self.enabled else WHILE_OFF_SEC
            if self.enabled:
                try:
                    await self.check()
                except Exception:                                # (a check that fails must not end the timer)
                    log.debug("the update check failed", exc_info=True)

    async def check(self) -> Update | None:
        """Asks the page now; the newer version it names, else None. `latest` follows the answer; an answer that did not come leaves it as it was."""
        body = await self._fetch(self._config().update_url, self.version, self.platform)
        answer = None if body is None else parse_update(body)
        if answer is None:
            log.debug("the update check got no usable answer from %s", self._config().update_url)
            return None
        newer = answer if compare_versions(answer.version, self.version) > 0 else None
        if newer != self.latest:
            self.latest = newer
            if newer is not None:
                log.info("NeoAPRS %s is available (this is %s): %s", newer.version, self.version, newer.url or "no address")
        return newer
