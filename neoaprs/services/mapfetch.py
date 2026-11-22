"""The base map job: a detailed map round the station, over a small map of the world.

`data/basemap.pmtiles` is cut from the Protomaps daily build for the box round the station.
One job runs at a time; a file is made as `.part` and moved into place when whole."""
import asyncio
import contextlib
import errno
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from neoaprs.clock import Clock, utcnow
from neoaprs.geo import box_around
from neoaprs.mapstate import Box, Estimate, Job, MapError, MapFile, MapStatus, State, Step
from neoaprs.pmtilesarchive import latest_build, read_header, url_exists
from neoaprs.pmtilescut import CutError, extract, part_of
from neoaprs.services.common import ConfigSource
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.worldmap import WORLD_FILE, world_file

log = logging.getLogger("neoaprs.mapfetch")

DETAIL = "basemap.pmtiles"
WORLD = WORLD_FILE
WORLD_MAXZOOM = 5
SLOW = "the map server is too slow now; try again later"
FAILED = "the map could not be made; the log says why"


@dataclass(frozen=True)
class Patience:
    stall_sec: float = 120.0                    # no change of percent or size for this long is a stall
    tries: int = 3                              # downloads begun before the job gives up
    pause_sec: float = 10.0                     # between a stalled download and the next
    poll_sec: float = 2.0                       # how often the downloaded size is read


PATIENCE = Patience()


class _Stalled(Exception):
    pass


def describe_file(path: Path) -> MapFile | None:
    """Return size, date, header box and zooms and the build note of a map file; None if missing."""
    try:
        stat = path.stat()
    except OSError:
        return None
    header = read_header(path)
    build = ""
    try:
        build = str(json.loads(path.with_suffix(".json").read_text()).get("build", ""))
    except (OSError, ValueError, AttributeError):
        pass
    return MapFile(path.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime, tz=UTC), header.bbox if header else None,
                   header.min_zoom if header else None, header.max_zoom if header else None, build)


def _remove(part: Path) -> None:
    """Delete a `.part` file; on failure only log, so the job is never kept busy.

    On Windows a cut that has just ended may still hold the file."""
    try:
        part.unlink(missing_ok=True)
    except OSError as e:
        log.warning("%s could not be deleted: %s", part.name, e)


class MapFetch:
    def __init__(self, data_dir: Path, config: ConfigSource, clock: Clock = utcnow, probe: Callable[[str], bool] = url_exists, patience: Patience = PATIENCE,
                 world: Callable[[Path], Path | None] = world_file) -> None:
        self.data_dir = data_dir
        self.config = config
        self.clock = clock
        self.changed: Signal[[]] = Signal("map_changed")
        self._probe = probe
        self.patience = patience
        self._world = world
        self._radius = 0                            # radius given to `begin`; 0 means the setting's
        self._tasks = TaskSet(self._task_failed)
        self.later = False                          # set by MapAuto: its map could not be fetched yet
        self.cancelled_by_user = False              # `cancel()` was called (a daemon stop does not)
        self._busy: Job | None = None
        self._current: "asyncio.Task[object] | None" = None
        self._step: Step = ""
        self._percent: int | None = None
        self._downloaded: int | None = None
        self._arrived: int | None = None            # bytes reported by the cut; read every `poll_sec`
        self._note = ""
        self._retry: tuple[int, int] | None = None
        self._moved = 0.0
        self._problem: MapError | None = None
        self._estimate: Estimate | None = None

    def _task_failed(self, task: "asyncio.Task[object]") -> None:
        log.error("the map job failed: %r", task.exception())

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    # ---- status
    def _plan(self) -> tuple[Box, int, int]:
        """Return the box, radius and zoom of the settings; raise MapError without a position."""
        config = self.config()
        place = config.station_position
        if place is None:
            raise MapError("the station has no position yet: set Latitude and Longitude (the map is cut round them)", problem="no_position")
        radius = self._radius or config.map_radius_km
        return box_around(*place, radius), radius, config.map_maxzoom

    def status(self) -> MapStatus:
        config = self.config()
        detail = describe_file(self.data_dir / DETAIL)
        code: Literal["", "no_position", "busy"]
        try:
            box: Box | None = self._plan()[0]
            blocked, code = ("", "") if self._busy is None else ("a map job is running", "busy")
        except MapError as e:
            box, blocked, code = None, str(e), "no_position"
        state: State = "estimating" if self._busy == "estimate" else "downloading" if self._busy == "fetch" else "error" if self._problem else "ready" if detail else "none"
        failure = self._problem if self._busy is None else None
        return MapStatus(state, self._step, self._percent, self._downloaded, self._note, blocked, "" if failure is None else str(failure), self._estimate, config.map_radius_km, config.map_maxzoom, box,
                         detail, self._describe_world(), self.later and detail is None, self._retry, code, failure)

    def _describe_world(self) -> MapFile | None:
        found = self._world(self.data_dir)
        return None if found is None else describe_file(found)

    @property
    def busy(self) -> bool:
        return self._busy is not None

    def _set(self, step: Step) -> None:
        self._step, self._percent, self._downloaded, self._note, self._retry = step, None, None, "", None
        self.changed.emit()

    def _moves(self) -> None:
        """Record progress for the stall watch and clear any stall note."""
        self._moved, self._note, self._retry = time.monotonic(), "", None

    def _progress(self, percent: int) -> None:
        if percent != self._percent:
            self._percent = percent
            self._moves()
            self.changed.emit()

    # ---- the jobs
    def _claim(self, job: Job) -> None:
        if self._busy is not None:
            raise MapError("a map job is running already", problem="busy")
        self._plan()
        self._busy, self._problem, self.later, self.cancelled_by_user = job, None, False, False
        self._step, self._percent, self._downloaded, self._note, self._retry = "", None, None, "", None

    def begin(self, job: Job, radius_km: int = 0) -> None:
        """Start the job in the background, for `radius_km` if given (else `map/radius_km`).

        Raise MapError if a job runs or there is no position. The end is signalled by `changed`."""
        self._claim(job)
        self._radius = radius_km
        self._current = self._tasks.spawn(self._run(job), "map-" + job)
        self.changed.emit()

    async def estimate(self) -> None:
        """Estimate the detailed map's size into `status().estimate`; raise MapError, CutError."""
        self._claim("estimate")
        await self._run("estimate", raising=True)

    async def fetch(self) -> None:
        """Make the world map if missing, then the detailed map. Raise MapError, CutError."""
        self._claim("fetch")
        await self._run("fetch", raising=True)

    def cancel(self) -> bool:
        """End the running job and remove its files; return False if none runs."""
        task = self._current
        if self._busy is None or task is None or task.done():
            return False
        self.cancelled_by_user = True
        task.cancel()
        return True

    async def end(self) -> None:
        """End the running job, if any, and wait for it; `cancelled_by_user` is left unchanged."""
        task = self._current
        if self._busy is not None and task is not None and not task.done():
            task.cancel()
            await asyncio.wait([task])

    async def _run(self, job: Job, raising: bool = False) -> None:
        self._current = asyncio.current_task()
        parts = [self.data_dir / (name + ".part") for name in (DETAIL, WORLD)]
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            for part in parts:
                part.unlink(missing_ok=True)
            await (self._estimate_job() if job == "estimate" else self._fetch_job())
        except asyncio.CancelledError:
            log.info("the map job was cancelled")
            raise
        except (MapError, CutError) as e:
            self._problem = e if isinstance(e, MapError) else MapError(str(e), e.problem, **e.params)
            log.warning("the map %s failed: %s", job, e)
            if raising:
                raise
        except Exception as e:
            full = isinstance(e, OSError) and e.errno == errno.ENOSPC
            self._problem = MapError(FAILED if not isinstance(e, OSError) else f"{FAILED}: {e.strerror or e}", problem="no_space" if full else "failed")
            log.exception("the map %s failed", job)
            if raising:
                raise
        finally:
            try:
                self._radius = 0
                for part in parts:
                    _remove(part)
            finally:
                self._busy, self._current, self._step, self._percent, self._downloaded, self._note, self._retry = None, None, "", None, None, "", None
                self.changed.emit()

    async def _source(self) -> tuple[str, str]:
        """Return the source to cut from and its build day ("" if not a daily build)."""
        chosen = self.config().map_source
        if chosen:
            named = re.search(r"(\d{8})\.pmtiles$", chosen)
            log.info("the map is cut from %s", chosen)
            return chosen, named.group(1) if named else ""
        self._set("build")
        found = await latest_build(self.clock(), self._probe)
        log.info("the map is cut from %s", found[0])
        return found

    async def _estimate_job(self) -> None:
        box, radius, zoom = self._plan()
        source, build = await self._source()
        self._set("area")
        cut = await extract(source, self.data_dir / DETAIL, box, zoom, dry_run=True)
        self._estimate = Estimate(cut.bytes, cut.tiles, radius, zoom, box, build)
        log.info("the map of %d km round us to zoom %d is %.0f MB (%d tiles)", radius, zoom, cut.bytes / 1e6, cut.tiles)

    async def _fetch_job(self) -> None:
        box, radius, zoom = self._plan()
        source, build = await self._source()
        if self._world(self.data_dir) is None:
            self._set("world")
            await self._make(source, build, WORLD, None, WORLD_MAXZOOM)
        self._set("area")
        await self._make(source, build, DETAIL, box, zoom)
        self._estimate = None
        log.info("the map of %d km round us to zoom %d is in %s", radius, zoom, self.data_dir / DETAIL)

    async def _make(self, source: str, build: str, name: str, box: Box | None, zoom: int) -> None:
        final = self.data_dir / name
        await self._download(source, final, box, zoom)
        try:
            final.with_suffix(".json").write_text(json.dumps({"build": build}))
        except OSError as e:
            log.warning("the note on the build of %s could not be written: %s", name, e)

    async def _download(self, source: str, final: Path, box: Box | None, zoom: int) -> None:
        """Cut the map into `final`, restarting a stalled cut; raise CutError after `tries`."""
        part = part_of(final)
        for attempt in range(1, self.patience.tries + 1):
            part.unlink(missing_ok=True)
            self._arrived = None
            try:
                return await self._watched(extract(source, final, box, zoom, on_percent=self._progress, on_size=self._sized))
            except _Stalled:
                log.warning("the download of %s stood still for %g s (try %d of %d)", part.name, self.patience.stall_sec, attempt, self.patience.tries)
            if attempt == self.patience.tries:
                raise CutError(SLOW, problem="slow") from None
            self._percent, self._downloaded = None, None
            self._note, self._retry = f"no progress: trying again ({attempt + 1} of {self.patience.tries})", (attempt + 1, self.patience.tries)
            self.changed.emit()
            await asyncio.sleep(self.patience.pause_sec)

    async def _watched(self, run: Awaitable[object]) -> None:
        """Wait for the cut, polling its size; end it and raise _Stalled after `stall_sec` idle."""
        task = asyncio.ensure_future(run)
        self._moved = time.monotonic()
        try:
            while not task.done():
                await asyncio.wait([task], timeout=self.patience.poll_sec)
                self._look()
                if not task.done() and time.monotonic() - self._moved > self.patience.stall_sec:
                    raise _Stalled
            await task
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    def _sized(self, size: int) -> None:
        self._arrived = size

    def _look(self) -> None:
        size = self._arrived
        if size is not None and size != self._downloaded:
            self._downloaded = size
            self._moves()
            self.changed.emit()


if __name__ == "__main__":
    import importlib
    # Imported here because mapcli imports this module.
    raise SystemExit(importlib.import_module("neoaprs.services.mapcli").main())
