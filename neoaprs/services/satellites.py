"""The map's satellites layer: the project's satellites file, kept in the data folder, and what the
pages that look are told every ROUND_SEC (marks, and the cards they have open).

Nothing is fetched or computed while no page looks. The file is fetched while one looks and it is
missing or a day old, at most once a day; NEOAPRS_UPDATE_CHECK=0 fetches nothing unless
NEOAPRS_SATELLITES_URL names a server on this computer."""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs.clock import Clock, utcnow
from neoaprs.satellitelist import FILE_NAME, MAX_BYTES, SATELLITES_URL, SatelliteFile, read_file, shown
from neoaprs.satellites import Orbit, Pass, Station, passes
from neoaprs.satelliteview import Card, Mark, View, card, mark
from neoaprs.signal import Signal
from neoaprs.tasks import Failures, TaskSet
from neoaprs.updatefetch import fetch_answer
from neoaprs.versions import on_this_computer

from .updatecheck import ENV_SWITCH

log = logging.getLogger("neoaprs.satellites")

ENV_URL = "NEOAPRS_SATELLITES_URL"
ROUND_SEC = 30.0
FILE_AGE = timedelta(days=1)  # a file made longer ago is fetched again
FETCH_EVERY_SEC = 86400.0
RETRY_SEC = 3600.0  # after a fetch that failed
PASSES_FOR = timedelta(hours=6)  # how long the passes found are used before they are searched again
# (address, version, platform, max bytes) -> (status, body)
Fetch = Callable[[str, str, str, int], Awaitable[tuple[int, bytes] | None]]
PassKey = tuple[Station, datetime]  # the station and the elements' epoch they were found for


def _read(path: Path) -> SatelliteFile | None:
    try:
        return read_file(path.read_bytes())
    except OSError:
        return None


def _write(path: Path, body: bytes) -> None:
    part = path.with_name(path.name + ".part")
    path.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(body)
    os.replace(part, path)


class Satellites:
    def __init__(
        self,
        data_dir: Path,
        where: Callable[[], tuple[float, float] | None],
        version: str,
        platform: str,
        fetch: Fetch = fetch_answer,
        clock: Clock = utcnow,
        environ: Mapping[str, str] = os.environ,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.path = data_dir / FILE_NAME
        self._where, self.version, self.platform, self._fetch, self._clock = where, version, platform, fetch, clock
        self._monotonic = monotonic or (lambda: asyncio.get_running_loop().time())
        given = environ.get(ENV_URL, "").strip()
        self.url = given if on_this_computer(given) else SATELLITES_URL
        self.fetching = environ.get(ENV_SWITCH) != "0" or bool(given and self.url == given)
        # Emitted after every round while a page looks.
        self.told: Signal[[View]] = Signal("satellites.told")
        self.view: View | None = None
        self.file: SatelliteFile | None = None
        self.asked = 0
        self._loaded = False
        self._looked = False
        self._cards: frozenset[int] = frozenset()
        self._fetched_at: float | None = None
        self._failed_at: float | None = None
        self._passes: dict[int, tuple[PassKey, datetime, list[Pass]]] = {}
        self._wake: asyncio.Event | None = None
        self._runner: asyncio.Task[None] | None = None
        self._tasks = TaskSet(log, "satellites")
        self.running = False

    def look(self, on: bool, cards: frozenset[int]) -> None:
        """Start or stop the rounds as the first page begins or the last one ends looking; new cards are told at once."""
        self._looked, self._cards = on, cards
        if not on:
            if self._runner is not None:
                self._runner.cancel()
                self._runner = None
            return
        if self._wake is not None:
            self._wake.set()
        self._run()

    def _run(self) -> None:
        if self.running and self._looked and (self._runner is None or self._runner.done()):
            self._runner = self._tasks.spawn(self._rounds(), "satellites")

    async def _rounds(self) -> None:
        failures = Failures("the satellites layer")
        self._wake = asyncio.Event()
        while True:
            self._wake.clear()
            try:
                await self.round()
                failures.worked()
            except Exception as e:
                failures.failed(e)
            try:
                await asyncio.wait_for(self._wake.wait(), ROUND_SEC)
            except TimeoutError:
                pass

    async def round(self) -> None:
        """Read the file once, fetch it when due, and tell the view of now."""
        if not self._loaded:
            self._loaded = True
            self.file = await asyncio.to_thread(_read, self.path)
        if self._due():
            await self._fetch_file()
        position = self._where()
        station = None if position is None else Station(position[0], position[1])
        self.view = await asyncio.to_thread(self._compute, self._clock(), station, self._cards)
        self.told.emit(self.view)

    def _due(self) -> bool:
        now = self._monotonic()
        made = None if self.file is None else self.file.made
        return (
            self.fetching
            and (made is None or self._clock() - made >= FILE_AGE)
            and (self._fetched_at is None or now - self._fetched_at >= FETCH_EVERY_SEC)
            and (self._failed_at is None or now - self._failed_at >= RETRY_SEC)
        )

    async def _fetch_file(self) -> None:
        self.asked += 1
        answer = await self._fetch(self.url, self.version, self.platform, MAX_BYTES)
        read = read_file(answer[1]) if answer is not None and answer[0] == 200 else None
        if read is None:
            if self._failed_at is None:
                log.info(
                    "the satellites file could not be fetched (%s); %s",
                    "no answer" if answer is None else f"answer {answer[0]}" if answer[0] != 200 else "not such a file",
                    "the last one is used" if self.file is not None else "the layer is empty until it comes",
                )
            self._failed_at = self._monotonic()
            return
        assert answer is not None
        await asyncio.to_thread(_write, self.path, answer[1])
        self.file, self._fetched_at, self._failed_at = read, self._monotonic(), None
        log.info("the satellites file came: %d satellites", len(read.satellites))

    def _passes_of(self, satellite_id: int, orbit: Orbit, station: Station, now: datetime) -> list[Pass]:
        key = (station, orbit.epoch)
        held = self._passes.get(satellite_id)
        if held is not None and held[0] == key and now - held[1] < PASSES_FOR and any(one.set > now for one in held[2]):
            return held[2]
        found = passes(orbit, station, now)
        self._passes[satellite_id] = (key, now, found)
        return found

    def _compute(self, now: datetime, station: Station | None, cards: frozenset[int]) -> View:
        marks: list[Mark] = []
        opened: list[Card] = []
        for satellite in self.file.satellites if self.file is not None else ():
            orbit = shown(satellite, now)
            if orbit is None:
                continue
            made = mark(satellite, orbit, now)
            if made is not None:
                marks.append(made)
            if satellite.id in cards:
                found = [] if station is None else self._passes_of(satellite.id, orbit, station, now)
                one = card(satellite, orbit, station, now, found)
                if one is not None:
                    opened.append(one)
        return View(now, None if self.file is None else self.file.elements_at, tuple(marks), tuple(opened))

    async def start(self) -> None:
        self.running = True
        self._run()

    async def stop(self) -> None:
        self.running = False
        self._runner = None
        await self._tasks.cancel_all()
