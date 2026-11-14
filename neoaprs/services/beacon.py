"""The beacon of one radio: our position packet sent on that radio every `beacon/interval_min` minutes and on request, or, for a moving station (`gps/source` is not `off`) on a radio with SmartBeaconing, when
SmartBeaconing says. Every radio has its own (the composition root makes one for each, and the controller runs it while its radio is on); the frame is the station's one maker's (services/beaconframe.py:
`BeaconFrames.position` for this radio), made when it is sent, from the settings then. The radio sends a sent frame to the packet log as a packet with direction "out", so nothing here keeps it.
A mobile beacon (services/mobilebeacon.py, neoaprs/smartbeacon.py) is the position, course, speed and altitude of the GPS fix (the services/gps.py `current()`, a fix that is not older than GPS_STALE_SEC); the
timer asks SmartBeaconing at every tick instead of waiting for an interval (`beacon/interval_min` is only On or Off there: any value but 0 is On, and it is not used), `next_due` is the time the speed of the fix says the next beacon by time is due, and `mobile` remembers the last beacon (when, the course, why:
`start` for the first fix of the run, `time`, `turn`, `request`). With no fix, none yet or none fresh, no beacon is built or sent at all (`NoFix`), and `problem` says why; the home position of the settings is never put in its place.
The interval in force on the radio is neoaprs/beaconrule.py's (`beacon_interval`: the one setting `beacon/interval_min` of the station, raised to 30 minutes while an HF radio is on); a radio whose limits have a random pause
adds one after each interval, and one that has no SmartBeaconing leaves a moving station fixed (HF: neoaprs/radiorules.py says why). The beacon is off while that is 0, for a moving station too: no timer, no SmartBeaconing, and `send_now` (Beacon now) still sends, for it is asked for. Off is not RX only: transmitting is switched off by `station/transmit`, which is the interlock's.
The last send is kept in the radio's own row (`memory_key_of`: today's `beacon/last_sent_at` for radio 1 and `hf/beacon_last_sent_at` for radio 2).

The timer is a task that looks at the clock once a `tick_sec`, so a test moves the clock and the beacon follows. The first beacon is `first_delay_sec` after the start (the radio and the TNC
settle first) unless the last beacon of an earlier run (the radio's row, written after each send) is less than an interval ago: then the first is due an interval after that one, so a restart does
not send another; then one an interval after each beacon, whether it was sent by the timer or on request. A beacon that is due while the radio is not connected, or while it is silent (it is switched
off at night), is not skipped: `next_due` stays where it was, in the past (told once per outage), and the first tick that finds the radio usable sends it, one beacon however many intervals went by. A TNC that
is settling after KISS ON is not usable either, and the beacon waits for it quietly. A frame the radio refuses (the write failed) is tried again `retry_sec` later, `ATTEMPTS` times in all; then the interval counts as skipped, and the next is the first interval boundary after now.

`frame()`, `status_frame()` and `position_info()` are the frames of the one maker under the old names: `frame()` is the queries' (app.py gives them radio 1's beacon until W3 gives them `beacon_frames`) and scripts/gen-protocol.py's;
`status_frame()` and `position_info()` are kept for the tests of the old shape (W3).
"""
import logging
from collections.abc import Callable, Mapping
import random
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsposition import uncompressed_position as uncompressed_position      # (the beacon's parts under their old names: services/beaconframe.py)
from neoaprs.beaconrule import beacon_interval
from neoaprs.clock import Clock, utcnow
from neoaprs.config import BEACON_SENT, HF_BEACON_SENT, Config, radio_state_key
from neoaprs.gpsfix import Fix
from neoaprs.interlock import Interlock
from neoaprs.radiospec import FM_ID, HF_ID, RadioId
from neoaprs.services.beaconframe import BeaconError as BeaconError, BeaconFrames, NoFix as NoFix, air_of, phg_text as phg_text
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.memory import Memory, Remembered, stamp
from neoaprs.services.mobilebeacon import MobilePlan, Positions
from neoaprs.services.radioset import AirRadio
from neoaprs.signal import Signal
from neoaprs.smartbeacon import Reason
from neoaprs.source import Source
from neoaprs.tasks import TaskSet, every

MEMORY_KEYS: Mapping[RadioId, str] = {FM_ID: BEACON_SENT, HF_ID: HF_BEACON_SENT}        # the rows of radios 1 and 2 as they are today; any other radio's is radio/<id>/beacon_last_sent_at

log = logging.getLogger("neoaprs.beacon")

FIRST_DELAY_SEC = 30.0
TICK_SEC = 1.0
RETRY_SEC = 5.0
MOBILE_GIVE_UP_SEC = 60.0                                       # a mobile beacon the radio refused ATTEMPTS times is tried again this much later, with the fix of then
ATTEMPTS = 6                                                    # the radio refusing the frame this many times in a row skips the interval


def memory_key_of(radio: RadioId) -> str:
    """The row a radio's beacon keeps its last send in (services/memory.py)."""
    return MEMORY_KEYS.get(radio) or radio_state_key(radio, "beacon_last_sent_at")


class Beacon:
    def __init__(self, radio: AirRadio | Radio, config: ConfigSource, clock: Clock = utcnow, first_delay_sec: float = FIRST_DELAY_SEC, tick_sec: float = TICK_SEC,
                 memory: Memory | None = None, retry_sec: float = RETRY_SEC, gps: Positions | None = None, *, frames: BeaconFrames | None = None) -> None:
        if frames is not None and gps is not None and gps is not frames.gps:
            raise ValueError("a beacon given the maker of frames follows the maker's GPS")
        self._old = frames is None                              # made the old way (until W3): its radios are read as the old shape, by the station's beacon/path, and its row is beacon/last_sent_at
        self._radio = air_of(radio, config, old=self._old)      # the radio it is the beacon of (services/beaconframe.py)
        self._frames = frames if frames is not None else BeaconFrames(config, gps, clock)       # the station's one maker of frames, whose GPS it follows; a beacon made the old way has its own
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
        self._memory_key = BEACON_SENT if self._old else memory_key_of(self._radio.id)       # the row the last send is kept in: the radio's own (the old call's: beacon/last_sent_at)
        self._planned_min = 0                                   # the interval next_due was planned for
        self._planned_mobile = False                            # whether it was planned for a mobile station
        self.mobile = MobilePlan()                              # the last mobile beacon, for SmartBeaconing and the page
        self.jitter: Callable[[float], float] = lambda most: random.uniform(0.0, most)       # the random pause of a radio that has one, in seconds, drawn up to `most` (a test gives its own)  # noqa: S311  (a pause on the air, no secret)
        self.sent: Signal[[ax25.Frame]] = Signal("beacon.sent")  # the frame of every beacon that went out on the radio (the iGate puts a moving station's position on APRS-IS with it)
        self._no_fix_told = False
        self._skip_told = False
        self._refused = 0                                       # how many times in a row the radio refused the due beacon
        self._retry_at: datetime | None = None                  # when the refused beacon is tried again
        self._tasks = TaskSet(log, "beacon")

    @property
    def radio(self) -> AirRadio:
        """The radio it is the beacon of."""
        return self._radio

    @property
    def frames(self) -> BeaconFrames:
        """The maker of its frames: the station's one."""
        return self._frames

    # ---- the frames, under the old names
    def frame(self, radio: AirRadio | Radio | None = None) -> ax25.Frame:
        """The frame of our position for the settings as they are now (a mobile station's: for the GPS fix as it is now), for `radio` (this beacon's by default: an answer to a station asks for the radio the
        question came on). Raises BeaconError when they do not make one, and NoFix, a BeaconError, for a mobile station with no fresh fix."""
        return self._frames.position(self._air(radio))

    def position_info(self) -> bytes:
        """The information field of our position for the receive-only iGate (BeaconFrames.position_info)."""
        return self._frames.position_info()

    def status_frame(self, text: str, radio: AirRadio | Radio | None = None) -> ax25.Frame | None:
        """The frame of a status report with this text for `radio` (this beacon's by default): BeaconFrames.status. None for an empty text; BeaconError when the settings make no frame."""
        return self._frames.status(text, self._air(radio))

    def _air(self, radio: AirRadio | Radio | None) -> AirRadio:
        return self._radio if radio is None else air_of(radio, self._config, old=self._old)

    # ---- sending
    def send_now(self, reason: str = "request") -> bool:
        """Sends the beacon on its radio and notes when and why; the next beacon counts from now: an interval and the radio's pause on, or, for a moving station on a radio with SmartBeaconing (FM), SmartBeaconing from this beacon; a moving station on a radio without it (HF) has the interval, for it sends its fix by time only. False (and `problem` says why) when the radio is not connected or
        is silent, would not take it, the settings make no frame, or a mobile station has no fresh fix. Nothing is sent while the call is not set or transmitting is off (the interlock); the beacon being Off does not stop it: Off is no automatic beacon, and Beacon now still sends."""
        if refusal := self._interlock.refused("beacon"):
            return self._failed(refusal)
        try:
            frame, fix = self._frames.position_and_fix(self._radio)
        except NoFix as e:
            return self._failed(f"no beacon: {e}")
        except BeaconError as e:
            return self._failed(f"the settings make no beacon: {e}", warn=True)
        if not self._radio.usable:
            return self._failed(self._radio.why_unusable())
        if not self._radio.send_frame(frame):
            return self._failed("the TNC did not take the frame (it is restarting into KISS mode, or the write failed)", warn=True)
        self.last_sent, self.last_reason, self.problem, self._skip_told = self.clock(), reason, "", False
        self._refused, self._retry_at = 0, None
        log.info("beacon sent (%s): %s", reason, frame.tnc2())
        self.sent.emit(frame)
        self._remembered.put({self._memory_key: stamp(self.last_sent)})
        smart = fix if self._mobile(self._config()) else None             # (a moving station on a radio without SmartBeaconing sends the fix but is planned as a fixed one: the interval and the pause)
        if smart is not None:
            self.mobile.sent(smart, self.last_sent, reason)
        self._plan_after_send(smart)
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
        self._earlier = await self._remembered.get_time(self._memory_key, now)
        self._started = now
        self._plan(self.interval_min)
        self._tasks.spawn(self._run(), "beacon")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()
        self._started, self.next_due = None, None

    def settings_changed(self) -> None:
        """The settings were saved: a changed interval, or a switch between a fixed and a mobile station, is planned from now on, at once; 0 (Off) stops the timer of a fixed one and SmartBeaconing of a mobile one. Any other change leaves the time of the next beacon alone."""
        if self._started is not None and (self.interval_min != self._planned_min or self._mobile(self._config()) != self._planned_mobile):
            self._plan(self.interval_min)

    @property
    def running(self) -> bool:
        """The timer is started (the controller runs a radio's beacon while that radio is on)."""
        return self._started is not None

    @property
    def interval_min(self) -> int:
        """The interval in force on this radio (neoaprs/beaconrule.py); 0 for one the settings do not have."""
        c = self._config()
        spec = c.radio(self._radio.id)
        return 0 if spec is None else beacon_interval(c.beacon_interval_min, spec, c.radios)

    def _mobile(self, c: Config) -> bool:
        """Whether the beacon follows the GPS: a moving station on a radio that has SmartBeaconing (FM); on HF the station is fixed whatever the GPS source says."""
        return c.mobile and self._radio.allowed.smart_beacon

    def _pause(self) -> timedelta:
        """The random pause after an interval, where the radio has one (HF, radiorules.py says why); none elsewhere."""
        most = self._radio.limits.beacon_jitter_sec
        return timedelta(seconds=self.jitter(most)) if most > 0 else timedelta()

    def _plan(self, interval_min: int) -> None:
        c = self._config()
        if interval_min > c.beacon_interval_min and interval_min != self._planned_min:
            log.info("the beacon interval %d min is raised to %d: the HF radio is on, and over HF not very often is the rule", c.beacon_interval_min, interval_min)
        """The next beacon for this interval: an interval after the latest one sent in this run, else after the one of the earlier run if that is still ahead of the start, else
        `first_delay_sec` after the start (a time that has passed is due at the next tick). A mobile station has none planned: SmartBeaconing says at each tick."""
        mobile = self._mobile(self._config())
        self._planned_min, self._planned_mobile = interval_min, mobile
        self._refused, self._retry_at = 0, None
        if self._started is None or interval_min == 0 or mobile:
            self.next_due = None
        elif self.last_sent is not None:
            self.next_due = self.last_sent + timedelta(minutes=interval_min) + self._pause()
        elif self._earlier is not None and self._earlier + timedelta(minutes=interval_min) > self._started:
            self.next_due = self._earlier + timedelta(minutes=interval_min) + self._pause()
        else:
            self.next_due = self._started + timedelta(seconds=self.first_delay_sec)

    def _plan_after_send(self, fix: Fix | None) -> None:
        if fix is not None:
            self.next_due = self.mobile.check(self._config().smart, fix, self.clock()).next_due
        elif self._started is not None and self._planned_min:
            self.next_due = self.clock() + timedelta(minutes=self._planned_min) + self._pause()

    async def _run(self) -> None:
        await every(self.tick_sec, self._tick, "the beacon ticker")

    def _due_reason(self, now: datetime) -> str | None:
        """Why a beacon is due now (`interval`, or for a mobile station what SmartBeaconing says), None when none is."""
        if self.interval_min == 0:
            return None
        if self._mobile(self._config()):
            return self._mobile_reason(now)
        return "interval" if self.next_due is not None and now >= self.next_due else None

    def _mobile_reason(self, now: datetime) -> Reason | None:
        gps = self._frames.gps                                  # (the maker's: SmartBeaconing decides on the fix the frame carries)
        fix = gps.current() if gps is not None else None
        if fix is None:
            self.next_due = None
            self.problem = f"no beacon: {gps.why_none() if gps is not None else 'no GPS is set up'}"
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

    def _tick(self) -> None:
        now = self.clock()
        usable = self._radio.usable
        if usable:
            self._skip_told = False
        reason = self._due_reason(now)
        if reason is None:
            return
        if refusal := self._interlock.refused("beacon"):
            self.problem = refusal
            return                                                  # (the beacon waits for the call, told once; it is sent at the first tick after the call is set)
        if not usable:
            if not self._skip_told and self._radio.state is not Source.State.CONNECTED:       # (a connected radio that is not usable is settling after KISS ON: the beacon waits for it, saying nothing)
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
        log.warning("the beacon was refused %d times (%s): %s", self._refused, self.problem, f"tried again in {MOBILE_GIVE_UP_SEC:g} s" if mobile else "skipped (the next one is an interval on, none is made up)")
        self._refused = 0
        if mobile:
            self._retry_at = now + timedelta(seconds=MOBILE_GIVE_UP_SEC)
        else:
            self._retry_at = None
            self._skip(self.next_due or now)

    def _skip(self, due: datetime) -> None:
        """The interval that was due passed without a beacon: the next is the first interval boundary after now."""
        step = timedelta(minutes=self._planned_min)
        self.next_due = due + step * ((self.clock() - due) // step + 1)
