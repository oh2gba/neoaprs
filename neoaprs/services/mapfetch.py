"""The base map, made by the daemon: a detailed map of the area round our station and a small map of the world under it.

`data/basemap.pmtiles` is cut out of the Protomaps daily build (or of `map/source`) with the pmtiles tool (neoaprs/pmtilestool.py) for the box that `map/radius_km` makes round the station's position, down to
`map/maxzoom`. The world under it and outside it is the one that ships with the program (neoaprs/worldmap.py, zoom 4); only when there is none (a clone that has not got the file) or the data folder's own is no good,
`data/basemap-world.pmtiles` is made first, the world to zoom 5 (about 15 MB). A world map the data folder has of its own is the one that is served.

A download that has stood still for `Patience.stall_sec` (neither the tool's percent nor the size of the `.part` file moved) is ended and tried again from the start, up to `Patience.tries` times in all, saying so in the
status (`note`); after the last try the job fails with a text that says the server is too slow, and the map that was there stays. The status also tells the size of the `.part` file, so that a slow download is seen to move.

One job at a time: `estimate()` is a dry run that says how big the detailed map will be, `fetch()` makes the files, `cancel()` ends the job running. A file is made beside the final one (`.part`) and moved into
place only when the tool has finished, so a failed or cancelled job leaves the map that was there. `status()` is what the page is told; `changed` is emitted with every change of it. The command line is `python -m neoaprs.services.mapfetch`
(neoaprs/services/mapcli.py)."""
import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from neoaprs.clock import Clock, utcnow
from neoaprs.geo import box_around
from neoaprs.mapstate import Box, Estimate, Job, MapError, MapFile, MapStatus, State, Step
from neoaprs.pmtilestool import ToolError, ensure, extract, find, latest_build, read_header, replace_file, url_exists
from neoaprs.services.common import ConfigSource
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.worldmap import WORLD_FILE, world_file

log = logging.getLogger("neoaprs.mapfetch")

DETAIL = "basemap.pmtiles"
WORLD = WORLD_FILE
WORLD_MAXZOOM = 5
SLOW = "the map server is too slow now; try again later"


@dataclass(frozen=True)
class Patience:
    stall_sec: float = 120.0                    # how long neither the percent nor the size of the file may move
    tries: int = 3                              # downloads begun in all before the job gives up
    pause_sec: float = 10.0                     # between the end of a stalled download and the next
    poll_sec: float = 2.0                       # how often the size of the file is looked at


PATIENCE = Patience()


class _Stalled(Exception):
    pass


def describe_file(path: Path) -> MapFile | None:
    """What is known of a map file: its size and date, the box and zooms of its header, and the build of its note. None if there is no such file."""
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


class MapFetch:
    def __init__(self, data_dir: Path, config: ConfigSource, clock: Clock = utcnow, installer: Callable[[Path], Awaitable[Path]] = ensure,
                 probe: Callable[[str], bool] = url_exists, patience: Patience = PATIENCE, world: Callable[[Path], Path | None] = world_file) -> None:
        self.data_dir = data_dir
        self.config = config
        self.clock = clock
        self.changed: Signal[[]] = Signal("map_changed")
        self._installer = installer
        self._probe = probe
        self.patience = patience
        self._world = world
        self._tasks = TaskSet(self._task_failed)
        self.later = False                          # set by neoaprs/services/mapauto.py: the map it began could not be fetched yet
        self.cancelled_by_user = False              # `cancel()` was called for the latest job (a stop of the daemon does not)
        self._busy: Job | None = None
        self._current: "asyncio.Task[object] | None" = None
        self._step: Step = ""
        self._percent: int | None = None
        self._downloaded: int | None = None
        self._note = ""
        self._moved = 0.0
        self._problem = ""
        self._estimate: Estimate | None = None

    def _task_failed(self, task: "asyncio.Task[object]") -> None:
        log.error("the map job failed: %r", task.exception())

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    # ---- what the page is told
    def _plan(self) -> tuple[Box, int, int]:
        """The box, radius and zoom the settings make; MapError without a position."""
        config = self.config()
        place = config.station_position
        if place is None:
            raise MapError("the station has no position yet: set Latitude and Longitude (the map is cut round them)")
        return box_around(*place, config.map_radius_km), config.map_radius_km, config.map_maxzoom

    def status(self) -> MapStatus:
        config = self.config()
        detail = describe_file(self.data_dir / DETAIL)
        try:
            box: Box | None = self._plan()[0]
            blocked = "" if self._busy is None else "a map job is running"
        except MapError as e:
            box, blocked = None, str(e)
        state: State = "estimating" if self._busy == "estimate" else "downloading" if self._busy == "fetch" else "error" if self._problem else "ready" if detail else "none"
        return MapStatus(state, self._step, self._percent, self._downloaded, self._note, blocked, self._problem if self._busy is None else "", self._estimate, config.map_radius_km, config.map_maxzoom, box,
                         detail, self._describe_world(), self.later and detail is None)

    def _describe_world(self) -> MapFile | None:
        found = self._world(self.data_dir)
        return None if found is None else describe_file(found)

    @property
    def busy(self) -> bool:
        return self._busy is not None

    def _set(self, step: Step) -> None:
        self._step, self._percent, self._downloaded, self._note = step, None, None, ""
        self.changed.emit()

    def _moves(self) -> None:
        """The download went on: the time of it is kept for the watch, and a note about a stall is no longer true."""
        self._moved, self._note = time.monotonic(), ""

    def _progress(self, percent: int) -> None:
        if percent != self._percent:
            self._percent = percent
            self._moves()
            self.changed.emit()

    # ---- the jobs
    def _claim(self, job: Job) -> None:
        if self._busy is not None:
            raise MapError("a map job is running already")
        self._plan()
        self._busy, self._problem, self.later, self.cancelled_by_user = job, "", False, False
        self._step, self._percent, self._downloaded, self._note = "", None, None, ""

    def begin(self, job: Job) -> None:
        """Starts the job in the background; MapError (nothing started) if one is running or there is no position. Its end is told by `changed`."""
        self._claim(job)
        self._current = self._tasks.spawn(self._run(job), "map-" + job)
        self.changed.emit()

    async def estimate(self) -> None:
        """A dry run: how big the detailed map will be (`status().estimate`). Raises MapError, ToolError."""
        self._claim("estimate")
        await self._run("estimate", raising=True)

    async def fetch(self) -> None:
        """Makes the world map when it is not there, then the detailed map. Raises MapError, ToolError."""
        self._claim("fetch")
        await self._run("fetch", raising=True)

    def cancel(self) -> bool:
        """Ends the job that is running (its files are removed); False if none is."""
        task = self._current
        if self._busy is None or task is None or task.done():
            return False
        self.cancelled_by_user = True
        task.cancel()
        return True

    async def end(self) -> None:
        """Ends the job that is running, if one is, and waits until it is over (not by the user: `cancelled_by_user` stays as it was)."""
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
        except (MapError, ToolError) as e:
            self._problem = str(e)
            log.warning("the map %s failed: %s", job, e)
            if raising:
                raise
        except Exception as e:
            self._problem = f"{type(e).__name__}: {e}"
            log.exception("the map %s failed", job)
            if raising:
                raise
        finally:
            for part in parts:
                part.unlink(missing_ok=True)
            self._busy, self._current, self._step, self._percent, self._downloaded, self._note = None, None, "", None, None, ""
            self.changed.emit()

    async def _program(self) -> Path:
        bin_dir = self.data_dir / "bin"
        found = find(bin_dir)
        if found is not None:
            return found
        self._set("tool")
        return await self._installer(bin_dir)

    async def _source(self) -> tuple[str, str]:
        """Where to cut from and the day of the build ("" for a source that is not a daily build)."""
        chosen = self.config().map_source
        if chosen:
            named = re.search(r"(\d{8})\.pmtiles$", chosen)
            return chosen, named.group(1) if named else ""
        self._set("build")
        return await latest_build(self.clock(), self._probe)

    async def _estimate_job(self) -> None:
        box, radius, zoom = self._plan()
        program = await self._program()
        source, build = await self._source()
        self._set("area")
        sizes = await extract(program, source, self.data_dir / (DETAIL + ".part"), box, zoom, dry_run=True)
        self._estimate = Estimate(sizes.bytes, sizes.tiles, radius, zoom, box, build)
        log.info("the map of %d km round us to zoom %d is %.0f MB (%d tiles)", radius, zoom, sizes.bytes / 1e6, sizes.tiles)

    async def _fetch_job(self) -> None:
        box, radius, zoom = self._plan()
        program = await self._program()
        source, build = await self._source()
        if self._world(self.data_dir) is None:
            self._set("world")
            await self._make(program, source, build, WORLD, None, WORLD_MAXZOOM)
        self._set("area")
        await self._make(program, source, build, DETAIL, box, zoom)
        self._estimate = None
        log.info("the map of %d km round us to zoom %d is in %s", radius, zoom, self.data_dir / DETAIL)

    async def _make(self, program: Path, source: str, build: str, name: str, box: Box | None, zoom: int) -> None:
        part, final = self.data_dir / (name + ".part"), self.data_dir / name
        await self._download(program, source, part, box, zoom)
        if not part.is_file():
            raise ToolError(f"the pmtiles program ended without making {part.name}")
        await asyncio.to_thread(replace_file, part, final)
        try:
            final.with_suffix(".json").write_text(json.dumps({"build": build}))
        except OSError as e:
            log.warning("the note on the build of %s could not be written: %s", name, e)

    async def _download(self, program: Path, source: str, part: Path, box: Box | None, zoom: int) -> None:
        """Runs the tool until it has made `part`; a run that stands still is ended and begun again from the start (the tool cannot take up a half-made file) after a pause, `tries` times in all; then ToolError."""
        for attempt in range(1, self.patience.tries + 1):
            part.unlink(missing_ok=True)
            try:
                return await self._watched(extract(program, source, part, box, zoom, on_percent=self._progress), part)
            except _Stalled:
                log.warning("the download of %s stood still for %g s (try %d of %d)", part.name, self.patience.stall_sec, attempt, self.patience.tries)
            if attempt == self.patience.tries:
                raise ToolError(SLOW) from None
            self._percent, self._downloaded = None, None
            self._note = f"no progress: trying again ({attempt + 1} of {self.patience.tries})"
            self.changed.emit()
            await asyncio.sleep(self.patience.pause_sec)

    async def _watched(self, run: Awaitable[object], part: Path) -> None:
        """Waits for the tool, looking at the size of `part` now and then; _Stalled (the tool is ended) when neither that nor the percent has moved for `stall_sec`."""
        task = asyncio.ensure_future(run)
        self._moved = time.monotonic()
        try:
            while not task.done():
                await asyncio.wait([task], timeout=self.patience.poll_sec)
                self._look(part)
                if not task.done() and time.monotonic() - self._moved > self.patience.stall_sec:
                    raise _Stalled
            await task
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    def _look(self, part: Path) -> None:
        try:
            size = part.stat().st_size
        except OSError:
            return
        if size != self._downloaded:
            self._downloaded = size
            self._moves()
            self.changed.emit()


if __name__ == "__main__":
    import importlib
    raise SystemExit(importlib.import_module("neoaprs.services.mapcli").main())         # (not imported at the top: the command line imports this module)
