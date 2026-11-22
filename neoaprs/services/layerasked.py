"""Source interface of the map layers, and the base of sources asked over HTTP.

`AskedFeed` paces the questions: interval, back-off, a stop after STOP_CODES, a 429's wait.
`AskedSource` is the base of a source asked through one feed."""
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

# Signature of updatefetch.fetch_feed.
FetchFeed = Callable[..., Awaitable[FeedAnswer | None]]
TOO_MANY = 429


def through(url: str, base: str) -> str:
    """Return `url` moved to the server `base` (NEOAPRS_LAYERS_URL), keeping path and query."""
    to, parts = urlsplit(base), urlsplit(url)
    return urlunsplit((to.scheme, to.netloc, parts.path, parts.query, ""))


class AskedFeed:
    """One feed of questions, asked at most every `every_sec` (monotonic seconds)."""

    def __init__(self, name: str, every_sec: float, clock: Callable[[], float], stops: bool = True, backoff_max_sec: float = BACKOFF_MAX_SEC) -> None:
        self.name, self.every_sec, self._clock, self.stops, self.backoff_max_sec = name, every_sec, clock, stops, backoff_max_sec
        self.asked_at: float | None = None
        self.not_before: float | None = None
        self.failures = 0
        self.stopped = False
        self.asked = 0

    def wait_sec(self) -> float | None:
        """Return the seconds until it may be asked (0: now), or None when stopped."""
        if self.stopped:
            return None
        if self.asked_at is None and self.not_before is None:
            return 0.0
        due = max(-float("inf") if self.asked_at is None else self.asked_at + self.every_sec, -float("inf") if self.not_before is None else self.not_before)
        return max(0.0, due - self._clock())

    def begin(self) -> bool:
        """Return True and record the question if due, so a second asker waits."""
        if self.wait_sec() != 0.0:
            return False
        self.asked_at = self._clock()
        self.asked += 1
        return True

    def succeeded(self) -> None:
        self.failures, self.not_before = 0, None

    def failed(self, answer: FeedAnswer | None = None) -> None:
        """Record a failed question; a 429 waits its Retry-After, a STOP_CODES answer stops."""
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
    """What a source may read of the daemon, and how it notifies the service."""
    layer: Layer
    source: Source
    config: Callable[[], Config]
    where: Callable[[], tuple[float, float] | None]       # own position, None if unknown
    fetch: FetchFeed
    version: str
    platform: str
    clock: Clock                                          # UTC
    monotonic: Callable[[], float]                        # for intervals
    services_on: bool
    base: str               # a local NEOAPRS_LAYERS_URL, else ""
    feed: Callable[[str, float, bool], AskedFeed]
    tell: Callable[[], None]
    changed: Callable[[], None]

    def service_url(self, url: str) -> str:
        return through(url, self.base) if self.base else url


class LayerSource(Protocol):
    """A source of a layer as the service drives it."""
    @property
    def away(self) -> bool: ...
    def things(self) -> tuple[Thing, ...]: ...           # not yet aged
    def receiver(self) -> ReceiverState | None: ...      # None for a service
    def wait_sec(self) -> float | None: ...
    async def ask(self) -> bool: ...                     # ask if due; return whether it asked
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class AskedSource:
    """A source asked over HTTP through one feed.

    `_question` returns the things to keep, or None after reporting the failure to the feed."""
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
