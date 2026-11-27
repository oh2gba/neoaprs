"""The GPS service: the latest fix of the feed, how fresh it is, and what follows from moving.

`current()` is the fix to beacon with (fresh, else None); `mobile_fix()` is the latest fix however
old. A serial receiver's port is claimed so no radio takes it; if one holds it, the GPS waits.
"""

import asyncio
import logging
from datetime import datetime
from typing import Literal, NamedTuple

from neoaprs.claims import PORT_KINDS, Claim, Claims
from neoaprs.clock import Clock, utcnow
from neoaprs.geo import distance_km
from neoaprs.gpsfeed import NO_ADDRESS, NO_FIX, NO_PORT, GpsFeed
from neoaprs.gpsfix import Fix
from neoaprs.policy import GPS_PLACE_EVERY_SEC, GPS_PLACE_MOVED_M, GPS_STALE_SEC
from neoaprs.serialprobe import claim_value
from neoaprs.services.common import ConfigSource
from neoaprs.signal import Signal
from neoaprs.source import Source
from neoaprs.tasks import TaskSet, cancel_all, every

log = logging.getLogger("neoaprs.gps")

TICK_SEC = 1.0
GpsStateName = Literal["off", "connecting", "no_fix", "fix", "stale"]
GpsReason = Literal["", "no_port", "no_address", "held", "no_answer"]


class FeedSettings(NamedTuple):
    kind: str  # off, gpsd or serial
    target: str  # host:port of the gpsd, or the serial port
    baud: int


class Gps:
    def __init__(
        self,
        feed: GpsFeed,
        config: ConfigSource,
        clock: Clock = utcnow,
        stale_sec: float = GPS_STALE_SEC,
        tick_sec: float = TICK_SEC,
        place_every_sec: float = GPS_PLACE_EVERY_SEC,
        place_moved_m: float = GPS_PLACE_MOVED_M,
        *,
        claims: Claims | None = None,
    ) -> None:
        self._feed = feed
        self._claims = claims
        self._held_by = ""  # the radio holding the port
        self._config = config
        self.clock = clock
        self.stale_sec = stale_sec
        self.tick_sec = tick_sec
        self.place_every_sec = place_every_sec
        self.place_moved_m = place_moved_m
        self.changed: Signal[[]] = Signal("gps.changed")
        self.moved: Signal[[]] = Signal("gps.moved")
        self._fix: Fix | None = None
        self._placed: tuple[datetime, float, float] | None = None  # when and where the row was put
        self._applied: FeedSettings | None = None
        self._reading = False
        self._apply_task: asyncio.Task[None] | None = None
        self._last_summary: tuple[str, str] = ("off", "")
        self._tasks = TaskSet(log, "gps")

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
        self._let_go()

    def settings_changed(self) -> None:
        """Restart the feed if its settings changed, and restart the moved-distance count."""
        if self._applied is not None and self._wanted() != self._applied:
            self.apply()
        fix = self.mobile_fix()
        self._placed = None if fix is None else (fix.at, fix.lat, fix.lon)
        self._announce()

    def apply(self) -> None:
        """(Re)start the feed with the current settings in a task, cancelling one still starting."""
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
        self._let_go()
        if wanted.kind == "serial" and (refused := self._hold(wanted.target)):
            self._held_by = refused
            log.warning("gps: %s is %s: the GPS waits for it", wanted.target, refused)
        elif wanted.kind != "off":
            log.info("gps: reading %s", self._feed.describe() or "nothing yet (no port or address set)")
            self._reading = True
            await self._feed.start()
        elif self._reading:
            self._reading = False
            log.info("gps: off")
        self._announce()

    def _hold(self, device: str) -> str:
        """Hold the receiver's port; return why not ("held by Packet 2"), or "" if held or moot."""
        value = claim_value(device)
        if self._claims is None or value is None:
            return ""
        other = self._claims.hold(Claim("gps", value, None))
        return "" if other is None else f"held by {self._claims.words(other.holder)}"

    def _let_go(self) -> None:
        self._held_by = ""
        if self._claims is not None:
            self._claims.release(None, "gps")

    def _tick(self) -> None:
        self._take_when_free()
        self._announce()

    def _take_when_free(self) -> None:
        """Restart a receiver waiting for its port once the radio holding it lets go."""
        if not (self._held_by and self._tasks and self._applied is not None and self._claims is not None):
            return
        value = claim_value(self._applied.target)
        if value is not None and all(c.value != value or c.kind not in PORT_KINDS for c in self._claims.all()):
            self._held_by = ""
            self.apply()

    async def _run(self) -> None:
        await every(self.tick_sec, self._tick, "the GPS state announcement")

    def take(self, fix: Fix) -> None:
        """Accept a new fix from the feed."""
        self._fix = fix
        self._follow(fix)
        self._last_summary = (self.state, self.problem)
        self.changed.emit()

    def feed_changed(self) -> None:
        """Called when the feed's state or problem changed."""
        self._announce()

    def _announce(self) -> None:
        """Emit `changed` when state or problem changed; a fix going stale has no report."""
        summary = (self.state, self.problem)
        if summary != self._last_summary:
            self._last_summary = summary
            self.changed.emit()

    def _follow(self, fix: Fix) -> None:
        """Emit `moved` for the first fix, or one far enough and late enough after the last."""
        if not self._config().mobile:
            return
        placed = self._placed
        if placed is not None and (
            (fix.at - placed[0]).total_seconds() < self.place_every_sec
            or distance_km(placed[1], placed[2], fix.lat, fix.lon) * 1000.0 < self.place_moved_m
        ):
            return
        self._placed = (fix.at, fix.lat, fix.lon)
        self.moved.emit()

    @property
    def fix(self) -> Fix | None:
        """The latest fix, however old."""
        return self._fix

    @property
    def fix_age_sec(self) -> float | None:
        return None if self._fix is None else (self.clock() - self._fix.at).total_seconds()

    def current(self) -> Fix | None:
        """The latest fix if not older than `stale_sec`, else None."""
        age = self.fix_age_sec
        return self._fix if age is not None and age <= self.stale_sec else None

    def mobile_fix(self) -> Fix | None:
        """The latest fix while the beacon is mobile, else None."""
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
        """Why there is no fix to use; empty while there is one or the GPS is off."""
        return "" if self.state in ("off", "fix") else self.why_none()

    @property
    def reason(self) -> GpsReason:
        """`problem` as a code: no port, no address, port held by a radio, or feed not answering."""
        state = self.state
        if state in ("off", "fix", "stale"):
            return ""
        if state == "connecting" and self._held_by:
            return "held"
        feed = self._feed.problem
        return (
            "no_port"
            if feed == NO_PORT
            else "no_address"
            if feed == NO_ADDRESS
            else ""
            if feed in ("", NO_FIX)
            else "no_answer"
        )

    def why_none(self) -> str:
        """Why `current()` is None, as a clause for the log."""
        state = self.state
        if state == "off":
            return "the GPS is off (gps/source)"
        if state == "stale":
            return f"the latest GPS fix is {round(self.fix_age_sec or 0)} s old" + (
                f" ({self._feed.problem})" if self._feed.problem else ""
            )
        if state == "connecting":
            return (
                f"the receiver's port is {self._held_by}"
                if self._held_by
                else self._feed.problem or f"waiting for {self._feed.describe() or 'the GPS'}"
            )
        return self._feed.problem or "the receiver has no position fix yet"
