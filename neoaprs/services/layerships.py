"""The two ship sources of the map layer: Fintraffic and the operator's own AIS receiver.

Fintraffic is asked while a page looks, with no station data in the request. An own receiver
(`map/ships_host`) is read over NMEA. Ships are kept in memory by MMSI and aged."""
import asyncio
import logging
from datetime import datetime

from neoaprs import aisfeed
from neoaprs.aisdecode import AisDecoder, AisPosition, AisStatic
from neoaprs.configlayers import ais_host_port
from neoaprs.digitraffic import read_locations, read_vessels
from neoaprs.layerthing import AIS_RETRY_SEC, RECEIVER_BOUND, EVERY_SEC, FINTRAFFIC_HEADERS, FINTRAFFIC_LOCATIONS, FINTRAFFIC_VESSELS, MAX_PACKED, MAX_UNPACKED, SHIPS_AGE_SEC, TELL_EVERY_SEC, ReceiverState, Thing, nearest, \
    newest, within
from neoaprs.shiptable import ShipTable

from .layerasked import AskedFeed, AskedSource, SourceContext

log = logging.getLogger("neoaprs.layers")

FEED_TIMEOUT_SEC = 30.0                         # the feed is hundreds of kilobytes; allow a slow line


class FintrafficShips(AskedSource):
    """Fintraffic through two feeds: positions and ship details.

    A stopped positions feed makes the source away; stopped details only leave ships unnamed."""

    def __init__(self, ctx: SourceContext) -> None:
        super().__init__(ctx)
        self.feed = ctx.feed("Fintraffic", EVERY_SEC["fintraffic_locations"], True)
        self.vessels = ctx.feed("Fintraffic vessels", EVERY_SEC["fintraffic_vessels"], True)
        self.table = ShipTable(ctx.clock)

    @property
    def away(self) -> bool:
        return super().away or not self.ctx.services_on

    def things(self) -> tuple[Thing, ...]:
        position = self.ctx.where()
        if position is None:
            return ()
        ships = self.table.things(self.ctx.clock(), SHIPS_AGE_SEC)
        return tuple(nearest(within(ships, position, self.ctx.config().map_radius_km), position))

    def wait_sec(self) -> float | None:
        if not self.ctx.services_on or self.feed.stopped:
            return None
        waits = [wait for wait in (self.feed.wait_sec(), self.vessels.wait_sec()) if wait is not None]
        return min(waits)

    async def ask(self) -> bool:
        async with self._lock:
            asked = False
            # Details first, so names are present when positions are told.
            if self.vessels.begin():
                asked = True
                await self._vessels()
            if self.feed.begin():
                asked = True
                self._failed = not await self._locations()
            return asked

    async def _get(self, feed: AskedFeed, url: str) -> bytes | None:
        """Return the body of a 200 answer; None after a failure, which is recorded on the feed."""
        answer = await self.ctx.fetch(self.ctx.service_url(url), self.ctx.version, self.ctx.platform, FINTRAFFIC_HEADERS, MAX_PACKED, MAX_UNPACKED, timeout_sec=FEED_TIMEOUT_SEC)
        if answer is not None and answer.status == 200:
            return answer.body
        log.debug("%s: %s", feed.name, "no answer" if answer is None else f"it answered {answer.status}")
        feed.failed(answer)
        return None

    async def _locations(self) -> bool:
        body = await self._get(self.feed, FINTRAFFIC_LOCATIONS)
        if body is None:
            return False
        positions = await asyncio.to_thread(read_locations, body)
        if positions is None:
            log.debug("Fintraffic: the answer is not the expected form")
            self.feed.failed()
            return False
        for position in positions:
            self.table.position(position)
        self.feed.succeeded()
        return True

    async def _vessels(self) -> None:
        body = await self._get(self.vessels, FINTRAFFIC_VESSELS)
        if body is None:
            return
        words = await asyncio.to_thread(read_vessels, body)
        if words is None:
            log.debug("Fintraffic vessels: the answer is not the expected form")
            self.vessels.failed()
            return
        for ship in words:
            self.table.static(ship)
        self.vessels.succeeded()


class ShipReceiver:
    """The operator's own AIS receiver: one open connection and a table of its ships."""

    def __init__(self, ctx: SourceContext) -> None:
        self.ctx = ctx
        self.host, self.port = ais_host_port(ctx.config().map_ships_host)
        self.table = ShipTable(ctx.clock, RECEIVER_BOUND)
        self.decoder = AisDecoder()
        self.state = ReceiverState("looking", 0, None)
        self._heard: datetime | None = None
        self._dirty = False                                  # decoded data not yet told to the pages
        self._last_told: float | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._task: asyncio.Task[None] | None = None
        self._writer: asyncio.StreamWriter | None = None

    # ---- what the service reads
    @property
    def away(self) -> bool:
        return self.state.state != "receiving"

    def things(self) -> tuple[Thing, ...]:
        return tuple(newest(self.table.things(self.ctx.clock(), SHIPS_AGE_SEC)))

    def receiver(self) -> ReceiverState:
        return self.state

    def wait_sec(self) -> float | None:
        return None                                          # listened to, never asked

    async def ask(self) -> bool:
        return False

    # ---- the connection
    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="layers-ais")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        wait = float(AIS_RETRY_SEC[0])
        while True:
            heard = False
            try:
                heard = await self._connection()
            except (OSError, TimeoutError) as e:
                log.debug("the AIS receiver at %s: %r", self.host, e)
            except Exception:
                log.exception("the AIS receiver at %s failed", self.host)
            self._set(ReceiverState("no_answer", self.state.things, self.state.heard_at))
            if heard:
                wait = float(AIS_RETRY_SEC[0])
            await asyncio.sleep(wait)
            if not heard:
                wait = min(wait * 2, float(AIS_RETRY_SEC[1]))

    async def _connection(self) -> bool:
        """Run one connection to its end; return whether any line came over it."""
        reader, writer = await aisfeed.connect(self.host, self.port)
        self._writer = writer
        # Fresh per connection, so a partial line of a lost one is dropped.
        lines = aisfeed.Lines()
        before = self._heard
        try:
            self._set(ReceiverState("receiving", self.state.things, self.state.heard_at))
            await aisfeed.read(reader, lines, self._handle, lambda: asyncio.get_running_loop().time())
        finally:
            writer.close()
            self._writer = None
        return self._heard != before

    def _handle(self, batch: list[str]) -> None:
        now = self.ctx.clock()
        for line in batch:
            try:
                found = self.decoder.feed(line, now)
            except Exception:                                # a bad line is skipped
                log.debug("the AIS receiver at %s: a line passed over", self.host, exc_info=True)
                found = None
            if isinstance(found, AisPosition):
                self.table.position(found)
            elif isinstance(found, AisStatic):
                self.table.static(found)
            if found is not None:
                self._heard, self._dirty = now, True
        self._schedule()

    # ---- telling the pages, at most every TELL_EVERY_SEC
    def _schedule(self) -> None:
        if not self._dirty or self._timer is not None:
            return
        loop = asyncio.get_running_loop()
        due = 0.0 if self._last_told is None else max(0.0, self._last_told + TELL_EVERY_SEC - loop.time())
        self._timer = loop.call_later(due, self._tell_now)

    def _tell_now(self) -> None:
        self._timer = None
        if not self._dirty:
            return
        self._dirty = False
        self._last_told = asyncio.get_running_loop().time()
        self._set(ReceiverState(self.state.state, len(self.things()), self._heard), tell=True)

    def _set(self, state: ReceiverState, tell: bool = False) -> None:
        """Set the state, log a change of word and notify the map topic.

        The table is told if `tell` is set or the away state changed."""
        before = self.state
        if state.state != before.state:
            log.info("the AIS receiver at %s: %s", self.host, {"receiving": "receiving", "no_answer": "no answer", "looking": "looking"}[state.state])
        if state != before:
            self.state = state
            self.ctx.changed()
        if tell or state.state != before.state:
            self.ctx.tell()
