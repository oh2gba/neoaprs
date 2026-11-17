"""The sound card's own levels of one radio (soundmixer.py), the part its driver keeps beside the modem (the Sound card type's Direwolf, the Mercury modem): what the card's playback and capture controls are
now, for the radio's row (the page draws a slider only where the card has the control, at the card's own level), and the operator's two values of the radio's settings (`tx_card`, `rx_card`) put on the card.

The values are put back at every start of the radio's modem (its program's `starts` moved: a start, a start again after it died, a card plugged in again), because the desktop's sound system and a replug move
the same controls; a value the operator never set (None) is never written, so that the card stays as the system has it. A change of a value is set at once, and restarts nothing: the modem keeps its sound
card open. While the radio runs the card is read every POLL_SEC, so that the row follows what the desktop's mixer does to it.

The card is the modem's (the one it runs on: the settings', or its own choice); "" (the Dummy radio's, a Mercury something else runs) has no levels. The mixer is called on a thread, one call at a time. The
system's mixer is `SystemMixer` (ALSA on Linux, Core Audio on Windows, none elsewhere and none under the no-devices switch); a test gives its own."""
import asyncio
import logging
import sys
from collections.abc import Callable

from . import nodevices, soundmixer
from .signal import Signal
from .soundmixer import NONE, Levels, Mixer
from .tasks import TaskSet, every
from .winmixer import Windows

log = logging.getLogger("neoaprs.soundmixer")

POLL_SEC = 2.0
NO_DEVICES = "the sound cards' own levels are not read or set"


class CardLevels:
    def __init__(self, card: Callable[[], str], starts: Callable[[], int], mixer: Mixer | None = None) -> None:
        self._card, self._starts = card, starts              # the modem's card now, and how many times its program was started
        self._mixer = mixer or SystemMixer()
        self.levels = NONE                                   # the card's controls as they were read last (kept while the radio is stopped: the row keeps its sliders)
        self._of = ""                                        # the card they are of
        self.changed: Signal[[]] = Signal("cardlevels.changed")
        self._wanted: tuple[int | None, int | None] = (None, None)      # the operator's values of the settings (None: never set)
        self._put_on: tuple[str, int] | None = None          # the card and the start of the modem the values were put on last
        self._asked: dict[str, tuple[int, int]] = {}         # by way, the percent set last and the one the card said after it: a control with fewer steps than 100 says the one asked while it holds the step
        self._lock = asyncio.Lock()
        self._tasks = TaskSet(log, "card levels")

    async def start(self, tx: int | None, rx: int | None) -> None:
        """The radio was started: its values are put on the card once the modem has one, and the card is read while it runs."""
        await self._tasks.cancel_all()
        self._wanted, self._put_on = (tx, rx), None
        await self.round()
        self._tasks.spawn(every(POLL_SEC, self.round, "the sound card's levels"), "card-levels")

    async def stop(self) -> None:
        """The radio was stopped: the levels read last stay on its row, so that its Transmit level row does not become the modem's own while it is off; a value moved meanwhile is put on at its start."""
        await self._tasks.cancel_all()
        self._put_on, self._asked = None, {}

    def want(self, tx: int | None, rx: int | None) -> None:
        """The operator's values as the settings have them now: a value that changed is set on the card at once."""
        before, self._wanted = self._wanted, (tx, rx)
        if (tx, rx) != before and self._put_on is not None:
            self._tasks.spawn(self._write(tx if tx != before[0] else None, rx if rx != before[1] else None), "card-levels-set")

    async def round(self) -> None:
        """One look at the card: the values put on it after a start of the modem (or on a card it moved to), else the card read."""
        card, starts = self._card(), self._starts()
        if card and (card, starts) != self._put_on:
            self._put_on, self._asked = (card, starts), {}
            if self._wanted != (None, None):
                log.info("the sound card %s is set to the radio's levels (playback %s, capture %s)", card, *(f"{v} %" if v is not None else "as it is" for v in self._wanted))
            await self._write(*self._wanted)
        elif card:
            self._show(self._said(await self._call(lambda: self._mixer.read(card))), card)

    async def _write(self, tx: int | None, rx: int | None) -> None:
        card = self._card()
        levels = await self._call(lambda: self._mixer.write(card, tx, rx) if card else NONE)
        for way, value, now in (("tx", tx, levels.tx), ("rx", rx, levels.rx)):
            if value is not None and now is not None:
                self._asked[way] = (value, now)
        self._show(self._said(levels), card)

    async def _call(self, mixer_call: Callable[[], Levels]) -> Levels:
        async with self._lock:
            return await asyncio.to_thread(mixer_call)

    def _said(self, levels: Levels) -> Levels:
        """The levels as the row says them: the percent asked last where the card still holds the step it took for it."""
        tx, rx = levels.tx, levels.rx
        if (asked := self._asked.get("tx")) is not None and asked[1] == tx:
            tx = asked[0]
        if (asked := self._asked.get("rx")) is not None and asked[1] == rx:
            rx = asked[0]
        return Levels(tx, rx)

    def _show(self, levels: Levels, card: str) -> None:
        """The levels read of `card` on the row; a control of the same card that could not be read now (unplugged, a failed call: none on this card) keeps the value read last, so that a slider comes and goes
        only with another card."""
        if not card:
            return
        if card == self._of:
            levels = Levels(self.levels.tx if levels.tx is None else levels.tx, self.levels.rx if levels.rx is None else levels.rx)
        self._of = card
        if levels != self.levels:
            self.levels = levels
            self.changed.emit()


class SystemMixer:
    """The mixer of this system: ALSA on Linux, Core Audio on Windows, none elsewhere; nothing at all under the no-devices switch, which is asked at every call."""

    def __init__(self) -> None:
        self._mixer: Mixer | None = None

    def _system(self) -> Mixer | None:
        if nodevices.refused(NO_DEVICES, logging.INFO):
            return None
        if self._mixer is None and sys.platform.startswith("linux"):
            self._mixer = soundmixer.Alsa()
        elif self._mixer is None and sys.platform == "win32":
            self._mixer = Windows()
        return self._mixer

    def read(self, card: str) -> Levels:
        mixer = self._system()
        return NONE if mixer is None or not card else mixer.read(card)

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        mixer = self._system()
        return NONE if mixer is None or not card else mixer.write(card, tx, rx)

