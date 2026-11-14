"""The daily update check: a minute after the start and then every 24 hours the daemon asks the version page (`update/url`) which version is the latest, sending its own version and platform and the random number of this installation (or 0 from a run of the source tree or while the row `update/not_counted` is true, which the project does not count; made once, the first time it is asked, and kept as the row `update/install_id` of the database: state of the daemon, not
a setting; it comes from nowhere on the machine, so that the project can count installations) and nothing else. When the answer is a
newer version, `latest` has it; the page is told in its next status and shows it beside the version. It is always on; `NEOAPRS_UPDATE_CHECK=0` in the environment switches it off for one run (the tests set it), and is looked at again an hour later while it is off.
A page that cannot be reached or understood is only a line in the debug log: the next try is the next day. Nothing but that number is kept between runs. `check_now` is the same question asked on request (the Settings tab's Check now): it works whatever the switches
say, tells what came of it, and leaves the schedule alone. `release_notes` is what is new between our version and the latest: the changelog at the tag of the latest release, fetched once and kept (neoaprs/releasenotes.py), for the page's What's new; or, asked for our own version, what the
update we have had brought: the changelog at our tag, for the same window opened after the update.
"""
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
ENV_SWITCH = "NEOAPRS_UPDATE_CHECK"             # "0" is off for this run, whatever the setting says
Fetch = Callable[[str, str, str, str], Awaitable[bytes | None]]     # (address, version, platform, installation number) to the body of the answer
FetchUrl = Callable[[str, str, str, int], Awaitable[bytes | None]]  # (address, version, platform, the most bytes wanted) to the body of the answer
INSTALL_ID_FORM = re.compile(r"[0-9a-f]{32}")
NOT_COUNTED_ID = "0"                            # sent in place of the installation's number by a run that is not a user's: a run from the source tree, or one the row NOT_COUNTED marks (the project's report leaves it out)
NO_ANSWER = "no answer from the update server; is there a connection?"
NO_VERSION = "the update server gave no usable answer; try again later"
NOTES_UNREACHABLE = "the release notes could not be fetched"
NOTES_UNKNOWN_VERSION = "that version is neither the newer one known nor this one"


@dataclass(frozen=True)
class CheckResult:
    """What a question put on request came to: `newer` (`version` is the latest), `current` (`version` is ours) or `no_answer` (`reason` says why)."""
    outcome: Literal["newer", "current", "no_answer"]
    version: str = ""
    reason: str = ""


class UpdateCheck:
    def __init__(self, config: ConfigSource, version: str, platform: str, fetch: Fetch, first_sec: float = FIRST_SEC, every_sec: float = EVERY_SEC,
                 environ: Mapping[str, str] = os.environ, memory: Memory | None = None, fetch_url: FetchUrl = fetch_url, developer: bool = False) -> None:
        self._config = config
        self.version = version
        self.platform = platform
        self._fetch = fetch
        self._fetch_url = fetch_url
        self._notes: dict[str, list[Section]] = {}               # every section of the changelog fetched, by the version at whose tag it was fetched: ours and the latest, no other
        self.first_sec = first_sec
        self.every_sec = every_sec
        self._environ = environ
        self._memory = memory
        self.developer = developer                               # a run from the source tree: its question carries the number 0 (NOT_COUNTED_ID)
        self._install_id: str | None = None                     # kept in the row INSTALL_ID; without a memory (the tests) it lasts as long as this object
        self.latest: Update | None = None                       # the answer, while it names a version newer than ours
        self.hf_dial = ""                                       # the HF dial the page named last (kept in the row HF_DIAL); empty: none yet, the built-in one stands
        self.dial_changed: Signal[[str]] = Signal("update.dial_changed")     # the HF dial the page names changed (and at the start, the one kept): the HF box shows it
        self._tasks = TaskSet(log, "update")
        self._asking = asyncio.Lock()                           # one question at a time, whoever asks

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    async def start(self) -> None:
        if not self._tasks:
            self._tasks.spawn(self._run(), "update-check")

    async def _kept_dial(self) -> None:
        """The HF dial the page named before this start, from the row HF_DIAL, told before the page is asked (inside the task: the start of the daemon does not wait for the database)."""
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

    async def sent_id(self) -> str:
        """What the question carries as `id`: the number of this installation, or `NOT_COUNTED_ID` for a run from the source tree and while the row NOT_COUNTED is true. The installation's own number is made and kept all the same, so that it is the one sent again when the row is taken away (the row is read at each question)."""
        number = await self.install_id()
        if self.developer:
            return NOT_COUNTED_ID
        marked = None if self._memory is None else await self._memory.setting(NOT_COUNTED)
        try:
            return NOT_COUNTED_ID if marked is not None and boolean(marked) else number
        except ValueError:
            return number

    async def _ask(self) -> tuple[Update | None, str]:
        """(the answer of the page, ''), or (None, why not)."""
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
        """Asks the page now; the newer version it names, else None. `latest` follows the answer; an answer that did not come leaves it as it was."""
        async with self._asking:
            answer, reason = await self._ask()
            if answer is None:
                log.debug("the update check got no usable answer from %s: %s", self._config().update_url, reason)
                return None
            await self._take_dial(answer.hf_dial)
            return self._take(answer)

    async def _take_dial(self, dial: str) -> None:
        """The HF dial of an answer, when it names one and it is another than the one known: kept, logged and told. An answer without one changes nothing (the last one stands)."""
        if not dial or dial == self.hf_dial:
            return
        log.info("the version page names the HF dial %s (was %s)", dial, self.hf_dial or "the built-in one")
        self.hf_dial = dial
        if self._memory is not None:
            await self._memory.put_settings({HF_DIAL: dial})
        self.dial_changed.emit(dial)

    async def release_notes(self, version: str, since: str = "") -> tuple[list[Section], str]:
        """What is new up to `version`, which must be the newer one the check found or our own (a page asks for no other address): the sections of the changelog at its tag of the versions newer than `since` and not newer
        than `version`, the newest first. Without `since` it is ours for the newer version (what an update to it brings) and, for our own, only the section of our version (what the update we have had brought); a page that
        remembers the version it last saw gives that one, so that an update over several versions shows all of them. The changelog of a tag is fetched once and kept; ([], why) when there are none to give."""
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
        """The same question on request, whether the daily check is on or not; `latest` follows the answer, and the timer of the daily check is not touched."""
        async with self._asking:
            answer, reason = await self._ask()
            if answer is None:
                return CheckResult("no_answer", reason=reason)
            newer = self._take(answer)
            return CheckResult("newer", newer.version) if newer is not None else CheckResult("current", self.version)
