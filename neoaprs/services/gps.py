"""The GPS service: the latest fix of the feed (neoaprs/gpsfeed.py), how fresh it is, and what follows from our moving.

The feed runs while `gps/source` is `gpsd` or `serial`, which is also what makes the beacon follow the GPS (`Config.mobile`). A save of `gps/*` stops it and starts it again with the
new numbers, in a task (a gpsd that does not answer takes its five seconds, and the save does not wait).

`state` is `off`, `connecting` (the line to the receiver is not up and no fix has come), `no_fix` (it is up, none has come), `fix`, or `stale` (the latest fix is older than `stale_sec`, `GPS_STALE_SEC`). `current()` is the
fix to beacon with: the latest while it is fresh, else None; a fix older than that is never used, and the home position of the settings is never put in its place. `mobile_fix()` is the latest fix, fresh or not, while
`gps/source` is not `off`: the place our own row on the map is kept at, so that a lost GPS leaves us where we were last seen, not at home.

`moved` is emitted when the fix has taken us far enough from where our row was put (GPS_PLACE_MOVED_M, and not more often than GPS_PLACE_EVERY_SEC) for the station book to follow and the ALOHA circle to be worked out again;
the composition root connects it. `changed` is emitted when the fix, the state or the problem changes."""
import asyncio
import logging
from datetime import datetime
from typing import Literal, NamedTuple

from neoaprs.clock import Clock, utcnow
from neoaprs.geo import distance_km
from neoaprs.gpsfeed import GpsFeed
from neoaprs.gpsfix import Fix
from neoaprs.policy import GPS_PLACE_EVERY_SEC, GPS_PLACE_MOVED_M, GPS_STALE_SEC
from neoaprs.services.common import ConfigSource
from neoaprs.signal import Signal
from neoaprs.source import Source
from neoaprs.tasks import TaskSet, cancel_all, every

log = logging.getLogger("neoaprs.gps")

TICK_SEC = 1.0
GpsStateName = Literal["off", "connecting", "no_fix", "fix", "stale"]


class FeedSettings(NamedTuple):
    kind: str                   # off, gpsd or serial
    target: str                 # host:port of the gpsd, or the serial port
    baud: int


class Gps:
    def __init__(self, feed: GpsFeed, config: ConfigSource, clock: Clock = utcnow, stale_sec: float = GPS_STALE_SEC, tick_sec: float = TICK_SEC,
                 place_every_sec: float = GPS_PLACE_EVERY_SEC, place_moved_m: float = GPS_PLACE_MOVED_M) -> None:
        self._feed = feed
        self._config = config
        self.clock = clock
        self.stale_sec = stale_sec
        self.tick_sec = tick_sec
        self.place_every_sec = place_every_sec
        self.place_moved_m = place_moved_m
        self.changed: Signal[[]] = Signal("gps.changed")
        self.moved: Signal[[]] = Signal("gps.moved")
        self._fix: Fix | None = None
        self._placed: tuple[datetime, float, float] | None = None       # when and where our row was last put
        self._applied: FeedSettings | None = None
        self._reading = False                                           # a feed has been started and not ended by a switch to `off` (the log says that switch once)
        self._apply_task: asyncio.Task[None] | None = None
        self._last_summary: tuple[str, str] = ("off", "")
        self._tasks = TaskSet(log, "gps")

    # ---- the life
    async def start(self) -> None:
        if self._tasks:
            return
        self.apply()
        self._tasks.spawn(self._run(), "gps-tick")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        self._apply_task = None
        self._reading = False
        await self._feed.stop()

    def settings_changed(self) -> None:
        """The settings were saved: a changed source, address, port or speed starts the feed afresh; turning the GPS on or off starts the count of how far we moved from where our row was put afresh."""
        if self._applied is not None and self._wanted() != self._applied:
            self.apply()
        fix = self.mobile_fix()
        self._placed = None if fix is None else (fix.at, fix.lat, fix.lon)          # (the composition root has put our row at this fix, or at home, as the settings now say)
        self._announce()

    def apply(self) -> None:
        """(Re)starts the feed with the settings as they are now, in a task; one that is still starting is ended first."""
        self._applied = self._wanted()
        self._apply_task = self._tasks.spawn(self._apply(self._apply_task, self._applied), "gps-apply")

    def _wanted(self) -> FeedSettings:
        c = self._config()
        return FeedSettings(c.gps_source, c.gps_host if c.gps_source == "gpsd" else c.gps_device, c.gps_baud)

    async def _apply(self, previous: "asyncio.Task[None] | None", wanted: FeedSettings) -> None:
        if previous is not None:
            await cancel_all([previous])
        await self._feed.stop()
        self._fix, self._placed = None, None
        self._feed.configure(*wanted)
        if wanted.kind != "off":
            log.info("gps: reading %s", self._feed.describe() or "nothing yet (no port or address set)")
            self._reading = True
            await self._feed.start()
        elif self._reading:
            self._reading = False
            log.info("gps: off")
        self._announce()

    async def _run(self) -> None:
        await every(self.tick_sec, self._announce, "the GPS state announcement")

    # ---- what the feed says (connected by the composition root)
    def take(self, fix: Fix) -> None:
        """A fix came."""
        self._fix = fix
        self._follow(fix)
        self._last_summary = (self.state, self.problem)
        self.changed.emit()

    def feed_changed(self) -> None:
        """The feed's state or problem changed."""
        self._announce()

    def _announce(self) -> None:
        """Tells `changed` when the state or the problem is not what it was (the age of a fix moves a state on, with no report to say so)."""
        summary = (self.state, self.problem)
        if summary != self._last_summary:
            self._last_summary = summary
            self.changed.emit()

    def _follow(self, fix: Fix) -> None:
        """Emits `moved` when our row should follow this fix: the first one, or one far enough and late enough after the last."""
        if not self._config().mobile:
            return
        placed = self._placed
        if placed is not None and ((fix.at - placed[0]).total_seconds() < self.place_every_sec or distance_km(placed[1], placed[2], fix.lat, fix.lon) * 1000.0 < self.place_moved_m):
            return
        self._placed = (fix.at, fix.lat, fix.lon)
        self.moved.emit()

    # ---- the fix
    @property
    def fix(self) -> Fix | None:
        """The latest fix, however old."""
        return self._fix

    @property
    def fix_age_sec(self) -> float | None:
        return None if self._fix is None else (self.clock() - self._fix.at).total_seconds()

    def current(self) -> Fix | None:
        """The fix to send a beacon with: the latest while it is not older than `stale_sec`, else None."""
        age = self.fix_age_sec
        return self._fix if age is not None and age <= self.stale_sec else None

    def mobile_fix(self) -> Fix | None:
        """The latest fix while the beacon is mobile, else None: where our row on the map is while the station moves."""
        return self._fix if self._config().mobile else None

    @property
    def state(self) -> GpsStateName:
        if self._config().gps_source == "off":
            return "off"
        age = self.fix_age_sec
        if age is None:
            return "no_fix" if self._feed.state in (Source.State.CONNECTED, Source.State.SILENT) else "connecting"
        return "fix" if age <= self.stale_sec else "stale"

    @property
    def problem(self) -> str:
        """Why there is no fix to use: the feed's problem line, or that the fix is old; empty while there is a fix and for a GPS that is off."""
        return "" if self.state in ("off", "fix") else self.why_none()

    def why_none(self) -> str:
        """Why `current()` is None, as a clause for the log and the page."""
        state = self.state
        if state == "off":
            return "the GPS is off (gps/source)"
        if state == "stale":
            return f"the latest GPS fix is {round(self.fix_age_sec or 0)} s old" + (f" ({self._feed.problem})" if self._feed.problem else "")
        if state == "connecting":
            return self._feed.problem or f"waiting for {self._feed.describe() or 'the GPS'}"
        return self._feed.problem or "the receiver has no position fix yet"
