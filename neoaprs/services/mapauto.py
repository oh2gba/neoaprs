"""Start the detailed map download automatically when the station gets a position.

The job (mapfetch.py) begins when a new place is set, unless the detailed map covers it.
The row `map/auto` is `wanted` until a map exists or the operator cancelled; each start retries."""
import asyncio
import logging

from neoaprs.config import MAP_AUTO, Config
from neoaprs.geo import box_around
from neoaprs.mapstate import Box, MapError, MapFile
from neoaprs.services.common import ConfigSource
from neoaprs.services.mapfetch import MapFetch
from neoaprs.services.memory import Memory, Remembered
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.mapauto")

WANTED = "wanted"
DONE = "done"
# Part of the radius a map must hold round the place; a move of a few km does not refetch.
COVERED = 0.9
# Degrees of tolerance: a header stores a box to a ten-millionth.
EDGE = 1e-5


def inside(box: Box, lat: float, lon: float) -> bool:
    west, south, east, north = box
    return south <= lat <= north and west <= lon <= east


def contains(outer: Box, inner: Box) -> bool:
    """Return whether `inner` lies in `outer`, within EDGE."""
    return outer[0] - EDGE <= inner[0] and outer[1] - EDGE <= inner[1] and inner[2] <= outer[2] + EDGE and inner[3] <= outer[3] + EDGE


def covers(detail: MapFile | None, lat: float, lon: float, radius_km: int) -> bool:
    """Return whether the detailed map exists and holds COVERED of the radius round the place."""
    if detail is None:
        return False
    return detail.bbox is None or contains(detail.bbox, box_around(lat, lon, radius_km * COVERED))


class MapAuto:
    def __init__(self, fetch: MapFetch, config: ConfigSource, memory: Memory | None = None, enabled: bool = True) -> None:
        self._fetch = fetch
        self._config = config
        self._enabled = enabled
        self._remembered = Remembered(memory)
        self._tasks = TaskSet(self._failed)
        self._state = ""
        self._mine = False                      # the job was begun here, not by the operator
        self._box: Box | None = None            # area of that job
        self._restarting = False
        self._was_busy = False

    async def start(self) -> None:
        """Read the stored state and begin a job that is still wanted."""
        if not self._enabled:
            return
        self._state = (await self._remembered.get(MAP_AUTO)) or ""
        if self._state == WANTED:
            if self._covered():
                self._settle()
            else:
                self._begin()

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()

    def settings_changed(self, before: Config) -> None:
        """Want the map when a saved setting gives a new place."""
        place = self._config().station_position
        if place is not None and place != before.station_position:
            self.wanted()

    def wanted(self) -> None:
        """Begin the detailed map round the station unless covered or a job runs.

        A running job of ours whose area misses the place is restarted."""
        config = self._config()
        place = config.station_position
        if not self._enabled or place is None:
            return
        if self._covered():
            self._settle()
            return
        if not self._fetch.busy:
            self._remember(WANTED)
            self._begin()
        elif self._mine and not self._restarting and self._box is not None and not inside(self._box, *place):
            self._restarting = True
            self._tasks.spawn(self._again(), "map-auto-again")

    # ---- the job
    def _covered(self) -> bool:
        config = self._config()
        place = config.station_position
        return place is not None and covers(self._fetch.status().detail, *place, config.map_radius_km)

    def _begin(self) -> None:
        try:
            self._fetch.begin("fetch")
        except MapError as e:
            log.info("the detailed map is not begun: %s", e)
            return
        self._mine = True
        config = self._config()
        place = config.station_position
        self._box = box_around(*place, config.map_radius_km) if place is not None else None
        log.info("the detailed map is being made %d km round the station, without being asked for", config.map_radius_km)

    async def _again(self) -> None:
        try:
            await self._fetch.end()
            self._begin()
        finally:
            self._restarting = False

    def fetch_changed(self) -> None:
        """Handle a change of the map job; react when a job has ended."""
        if not self._enabled:
            return
        busy = self._fetch.busy
        ended = self._was_busy and not busy
        self._was_busy = busy
        if ended and not self._restarting:
            self._ended()

    def _ended(self) -> None:
        mine, self._mine = self._mine, False
        status = self._fetch.status()
        if self._covered() or (mine and self._fetch.cancelled_by_user):
            self._settle()
        elif mine and status.problem:
            self._fetch.later = True
            self._fetch.changed.emit()
            log.info("the detailed map will be tried again at the next start: %s", status.problem)

    def _settle(self) -> None:
        """Mark nothing as owed: the map covers the place or the operator ended the job."""
        if self._state == WANTED:
            self._remember(DONE)
        if self._fetch.later:
            self._fetch.later = False
            self._fetch.changed.emit()

    def _remember(self, state: str) -> None:
        self._state = state
        self._remembered.put({MAP_AUTO: state})

    @staticmethod
    def _failed(task: "asyncio.Task[None]") -> None:
        log.error("the automatic map job failed: %r", task.exception())
