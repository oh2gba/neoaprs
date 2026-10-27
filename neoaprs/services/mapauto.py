"""The detailed map without a click: the first time a place is set and there is no detailed map yet, the job of Settings, Map, Download (neoaprs/services/mapfetch.py) is begun, so that the map round the station is there by the end of the setup
(the guide sends the place when it goes on from its Position step, and its last step and the header of the page show the download's progress; nobody is asked).

It is once for an installation. The row `map/auto` (`MAP_AUTO`, state of the daemon, not a setting) says where it stands: empty (never begun), `wanted` (begun, and not yet made) and `done` (a detailed map exists, or the
operator cancelled the job: never again). A job that fails, most likely for want of a connection, leaves the row `wanted` and tells the page (`MapFetch.later`: "the detailed map will come when you are online"); the next
start of the daemon tries it again, and so does each start until it works. The world map, which ships with the program, is under the page meanwhile.

The area is the setting's `map/radius_km` round the station (150 km unless the operator changed it), the same map that Settings, Map, Download makes; the setting is not touched.

A place set when none was before (or another place) starts it, and nothing else does: a station that has a place and no detailed map is not given a download of its own accord at an upgrade. While the job it began is running, a new place
outside the area being made ends it and begins it again for that place. The settings button stays for later; a job the operator started is the operator's, but a detailed map that comes of it counts as done."""
import asyncio
import logging

from neoaprs.config import MAP_AUTO, Config
from neoaprs.geo import box_around
from neoaprs.mapstate import Box, MapError
from neoaprs.services.common import ConfigSource
from neoaprs.services.mapfetch import MapFetch
from neoaprs.services.memory import Memory, Remembered
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.mapauto")

WANTED = "wanted"
DONE = "done"


def inside(box: Box, lat: float, lon: float) -> bool:
    west, south, east, north = box
    return south <= lat <= north and west <= lon <= east


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
        if self._detail():
            self._settle(DONE)
        elif self._state == WANTED:
            self._begin()

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()

    def settings_changed(self, before: Config) -> None:
        """The settings were saved: a place that is new starts the job."""
        place = self._config().station_position
        if not self._enabled or place is None or place == before.station_position or self._state == DONE or self._detail():
            return
        if not self._fetch.busy:
            self._remember(WANTED)
            self._begin()
        elif self._mine and not self._restarting and self._box is not None and not inside(self._box, *place):
            self._restarting = True
            self._tasks.spawn(self._again(), "map-auto-again")

    # ---- the job
    def _detail(self) -> bool:
        return self._fetch.status().detail is not None

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
        log.info("the detailed map is being made %d km round the station, once, without being asked for", config.map_radius_km)

    async def _again(self) -> None:
        try:
            await self._fetch.end()
            self._begin()
        finally:
            self._restarting = False

    def fetch_changed(self) -> None:
        """The map job changed (neoaprs/wiring.py connects it): a job of this part that has ended is looked at."""
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
        if status.detail is not None:
            self._settle(DONE)
        elif mine:
            if self._fetch.cancelled_by_user:
                self._settle(DONE)
            elif status.problem:
                self._fetch.later = True
                self._fetch.changed.emit()
                log.info("the detailed map will be tried again at the next start: %s", status.problem)

    def _settle(self, state: str) -> None:
        if self._state != state:
            self._remember(state)
        if self._fetch.later:
            self._fetch.later = False
            self._fetch.changed.emit()

    def _remember(self, state: str) -> None:
        self._state = state
        self._remembered.put({MAP_AUTO: state})

    @staticmethod
    def _failed(task: "asyncio.Task[None]") -> None:
        log.error("the automatic map job failed: %r", task.exception())
