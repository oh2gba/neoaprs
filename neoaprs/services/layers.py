"""The map's traffic layers (aircraft and ships): the source in force of each layer, kept in memory.

A source is asked only while a page looks at its layer, as often as its feed allows.
NEOAPRS_UPDATE_CHECK=0 asks no service; NEOAPRS_LAYERS_URL replaces the services even then."""
import asyncio
import logging
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from urllib.parse import urlsplit

from neoaprs import radarcape, readsb
from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.layerthing import AGE_CHECK_SEC, EVERY_SEC, LAYERS, MAX_PACKED, MAX_UNPACKED, OWN_RECEIVERS, Layer, LayerState, LayerTable, ReceiverState, Source, Thing, in_force, max_age_sec, nearest, newest, offered, service_url, within
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.updatefetch import fetch_feed
from neoaprs.versions import on_this_computer

from .layerasked import AskedFeed, AskedSource, FetchFeed, LayerSource, SourceContext
from .layerships import FintrafficShips, ShipReceiver
from .updatecheck import ENV_SWITCH

log = logging.getLogger("neoaprs.layers")

ENV_URL = "NEOAPRS_LAYERS_URL"
RECEIVER_TIMEOUT_SEC = 4.0                      # per place tried
RECEIVER_BACKOFF_MAX_SEC = 60.0                 # short, as a receiver on the local network returns soon
SERVICE_NAMES = {"adsbfi": "adsb.fi", "adsblol": "adsb.lol", "fintraffic": "Fintraffic"}
NO_WAIT_SEC = 1.0                               # pause when another asker took the feed first


Reader = Callable[[bytes, datetime], list[Thing] | None]


def _served(body: bytes, at: datetime, position: tuple[float, float], radius_km: float) -> list[Thing] | None:
    """Return the aircraft within the circle, nearest first; None if the body is not readsb JSON."""
    things = readsb.read_aircraft(body, at)
    return None if things is None else nearest(within(things, position, radius_km), position)


def _received(read: Reader, body: bytes, at: datetime) -> tuple[int, list[Thing]] | None:
    """Return the count of positioned aircraft and the newest kept (RECEIVER_BOUND), or None."""
    things = read(body, at)
    return None if things is None else (len(things), newest(things))


class AircraftService(AskedSource):
    """adsb.fi or adsb.lol, asked for the rounded circle round our position."""

    def __init__(self, ctx: SourceContext) -> None:
        super().__init__(ctx)
        self.feed = ctx.feed(SERVICE_NAMES.get(ctx.source, ctx.source), EVERY_SEC["adsbfi" if ctx.source == "adsbfi" else "adsblol"], True)

    @property
    def away(self) -> bool:
        return super().away or not self.ctx.services_on or self.ctx.where() is None

    def wait_sec(self) -> float | None:
        return None if not self.ctx.services_on or self.ctx.where() is None else self.feed.wait_sec()

    async def _question(self) -> list[Thing] | None:
        position = self.ctx.where()
        if position is None:
            return None
        radius = self.ctx.config().map_radius_km
        url = self.ctx.service_url(service_url(self.ctx.source, *position, radius))
        answer = await self.ctx.fetch(url, self.ctx.version, self.ctx.platform, {}, MAX_PACKED, MAX_UNPACKED)
        things = await asyncio.to_thread(_served, answer.body, self.ctx.clock(), position, radius) if answer is not None and answer.status == 200 else None
        if things is None:
            log.debug("%s: %s", self.feed.name, "no answer" if answer is None else f"the answer {answer.status} is not readsb's JSON" if answer.status == 200 else f"it answered {answer.status}")
            self.feed.failed(None if answer is None or answer.status == 200 else answer)
        return things


def _radarcape_urls(address: str) -> list[str]:
    url = radarcape.radarcape_url(address)
    return [] if url is None else [url]


class AircraftReceiver(AskedSource):
    """The operator's own readsb receiver (map/aircraft_host); subclasses set name, places and read.

    The first place that answers is kept; the search starts again after a failure."""
    name = "the aircraft receiver"
    places: Callable[[str], list[str]] = staticmethod(readsb.receiver_urls)
    read: Reader = staticmethod(readsb.read_aircraft)

    def __init__(self, ctx: SourceContext) -> None:
        super().__init__(ctx)
        self.feed = AskedFeed(self.name, EVERY_SEC["aircraft_receiver"], ctx.monotonic, stops=False, backoff_max_sec=RECEIVER_BACKOFF_MAX_SEC)
        self.urls = self.places(ctx.config().map_aircraft_host)
        # Only the host goes to the log, never the address as typed.
        self.host = (urlsplit(self.urls[0]).hostname or "?") if self.urls else ""
        self.found: str | None = None
        self.state: ReceiverState = ReceiverState("looking", 0, None)

    def receiver(self) -> ReceiverState:
        return self.state

    async def start(self) -> None:
        """Ask once even if no page looks, so Settings can show the state."""
        if await self.ask():
            self.ctx.tell()

    async def _question(self) -> list[Thing] | None:
        for url in [self.found] if self.found is not None else self.urls:
            answer = await self.ctx.fetch(url, self.ctx.version, self.ctx.platform, {}, MAX_PACKED, MAX_UNPACKED, timeout_sec=RECEIVER_TIMEOUT_SEC)
            now = self.ctx.clock()
            read = await asyncio.to_thread(_received, self.read, answer.body, now) if answer is not None and answer.status == 200 else None
            if read is not None:
                self.found = url
                self._state(ReceiverState("receiving", read[0], now))
                return read[1]
        self.found = None
        self.feed.failed()
        self._state(ReceiverState("no_answer", self.state.things, self.state.heard_at))
        return None

    def _state(self, state: ReceiverState) -> None:
        if state.state != self.state.state:
            log.info("%s %s: %s", self.name, f"at {self.host}" if self.host else "without an address", {"receiving": "receiving", "no_answer": "no answer", "looking": "looking"}[state.state])
        if state != self.state:
            self.state = state
            self.ctx.changed()


class Radarcape(AircraftReceiver):
    """The operator's own Radarcape (map/aircraft_host); with no address nothing is asked."""
    name = "the Radarcape"
    places = staticmethod(_radarcape_urls)
    read = staticmethod(radarcape.read_aircraft)


Maker = Callable[[SourceContext], LayerSource]
SOURCES: dict[tuple[Layer, Source], Maker] = {("aircraft", "adsbfi"): AircraftService, ("aircraft", "adsblol"): AircraftService, ("aircraft", "radarcape"): Radarcape, ("aircraft", "receiver"): AircraftReceiver,
                                              ("ships", "fintraffic"): FintrafficShips, ("ships", "receiver"): ShipReceiver}
# The source in force and, for a receiver, its address; a source is made again when either changes.
Key = tuple[Source, str]


def chosen(config: Config, layer: Layer) -> str:
    return config.map_aircraft if layer == "aircraft" else config.map_ships


def _address(config: Config, layer: Layer) -> str:
    return config.map_aircraft_host if layer == "aircraft" else config.map_ships_host


class Layers:
    def __init__(self, config: Callable[[], Config], where: Callable[[], tuple[float, float] | None], version: str, platform: str, fetch: FetchFeed = fetch_feed, clock: Clock = utcnow,
                 environ: Mapping[str, str] = os.environ, monotonic: Callable[[], float] | None = None) -> None:
        self._config, self._where, self.version, self.platform, self._fetch, self._clock = config, where, version, platform, fetch, clock
        self._monotonic = monotonic or (lambda: asyncio.get_running_loop().time())
        given = environ.get(ENV_URL, "").strip()
        self.base = given if on_this_computer(given) else ""
        self.services_on = environ.get(ENV_SWITCH) != "0" or bool(self.base)
        # Emitted when a layer's source, offer or receiver state changes.
        self.changed: Signal[[]] = Signal("layers.changed")
        self.told: Signal[[LayerTable]] = Signal("layers.told")
        self._held: dict[Layer, tuple[Key, LayerSource | None]] = {}
        self._watched: set[Layer] = set()
        self._runners: dict[Layer, asyncio.Task[None]] = {}
        self._feeds: dict[str, AskedFeed] = {}
        # Things last told per layer; ageing tells again when it drops some.
        self._counts: dict[Layer, int] = {}
        self._states: tuple[LayerState, ...] = ()
        self._tasks = TaskSet(log, "layers")
        # Replaced sources whose stop has not finished; the daemon's stop finishes them.
        self._retired: list[LayerSource] = []
        self.running = False

    # ---- what the page is told
    def states(self) -> list[LayerState]:
        config, position = self._config(), self._where()
        found = []
        for layer in LAYERS:
            offer = offered(layer, position, config.map_radius_km)
            source = in_force(layer, chosen(config, layer), offer)
            held = self._held.get(layer)
            made = held[1] if held is not None and held[0][0] == source else None
            found.append(LayerState(layer, source, offer, made.receiver() if made is not None and source in OWN_RECEIVERS else None))
        return found

    def table(self, layer: Layer) -> LayerTable:
        """Return the layer's table: the things of its source within the age limit."""
        held = self._held.get(layer)
        if held is None:
            return LayerTable(layer, "none", False, ())
        (source, _), made = held
        if made is None:
            return LayerTable(layer, source, False, ())
        now, limit = self._clock(), max_age_sec(layer, source)
        return LayerTable(layer, source, made.away, tuple(thing for thing in made.things() if (now - thing.at).total_seconds() <= limit))

    def watch(self, layer: Layer, on: bool) -> None:
        """Start or stop asking the layer's source as a page begins or ends looking at it."""
        if on:
            self._watched.add(layer)
            self._run(layer)
        else:
            self._watched.discard(layer)
            self._stop_runner(layer)

    # ---- the settings and our position
    def config_changed(self, config: Config) -> None:
        self._refresh()

    def moved(self) -> None:
        """Re-evaluate the ships offer and any service that had no position."""
        self._refresh()

    def _key(self, config: Config, layer: Layer) -> Key:
        source = in_force(layer, chosen(config, layer), offered(layer, self._where(), config.map_radius_km))
        return source, _address(config, layer) if source in OWN_RECEIVERS else ""

    def _refresh(self) -> None:
        config = self._config()
        for layer in LAYERS:
            key = self._key(config, layer)
            held = self._held.get(layer)
            if held is None or held[0] != key:
                self._replace(layer, key, held)
            else:
                self._run(layer)
        self._maybe_changed()

    def _replace(self, layer: Layer, key: Key, held: tuple[Key, LayerSource | None] | None) -> None:
        """Stop the old source, start the new one and tell the pages its empty table."""
        self._stop_runner(layer)
        # When not running the old source was never started, or the daemon's stop stops it.
        if held is not None and held[1] is not None and self.running:
            self._retired.append(held[1])
            self._tasks.spawn(self._retire(held[1]), f"layers-stop-{layer}")
        maker = SOURCES.get((layer, key[0]))
        made = None if maker is None else maker(self._context(layer, key[0]))
        self._held[layer] = (key, made)
        if made is not None and self.running:
            self._tasks.spawn(self._start_source(layer, made), f"layers-start-{layer}")
        if held is not None:
            self._tell(layer)
        self._run(layer)

    async def _retire(self, old: LayerSource) -> None:
        await old.stop()
        if old in self._retired:
            self._retired.remove(old)

    def _context(self, layer: Layer, source: Source) -> SourceContext:
        return SourceContext(layer, source, self._config, self._where, self._fetch, self.version, self.platform, self._clock, self._monotonic, self.services_on, self.base, self._feed,
                             lambda: self._tell_from(layer, source), self._maybe_changed)

    def _feed(self, name: str, every_sec: float, stops: bool) -> AskedFeed:
        """Return the feed of that name; it outlives sources, so a stopped service stays stopped."""
        if name not in self._feeds:
            self._feeds[name] = AskedFeed(name, every_sec, self._monotonic, stops)
        return self._feeds[name]

    # ---- asking
    def _run(self, layer: Layer) -> None:
        held = self._held.get(layer)
        runner = self._runners.get(layer)
        if self.running and layer in self._watched and held is not None and held[1] is not None and (runner is None or runner.done()):
            self._runners[layer] = self._tasks.spawn(self._asking(layer, held[1]), f"layers-{layer}")

    def _stop_runner(self, layer: Layer) -> None:
        runner = self._runners.pop(layer, None)
        if runner is not None:
            runner.cancel()

    async def _asking(self, layer: Layer, made: LayerSource) -> None:
        """Ask the source as often as its feed allows, until it reports nothing to wait for."""
        while (wait := made.wait_sec()) is not None:
            if wait > 0:
                await asyncio.sleep(wait)
            if await made.ask():
                self._tell(layer)
                self._maybe_changed()
            elif wait == 0:
                await asyncio.sleep(NO_WAIT_SEC)

    async def _start_source(self, layer: Layer, made: LayerSource) -> None:
        await made.start()
        self._maybe_changed()

    def _tell_from(self, layer: Layer, source: Source) -> None:
        held = self._held.get(layer)
        if held is not None and held[0][0] == source:
            self._tell(layer)

    def _tell(self, layer: Layer) -> None:
        if layer in self._watched:
            table = self.table(layer)
            self._counts[layer] = len(table.things)
            self.told.emit(table)

    def _maybe_changed(self) -> None:
        states = tuple(self.states())
        if states != self._states:
            self._states = states
            self.changed.emit()

    async def _ageing(self) -> None:
        while True:
            await asyncio.sleep(AGE_CHECK_SEC)
            for layer in list(self._watched):
                if len(self.table(layer).things) < self._counts.get(layer, 0):
                    self._tell(layer)

    # ---- the daemon
    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        # Start sources made before the daemon started.
        for layer, (_, made) in list(self._held.items()):
            if made is not None:
                self._tasks.spawn(self._start_source(layer, made), f"layers-start-{layer}")
        self._refresh()
        self._tasks.spawn(self._ageing(), "layers-ageing")

    async def stop(self) -> None:
        self.running = False
        held = [made for _, made in self._held.values() if made is not None] + self._retired
        self._runners.clear()
        await self._tasks.cancel_all()
        for made in held:
            await made.stop()
