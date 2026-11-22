"""Tune and the keying test of the Mercury HF modem.

The half of `Mercury` (mercurymodem.py) that drives Mercury's TUNE command; no frame is sent
while a test is on.
"""
import asyncio
import logging

from .coded import CodedError, code_of
from .mercury import KEY_TEST_SEC, TUNE_OFF, TUNE_SEC, Keying, key_test_level, tune_command, tune_level
from .signal import Signal
from .tasks import TaskSet, cancel_all

log = logging.getLogger("neoaprs.mercury")

NOT_RUNNING = "the Mercury radio is not running"


class Tuning:
    # one of mercurymodem.TESTS
    test: str
    # the Dummy HF radio's speaker: Tune is refused
    speaker: bool
    keying: Keying
    tx_gain_db: int  # the tune tone follows it
    changed: Signal[[]]
    _tasks: TaskSet
    _generation: int
    _test_task: asyncio.Task[None] | None

    @property
    def running(self) -> bool:
        raise NotImplementedError

    def hold(self) -> str:
        raise NotImplementedError

    def _write(self, line: str) -> bool:
        raise NotImplementedError

    def _refusal(self) -> str:
        """Return why the tone cannot start now, else ""."""
        if not self.running or self.speaker:
            return NOT_RUNNING
        if self.test:
            return ""
        return self.hold()

    async def _begin(self, test: str, level_dbfs: float, seconds: float) -> None:
        name = "the tune tone" if test == "tune" else "the keying test"
        if why := self._refusal():
            log.info("Mercury: %s was refused: %s", name, why)
            if why == NOT_RUNNING:
                raise CodedError("the Mercury radio is not running", "hf.not_running")
            # the page says which by `held`
            raise CodedError(f"the radio is not free: {why}", "hf.held", held="busy" if code_of(why)[0] == "radio.channel_busy" else "transmitting")
        await self._cancel_test()
        if not self._write(tune_command(level_dbfs)):
            log.info("Mercury: %s was refused: the control port is not open", name)
            raise CodedError("the Mercury radio is not running", "hf.not_running")
        self.test = test
        log.info("Mercury: %s for %g s (%g dBFS, keyed by %s)", name, seconds, level_dbfs, self.keying.text)
        self._test_task = self._tasks.spawn(self._end_after(seconds, self._generation), "mercury-test")
        self.changed.emit()

    async def tune(self) -> None:
        """Key the radio with the tune tone for TUNE_SEC or until `tune_stop`.

        Raise CodedError if not running (`hf.not_running`) or not free (`hf.held`).
        """
        await self._begin("tune", tune_level(self.tx_gain_db), TUNE_SEC)

    async def _retune(self) -> None:
        """Restart the tone at the new transmit gain.

        Mercury refuses a TUNE while one runs, so the tone is ended and begun again.
        """
        if self.test != "tune":
            return
        level = tune_level(self.tx_gain_db)
        if not (self._write(TUNE_OFF) and self._write(tune_command(level))):
            return
        log.info("Mercury: the tune tone follows the transmit gain to %g dBFS", level)
        await self._cancel_test()
        self._test_task = self._tasks.spawn(self._end_after(TUNE_SEC, self._generation), "mercury-test")

    async def key_test(self) -> None:
        """Key the radio for KEY_TEST_SEC; silent for a keying line, the tune tone for VOX.

        Refusals are those of `tune`.
        """
        await self._begin("key", key_test_level(self.keying.kind), KEY_TEST_SEC)

    async def tune_stop(self) -> None:
        """End the tone or the test early; do nothing when none is on."""
        if not self.test:
            return
        await self._cancel_test()
        self._end()

    async def _cancel_test(self) -> None:
        task, self._test_task = self._test_task, None
        if task is not None and task is not asyncio.current_task():
            await cancel_all([task])

    def _end(self) -> None:
        self._write(TUNE_OFF)
        if self.test:
            log.info("Mercury: %s ended", "the tune tone" if self.test == "tune" else "the keying test")
        self.test = ""
        self.changed.emit()

    async def _end_after(self, seconds: float, generation: int) -> None:
        await asyncio.sleep(seconds)
        self._test_task = None
        if generation == self._generation:
            self._end()
