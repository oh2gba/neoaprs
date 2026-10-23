"""The beacon: our own position packet, built from the settings and sent through the Tnc every `beacon/interval_min` minutes and on request.

The frame is `frame()`: the tocall (`neoaprs.TOCALL`, not a setting), the digipeaters and the symbol, the comment and the position (`=`, a station with messaging; always the plain uncompressed form, which every receiver reads, rounded to the
hundredth of a minute and never ambiguous) come from the settings. Right after the position, before the comment, goes the PHG data extension (`PHGphgd`: power, height, gain and directivity of the antenna) when `beacon/power_w` is
set; the comment may then be 36 characters, 43 otherwise (`Config.comment_limit`), and the frame is refused when it is longer. The Tnc puts a sent frame in the packet log as a packet with direction "out", so nothing here keeps it.
The status report (`status_frame(text)`: `>` and the time as `DDHHMMz`, then the text, at most 55 printable ASCII characters without `|` and `~`) is made here, by the same tocall and path, but sent by services/rigstatus.py, not after each beacon.

The timer is a task that looks at the clock once a `tick_sec`, so a test moves the clock and the beacon follows. The first beacon is `first_delay_sec` after the start (the radio and the TNC
settle first) unless the last beacon of an earlier run (the row `beacon/last_sent_at`, written after each send) is less than an interval ago: then the first is due an interval after that one, so a restart does
not send another; then one an interval after each beacon, whether it was sent by the timer or on request. A beacon that is due while the Tnc is not connected, or while the radio is silent (it is switched
off at night), is not skipped: `next_due` stays where it was, in the past (told once per outage), and the first tick that finds the radio usable sends it, one beacon however many intervals went by. A Tnc that
is settling after KISS ON is not usable either, and the beacon waits for it quietly. A frame the Tnc refuses (the write failed) is tried again `retry_sec` later, `ATTEMPTS` times in all; then the interval counts as skipped, and the next is the first interval boundary after now.
"""
import asyncio
import logging
import math
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsposition import uncompressed_position
from neoaprs.clock import Clock, utcnow
from neoaprs.config import ANTENNA_DIRECTIONS, BEACON_SENT, SYMBOL_TABLES, Config, can_transmit
from neoaprs.configstatus import MAX_STATUS
from neoaprs.configtypes import over_the_air_problem
from neoaprs.interlock import Interlock
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, our_frame
from neoaprs.services.memory import Memory, Remembered, stamp
from neoaprs.source import Source
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.beacon")

FIRST_DELAY_SEC = 30.0
TICK_SEC = 1.0
RETRY_SEC = 5.0
ATTEMPTS = 6                                                    # the Tnc refusing the frame this many times in a row skips the interval
_FEET_PER_METRE = 3.2808


class BeaconError(ValueError):
    """The settings do not make a frame."""


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def phg_text(power_w: int, height_m: float, gain_db: int, direction: str) -> str:
    """The PHG data extension `PHGphgd`: p is the square root of the power in watts, h the base-2 logarithm of the height in tens of feet, g the gain in dB and d the directivity (0 omni, 1 NE,
    2 E ... 7 NW, 8 N, the specification's order); p and h rounded and held to 0 to 9."""
    p = min(9, _round_half_up(math.sqrt(power_w)))
    feet = height_m * _FEET_PER_METRE
    h = 0 if feet <= 10 else min(9, _round_half_up(math.log2(feet / 10)))
    return f"PHG{p}{h}{min(9, max(0, gain_db))}{ANTENNA_DIRECTIONS.index(direction)}"


class Beacon:
    def __init__(self, tnc: Radio, config: ConfigSource, clock: Clock = utcnow, first_delay_sec: float = FIRST_DELAY_SEC, tick_sec: float = TICK_SEC,
                 memory: Memory | None = None, retry_sec: float = RETRY_SEC) -> None:
        self._tnc = tnc
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self.first_delay_sec = first_delay_sec
        self.tick_sec = tick_sec
        self.retry_sec = retry_sec
        self.last_sent: datetime | None = None                  # when the latest beacon went out
        self.last_reason = ""                                   # why: "interval" or "request"
        self.next_due: datetime | None = None                   # when the timer sends the next one; None while the interval is 0 or the beacon is not started
        self.problem = ""                                       # why the latest attempt did not send; empty after one that did
        self._started: datetime | None = None
        self._earlier: datetime | None = None                   # the beacon of an earlier run, as the row kept it; None if there was none
        self._remembered = Remembered(memory)
        self._planned_min = 0                                   # the interval next_due was planned for
        self._skip_told = False
        self._refused = 0                                       # how many times in a row the Tnc refused the due beacon
        self._retry_at: datetime | None = None                  # when the refused beacon is tried again
        self._tasks = TaskSet(log, "beacon")

    # ---- the frame
    def frame(self) -> ax25.Frame:
        """The frame of our beacon for the settings as they are now. Raises BeaconError when they do not make one (a call that is not a call, a comment too long)."""
        c = self._config()
        if reason := can_transmit(c):
            raise BeaconError(reason)
        if problem := c.comment_problem():
            raise BeaconError(problem)
        if c.station_lat is None or c.station_lon is None:
            raise BeaconError("set your position first")
        if not (-90.0 <= c.station_lat <= 90.0 and -180.0 <= c.station_lon <= 180.0):
            raise BeaconError(f"the position {c.station_lat}, {c.station_lon} is not on the earth")
        if c.station_symbol_table not in SYMBOL_TABLES or len(c.station_symbol_table) != 1 or not "!" <= c.station_symbol_code <= "~" or len(c.station_symbol_code) != 1:
            raise BeaconError(f"the symbol {c.station_symbol_table!r} {c.station_symbol_code!r} is not a table (/ \\ A-Z 0-9) and one printable character")
        try:
            position = uncompressed_position(c.station_lat, c.station_lon, c.station_symbol_table, c.station_symbol_code)
        except ValueError as e:
            raise BeaconError(str(e)) from None
        return self._frame_of(b"=" + position + self._phg(c) + c.station_comment.encode("ascii"))

    @staticmethod
    def _phg(c: Config) -> bytes:
        if c.beacon_power_w is None:
            return b""
        return phg_text(c.beacon_power_w, c.beacon_antenna_height_m, c.beacon_antenna_gain_db, c.beacon_antenna_direction).encode("ascii")

    def status_frame(self, text: str) -> ax25.Frame | None:
        """The frame of a status report with this text: `>`, the time as day, hour and minute in UTC with a `z` (`211200z`), then the text; by the beacon's destination and path. None for an empty
        text. Raises BeaconError when the settings make no frame."""
        if not text:
            return None
        if problem := over_the_air_problem(text):
            raise BeaconError(f"the status: {problem}")
        if len(text) > MAX_STATUS:
            raise BeaconError(f"the status is {len(text)} characters, more than the {MAX_STATUS} that fit after its time")
        return self._frame_of(b">" + self.clock().strftime("%d%H%M").encode("ascii") + b"z" + text.encode("ascii"))

    def _frame_of(self, info: bytes) -> ax25.Frame:
        """Our frame with this information field: from `station/call` to `beacon/destination` by way of `beacon/path`."""
        c = self._config()
        if reason := can_transmit(c):
            raise BeaconError(reason)
        if len(info) > ax25.MAX_INFO:
            raise BeaconError(f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows")
        try:
            return our_frame(c, c.beacon_path_calls, info)
        except FRAME_ERRORS as e:
            raise BeaconError(str(e)) from None

    # ---- sending
    def send_now(self, reason: str = "request") -> bool:
        """Sends the beacon through the Tnc and notes when and why; the interval counts from now. False (and `problem` says why) when the Tnc is not connected or the radio is silent, would not take it, or the
        settings make no frame. Nothing is sent while the call is not set (the interlock)."""
        if refusal := self._interlock.refused("beacon"):
            return self._failed(refusal)
        try:
            frame = self.frame()
        except BeaconError as e:
            return self._failed(f"the settings make no beacon: {e}", warn=True)
        if not self._tnc.usable:
            return self._failed(self._tnc.why_unusable())
        if not self._tnc.send_frame(frame):
            return self._failed("the TNC did not take the frame (it is restarting into KISS mode, or the write failed)", warn=True)
        self.last_sent, self.last_reason, self.problem, self._skip_told = self.clock(), reason, "", False
        self._refused, self._retry_at = 0, None
        log.info("beacon sent (%s): %s", reason, frame.tnc2())
        self._remembered.put({BEACON_SENT: stamp(self.last_sent)})
        self._plan_after_send()
        return True

    def _failed(self, problem: str, warn: bool = False) -> bool:
        self.problem = problem
        if warn:
            log.warning("no beacon sent: %s", problem)
        return False

    # ---- the timer
    async def start(self) -> None:
        if self._tasks:
            return
        now = self.clock()
        self._earlier = await self._remembered.get_time(BEACON_SENT, now)
        self._started = now
        self._plan(self.interval_min)
        self._tasks.spawn(self._run(), "beacon")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()
        self._started, self.next_due = None, None

    def settings_changed(self) -> None:
        """The settings were saved: a changed interval is planned from now on, at once; 0 stops the timer. Any other change leaves the time of the next beacon alone."""
        if self._started is not None and self.interval_min != self._planned_min:
            self._plan(self.interval_min)

    @property
    def interval_min(self) -> int:
        return self._config().beacon_interval_min

    def _plan(self, interval_min: int) -> None:
        """The next beacon for this interval: an interval after the latest one sent in this run, else after the one of the earlier run if that is still ahead of the start, else
        `first_delay_sec` after the start (a time that has passed is due at the next tick)."""
        self._planned_min = interval_min
        self._refused, self._retry_at = 0, None
        if self._started is None or interval_min == 0:
            self.next_due = None
        elif self.last_sent is not None:
            self.next_due = self.last_sent + timedelta(minutes=interval_min)
        elif self._earlier is not None and self._earlier + timedelta(minutes=interval_min) > self._started:
            self.next_due = self._earlier + timedelta(minutes=interval_min)
        else:
            self.next_due = self._started + timedelta(seconds=self.first_delay_sec)

    def _plan_after_send(self) -> None:
        if self._started is not None and self._planned_min:
            self.next_due = self.clock() + timedelta(minutes=self._planned_min)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_sec)
            self._tick()

    def _tick(self) -> None:
        now = self.clock()
        due = self.next_due
        usable = self._tnc.usable
        if usable:
            self._skip_told = False
        if due is None or now < due:
            return
        if refusal := self._interlock.refused("beacon"):
            self.problem = refusal
            return                                                  # (the beacon waits for the call, told once; it is sent at the first tick after the call is set)
        if not usable:
            if not self._skip_told and self._tnc.state is not Source.State.CONNECTED:       # (a connected Tnc that is not usable is settling after KISS ON: the beacon waits for it, saying nothing)
                self._skip_told = True
                log.warning("the beacon is due and %s: it goes out when the radio is back", self._tnc.why_unusable())
            return
        if self._retry_at is not None and now < self._retry_at:
            return
        if self.send_now("interval"):
            return
        self._refused += 1
        if self._refused < ATTEMPTS:
            self._retry_at = now + timedelta(seconds=self.retry_sec)
            return
        log.warning("the beacon was refused %d times (%s): skipped (the next one is an interval on, none is made up)", self._refused, self.problem)
        self._refused, self._retry_at = 0, None
        self._skip(due)

    def _skip(self, due: datetime) -> None:
        """The interval that was due passed without a beacon: the next is the first interval boundary after now."""
        step = timedelta(minutes=self._planned_min)
        self.next_due = due + step * ((self.clock() - due) // step + 1)

