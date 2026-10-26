"""The daily update check: a minute after the start and then every 24 hours the daemon asks the version page (`update/url`) which version is the latest, sending its own version and platform and the random number of this installation (made once, the first time it is asked, and kept as the row `update/install_id` of the database: state of the daemon, not
a setting; it comes from nowhere on the machine, so that the project can count installations) and nothing else. When the answer is a
newer version, `latest` has it; the page is told in its next status and shows it beside the version. It is always on; `NEOAPRS_UPDATE_CHECK=0` in the environment switches it off for one run (the tests set it), and is looked at again an hour later while it is off.
A page that cannot be reached or understood is only a line in the debug log: the next try is the next day. Nothing but that number is kept between runs. `check_now` is the same question asked on request (the Settings tab's Check now): it works whatever the switches
say, tells what came of it, and leaves the schedule alone.
"""
import asyncio
import logging
import os
import re
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from neoaprs.config import INSTALL_ID
from neoaprs.services.common import ConfigSource
from neoaprs.services.memory import Memory
from neoaprs.tasks import TaskSet
from neoaprs.versions import Update, compare_versions, parse_update

log = logging.getLogger("neoaprs.update")

FIRST_SEC = 60.0
EVERY_SEC = 24 * 3600.0
WHILE_OFF_SEC = 3600.0
ENV_SWITCH = "NEOAPRS_UPDATE_CHECK"             # "0" is off for this run, whatever the setting says
Fetch = Callable[[str, str, str, str], Awaitable[bytes | None]]     # (address, version, platform, installation number) to the body of the answer
INSTALL_ID_FORM = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class CheckResult:
    """What a question put on request came to: `newer` (`version` is the latest), `current` (`version` is ours) or `no_answer` (`reason` says why)."""
    outcome: Literal["newer", "current", "no_answer"]
    version: str = ""
    reason: str = ""


class UpdateCheck:
    def __init__(self, config: ConfigSource, version: str, platform: str, fetch: Fetch, first_sec: float = FIRST_SEC, every_sec: float = EVERY_SEC,
                 environ: Mapping[str, str] = os.environ, memory: Memory | None = None) -> None:
        self._config = config
        self.version = version
        self.platform = platform
        self._fetch = fetch
        self.first_sec = first_sec
        self.every_sec = every_sec
        self._environ = environ
        self._memory = memory
        self._install_id: str | None = None                     # kept in the row INSTALL_ID; without a memory (the tests) it lasts as long as this object
        self.latest: Update | None = None                       # the answer, while it names a version newer than ours
        self._tasks = TaskSet(log, "update")
        self._asking = asyncio.Lock()                           # one question at a time, whoever asks

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    async def start(self) -> None:
        if not self._tasks:
            self._tasks.spawn(self._run(), "update-check")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

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

    async def install_id(self) -> str:
        """The number of this installation: 32 lowercase hex characters from 16 random bytes, made the first time it is needed and kept in the database. A row that is not of that form is made again."""
        if self._install_id is None:
            kept = None if self._memory is None else await self._memory.setting(INSTALL_ID)
            if kept is not None and INSTALL_ID_FORM.fullmatch(kept):
                self._install_id = kept
            else:
                self._install_id = secrets.token_hex(16)
                if self._memory is not None:
                    await self._memory.put_settings({INSTALL_ID: self._install_id})
        return self._install_id

    async def _ask(self) -> tuple[Update | None, str]:
        """(the answer of the page, ''), or (None, why not)."""
        address = self._config().update_url
        body = await self._fetch(address, self.version, self.platform, await self.install_id())
        if body is None:
            return None, "the version page could not be reached"
        answer = parse_update(body)
        return (answer, "") if answer is not None else (None, "the version page gave an answer that is not a version")

    def _take(self, answer: Update) -> Update | None:
        newer = answer if compare_versions(answer.version, self.version) > 0 else None
        if newer != self.latest:
            self.latest = newer
            if newer is not None:
                log.info("NeoAPRS %s is available (this is %s): %s", newer.version, self.version, newer.url or "no address")
        return newer

    async def check(self) -> Update | None:
        """Asks the page now; the newer version it names, else None. `latest` follows the answer; an answer that did not come leaves it as it was."""
        async with self._asking:
            answer, reason = await self._ask()
            if answer is None:
                log.debug("the update check got no usable answer from %s: %s", self._config().update_url, reason)
                return None
            return self._take(answer)

    async def check_now(self) -> CheckResult:
        """The same question on request, whether the daily check is on or not; `latest` follows the answer, and the timer of the daily check is not touched."""
        async with self._asking:
            answer, reason = await self._ask()
            if answer is None:
                return CheckResult("no_answer", reason=reason)
            newer = self._take(answer)
            return CheckResult("newer", newer.version) if newer is not None else CheckResult("current", self.version)
