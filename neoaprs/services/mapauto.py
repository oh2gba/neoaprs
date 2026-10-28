"""The detailed map without a click: when the setup guide goes on from its Position step (the page sends the place when it is new, else the command `map_wanted`) and when a place is set that was not before (or another place, on
the Beacon tab), the job of Settings, Map, Download (neoaprs/services/mapfetch.py) is begun for the setting's `map/radius_km` round the station (150 km unless the operator changed it; the setting is not touched), unless the
detailed map that is there covers that area already. So the map round the station is there by the end of the setup, and nobody is asked; the header of the page shows the download's progress.

A detailed map covers the place when its area holds the box of COVERED of the radius round the place: a move of a few km does not make the map again, a move to another town does, and so does the 50 km map an earlier
version made by itself when the guide is run again with the radius at 150 km. A map whose area is not known (a header that cannot be read) is taken to cover it. Nothing is downloaded of its own accord at an upgrade
or at a start: a station that has a place and no map, or a small one, is given the map when the guide is run again or the place is changed.

The row `map/auto` (`MAP_AUTO`, state of the daemon, not a setting) says whether a job that was begun is still owed: `wanted` (begun, and not yet made) or `done` (a detailed map came of it, or the operator cancelled the
job). A job that fails, most likely for want of a connection, leaves the row `wanted` and tells the page (`MapFetch.later`: "the detailed map will come when you are online"); the next start of the daemon tries it again, and
so does each start until it works. The operator's Cancel settles it: not again by itself, until the guide or a new place asks again. The world map, which ships with the program, is under the page meanwhile.

While the job this part began is running, a new place outside the area being made ends it and begins it again for that place. The settings button stays for later; a job the operator started is the operator's, but a
detailed map that comes of it settles what is owed."""
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
COVERED = 0.9                                   # the part of the radius, in every direction, that a detailed map must hold round the place to be the map of the place
EDGE = 1e-5                                     # degrees: a header keeps a box to a ten-millionth, and a box that was asked for is read back to that


def inside(box: Box, lat: float, lon: float) -> bool:
    west, south, east, north = box
    return south <= lat <= north and west <= lon <= east


def contains(outer: Box, inner: Box) -> bool:
    """Whether `inner` lies in `outer`, to EDGE."""
    return outer[0] - EDGE <= inner[0] and outer[1] - EDGE <= inner[1] and inner[2] <= outer[2] + EDGE and inner[3] <= outer[3] + EDGE


def covers(detail: MapFile | None, lat: float, lon: float, radius_km: int) -> bool:
    """Whether the detailed map is the map of the place: it is there and its area holds COVERED of the radius round the place (an area that is not known is taken to)."""
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
        self._mine = False                      # the job that is running (or was) is one this part began
        self._box: Box | None = None            # the area of that job
        self._restarting = False
        self._was_busy = False

    async def start(self) -> None:
        """Reads where it stood; a job that was wanted and is not made is begun again."""
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
        """The settings were saved: a place that is new wants the map round it."""
        place = self._config().station_position
        if place is not None and place != before.station_position:
            self.wanted()

    def wanted(self) -> None:
        """The map of the area is wanted (the guide went on from its Position step, or the place is new): the detailed map is begun for the setting's radius round the station, unless the one that is there covers the place,
        or a job runs (one of ours for an area the place is not in is ended and begun again for the place). Nothing without a place, and nothing where the process does not ask for it."""
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
        """The map job changed (neoaprs/wiring.py connects it): a job that has ended is looked at."""
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
        if status.detail is not None or (mine and self._fetch.cancelled_by_user):
            self._settle()
        elif mine and status.problem:
            self._fetch.later = True
            self._fetch.changed.emit()
            log.info("the detailed map will be tried again at the next start: %s", status.problem)

    def _settle(self) -> None:
        """Nothing is owed: a detailed map is there, or the operator ended the job."""
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
