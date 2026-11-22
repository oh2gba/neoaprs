"""The daily update check: ask the version page which version is the latest.

The daemon asks daily, sending its version, platform and a random installation number (0 for a
source-tree run). `NEOAPRS_UPDATE_CHECK=0` switches the check off for one run."""
import asyncio
import logging
import os
import re
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from neoaprs.config import HF_DIAL, INSTALL_ID
from neoaprs.configtypes import boolean
from neoaprs.releasenotes import MAX_BYTES, Section, between, changelog_url, section_of, sections
from neoaprs.services.common import ConfigSource
from neoaprs.services.memory import Memory
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet, every
from neoaprs.updatefetch import fetch_url
from neoaprs.versions import NOT_COUNTED, Update, compare_versions, parse_update

log = logging.getLogger("neoaprs.update")

FIRST_SEC = 60.0
EVERY_SEC = 24 * 3600.0
WHILE_OFF_SEC = 3600.0
# "0" is off for this run, whatever the setting says
ENV_SWITCH = "NEOAPRS_UPDATE_CHECK"
# (address, version, platform, installation number) -> body of the answer
Fetch = Callable[[str, str, str, str], Awaitable[bytes | None]]
# (address, version, platform, max bytes) -> body of the answer
FetchUrl = Callable[[str, str, str, int], Awaitable[bytes | None]]
INSTALL_ID_FORM = re.compile(r"[0-9a-f]{32}")
# sent instead of the installation number by a run not counted (source tree, NOT_COUNTED row)
NOT_COUNTED_ID = "0"
NO_ANSWER = "no answer from the update server; is there a connection?"
NO_VERSION = "the update server gave no usable answer; try again later"
# codes for why there are no release notes
NOTES_UNREACHABLE = "unreachable"
NOTES_UNKNOWN_VERSION = "unknown_version"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of an on-request check: `newer` (`version` is the latest), `current` or `no_answer`.

    `reason` says why when there was no answer."""
    outcome: Literal["newer", "current", "no_answer"]
    version: str = ""
    reason: str = ""

    @property
    def why(self) -> Literal["", "offline", "bad_answer"]:
        """`reason` as a page code: `offline` or `bad_answer`; empty unless `no_answer`."""
        return "" if self.outcome != "no_answer" else "offline" if self.reason == NO_ANSWER else "bad_answer"


class UpdateCheck:
    def __init__(self, config: ConfigSource, version: str, platform: str, fetch: Fetch, first_sec: float = FIRST_SEC, every_sec: float = EVERY_SEC,
                 environ: Mapping[str, str] = os.environ, memory: Memory | None = None, fetch_url: FetchUrl = fetch_url, developer: bool = False) -> None:
        self._config = config
        self.version = version
        self.platform = platform
        self._fetch = fetch
        self._fetch_url = fetch_url
        # changelog sections by version: ours and the latest only
        self._notes: dict[str, list[Section]] = {}
        self.first_sec = first_sec
        self.every_sec = every_sec
        self._environ = environ
        self._memory = memory
        self.developer = developer
        self._install_id: str | None = None
        self.latest: Update | None = None
        # the HF dial the page named last; empty: none yet
        self.hf_dial = ""
        self.dial_changed: Signal[[str]] = Signal("update.dial_changed")
        self._tasks = TaskSet(log, "update")
        # one question at a time, whoever asks
        self._asking = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    async def start(self) -> None:
        if not self._tasks:
            self._tasks.spawn(self._run(), "update-check")

    async def _kept_dial(self) -> None:
        """Tell the kept HF dial before asking the page."""
        if self._memory is not None and not self.hf_dial and (kept := await self._memory.setting(HF_DIAL)):
            self.hf_dial = kept
            self.dial_changed.emit(kept)

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await self._kept_dial()
        await every(self._wait, self._round, "the update check", first=self.first_sec)

    def _wait(self) -> float:
        return self.every_sec if self.enabled else WHILE_OFF_SEC

    async def _round(self) -> None:
        if self.enabled:
            await self.check()

    async def install_id(self) -> str:
        """Return the installation number (32 hex characters), made on first use and kept."""
        if self._install_id is None:
            kept = None if self._memory is None else await self._memory.setting(INSTALL_ID)
            if kept is not None and INSTALL_ID_FORM.fullmatch(kept):
                self._install_id = kept
            else:
                self._install_id = secrets.token_hex(16)
                if self._memory is not None:
                    await self._memory.put_settings({INSTALL_ID: self._install_id})
        return self._install_id

    async def sent_id(self) -> str:
        """Return the `id` the question carries: the installation number, or `NOT_COUNTED_ID`.

        The latter applies to source-tree runs and while the row NOT_COUNTED is true."""
        number = await self.install_id()
        if self.developer:
            return NOT_COUNTED_ID
        marked = None if self._memory is None else await self._memory.setting(NOT_COUNTED)
        try:
            return NOT_COUNTED_ID if marked is not None and boolean(marked) else number
        except ValueError:
            return number

    async def _ask(self) -> tuple[Update | None, str]:
        """Return (the page's answer, ""), or (None, the reason)."""
        address = self._config().update_url
        body = await self._fetch(address, self.version, self.platform, await self.sent_id())
        if body is None:
            return None, NO_ANSWER
        answer = parse_update(body)
        return (answer, "") if answer is not None else (None, NO_VERSION)

    def _take(self, answer: Update) -> Update | None:
        newer = answer if compare_versions(answer.version, self.version) > 0 else None
        if newer != self.latest:
            self.latest = newer
            if newer is not None:
                log.info("NeoAPRS %s is available (this is %s): %s", newer.version, self.version, newer.url or "no address")
        return newer

    async def check(self) -> Update | None:
        """Ask the page now and return the newer version it names, else None."""
        async with self._asking:
            answer, reason = await self._ask()
            if answer is None:
                log.debug("the update check got no usable answer from %s: %s", self._config().update_url, reason)
                return None
            await self._take_dial(answer.hf_dial)
            return self._take(answer)

    async def _take_dial(self, dial: str) -> None:
        """Keep, log and tell the answer's HF dial if it differs from the known one."""
        if not dial or dial == self.hf_dial:
            return
        log.info("the version page names the HF dial %s (was %s)", dial, self.hf_dial or "the built-in one")
        self.hf_dial = dial
        if self._memory is not None:
            await self._memory.put_settings({HF_DIAL: dial})
        self.dial_changed.emit(dial)

    async def release_notes(self, version: str, since: str = "") -> tuple[list[Section], str]:
        """Return (sections newer than `since` up to `version`, newest first; "").

        `version` must be the latest or our own; return ([], why) when there is nothing to give."""
        newer = self.latest is not None and version == self.latest.version
        if not newer and version != self.version:
            return [], NOTES_UNKNOWN_VERSION
        found = self._notes.get(version)
        if found is None:
            body = await self._fetch_url(changelog_url(version), self.version, self.platform, MAX_BYTES)
            if body is None:
                return [], NOTES_UNREACHABLE
            found = sections(body.decode("utf-8", errors="replace"))
            kept = {self.version, self.latest.version if self.latest is not None else self.version}
            self._notes = {tag: text for tag, text in self._notes.items() if tag in kept} | {version: found}
        if since:
            return between(found, since, version), ""
        return (between(found, self.version, version) if newer else section_of(found, version)), ""

    async def check_now(self) -> CheckResult:
        """Ask on request even if the daily check is off; `latest` follows, the timer is kept."""
        async with self._asking:
            answer, reason = await self._ask()
            if answer is None:
                return CheckResult("no_answer", reason=reason)
            await self._take_dial(answer.hf_dial)
            newer = self._take(answer)
            return CheckResult("newer", newer.version) if newer is not None else CheckResult("current", self.version)
