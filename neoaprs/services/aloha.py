"""The ALOHA circle of our station (neoaprs/aloha.py has the method), kept up to date: worked out at the start, once a minute, and when the settings move our position. `radius_km` is the latest value, in
tenths of a kilometre; `changed` is emitted when it differs from the one before. None while our position is not known or the stations heard do not fill the channel."""
import asyncio
import logging

from neoaprs.aloha import circle
from neoaprs.clock import Clock, utcnow
from neoaprs.policy import ALOHA_EVERY_SEC
from neoaprs.signal import Signal
from neoaprs.stationbook import StationBook
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.aloha")


class Aloha:
    def __init__(self, book: StationBook, clock: Clock = utcnow, every_sec: float = ALOHA_EVERY_SEC) -> None:
        self._book = book
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
        while True:
            await asyncio.sleep(self.every_sec)
            try:
                self.refresh()
            except Exception:
                log.exception("the ALOHA circle could not be worked out")                 # (the timer goes on: the circle is worked out again at the next tick)

    def refresh(self) -> None:
        """Works the circle out from the stations as they are now."""
        found = circle(self._book.me_position, self._book.stations(), self._clock())
        radius = None if found is None else round(found.radius_km, 1)
        if radius != self.radius_km:
            self.radius_km = radius
            self.changed.emit()
