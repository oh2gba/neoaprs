"""What a source of the map's layers of traffic is to the layers' service (neoaprs/services/layers.py), and the rules of one that is asked: one feed of questions over HTTP (`AskedFeed`) with its interval,
its back-off after failures, its stop for good after a refusal of the request itself (STOP_CODES) and the wait a 429 asks for; and the base of a source asked that way (`AskedSource`).

A source is made by the service from its table keyed by (layer, source) with a `SourceContext`: what of the daemon it may read and how it tells the service that its table or its receiver's state changed.
It keeps its things in memory and nothing else; the service ages them and hands them to the pages."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from neoaprs.clock import Clock
from neoaprs.config import Config
from neoaprs.layerthing import BACKOFF_MAX_SEC, STOP_CODES, Layer, ReceiverState, Source, Thing, backoff_sec
from neoaprs.updatefetch import FeedAnswer

log = logging.getLogger("neoaprs.layers")

FetchFeed = Callable[..., Awaitable[FeedAnswer | None]]      # updatefetch.fetch_feed: (url, version, platform, headers, max_packed, max_unpacked, timeout_sec=...)
TOO_MANY = 429


def through(url: str, base: str) -> str:
    """The service's address asked of the server `base` instead (NEOAPRS_LAYERS_URL): its scheme, host and port, the service's path and query."""
    to, parts = urlsplit(base), urlsplit(url)
    return urlunsplit((to.scheme, to.netloc, parts.path, parts.query, ""))


class AskedFeed:
    """One feed of questions: asked at most every `every_sec` (by `clock`, monotonic seconds), after n failures in a row not before the back-off, after a 429 not before its Retry-After, and never again
    after an answer of STOP_CODES while `stops` (a service; the own receiver does not stop). The service keeps it by name, so that a source made again finds its feed as it was."""

    def __init__(self, name: str, every_sec: float, clock: Callable[[], float], stops: bool = True, backoff_max_sec: float = BACKOFF_MAX_SEC) -> None:
        self.name, self.every_sec, self._clock, self.stops, self.backoff_max_sec = name, every_sec, clock, stops, backoff_max_sec
        self.asked_at: float | None = None          # when it was last asked
        self.not_before: float | None = None        # the back-off or a Retry-After
        self.failures = 0                           # in a row
        self.stopped = False
        self.asked = 0                              # how many questions in all

    def wait_sec(self) -> float | None:
        """How long until it may be asked (0: now); None when it is stopped."""
        if self.stopped:
            return None
        if self.asked_at is None and self.not_before is None:
            return 0.0
        due = max(-float("inf") if self.asked_at is None else self.asked_at + self.every_sec, -float("inf") if self.not_before is None else self.not_before)
        return max(0.0, due - self._clock())

    def begin(self) -> bool:
        """Whether it may be asked now; if so, now is when it was asked (a second asker waits its turn)."""
        if self.wait_sec() != 0.0:
            return False
        self.asked_at = self._clock()
        self.asked += 1
        return True

    def succeeded(self) -> None:
        self.failures, self.not_before = 0, None

    def failed(self, answer: FeedAnswer | None = None) -> None:
        """The question failed (`answer` None: no answer, or not in the expected form): the back-off from when it was asked; a 429 waits what it says; a refusal of STOP_CODES stops the feed, with one warning."""
        self.failures += 1
        start = self._clock() if self.asked_at is None else self.asked_at
        if answer is not None and self.stops and answer.status in STOP_CODES:
            self.stopped = True
            log.warning("%s answered %d: it is not asked again until the daemon starts again", self.name, answer.status)
        elif answer is not None and answer.status == TOO_MANY and answer.retry_after_sec is not None:
            self.not_before = self._clock() + answer.retry_after_sec
        else:
            self.not_before = start + min(backoff_sec(self.every_sec, self.failures), self.backoff_max_sec)


@dataclass(frozen=True)
class SourceContext:
    """What a source may read of the daemon, and how it tells the service."""
    layer: Layer
    source: Source
    config: Callable[[], Config]
    where: Callable[[], tuple[float, float] | None]       # our position (the station book's), None while there is none
    fetch: FetchFeed
    version: str
    platform: str
    clock: Clock                                          # UTC: the time of a thing, its age
    monotonic: Callable[[], float]                        # the intervals
    services_on: bool                                     # whether a service on the internet may be asked (not with NEOAPRS_UPDATE_CHECK=0, unless NEOAPRS_LAYERS_URL names a server here)
    base: str                                             # NEOAPRS_LAYERS_URL when it names a server on this computer, else ""
    feed: Callable[[str, float, bool], AskedFeed]          # the feed of that name (name, every_sec, stops), kept by the service
    tell: Callable[[], None]                              # the source's table is to be told to the pages that look (a source that is listened to)
    changed: Callable[[], None]                           # its receiver's state changed (the topic `map`)

    def service_url(self, url: str) -> str:
        return through(url, self.base) if self.base else url


class LayerSource(Protocol):
    """A source of a layer as the service drives it."""
    @property
    def away(self) -> bool: ...                            # the last question failed or was not in the expected form, the connection is down, or there is nothing to ask with
    def things(self) -> tuple[Thing, ...]: ...           # what it holds, not yet aged
    def receiver(self) -> ReceiverState | None: ...      # an own receiver's state; None for a service
    def wait_sec(self) -> float | None: ...              # how long until it is asked next while a page looks; None: it is not asked (listened to, stopped, or nothing to ask with)
    async def ask(self) -> bool: ...                     # one question if it is due; whether one was asked
    async def start(self) -> None: ...                   # the daemon runs with it in force (a receiver: its first question, or its connection)
    async def stop(self) -> None: ...


class AskedSource:
    """A source asked over HTTP through one feed: `_question` asks and reads, and gives the things to keep, or None when it failed (having told the feed)."""
    feed: AskedFeed

    def __init__(self, ctx: SourceContext) -> None:
        self.ctx = ctx
        self._things: tuple[Thing, ...] = ()
        self._failed = False
        self._lock = asyncio.Lock()

    @property
    def away(self) -> bool:
        return self._failed or self.feed.stopped

    def things(self) -> tuple[Thing, ...]:
        return self._things

    def receiver(self) -> ReceiverState | None:
        return None

    def wait_sec(self) -> float | None:
        return self.feed.wait_sec()

    async def ask(self) -> bool:
        async with self._lock:
            if not self.feed.begin():
                return False
            things = await self._question()
            self._failed = things is None
            if things is not None:
                self._things = tuple(things)
                self.feed.succeeded()
            return True

    async def _question(self) -> list[Thing] | None:
        raise NotImplementedError

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
