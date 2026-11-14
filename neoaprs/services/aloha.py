"""The ALOHA circle of our station (neoaprs/aloha.py has the method), kept up to date: worked out at the start, once a minute, and when the settings move our position. `radius_km` is the latest value, in
tenths of a kilometre; `changed` is emitted when it differs from the one before. None while our position is not known or the stations heard do not fill the channel.

The circle the map draws is the main radio's (plan rule 3.8): worked out from the stations the main radio heard, while its type says it shares a 1200 baud channel (`Allowed.shared_channel`: an FM radio);
none while the main radio's does not (an HF radio) or there is no radio. Given no radios (`main` None: a test's), every station heard on the air counts, as before the radios were by id."""
import logging
from collections.abc import Callable

from neoaprs.aloha import Circle, circle
from neoaprs.clock import Clock, utcnow
from neoaprs.policy import ALOHA_EVERY_SEC
from neoaprs.services.radioset import AirRadio
from neoaprs.signal import Signal
from neoaprs.stationbook import StationBook
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.aloha")


class Aloha:
    def __init__(self, book: StationBook, clock: Clock = utcnow, every_sec: float = ALOHA_EVERY_SEC, *, main: Callable[[], AirRadio | None] | None = None) -> None:
        self._book = book
        self._main = main                                     # the main radio now (the registry's `main`); None: no radios given, every station of the air counts
        self._clock = clock
        self.every_sec = every_sec
        self.changed: Signal[[]] = Signal("aloha.changed")
        self.radius_km: float | None = None
        self._tasks = TaskSet(log, "aloha")

    async def start(self) -> None:
        self.refresh()
        if not self._tasks:
            self._tasks.spawn(self._run(), "aloha")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await every(self.every_sec, self.refresh, "the ALOHA circle")

    def refresh(self) -> None:
        """Works the circle out from the stations as they are now."""
        found = self._found()
        radius = None if found is None else round(found.radius_km, 1)
        if radius != self.radius_km:
            self.radius_km = radius
            self.changed.emit()

    def _found(self) -> Circle | None:
        if self._main is None:
            return circle(self._book.me_position, self._book.stations(), self._clock())
        radio = self._main()
        if radio is None or not radio.allowed.shared_channel:
            return None
        return circle(self._book.me_position, self._book.stations(), self._clock(), radio.id)
