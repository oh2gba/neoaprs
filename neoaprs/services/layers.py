"""The map's layers of traffic (aircraft and ships; the ships' two sources are layerships.py's): the source in force of each layer (Settings, Map: map/aircraft, map/ships, while the station is offered it), asked only while a page looks at its layer and
never more often than its feed allows, its things kept in memory by id and nothing written anywhere, the whole table handed to the pages that look (`told`) and what the topic `map` says of each layer (`states`,
`changed`). The rules and the numbers are neoaprs/layerthing.py's; one source is a small object made from SOURCES, keyed by (layer, source).

- A service on the internet (adsb.fi, adsb.lol) is asked for the map's circle round our position, rounded (layerthing.service_url), and its answer is cut to the true circle and to the LIMIT nearest.
- An own aircraft receiver (readsb's file, as tar1090 and dump1090 serve it, or a Radarcape's list) is cut by nothing but the guard of RECEIVER_BOUND; it is asked once at the start and at a save that chooses
  it or changes its address, for its state in Settings, and otherwise only while a page looks. readsb's file is tried in the known places (readsb.receiver_urls), the first that answers is kept and asked from
  then on, and the search begins again after a failure; a Radarcape is asked in its one place (radarcape.radarcape_url), and one with no address is not looked for.
- An answer is read and cut on a thread of its own (it may be some megabytes): the daemon's loop goes on meanwhile.
- Silence: no failure reaches the page but the own receiver's state; a source that fails keeps its things, which age out, and its table says `away`.
- The doors: `NEOAPRS_NO_DEVICES=1` refuses what is not on this computer (updatefetch, nodevices); `NEOAPRS_UPDATE_CHECK=0` asks no service; `NEOAPRS_LAYERS_URL`, a server on this computer, is asked in the
  services' place (their paths kept), even while the update check is off."""
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

ENV_URL = "NEOAPRS_LAYERS_URL"                  # development and tests: a server on this computer in the place of every service
RECEIVER_TIMEOUT_SEC = 4.0                      # of each place tried on an own receiver (a search tries eight)
RECEIVER_BACKOFF_MAX_SEC = 60.0                 # the longest wait after failures of an own receiver (on the station's own network: it is seen again soon after it is back)
SERVICE_NAMES = {"adsbfi": "adsb.fi", "adsblol": "adsb.lol", "fintraffic": "Fintraffic"}     # (for the log)
NO_WAIT_SEC = 1.0                               # the pause of a round that found its feed taken by another question just now


Reader = Callable[[bytes, datetime], list[Thing] | None]


def _served(body: bytes, at: datetime, position: tuple[float, float], radius_km: float) -> list[Thing] | None:
    """A service's answer read and cut to the true circle and the nearest; None when it is not readsb's JSON."""
    things = readsb.read_aircraft(body, at)
    return None if things is None else nearest(within(things, position, radius_km), position)


def _received(read: Reader, body: bytes, at: datetime) -> tuple[int, list[Thing]] | None:
    """An own receiver's answer read: how many aircraft it gave with a position, and the ones kept (RECEIVER_BOUND, the newest); None when it is not in the receiver's form."""
    things = read(body, at)
    return None if things is None else (len(things), newest(things))


class AircraftService(AskedSource):
    """adsb.fi or adsb.lol: the circle round our position, rounded, as the service's question; the answer cut to the true circle and the nearest."""

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
    """The operator's own aircraft receiver of readsb's file (map/aircraft_host): every aircraft it gives with a position, its state for Settings. A kind of receiver is its name for the log, the places its
    address is tried in, and its reader."""
    name = "the aircraft receiver"
    places: Callable[[str], list[str]] = staticmethod(readsb.receiver_urls)
    read: Reader = staticmethod(readsb.read_aircraft)

    def __init__(self, ctx: SourceContext) -> None:
        super().__init__(ctx)
        self.feed = AskedFeed(self.name, EVERY_SEC["aircraft_receiver"], ctx.monotonic, stops=False, backoff_max_sec=RECEIVER_BACKOFF_MAX_SEC)     # (a new one with each address)
        self.urls = self.places(ctx.config().map_aircraft_host)
        self.host = (urlsplit(self.urls[0]).hostname or "?") if self.urls else ""      # (for the log: never the address as typed)
        self.found: str | None = None                                       # the place that answered last
        self.state: ReceiverState = ReceiverState("looking", 0, None)

    def receiver(self) -> ReceiverState:
        return self.state

    async def start(self) -> None:
        """The first question, outside the looks, for the receiver's state in Settings."""
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
    """The operator's own Radarcape (map/aircraft_host): its own list asked in its one place; with no address nothing is asked and its state is no answer."""
    name = "the Radarcape"
    places = staticmethod(_radarcape_urls)
    read = staticmethod(radarcape.read_aircraft)


Maker = Callable[[SourceContext], LayerSource]
SOURCES: dict[tuple[Layer, Source], Maker] = {("aircraft", "adsbfi"): AircraftService, ("aircraft", "adsblol"): AircraftService, ("aircraft", "radarcape"): Radarcape, ("aircraft", "receiver"): AircraftReceiver,
                                              ("ships", "fintraffic"): FintrafficShips, ("ships", "receiver"): ShipReceiver}
Key = tuple[Source, str]                        # the source in force and, for a receiver, its address: a source is made again when either changes


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
        self.changed: Signal[[]] = Signal("layers.changed")                 # what the topic `map` says of a layer changed: its source, its offer, its receiver's state
        self.told: Signal[[LayerTable]] = Signal("layers.told")             # a layer's table for the pages that look
        self._held: dict[Layer, tuple[Key, LayerSource | None]] = {}
        self._watched: set[Layer] = set()
        self._runners: dict[Layer, asyncio.Task[None]] = {}
        self._feeds: dict[str, AskedFeed] = {}
        self._counts: dict[Layer, int] = {}                                 # the things last told of each layer (the ageing tells a table again when it drops some)
        self._states: tuple[LayerState, ...] = ()
        self._tasks = TaskSet(log, "layers")
        self._retired: list[LayerSource] = []                               # sources replaced whose stop has not yet run to its end (the daemon's stop finishes them)
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
        """The layer's whole table as it is now: the things of its source not older than its age limit."""
        held = self._held.get(layer)
        if held is None:
            return LayerTable(layer, "none", False, ())
        (source, _), made = held
        if made is None:
            return LayerTable(layer, source, False, ())
        now, limit = self._clock(), max_age_sec(layer, source)
        return LayerTable(layer, source, made.away, tuple(thing for thing in made.things() if (now - thing.at).total_seconds() <= limit))

    def watch(self, layer: Layer, on: bool) -> None:
        """Some page looks at the layer (`on`), or none does any more: its source is asked while one does."""
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
        """Our position moved (the GPS): the offer of the ships, and a service that had no position to ask with."""
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
                self._run(layer)                    # (a service that had no position to ask with has one now)
        self._maybe_changed()

    def _replace(self, layer: Layer, key: Key, held: tuple[Key, LayerSource | None] | None) -> None:
        """The layer's source in force is another: the old one stops, the new one starts, and the pages that look are told its empty table."""
        self._stop_runner(layer)
        if held is not None and held[1] is not None and self.running:          # (not running: it was never started, or the daemon's stop stops it)
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
        """The feed of that name, the same across the sources made again (a service that stopped stays stopped until the daemon starts again)."""
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
        """The source asked while a page looks, as often as its feed allows; it ends when the source is not asked (listened to, stopped, nothing to ask with)."""
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
        for layer, (_, made) in list(self._held.items()):          # (sources made before the start, by a save: started now)
            if made is not None:
                self._tasks.spawn(self._start_source(layer, made), f"layers-start-{layer}")
        self._refresh()                                             # (the settings read at the start: a source that is another is made and started)
        self._tasks.spawn(self._ageing(), "layers-ageing")

    async def stop(self) -> None:
        self.running = False
        held = [made for _, made in self._held.values() if made is not None] + self._retired     # (a source replaced while the tasks end is still stopped)
        self._runners.clear()
        await self._tasks.cancel_all()
        for made in held:
            await made.stop()
