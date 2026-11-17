"""Tune, the keying test and the transmit level of a radio of the Sound card type, the half of the modem part (direwolfmodem.py, whose `DirewolfModem` inherits this) that runs Direwolf's own calibration runs
(`-x`, direwolf.c:1056-1110): the radio's Direwolf is stopped cleanly (its input closed), the run keys the radio and sends (the alternating mark and space tones for Tune, the PTT alone for the keying test, the mark
tone for a radio on VOX, which silence does not key) until the daemon closes its input after TUNE_SEC or KEY_TEST_SEC, and the radio's Direwolf is started again on the same KISS port. The hold is on meanwhile
(`test` is what is on), so the services wait as for any radio that is not free. A change of the transmit level starts the program again with it (`-G`): the tune tones too. Each press of the page's - and + is a
change of the setting, so the start waits until the presses have ended (SETTLE_SEC after the last): several presses in a row are one start, not one each, each of which leaves the radio deaf for seconds.

Every swap of the program (a test, its end, a new level) is one at a time, first lets the radio's Direwolf send the frames the line handed it (a stop would lose them), and is given up when the radio was
stopped or started again while it waited: a run started after that would be left beside the radio's own, keying it with no one to stop it. A class of its own for its size alone: it reads and sets the modem's
state and asks it to start its program, which the modem part provides; the hold and the status words, which say the test, are here too."""
import asyncio
import logging
import time

from .childprogram import Command
from .coded import CodedError, Reason
from .direwolf import KEY_TEST_SEC, MODE, TUNE_SEC, TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from .direwolfprogram import Program
from .mercury import Keying
from .signal import Signal
from .tasks import TaskSet, cancel_all

log = logging.getLogger("neoaprs.direwolf")

TRANSMITTING = Reason("the radio is transmitting", "radio.transmitting")
DRAIN_SEC = 5.0                        # how long a test or a new transmit level waits for the frames the radio's Direwolf holds (a busy channel, its slot time and persistence) before it stops it all the same
DRAIN_POLL_SEC = 0.05
SETTLE_SEC = 1.0                       # how long after the latest change of the transmit level the program is started again with it: the presses of - and + in a row are one start
NOT_RUNNING = "the radio is not running"


def clamp(gain_db: int) -> int:
    """The transmit gain within what Direwolf's level takes (TX_GAIN_MIN_DB to TX_GAIN_MAX_DB)."""
    return max(TX_GAIN_MIN_DB, min(TX_GAIN_MAX_DB, int(gain_db)))


class Tuning:
    state: str
    problem: str
    test: str
    keyed: bool
    busy: bool
    keying: Keying
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
    _gain_asks = 0                         # the changes of the transmit level so far: a start waits for the latest

    def _program_to_run(self) -> Command | None:
        raise NotImplementedError

    async def _run(self, program: Command, test: str = "") -> None:
        raise NotImplementedError

    async def tune(self) -> None:
        """The alternating tones for TUNE_SEC, or until `tune_stop`. CodedError when the radio is not running (`hf.not_running`) or a frame is on the air (`hf.held`)."""
        await self._begin("tune", TUNE_SEC)

    async def key_test(self) -> None:
        """The radio keyed for KEY_TEST_SEC: the PTT alone, the mark tone for a radio on VOX. The same refusals as `tune`."""
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
            log.info("Direwolf: %s for %g s (keyed by %s)", "the tune tones" if test == "tune" else "the keying test", seconds, self.keying.text)
            if not await self._stopped(drain):                       # (the radio's Direwolf ends cleanly: the calibration run takes its sound card)
                return
            await self._run(program, test)
            self._test_task = self._tasks.spawn(self._end_after(seconds, self._generation), "direwolf-test")

    async def _stopped(self, drain: bool) -> bool:
        """The program stopped cleanly, the radio's Direwolf first given the frames it holds to send (`drain`); whether the radio is still this swap's: not when it was stopped, started again or ended meanwhile,
        whose own start then has the sound card (nothing more is started here, so that no run is left beside it)."""
        generation = self._generation
        if drain:
            await self._drained()
        if generation == self._generation:
            await asyncio.to_thread(self._program.stop)
        if generation != self._generation or self.state not in ("starting", "running"):
            log.info("Direwolf: the radio was stopped or started again meanwhile: the swap is given up")
            return False
        self.keyed = self.busy = False
        self._starting_since = time.monotonic()                      # (down until the next run listens: starting())
        return True

    async def _drained(self) -> None:
        """Waits, DRAIN_SEC at most, until every frame the line handed the radio's Direwolf has gone: it keyed after the last of them and is unkeyed again (Direwolf holds a frame until the channel is clear, and
        a stop would lose it). The hold is on meanwhile (`test`), so the line hands no more."""
        loop = asyncio.get_running_loop()
        until = loop.time() + DRAIN_SEC
        while (self.keyed or self._keyed_upto < self._handed) and loop.time() < until:
            await asyncio.sleep(DRAIN_POLL_SEC)
        if self.keyed or self._keyed_upto < self._handed:
            log.warning("Direwolf: %d frames handed to it had not gone after %g s; it is stopped all the same", self._handed - self._keyed_upto, DRAIN_SEC)

    def hold(self) -> str:
        """Why no frame is to go now: a calibration run has the radio, or is waiting for the frames handed before it to go; "" when one may (Direwolf queues our frames and listens before it transmits)."""
        return TRANSMITTING if self.test else ""

    def describe(self) -> str:
        """The modem in a few words, for the radio's status line: "Direwolf AFSK1200, listening". The ports are the log's business."""
        if self.state == "waiting":
            return f"Direwolf {MODE}: {self.problem}"
        if self.test:
            return f"Direwolf {MODE}, {'tuning' if self.test == 'tune' else 'keyed'}"
        if self.state != "running":
            return f"Direwolf {MODE}, {self.state}"
        return f"Direwolf {MODE}, {'transmitting' if self.keyed else 'channel busy' if self.busy else 'listening'}"

    async def tune_stop(self) -> None:
        """Ends the tones or the test early; nothing when none is on."""
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
        """The calibration run ended (its input closed: Direwolf unkeys) and the radio's Direwolf started again on its port."""
        if not await self._stopped(drain=False):
            return
        log.info("Direwolf: %s ended", "the tune tones" if self.test == "tune" else "the keying test")
        self.test, self._after_test = "", True
        self.changed.emit()
        if (program := self._program_to_run()) is not None:
            await self._run(program)

    def set_tx_gain(self, gain_db: int) -> None:
        """The transmit level of the settings: a change starts the program again with it (a gap of about a second, Direwolf's cleanup), the tune tones too, once no other change has come for SETTLE_SEC; the
        keying test is left to end (the radio's Direwolf after it has the new level)."""
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
            return                                                       # (a later change starts it, or the radio was started again meanwhile, with the level)
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
