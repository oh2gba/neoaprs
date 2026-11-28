"""Tune, keying test and transmit level of a Sound card radio (half of `DirewolfModem`).

A calibration run (`-x`) swaps the program: stop it, run the test, restart on the same KISS port.
A swap lets held frames go first and is given up if the radio was stopped or restarted meanwhile.
"""

import asyncio
import logging
import time

from .childprogram import Command
from .coded import CodedError, Reason
from .direwolf import KEY_TEST_SEC, TUNE_SEC, TX_GAIN_MAX_DB, TX_GAIN_MIN_DB, mode_of
from .direwolfprogram import Program
from .mercury import Keying
from .signal import Signal
from .tasks import TaskSet, cancel_all

log = logging.getLogger("neoaprs.direwolf")

TRANSMITTING = Reason("the radio is transmitting", "radio.transmitting")
# Time for Direwolf to send held frames (busy channel) before it is stopped.
DRAIN_SEC = 5.0
DRAIN_POLL_SEC = 0.05
# Quiet time after the latest gain change before the restart; presses in a row restart once.
SETTLE_SEC = 1.0
NOT_RUNNING = "the radio is not running"


def clamp(gain_db: int) -> int:
    """Return the gain limited to TX_GAIN_MIN_DB..TX_GAIN_MAX_DB."""
    return max(TX_GAIN_MIN_DB, min(TX_GAIN_MAX_DB, int(gain_db)))


class Tuning:
    state: str
    problem: str
    test: str
    keyed: bool
    busy: bool
    keying: Keying
    baud: int
    tx_gain_db: int
    changed: Signal[[]]
    _program: Program
    _tasks: TaskSet
    _generation: int
    _after_test: bool
    _starting_since: float
    _test_task: asyncio.Task[None] | None
    _swapping: asyncio.Lock
    _handed: int
    _keyed_upto: int
    _gain_asks = 0  # count of gain changes; a restart waits for the latest

    def _program_to_run(self) -> Command | None:
        raise NotImplementedError

    def _rig_holds(self) -> Reason | str:
        raise NotImplementedError

    async def _run(self, program: Command, test: str = "") -> None:
        raise NotImplementedError

    async def tune(self) -> None:
        """Send the alternating tones for TUNE_SEC; raise CodedError unless the radio is running."""
        await self._begin("tune", TUNE_SEC)

    async def key_test(self) -> None:
        """Key the radio for KEY_TEST_SEC (mark tone on VOX); refuses as `tune` does."""
        await self._begin("key", KEY_TEST_SEC)

    async def _begin(self, test: str, seconds: float) -> None:
        program = self._program_to_run()
        if program is None or (self.state != "running" and not self.test):
            raise CodedError(NOT_RUNNING, "hf.not_running")
        if self.keyed and not self.test:
            raise CodedError(f"the radio is not free: {TRANSMITTING}", "hf.held", held="transmitting")
        async with self._swapping:
            await self._cancel_test()
            drain, self.test = not self.test, test
            self.changed.emit()
            log.info(
                "Direwolf: %s for %g s (keyed by %s)",
                "the tune tones" if test == "tune" else "the keying test",
                seconds,
                self.keying.text,
            )
            if not await self._stopped(drain):  # the calibration run takes over the sound card
                return
            await self._run(program, test)
            self._test_task = self._tasks.spawn(self._end_after(seconds, self._generation), "direwolf-test")

    async def _stopped(self, drain: bool) -> bool:
        """Stop the program, first letting it send held frames if `drain`.

        Return False if the radio was stopped or restarted meanwhile: that start owns the card."""
        generation = self._generation
        if drain:
            await self._drained()
        if generation == self._generation:
            await asyncio.to_thread(self._program.stop)
        if generation != self._generation or self.state not in ("starting", "running"):
            log.info("Direwolf: the radio was stopped or started again meanwhile: the swap is given up")
            return False
        self.keyed = self.busy = False
        self._starting_since = time.monotonic()  # down until the next run listens
        return True

    async def _drained(self) -> None:
        """Wait up to DRAIN_SEC until every frame handed to Direwolf has been sent."""
        loop = asyncio.get_running_loop()
        until = loop.time() + DRAIN_SEC
        while (self.keyed or self._keyed_upto < self._handed) and loop.time() < until:
            await asyncio.sleep(DRAIN_POLL_SEC)
        if self.keyed or self._keyed_upto < self._handed:
            log.warning(
                "Direwolf: %d frames handed to it had not gone after %g s; it is stopped all the same",
                self._handed - self._keyed_upto,
                DRAIN_SEC,
            )

    def hold(self) -> str:
        """Return why no frame may go now (a calibration run has the radio), or ""."""
        return TRANSMITTING if self.test else ""

    def frame_hold(self) -> Reason | str:
        return self._rig_holds() or self.hold()

    def refuses_line(self) -> str:
        """Direwolf's line is opened whenever it listens."""
        return ""

    def describe(self) -> str:
        """Return the status line, for example "Direwolf AFSK1200, listening"."""
        mode = mode_of(self.baud)
        if self.state == "waiting":
            return f"Direwolf {mode}: {self.problem}"
        if self.test:
            return f"Direwolf {mode}, {'tuning' if self.test == 'tune' else 'keyed'}"
        if self.state != "running":
            return f"Direwolf {mode}, {self.state}"
        return f"Direwolf {mode}, {'transmitting' if self.keyed else 'channel busy' if self.busy else 'listening'}"

    async def tune_stop(self) -> None:
        """End the tones or the test early; do nothing if none is on."""
        async with self._swapping:
            if self.test:
                await self._cancel_test()
                await self._finish_test()

    async def _cancel_test(self) -> None:
        task, self._test_task = self._test_task, None
        if task is not None and task is not asyncio.current_task():
            await cancel_all([task])

    async def _end_after(self, seconds: float, generation: int) -> None:
        await asyncio.sleep(seconds)
        async with self._swapping:
            self._test_task = None
            if generation == self._generation and self.test:
                await self._finish_test()

    async def _finish_test(self) -> None:
        """End the calibration run (closing the input unkeys) and restart Direwolf on its port."""
        if not await self._stopped(drain=False):
            return
        log.info("Direwolf: %s ended", "the tune tones" if self.test == "tune" else "the keying test")
        self.test, self._after_test = "", True
        self.changed.emit()
        if (program := self._program_to_run()) is not None:
            await self._run(program)

    def set_tx_gain(self, gain_db: int) -> None:
        """Set the transmit level and restart the program once no change has come for SETTLE_SEC.

        A running keying test is left to end."""
        gain = clamp(gain_db)
        if gain == self.tx_gain_db:
            return
        self.tx_gain_db = gain
        self._gain_asks += 1
        if self.test == "tune" or (not self.test and self.state in ("starting", "running")):
            self._tasks.spawn(self._again(self._gain_asks, self._generation), "direwolf-gain")

    async def _again(self, ask: int, generation: int) -> None:
        await asyncio.sleep(SETTLE_SEC)
        program = self._program_to_run()
        if program is None or ask != self._gain_asks or generation != self._generation:
            # a later change restarts it, or a restart already used the new level
            return
        async with self._swapping:
            test = self.test
            if test == "key" or not await self._stopped(drain=not test):
                return
            if test:
                await self._run(program, test)
                await self._cancel_test()
                self._test_task = self._tasks.spawn(self._end_after(TUNE_SEC, self._generation), "direwolf-test")
            else:
                self._after_test = True
                await self._run(program)
