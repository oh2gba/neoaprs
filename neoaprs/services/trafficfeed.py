"""What the two feeds of the map's traffic share, the ships (services/ais.py) and the aircraft (services/adsb.py): open data read over the internet round our position, kept in memory by a key (the MMSI, the
ICAO address), each item told as it changes and forgotten when it has not been heard for a while. The map only shows them: a feed reads, and has nothing that sends; nothing of it reaches the radio, APRS-IS,
the station book or the database.

A feed runs while its switch is on (`ais/enabled`, `adsb/enabled`): it asks every `every_sec`, sooner after the switch or our position changed, and after a failure waits longer each time (`Backoff`). Without
a position (no station/lat and no GPS fix) it waits for one. The state is a word the page shows under the switch, with the problem as a code the page words (and the server's status of an HTTP error)."""
import asyncio
import enum
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.signal import Signal
from neoaprs.source import Backoff
from neoaprs.tasks import TaskSet
from neoaprs.trafficfetch import FetchError, get_json
from neoaprs.traffictrack import Tracks
from neoaprs.updatedownload import in_thread

log = logging.getLogger("neoaprs.traffic")

Centre = Callable[[], tuple[float, float] | None]
Fetch = Callable[[str, str, int], Awaitable[Any]]
NO_POSITION = "no_position"  # (the code of `problem`: neither station/lat nor a GPS fix)


async def fetch_json(url: str, user: str, max_bytes: int) -> Any:
    """`get_json` on a thread of its own, awaited."""
    return await in_thread(lambda: get_json(url, user, max_bytes), "traffic-fetch")


class Feed[T]:
    """A feed of items by key; a subclass says what the switch is (`switch`) and how a round is read (`read`)."""

    class State(enum.Enum):
        OFF = "off"                      # the switch is off
        WAITING = "waiting"              # on, and no position to ask round
        CONNECTING = "connecting"        # on, and the first answer has not come
        RECEIVING = "receiving"          # the latest answer was read
        FAILING = "failing"              # the latest question failed: `problem` says why; the items heard before stay until they are old

    name = "feed"
    what = "items"                       # what it shows, for the log
    every_sec = 60.0
    track_step_m = 50.0                  # a place of the track is kept when the item has moved this far
    keep_sec = 3600.0                    # an item not heard for this long is forgotten

    def __init__(self, config: Callable[[], Config], centre: Centre, user: str, fetch: Fetch = fetch_json, clock: Clock = utcnow, backoff: Backoff | None = None) -> None:
        self._config, self._centre, self.user, self._fetch, self.clock = config, centre, user, fetch, clock
        self.items: dict[str, T] = {}
        self.state = Feed.State.OFF
        self.problem = ""  # a code: no_position, unreachable, http (with http_status), bad_answer
        self.http_status: int | None = None
        self.updated_at: datetime | None = None          # when the latest answer was read
        self.changed: Signal[[str]] = Signal(f"{self.name}.changed")           # the key of an item that came, changed or went
        self.cleared: Signal[[]] = Signal(f"{self.name}.cleared")              # every item went at once (the switch was turned off)
        self.state_changed: Signal[[]] = Signal(f"{self.name}.state")
        self._backoff = backoff or Backoff([30.0, 60.0, 120.0, 300.0])
        self._wake = asyncio.Event()
        self._tasks = TaskSet(log, self.name)
        self._runner: asyncio.Task[None] | None = None
        self.tracks = Tracks(self.track_step_m)
        self._told: dict[str, int] = {}                  # how many places of each item's track the page was last told of (a place that grows old changes the row as a new one does)

    # ---- what a subclass says
    def switch(self, config: Config) -> bool:
        raise NotImplementedError

    async def read(self, centre: tuple[float, float]) -> Mapping[str, T]:
        """The items round `centre` now (raises FetchError)."""
        raise NotImplementedError

    def heard_at(self, item: T) -> datetime:
        raise NotImplementedError

    def place(self, item: T) -> tuple[float, float]:
        raise NotImplementedError

    def same(self, told: T, now: T) -> bool:
        """Whether the item as heard now need not be told: the one the page was told stays (a ship that only reported again in the same place)."""
        return told == now

    def radius(self, config: Config) -> float:
        """How far round our position it reads (ais/radius_km, adsb/radius_km)."""
        raise NotImplementedError

    def window_min(self, config: Config) -> int:
        """The minutes of track the page draws (ais/track_min, adsb/track_min); 0: none."""
        raise NotImplementedError

    @property
    def radius_km(self) -> float:
        return self.radius(self._config())

    def track(self, key: str) -> list[tuple[float, float]]:
        """The track of an item for the page: its places within the window, the oldest first; empty when the window is 0."""
        minutes = self.window_min(self._config())
        return self.tracks.since(key, self.clock() - timedelta(minutes=minutes)) if minutes > 0 else []

    # ---- the switch
    @property
    def enabled(self) -> bool:
        return self.switch(self._config())

    @property
    def word(self) -> str:
        """The state as the page is told it."""
        return self.state.value

    def __len__(self) -> int:
        return len(self.items)

    async def start(self) -> None:
        self.settings_changed()

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    def config_changed(self, config: Config) -> None:
        self.settings_changed()

    def settings_changed(self) -> None:
        """The settings were saved: the switch starts or ends the feed (what it had goes at once), and a feed that runs is asked again now (our place may have moved)."""
        if self.enabled:
            if self._runner is None or self._runner.done():
                log.info("%s is on: the %s within %.0f km of our position are read and shown, never sent", self.name, self.what, self.radius_km)
                self._backoff.reset()
                self._set_state(Feed.State.CONNECTING, "")
                self._runner = self._tasks.spawn(self._run(), self.name)
            self._wake.set()
            return
        if self._runner is not None:
            log.info("%s is off: the %s are forgotten", self.name, self.what)
            self._runner.cancel()
            self._runner = None
        self.updated_at = None
        self.tracks.clear()
        self._told.clear()
        if self.items:
            self.items.clear()
            self.cleared.emit()
        self._set_state(Feed.State.OFF, "")

    # ---- the rounds
    async def _run(self) -> None:
        while True:
            self._wake.clear()
            wait = await self._round()
            try:
                await asyncio.wait_for(self._wake.wait(), wait)
            except TimeoutError:
                pass

    async def _round(self) -> float:
        """One question, and how long to wait for the next."""
        centre = self._centre()
        if centre is None:
            self._set_state(Feed.State.WAITING, NO_POSITION)
            self._take({})
            return self.every_sec
        try:
            found = await self.read(centre)
        except FetchError as e:
            wait = max(self._backoff.next_delay_sec(), self.every_sec)
            if (self.problem, self.http_status) != (e.reason, e.status):
                log.info("%s could not be read: %s (asked again in %.0f s)", self.name, e, wait)
            self._set_state(Feed.State.FAILING, e.reason, e.status)
            self._forget_old()
            return wait
        self._backoff.connected()
        self.updated_at = self.clock()
        self._take(found)
        self._set_state(Feed.State.RECEIVING, "")
        return self.every_sec

    def _take(self, found: Mapping[str, T]) -> None:
        """The items of a round in place of the ones before, their places added to their tracks: each that came, changed or went is told, and one whose track the page draws differently (a place grew old)."""
        old = self.items
        self.items = {key: old[key] if key in old and self.same(old[key], item) else item for key, item in found.items()}
        for key in [k for k in old if k not in self.items]:
            self.tracks.drop(key)
            self._told.pop(key, None)
            self.changed.emit(key)
        minutes = self.window_min(self._config())
        since = self.clock() - timedelta(minutes=minutes)
        for key, item in self.items.items():
            self.tracks.add(key, self.heard_at(item), *self.place(item))
            places = self.tracks.count(key, since) if minutes > 0 else 0
            if old.get(key) != item or self._told.get(key) != places:
                self._told[key] = places
                self.changed.emit(key)

    def _forget_old(self) -> None:
        """While the feed fails, an item not heard for `keep_sec` goes."""
        limit = self.clock() - timedelta(seconds=self.keep_sec)
        self._take({key: item for key, item in self.items.items() if self.heard_at(item) > limit})

    def _set_state(self, state: "Feed.State", problem: str, http_status: int | None = None) -> None:
        if (state, problem, http_status) != (self.state, self.problem, self.http_status):
            self.state, self.problem, self.http_status = state, problem, http_status
            self.state_changed.emit()
