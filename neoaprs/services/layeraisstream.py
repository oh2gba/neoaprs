"""Ships from AISStream with the operator's own key (`map/ships_key`).

One WebSocket while a page looks at the layer, for the box round the map's circle; a changed box is
subscribed again, at most once a second. Reconnects back off with jitter; a refused key is tried
again after a longer back-off. The server closes the connection without a word, at once after the
subscription, for a key it does not know."""

import asyncio
import logging
import random
import ssl
from urllib.parse import urlsplit

from neoaprs import nodevices
from neoaprs.aisdecode import AisPosition, AisStatic
from neoaprs.aisstream import Box, Confirmed, Refused, boxes, read_message, subscription
from neoaprs.layerthing import AIS_RETRY_SEC, LIMIT, SHIPS_AGE_SEC, TELL_EVERY_SEC, Problem, Thing, nearest, within
from neoaprs.shiptable import ShipTable
from neoaprs.tasks import TaskSet
from neoaprs.websocketclient import WebSocketClient, WebSocketError

from .layerasked import SourceContext

log = logging.getLogger("neoaprs.layers")

NAME = "AISStream"
# The handshake has taken over 20 s; 45 s has always been enough.
CONNECT_SEC = 45.0
FOLLOW_SEC = 1.0  # the server closes a connection that subscribes more often
PING_SEC = 30.0
# Nothing at all for this long, not even the answer to a ping, is a stalled connection.
STALL_SEC = 90.0
# a table of ships this large is cut to the newest (the box is larger than the circle)
BOUND = 4 * LIMIT
# Connections in a row that the server ended cleanly, with nothing said, within QUICK_CLOSE_SEC of
# the subscription, which make the key refused. A reset, a timeout or a stall is an outage instead.
SILENT_CLOSES = 3
QUICK_CLOSE_SEC = 5.0
# A refused key is tried again after this, doubled per refusal up to the second.
REFUSED_RETRY_SEC = (600.0, 21600.0)
# A connection that lasted this long resets the back-off.
STEADY_SEC = 60.0


class AisStreamShips:
    """The source of the Ships layer while AISStream is chosen; asked only while a page looks."""

    def __init__(self, ctx: SourceContext, key: str, url: str) -> None:
        self.ctx, self.key, self.url = ctx, key, url
        self.table = ShipTable(ctx.clock, BOUND)
        self.refused = False
        self.receiving = False
        self.connections = 0
        self._failures = 0
        self._silent = 0
        self._refusals = 0
        self._stalled = False
        self._not_before = 0.0
        self._sent: tuple[Box, ...] | None = None
        self._subscribed_at = -FOLLOW_SEC
        self._last_told: float | None = None
        self._timer: asyncio.TimerHandle | None = None

    @property
    def away(self) -> bool:
        return not self.receiving or self.refused or not self.ctx.services_on

    @property
    def problem(self) -> Problem:
        return "key_refused" if self.refused else ""

    def things(self) -> tuple[Thing, ...]:
        position = self.ctx.where()
        if position is None:
            return ()
        ships = self.table.things(self.ctx.clock(), SHIPS_AGE_SEC)
        return tuple(nearest(within(ships, position, self.ctx.config().map_radius_km), position))

    def receiver(self) -> None:
        return None

    def wait_sec(self) -> float | None:
        if not self.ctx.services_on or not self.key or self.ctx.where() is None:
            return None
        return max(0.0, self._not_before - self.ctx.monotonic())

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def ask(self) -> bool:
        """Run one connection to its end (a page stopping to look cancels it); then wait a while."""
        heard, began = False, self.ctx.monotonic()
        try:
            heard = await self._connection()
        except (OSError, TimeoutError, WebSocketError, ssl.SSLError) as e:
            log.debug("%s: %r", NAME, e)
            self._silent = 0
        finally:
            self._set_receiving(False)
        steady = heard and self.ctx.monotonic() - began >= STEADY_SEC
        self._failures = 0 if steady else self._failures + 1
        if self.refused:
            wait = min(REFUSED_RETRY_SEC[0] * 2 ** min(self._refusals - 1, 10), REFUSED_RETRY_SEC[1])
        else:
            wait = min(AIS_RETRY_SEC[0] * 2 ** min(self._failures, 10), AIS_RETRY_SEC[1])
        self._not_before = self.ctx.monotonic() + wait * random.uniform(0.5, 1.0)  # noqa: S311 (a jitter)
        return True

    def _areas(self) -> tuple[Box, ...] | None:
        position = self.ctx.where()
        return None if position is None else boxes(*position, self.ctx.config().map_radius_km)

    async def _connection(self) -> bool:
        """Return whether a ship came over the connection."""
        parts = urlsplit(self.url)
        nodevices.check_host(parts.hostname or "", NAME)
        secure = parts.scheme == "wss"
        ws = await WebSocketClient.connect(
            parts.hostname or "",
            parts.port or (443 if secure else 80),
            parts.path or "/",
            CONNECT_SEC,
            ssl.create_default_context() if secure else None,
            deflate=True,
            agent=f"NeoAPRS/{self.ctx.version}",
        )
        self.connections += 1
        tasks = TaskSet(log, NAME)
        heard = confirmed = False
        self._stalled = False
        try:
            areas = self._areas()
            if areas is None:
                return False
            await self._subscribe(ws, areas)  # within the server's 3 seconds
            subscribed = self.ctx.monotonic()
            tasks.spawn(self._follow(ws), "aisstream-follow")
            while (message := await ws.recv()) is not None:
                found = read_message(message[1], self.ctx.clock())
                if isinstance(found, Refused):
                    self._refused(found)
                    return heard
                if isinstance(found, Confirmed):
                    log.info("%s: subscribed", NAME)
                    confirmed, self._silent = True, 0
                    self._accepted()
                    self._set_receiving(True)
                elif isinstance(found, AisPosition):
                    self.table.position(found)
                    heard = True
                    self._accepted()
                    self._set_receiving(True)
                    self._tell_soon()
                elif isinstance(found, AisStatic):
                    self.table.static(found)
            quick = self.ctx.monotonic() - subscribed <= QUICK_CLOSE_SEC
            if not (confirmed or heard or ws.heard_data or ws.lost or self._stalled) and quick:
                self._silent += 1
                if self._silent >= SILENT_CLOSES:
                    self._silent = 0
                    self._refused(Refused(True, "the connection was closed at once after the subscription"))
                    return heard
            else:
                self._silent = 0
            log.info("%s: the server closed the connection", NAME)
            return heard
        finally:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            await tasks.cancel_all()
            ws.close()

    async def _subscribe(self, ws: WebSocketClient, areas: tuple[Box, ...]) -> None:
        await ws.send_text(subscription(self.key, areas))
        self._sent, self._subscribed_at = areas, self.ctx.monotonic()

    async def _follow(self, ws: WebSocketClient) -> None:
        """Subscribe again when the box changes; ping, and close a connection that has stalled."""
        loop = asyncio.get_running_loop()
        pinged = loop.time()
        while True:
            await asyncio.sleep(FOLLOW_SEC)
            areas = self._areas()
            if areas is not None and areas != self._sent and self.ctx.monotonic() - self._subscribed_at >= FOLLOW_SEC:
                log.info("%s: the area changed, subscribing again", NAME)
                await self._subscribe(ws, areas)
            if loop.time() - ws.heard > STALL_SEC:
                log.info("%s: nothing came for %d s, connecting again", NAME, STALL_SEC)
                self._stalled = True
                ws.close()
                return
            if loop.time() - pinged >= PING_SEC:
                pinged = loop.time()
                await ws.ping()

    def _refused(self, refused: Refused) -> None:
        words = refused.words.replace(self.key, "...") if self.key else refused.words
        if refused.key:
            self._refusals += 1
            log.warning("%s refused the key: %s", NAME, words)
            if not self.refused:
                self.refused = True
                self.ctx.changed()
                self.ctx.tell()
        else:
            log.info("%s answered: %s", NAME, words)

    def _accepted(self) -> None:
        self._refusals = 0
        if self.refused:
            self.refused = False
            log.info("%s took the key", NAME)
            self.ctx.changed()
            self.ctx.tell()

    def _set_receiving(self, on: bool) -> None:
        if on != self.receiving:
            self.receiving = on
            self.ctx.tell()

    def _tell_soon(self) -> None:
        """Tell the pages, at most every TELL_EVERY_SEC: what came between is told at the end of it."""
        if self._timer is not None:
            return
        loop = asyncio.get_running_loop()
        due = 0.0 if self._last_told is None else max(0.0, self._last_told + TELL_EVERY_SEC - loop.time())
        self._timer = loop.call_later(due, self._tell_now)

    def _tell_now(self) -> None:
        self._timer = None
        self._last_told = asyncio.get_running_loop().time()
        self.ctx.tell()
