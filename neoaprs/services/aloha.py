"""The ALOHA circles of our station, refreshed at start, every minute and when we move.

One circle for each radio that is on and shares a 1200 baud channel; `changed` is emitted when
`radii` differ from the previous ones.
"""
import logging
from collections.abc import Callable, Iterable, Iterator

from neoaprs.aloha import Circle, circle
from neoaprs.clock import Clock, utcnow
from neoaprs.policy import ALOHA_EVERY_SEC
from neoaprs.radiotype import RadioId
from neoaprs.services.radioset import AirRadio
from neoaprs.signal import Signal
from neoaprs.stationbook import StationBook
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.aloha")


# Key of the single circle when no radios are given: every station heard counts.
AIR: RadioId = 0


class Aloha:
    def __init__(self, book: StationBook, clock: Clock = utcnow, every_sec: float = ALOHA_EVERY_SEC, *, radios: Callable[[], Iterable[AirRadio]] | None = None) -> None:
        self._book = book
        self._radios = radios
        self._clock = clock
        self.every_sec = every_sec
        self.changed: Signal[[]] = Signal("aloha.changed")
        self.radii: dict[RadioId, float] = {}                 # radius in km by radio id; no entry without a circle
        self._tasks = TaskSet(log, "aloha")

    @property
    def radius_km(self) -> float | None:
        """The radius of the first circle, or None."""
        return next(iter(self.radii.values()), None)

    async def start(self) -> None:
        self.refresh()
        if not self._tasks:
            self._tasks.spawn(self._run(), "aloha")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await every(self.every_sec, self.refresh, "the ALOHA circle")

    def refresh(self) -> None:
        """Recompute the circles from the stations now known."""
        radii = {id: round(found.radius_km, 1) for id, found in self._found()}
        if list(radii.items()) != list(self.radii.items()):
            self.radii = radii
            self.changed.emit()

    def _found(self) -> Iterator[tuple[RadioId, Circle]]:
        stations, now, me = self._book.stations(), self._clock(), self._book.me_position
        if self._radios is None:
            if (found := circle(me, stations, now)) is not None:
                yield AIR, found
            return
        for radio in self._radios():
            if radio.allowed.shared_channel and (found := circle(me, stations, now, radio.id)) is not None:
                yield radio.id, found
