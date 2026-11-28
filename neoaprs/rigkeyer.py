"""Key a radio through a rig program as its modem says PTT ON and PTT OFF.

One task brings the rig to what is wanted, one command at a time: a key-down never lasts past its
limit, a key-up is repeated until the program confirms it, and the program is asked while idle.
"""

import asyncio
import logging
import math
import time
from collections.abc import Callable

from .coded import Reason
from .rigptt import Ptt, RigRefused
from .tasks import TaskSet

log = logging.getLogger("neoaprs.rig")

RIG_SILENT = Reason("the rig program does not answer", "radio.rig_silent")
PROBLEMS = ("", "rig_silent", "rig_keyed_long")
PROBE_SEC = 10.0
RETRY_SEC = (0.2, 0.5, 1.0, 2.0, 5.0)
SHOUT_SEC = 60.0  # an unconfirmed key-up is logged again this often
STOP_SEC = 5.0


class RigKeyer:
    """Follows `key(on, limit_sec)`; `problem` is a code of PROBLEMS, `holds()` why no frame may go."""

    def __init__(self, ptt: Ptt, changed: Callable[[], None], monotonic: Callable[[], float] = time.monotonic) -> None:
        self.ptt, self._changed, self.monotonic = ptt, changed, monotonic
        self.want = False
        self.state: bool | None = None  # what the program confirmed last; None: not known
        self.answering: bool | None = None
        self.failing = False  # the latest command was refused or not answered
        self.keyed_long = False
        self.maybe_keyed = False  # a key-down was sent and no key-up confirmed since
        self.key_downs = 0
        self.latency_sec: float | None = None  # of the latest key-down: asked to confirmed
        self._deadline = math.inf
        self._asked_at = 0.0
        self._shouted = -math.inf
        self._wake = asyncio.Event()
        self._tasks = TaskSet(log, "rig")

    def describe(self) -> str:
        return self.ptt.describe()

    def start(self) -> None:
        self._tasks.spawn(self._drive(), "rig-drive")
        self._tasks.spawn(self._probe_every(), "rig-probe")

    @property
    def problem(self) -> str:
        if self.failing or self.answering is False:
            return "rig_silent"
        return "rig_keyed_long" if self.keyed_long else ""

    def holds(self) -> Reason | str:
        """Return why no frame may go: the program does not answer, or the rig's state is not known."""
        return RIG_SILENT if self.failing or self.answering is not True or self.state is None else ""

    def key(self, on: bool, limit_sec: float = math.inf) -> None:
        """Key down for at most `limit_sec`, or key up."""
        if on == self.want:
            return
        now = self.monotonic()
        self.want = on
        if on:
            self._deadline, self._asked_at = now + limit_sec, now
        elif self.keyed_long:
            self.keyed_long = False  # a key-down the modem ended itself
            self._changed()
        self._wake.set()

    def extend(self, seconds: float) -> None:
        """Let the key-down under way last `seconds` longer."""
        if self.want:
            self._deadline += seconds
            self._wake.set()

    async def stop(self) -> None:
        """Stop following; key up and wait for the confirmation for up to STOP_SEC."""
        await self._tasks.cancel_all()
        self.want = False
        if self.state is False or not self.maybe_keyed:
            return
        end = self.monotonic() + STOP_SEC
        for pause in (*RETRY_SEC, *([RETRY_SEC[-1]] * 100)):
            try:
                await self.ptt.set(False)
                self.state = False
                log.info("%s: key-up confirmed", self.describe())
                return
            except RigRefused as e:
                why = str(e)
            if self.monotonic() + pause >= end:
                break
            await asyncio.sleep(pause)
        log.error(
            "the radio may still be keyed: %s did not confirm the key-up before NeoAPRS stopped keying through it (%s)",
            self.describe(),
            why,
        )

    async def _drive(self) -> None:
        retries = 0
        while True:
            if self.want and self.monotonic() >= self._deadline:
                self._dead_man()
            if self.state == self.want:
                await self._settled()
                continue
            target = self.want
            if target:
                self.state, self.maybe_keyed = None, True  # a key-down cut short may have keyed the rig
            try:
                await self.ptt.set(target)
            except RigRefused as e:
                self.state = None
                if target and e.answered:
                    self.maybe_keyed = False  # the program said the rig is not keyed
                self._refused(target, str(e))
                if target:
                    self.want = False  # the rig may have keyed late
                else:
                    await asyncio.sleep(RETRY_SEC[min(retries, len(RETRY_SEC) - 1)])
                    retries += 1
                continue
            retries = 0
            self.state = target
            self._confirmed(target)

    async def _settled(self) -> None:
        """Wait for a change of what is wanted, or for the end of the key-down's time."""
        self._wake.clear()
        try:
            async with asyncio.timeout(self._deadline - self.monotonic() if self.want else None):
                await self._wake.wait()
        except TimeoutError:
            pass

    def _dead_man(self) -> None:
        log.error(
            "the radio was keyed for longer than its frame and the modem has not ended it: key-up is sent to %s",
            self.describe(),
        )
        self.want, self.keyed_long = False, True
        self._changed()

    def _refused(self, target: bool, why: str) -> None:
        was = self.problem
        self.failing, self.answering = True, False
        now = self.monotonic()
        if target:
            log.warning(
                "%s did not key the radio (%s): the frame goes out unheard, and frames wait until it answers",
                self.describe(),
                why,
            )
        elif not self.maybe_keyed:
            if was != "rig_silent":
                log.warning("%s does not answer (%s): frames for the radio wait until it does", self.describe(), why)
        elif now - self._shouted >= SHOUT_SEC:
            self._shouted = now
            log.error(
                "the radio may still be keyed: %s did not confirm the key-up (%s); it is asked again",
                self.describe(),
                why,
            )
        if self.problem != was:
            self._changed()

    def _confirmed(self, target: bool) -> None:
        was, unconfirmed = self.problem, self.failing and self.maybe_keyed and not target
        self.failing, self.answering = False, True
        self.maybe_keyed = self.maybe_keyed and target
        if target:
            self.key_downs += 1
            self.latency_sec = self.monotonic() - self._asked_at
            log.debug("%s keyed the radio in %.3f s", self.describe(), self.latency_sec)
        elif unconfirmed:
            self._shouted = -math.inf
            log.warning("%s confirmed the key-up", self.describe())
        if self.problem != was:
            self._changed()

    async def _probe_every(self) -> None:
        while True:
            if not self.want and self.state is False:
                await self._probe()
            await asyncio.sleep(PROBE_SEC)

    async def _probe(self) -> None:
        try:
            await self.ptt.probe()
        except RigRefused as e:
            if self.answering is not False:
                log.warning("%s does not answer (%s): frames for the radio wait until it does", self.describe(), e)
                self.answering = False
                self._changed()
            return
        if self.answering is not True:
            log.info("%s answers", self.describe())
            self.answering = True
            self._changed()
