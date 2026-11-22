"""Sound card levels of one radio: read the card's controls and set the radio's values on it.

The values of `tx_card` and `rx_card` are put on the card at every modem start and on change;
the card is polled while the radio runs. Playback is the radio's only while `tx_gain_db` is 0.
"""

import asyncio
import logging
import sys
from collections.abc import Callable

from . import nodevices, soundmixer
from .radiospec import RadioSpec
from .signal import Signal
from .soundmixer import NONE, Levels, Mixer
from .tasks import TaskSet, every
from .winmixer import Windows

log = logging.getLogger("neoaprs.soundmixer")

POLL_SEC = 2.0
NO_DEVICES = "the sound cards' own levels are not read or set"


class CardLevels:
    def __init__(
        self,
        card: Callable[[], str],
        starts: Callable[[], int],
        mixer: Mixer | None = None,
        own: Callable[[], bool] = lambda: True,
    ) -> None:
        self._card, self._starts = card, starts  # the modem's card; modem start count
        self._own = own  # whether the radio has a card of its own
        self._mixer = mixer or SystemMixer()
        self._present = self._mixer.present if isinstance(self._mixer, SystemMixer) else lambda: True
        self.levels = NONE  # the controls as read last
        self._of = ""  # the card they are of
        self.read = False  # whether the radio's own card was read in this run
        self._faulted: set[str] = set()  # cards whose mixer call failed
        self.changed: Signal[[]] = Signal("cardlevels.changed")
        self._wanted: tuple[int | None, int | None] = (None, None)  # None: never set
        self._put_on: tuple[str, int] | None = None  # card and modem start of the last write
        # per way: the percent asked and what the card reported (coarse controls round)
        self._asked: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()
        self._tasks = TaskSet(log, "card levels")

    async def start(self, tx: int | None, rx: int | None) -> None:
        """Put the radio's values on the card once the modem has one; poll it while it runs."""
        await self._tasks.cancel_all()
        self._wanted, self._put_on = (tx, rx), None
        try:
            await self.round()
        except Exception:
            log.info("the sound card's own levels could not be looked at", exc_info=True)
        self._tasks.spawn(every(POLL_SEC, self.round, "the sound card's levels"), "card-levels")

    async def stop(self) -> None:
        """Stop polling; the last levels stay."""
        await self._tasks.cancel_all()
        self._put_on, self._asked = None, {}

    @property
    def known(self) -> bool:
        """Return whether the levels are the card's, or there is nothing to wait for."""
        return self.read or not self._own() or not self._present() or (self._starts() > 0 and not self._card())

    def want(self, tx: int | None, rx: int | None) -> None:
        """Set a changed value on the card at once."""
        before, self._wanted = self._wanted, (tx, rx)
        if (tx, rx) != before and self._put_on is not None:
            self._tasks.spawn(
                self._write(tx if tx != before[0] else None, rx if rx != before[1] else None), "card-levels-set"
            )

    async def round(self) -> None:
        """Put the values on the card after a modem start or card change, else read the card."""
        card, starts = self._card(), self._starts()
        if card and (card, starts) != self._put_on:
            self._put_on, self._asked = (card, starts), {}
            if self._wanted != (None, None):
                log.info(
                    "the sound card %s is set to the radio's levels (playback %s, capture %s)",
                    card,
                    *(f"{v} %" if v is not None else "as it is" for v in self._wanted),
                )
            await self._write(*self._wanted)
        elif card:
            self._show(self._said(await self._call(card, lambda: self._mixer.read(card))), card)

    async def _write(self, tx: int | None, rx: int | None) -> None:
        card = self._card()
        levels = await self._call(card, lambda: self._mixer.write(card, tx, rx) if card else NONE)
        for way, value, now in (("tx", tx, levels.tx), ("rx", rx, levels.rx)):
            if value is not None and now is not None:
                self._asked[way] = (value, now)
        self._show(self._said(levels), card)

    async def _call(self, card: str, mixer_call: Callable[[], Levels]) -> Levels:
        """Return the mixer's answer for `card`; no levels (logged once) if the call fails."""
        async with self._lock:
            try:
                return await asyncio.to_thread(mixer_call)
            except Exception:
                if card not in self._faulted:
                    self._faulted.add(card)
                    log.info(
                        "the own levels of the sound card %s could not be had: it has no sliders", card, exc_info=True
                    )
                return NONE

    def _said(self, levels: Levels) -> Levels:
        """Return the levels, showing the percent asked last while the card still holds its step."""
        tx, rx = levels.tx, levels.rx
        if (asked := self._asked.get("tx")) is not None and asked[1] == tx:
            tx = asked[0]
        if (asked := self._asked.get("rx")) is not None and asked[1] == rx:
            rx = asked[0]
        return Levels(tx, rx)

    def _show(self, levels: Levels, card: str) -> None:
        """Show the levels read of `card`; an unreadable control of the same card keeps its value."""
        if not card:
            return
        if card == self._of:
            levels = Levels(
                self.levels.tx if levels.tx is None else levels.tx, self.levels.rx if levels.rx is None else levels.rx
            )
        self._of = card
        if levels != self.levels or not self.read:
            self.levels, self.read = levels, True
            self.changed.emit()


def wanted(spec: RadioSpec) -> tuple[int | None, int | None]:
    """Return the card values: playback only while the modem's transmit gain is 0."""
    return (spec.value("tx_card") if spec.value("tx_gain_db") == 0 else None), spec.value("rx_card")


class SystemMixer:
    """The mixer of this system: ALSA on Linux, Core Audio on Windows, none elsewhere."""

    def __init__(self) -> None:
        self._mixer: Mixer | None = None

    def present(self) -> bool:
        """Return whether this system has a mixer (ALSA on Linux, or Windows) and devices are on."""
        if nodevices.on():
            return False
        mixer = self._system()
        return mixer is not None and (not isinstance(mixer, soundmixer.Alsa) or mixer.present())

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
