"""The ALOHA circles of our station (neoaprs/aloha.py has the method), kept up to date: worked out at the start, once a minute, and when the settings move our position. `radii` are the latest values, in
tenths of a kilometre, by radio; `changed` is emitted when they differ from the ones before. A radio has none while our position is not known or the stations it heard do not fill its channel.

There is a circle for each radio that is on and whose type says it shares a 1200 baud channel (`Allowed.shared_channel`: an FM radio), worked out from the stations that radio heard (plan rule 3.8), in
the order of the boxes; none while no such radio is on. Given no radios (`radios` None: a test's), every station heard on the air counts, as before the radios were by id, under the id AIR."""
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


AIR: RadioId = 0                                  # the key of the one circle of a service given no radios (a test's): every station heard on the air


class Aloha:
    def __init__(self, book: StationBook, clock: Clock = utcnow, every_sec: float = ALOHA_EVERY_SEC, *, radios: Callable[[], Iterable[AirRadio]] | None = None) -> None:
        self._book = book
        self._radios = radios                                 # the radios that are on, in the order of their boxes; None: no radios given, every station of the air counts
        self._clock = clock
        self.every_sec = every_sec
        self.changed: Signal[[]] = Signal("aloha.changed")
        self.radii: dict[RadioId, float] = {}                 # the radius of each radio's circle, by its id, in the order of the boxes; a radio without a circle is not in it
        self._tasks = TaskSet(log, "aloha")

    @property
    def radius_km(self) -> float | None:
        """The radius of the one circle there is (the air's of a service given no radios, a station's one FM radio); None for none. With several the first, in the order of the boxes."""
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
        """Works the circles out from the stations as they are now."""
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
