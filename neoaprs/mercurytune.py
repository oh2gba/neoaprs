"""Tune and the keying test of the Mercury HF modem, the half of the modem part (mercurymodem.py, whose `Mercury` inherits this) that drives Mercury's own TUNE command on the control port: the radio is keyed through
the keying the modem runs with and the tone goes through its sound card, for TUNE_SEC or until the operator presses again, or for the second of the keying test; the hold is on meanwhile (`test` is what is on, and
`hold` reads it), so no frame of ours goes under the tone, and Mercury unkeys by itself after a minute whatever happens to us (mercury.py says what the levels and the times are and why). A class of its own for its
size alone: it reads and sets the modem's state (`test`, `speaker`, `keying`, `changed`, the tasks and the generation of the start) and asks it whether it runs, what holds it and to write a line, which the modem
part provides."""
import asyncio
import logging

from .coded import CodedError
from .mercury import KEY_TEST_SEC, TUNE_LEVEL_DBFS, TUNE_OFF, TUNE_SEC, Keying, key_test_level, tune_command
from .signal import Signal
from .tasks import TaskSet, cancel_all

log = logging.getLogger("neoaprs.mercury")

NOT_RUNNING = "the HF radio is not running"


class Tuning:
    test: str                              # one of mercurymodem.TESTS: the tune tone or the keying test is on (the hold is on with it)
    speaker: bool                          # started as the speaker of the Dummy HF radio: nothing is keyed, Tune is refused
    keying: Keying
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
        """Why the tone cannot start now: the modem is not running, or a frame is on the air or the channel is busy; "" when it can."""
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
                raise CodedError("the HF radio is not running", "hf.not_running")
            raise CodedError(f"the radio is not free: {why}", "hf.held", reason=why)
        await self._cancel_test()
        if not self._write(tune_command(level_dbfs)):
            log.info("Mercury: %s was refused: the control port is not open", name)
            raise CodedError("the HF radio is not running", "hf.not_running")
        self.test = test
        log.info("Mercury: %s for %g s (%g dBFS, keyed by %s)", name, seconds, level_dbfs, self.keying.text)
        self._test_task = self._tasks.spawn(self._end_after(seconds, self._generation), "mercury-test")
        self.changed.emit()

    async def tune(self) -> None:
        """Keys the radio with the tune tone through the sound card and the keying in use, for TUNE_SEC or until `tune_stop`. CodedError when the modem is not running (`hf.not_running`) or the radio is not free (`hf.held`)."""
        await self._begin("tune", TUNE_LEVEL_DBFS, TUNE_SEC)

    async def key_test(self) -> None:
        """Keys the radio for KEY_TEST_SEC, so that the operator sees it go to transmit and come back: with next to no audio where the keying is a line (RTS, DTR, CM108), with the tune tone where the radio keys on audio
        (VOX: a silent test would leave it in receive). The same refusals as `tune`."""
        await self._begin("key", key_test_level(self.keying.kind), KEY_TEST_SEC)

    async def tune_stop(self) -> None:
        """Ends the tone or the test early; nothing when none is on."""
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
