"""The beacon of one radio: our position packet, sent on an interval and on request.

A fixed station beacons by interval, after the radio's random pause within each slot; a moving one asks
SmartBeaconing at every tick. A refused frame is retried `ATTEMPTS` times, then the interval is skipped.
"""

import logging
from datetime import datetime, timedelta

from neoaprs import ax25, coded, pause
from neoaprs.aprsposition import uncompressed_position as uncompressed_position  # re-export
from neoaprs.beaconrule import beacon_interval, beacon_radios, ticked
from neoaprs.clock import Clock, StepWatch, utcnow
from neoaprs.config import BEACON_SENT, Config, can_transmit, radio_state_key
from neoaprs.gpsfix import Fix
from neoaprs.interlock import Interlock
from neoaprs.radiospec import RadioId, transmits
from neoaprs.radiotype import ONLY_RECEIVES as ONLY_RECEIVES  # re-export
from neoaprs.services.beaconframe import (
    BeaconError as BeaconError,
    BeaconFrames,
    NoFix as NoFix,
    air_of,
    phg_text as phg_text,
)
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.memory import Memory, Remembered, stamp
from neoaprs.services.mobilebeacon import MobilePlan, Positions
from neoaprs.services.radioset import AirRadio
from neoaprs.signal import Signal
from neoaprs.smartbeacon import Reason
from neoaprs.source import Source
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.beacon")

FIRST_DELAY_SEC = 30.0
TICK_SEC = 1.0
RETRY_SEC = 5.0
MOBILE_GIVE_UP_SEC = 60.0
ATTEMPTS = 6
NOT_ON_THIS_RADIO = coded.Reason(
    "the beacon does not go out on this radio (its Send on is not ticked)", "beacon.not_on_radio"
)
NOT_TAKEN = coded.Reason(
    "the TNC did not take the frame (it is restarting into KISS mode, or the write failed)", "radio.not_taken"
)


def no_fix(why: str) -> coded.Reason:
    """The reason a moving station sends no beacon: its GPS has no fresh fix."""
    return coded.Reason(f"no beacon: {why}", "beacon.no_fix")


def memory_key_of(radio: RadioId) -> str:
    """The memory row holding a radio's last beacon time: `radio/<id>/beacon_last_sent_at`."""
    return radio_state_key(radio, "beacon_last_sent_at")


class Beacon:
    def __init__(
        self,
        radio: AirRadio | Radio,
        config: ConfigSource,
        clock: Clock = utcnow,
        first_delay_sec: float = FIRST_DELAY_SEC,
        tick_sec: float = TICK_SEC,
        memory: Memory | None = None,
        retry_sec: float = RETRY_SEC,
        gps: Positions | None = None,
        *,
        frames: BeaconFrames | None = None,
    ) -> None:
        if frames is not None and gps is not None and gps is not frames.gps:
            raise ValueError("a beacon given the maker of frames follows the maker's GPS")
        self._old = frames is None  # legacy construction: old radio shape and memory row
        self._radio = air_of(radio, config, old=self._old)
        self._frames = frames if frames is not None else BeaconFrames(config, gps, clock)
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self.first_delay_sec = first_delay_sec
        self.tick_sec = tick_sec
        self.retry_sec = retry_sec
        self.last_sent: datetime | None = None
        self.last_reason = ""
        self.next_due: datetime | None = None
        # the unpaused time of next_due, and the slot of the latest timed send
        self._slot: datetime | None = None
        self._anchor: datetime | None = None
        self.problem = ""
        # what makes `problem` go when it is gone: "interlock", "send_on", "radio", or "" (the next send)
        self._cause = ""
        self._started: datetime | None = None
        self._steps = StepWatch()
        self._up = False
        self._earlier: datetime | None = None
        self._remembered = Remembered(memory)
        self._memory_key = BEACON_SENT if self._old else memory_key_of(self._radio.id)
        self._planned_min = 0
        self._planned_mobile = False
        self.mobile = MobilePlan()
        self.jitter: pause.Draw = pause.draw
        self.sent: Signal[[ax25.Frame]] = Signal("beacon.sent")
        self._no_fix_told = False
        self._skip_told = False
        self._refused = 0
        self._retry_at: datetime | None = None
        self._tasks = TaskSet(log, "beacon")

    @property
    def radio(self) -> AirRadio:
        return self._radio

    @property
    def frames(self) -> BeaconFrames:
        return self._frames

    def frame(self, radio: AirRadio | Radio | None = None) -> ax25.Frame:
        """Return our position frame for `radio` (default: this beacon's); BeaconError or NoFix."""
        return self._frames.position(self._air(radio))

    def position_info(self) -> bytes:
        """Return the position information field for the receive-only iGate."""
        return self._frames.position_info()

    def status_frame(self, text: str, radio: AirRadio | Radio | None = None) -> ax25.Frame | None:
        """Return a status frame for `text` (None if empty); raise BeaconError if impossible."""
        return self._frames.status(text, self._air(radio))

    def _air(self, radio: AirRadio | Radio | None) -> AirRadio:
        return self._radio if radio is None else air_of(radio, self._config, old=self._old)

    def send_now(self, reason: str = "request") -> bool:
        """Send the beacon now and replan from it; False, with `problem` set, on failure.

        An interval of 0 does not stop this; the interlock and `goes_out` do.
        """
        if refusal := self._interlock.refused("beacon"):
            return self._failed(refusal, cause="interlock")
        if not self.goes_out:
            spec = self._config().radio(self._radio.id)
            return self._failed(
                ONLY_RECEIVES if spec is not None and not transmits(spec) else NOT_ON_THIS_RADIO, cause="send_on"
            )
        try:
            frame, fix = self._frames.position_and_fix(self._radio)
        except NoFix as e:
            return self._failed(no_fix(str(e)))
        except BeaconError as e:
            return self._failed(coded.Reason.of(e, f"the settings make no beacon: {e}"), warn=True)
        if not self._radio.usable:
            return self._failed(self._radio.why_unusable(), cause="radio")
        if not self._radio.send_frame(frame):
            return self._failed(NOT_TAKEN.but(radio=self._radio.id, name=self._radio.name), warn=True)
        self.last_sent, self.last_reason, self.problem, self._cause, self._skip_told = (
            self.clock(),
            reason,
            "",
            "",
            False,
        )
        self._anchor = self._anchor_of(self.last_sent, reason)
        self._refused, self._retry_at = 0, None
        log.info("beacon sent (%s): %s", reason, frame.tnc2())
        self.sent.emit(frame)
        self._remembered.put({self._memory_key: stamp(self.last_sent)})
        smart = fix if self._mobile(self._config()) else None
        if smart is not None:
            self.mobile.sent(smart, self.last_sent, reason)
        self._plan_after_send(smart)
        return True

    def _failed(self, problem: str, warn: bool = False, cause: str = "") -> bool:
        self.problem, self._cause = problem, cause
        if warn:
            log.warning("no beacon sent: %s", problem)
        return False

    async def start(self) -> None:
        if self._tasks:
            return
        now = self.clock()
        self._earlier = await self._remembered.get_time(self._memory_key, now)
        self._started, self._up, self.problem = now, False, ""
        self._steps.forward(self.clock)
        if (spec := self._config().radio(self._radio.id)) is not None:
            ticked(spec, say=True)  # logs an invalid stored Send on once
        self._plan(self.interval_min)
        self._tasks.spawn(self._run(), "beacon")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()
        self._started, self.next_due = None, None

    def settings_changed(self) -> None:
        """Replan at once if the interval or fixed/mobile mode changed; else keep the schedule."""
        self._recheck()
        if self._started is not None and (
            self.interval_min != self._planned_min or self._mobile(self._config()) != self._planned_mobile
        ):
            self._plan(self.interval_min)

    def _recheck(self) -> None:
        """Drop the problem when its cause is gone: transmit is allowed, Send on is ticked, the radio takes frames."""
        cause = self._cause
        if (
            (cause == "interlock" and can_transmit(self._config()) is None)
            or (cause == "send_on" and self.goes_out)
            or (cause == "radio" and self._radio.usable)
        ):
            self.problem, self._cause = "", ""

    @property
    def running(self) -> bool:
        """Whether the timer is started."""
        return self._started is not None

    @property
    def goes_out(self) -> bool:
        """Whether the beacon goes out on this radio (`beacon_radios`); an off radio passes."""
        c = self._config()
        spec = c.radio(self._radio.id)
        return spec is None or not spec.enabled or spec.id in beacon_radios(c.radios)

    @property
    def interval_min(self) -> int:
        """The interval in force on this radio; 0 for an unknown radio or one with no beacon."""
        c = self._config()
        spec = c.radio(self._radio.id)
        return 0 if spec is None or not self.goes_out else beacon_interval(c.beacon_interval_min, spec, c.radios)

    def _mobile(self, c: Config) -> bool:
        """Whether the beacon follows the GPS; without SmartBeaconing (HF) the station is fixed."""
        return c.mobile and self._radio.allowed.smart_beacon

    def _anchor_of(self, sent: datetime, reason: str) -> datetime:
        """Return what the next interval counts from: a timed beacon's slot, else when it went."""
        if reason != "interval" or self._slot is None:
            return sent
        return pause.anchor((self._slot, self._radio.limits.beacon_jitter_sec), sent)

    def _set_due(self, slot: datetime) -> None:
        """Plan the next beacon in `slot`, after a pause drawn anew."""
        most = self._radio.limits.beacon_jitter_sec
        self._slot = slot
        self.next_due = slot + pause.capped(pause.share(self.jitter, most), most)

    def _plan(self, interval_min: int) -> None:
        """Plan `next_due`: an interval after the last send, else the earlier run's, else start."""
        c = self._config()
        if interval_min > c.beacon_interval_min and interval_min != self._planned_min:
            where = f"the {self._radio.name} radio" if self._radio.name else "this radio"
            log.info(
                "the beacon interval %d min is raised to %d on %s: %d minutes is the shortest its type takes",
                c.beacon_interval_min,
                interval_min,
                where,
                interval_min,
            )
        mobile = self._mobile(c)
        self._planned_min, self._planned_mobile = interval_min, mobile
        self._refused, self._retry_at = 0, None
        if self._started is None or interval_min == 0 or mobile:
            self.next_due = self._slot = None
        elif self.last_sent is not None:
            self._set_due((self._anchor or self.last_sent) + timedelta(minutes=interval_min))
        elif self._earlier is not None and self._earlier + timedelta(minutes=interval_min) > self._started:
            self._set_due(self._earlier + timedelta(minutes=interval_min))
        else:
            self._set_due(self._started + timedelta(seconds=self.first_delay_sec))

    def _plan_after_send(self, fix: Fix | None) -> None:
        if fix is not None:
            self.next_due = self.mobile.check(self._config().smart, fix, self.clock()).next_due
        elif self._started is not None and self._planned_min:
            self._set_due((self._anchor or self.clock()) + timedelta(minutes=self._planned_min))

    async def _run(self) -> None:
        await every(self.tick_sec, self._tick, "the beacon ticker")

    def _due_reason(self, now: datetime) -> str | None:
        """The reason a beacon is due now (`interval` or SmartBeaconing's), else None."""
        if self.interval_min == 0:
            return None
        if self._mobile(self._config()):
            return self._mobile_reason(now)
        return "interval" if self.next_due is not None and now >= self.next_due else None

    def _mobile_reason(self, now: datetime) -> Reason | None:
        gps = self._frames.gps  # the frame maker's: same fix as the frame
        fix = gps.current() if gps is not None else None
        if fix is None:
            self.next_due = None
            self.problem = no_fix(gps.why_none() if gps is not None else "no GPS is set up")
            if not self._no_fix_told:
                self._no_fix_told = True
                log.warning("%s", self.problem)
            return None
        if self._no_fix_told:
            self._no_fix_told, self.problem = False, ""
            log.info("the GPS has a fix again: the beacon follows it")
        decision = self.mobile.check(self._config().smart, fix, now)
        self.next_due = decision.next_due
        return decision.reason

    def _hold_first(self, now: datetime, usable: bool) -> None:
        """Keep the first beacon's drawn pause across a clock stepped forward and after a radio that came up late."""
        if self.last_sent is not None or self._slot is None or self.next_due is None or self._mobile(self._config()):
            self._up = self._up or usable
            return
        shift = self._steps.forward(self.clock)
        if usable and not self._up and now > self.next_due + shift:
            shift = now - self._slot
        self._up = self._up or usable
        if shift and self._started is not None:
            self._started, self._slot, self.next_due = self._started + shift, self._slot + shift, self.next_due + shift

    def _tick(self) -> None:
        now = self.clock()
        usable = self._radio.usable
        self._hold_first(now, usable)
        if usable:
            self._skip_told = False
        self._recheck()
        reason = self._due_reason(now)
        if reason is None:
            return
        if refusal := self._interlock.refused("beacon"):
            self.problem, self._cause = refusal, "interlock"
            return
        if not usable:
            # a connected radio that is unusable is settling after KISS ON: wait quietly
            if not self._skip_told and self._radio.state is not Source.State.CONNECTED:
                self._skip_told = True
                log.warning("the beacon is due and %s: it goes out when the radio is back", self._radio.why_unusable())
            return
        if self._retry_at is not None and now < self._retry_at:
            return
        if self.send_now(reason):
            return
        self._refused += 1
        if self._refused < ATTEMPTS:
            self._retry_at = now + timedelta(seconds=self.retry_sec)
            return
        mobile = self._mobile(self._config())
        log.warning(
            "the beacon was refused %d times (%s): %s",
            self._refused,
            self.problem,
            f"tried again in {MOBILE_GIVE_UP_SEC:g} s"
            if mobile
            else "skipped (the next one is an interval on, none is made up)",
        )
        self._refused = 0
        if mobile:
            self._retry_at = now + timedelta(seconds=MOBILE_GIVE_UP_SEC)
        else:
            self._retry_at = None
            self._skip(self._slot or now)

    def _skip(self, slot: datetime) -> None:
        """Skip the missed interval: the next is the first interval boundary after now."""
        step = timedelta(minutes=self._planned_min)
        self._set_due(slot + step * ((self.clock() - slot) // step + 1))
