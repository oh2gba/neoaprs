"""Our status report: when it is sent, and what it says.

The text comes from the radio through Hamlib rigctld (`status/source` `rig`) or from `station/status`
(`text`). A report goes out per radio in its interval's slot, after the radio's random pause.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Literal

from neoaprs import ax25, pause
from neoaprs.beaconrule import beacon_interval, send_on_radios
from neoaprs.clock import Clock, utcnow
from neoaprs.coded import Reason
from neoaprs.config import STATUS_SENT, STATUS_TEXT, Config, radio_state_key
from neoaprs.configstatus import MAX_STATUS, fill_template
from neoaprs.configtypes import over_the_air_problem
from neoaprs.interlock import Interlock
from neoaprs.radiospec import RadioId, live
from neoaprs.rigctld import Reading, RigError, read_rig
from neoaprs.services.beacon import Beacon
from neoaprs.services.beaconframe import BeaconError, BeaconFrames, air_of
from neoaprs.services.common import ConfigSource, Radio, is_pick
from neoaprs.services.memory import Memory, Remembered, stamp
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, first_sender
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.status")

POLL_SEC = 30.0
TICK_SEC = 1.0
NO_TEXT = Reason("there is no status text", "status.no_text")
RigState = Literal["off", "on", "unused"]
Reader = Callable[[str, int], Awaitable[Reading]]


def memory_key_of(radio: RadioId) -> str:
    """Return the memory row holding when the last status went out on the radio."""
    return radio_state_key(radio, "status_last_sent_at")


def freq_text(hz: int) -> str:
    """Return the frequency as `14.074 MHz`, rounded to the kHz."""
    khz = (hz + 500) // 1000
    return f"{khz // 1000}.{khz % 1000:03d} MHz"


def clipped(text: str, max_length: int = MAX_STATUS) -> str:
    """Return the text cut to `max_length`; anything but allowed printable ASCII becomes `?`."""
    return "".join(c if over_the_air_problem(c) == "" else "?" for c in text)[:max_length]


class RigStatus:
    def __init__(
        self,
        radios: RadioPick | Radio,
        config: ConfigSource,
        frames: BeaconFrames | Beacon,
        clock: Clock = utcnow,
        poll_sec: float = POLL_SEC,
        read: Reader = read_rig,
        memory: Memory | None = None,
        tick_sec: float = TICK_SEC,
    ) -> None:
        self._radios = radios
        self._config = config
        self._interlock = Interlock(config)
        self._frames = frames.frames if isinstance(frames, Beacon) else frames
        self._old = isinstance(frames, Beacon) or not is_pick(radios)
        self.clock = clock
        self.poll_sec = poll_sec
        self.tick_sec = tick_sec
        self._read = read
        self.jitter: pause.Draw = pause.draw
        self._started: datetime | None = None
        # by radio: the drawn pause of the current wait as a share of the most, the wait's slot and
        # how late in it the report may go, the slot of the latest timed report, no new try before a time
        self._shares: dict[RadioId, float] = {}
        self._slots: dict[RadioId, tuple[datetime, float]] = {}
        self._anchors: dict[RadioId, datetime] = {}
        self._retry_at: dict[RadioId, datetime] = {}
        # the text of the latest poll, and when it was read
        self._text: str | None = None
        self._text_at: datetime | None = None
        # when the latest report went out, restored after a restart
        self.last_sent_at: datetime | None = None
        # what it said; empty until one has gone
        self.last_text = ""
        self.rig_state: RigState = "unused"
        # when the latest report went out on each radio, restored after a restart
        self.sent_on: dict[RadioId, datetime] = {}
        # radio with no send yet: the station's latest report when it joined; counted from there
        self._joined: dict[RadioId, datetime | None] = {}
        # last logged reason a report was not sent on each radio (NO_RADIO under 0)
        self._told: dict[RadioId, str] = {}
        # why the radio gave no reading last time
        self._rig_problem = ""
        self._remembered = Remembered(memory)
        self._tasks = TaskSet(log, "status")

    # ---- the life
    async def start(self) -> None:
        if self._tasks:
            return
        # nothing sent in this run: the stored row is the latest
        if self.last_sent_at is None and not self.last_text:
            self.last_sent_at = await self._remembered.get_time(STATUS_SENT, self.clock())
            self.last_text = await self._remembered.get(STATUS_TEXT) or ""
        if is_pick(self._radios):
            for spec in live(self._config().radios):
                if (
                    spec.id not in self.sent_on
                    and (at := await self._remembered.get_time(memory_key_of(spec.id), self.clock())) is not None
                ):
                    self.sent_on[spec.id] = at
        self._started = self.clock()
        self._tasks.spawn(self._run(), "rigstatus")
        self._tasks.spawn(every(self.tick_sec, self._tick, "the status timer"), "rigstatus-tick")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()

    async def _run(self) -> None:
        await every(self.poll_sec, self.poll, "the status poll", at_start=True)

    @property
    def frames(self) -> BeaconFrames:
        """The station's frame maker."""
        return self._frames

    def _radio(self) -> AirRadio | None:
        """Return the radio ?APRSS uses when none is named: first sender or old-shape radio."""
        return first_sender(self._radios) if is_pick(self._radios) else air_of(self._radios, self._config, old=True)

    def _targets(self, c: Config) -> list[tuple[RadioId, AirRadio | None, int]]:
        """Return the target radios with each one's interval in minutes.

        The radio is None for one the registry does not run."""
        if not is_pick(self._radios):
            radio = air_of(self._radios, self._config, old=True)
            return [(radio.id, radio, c.status_interval_min)]
        found: list[tuple[RadioId, AirRadio | None, int]] = []
        for id in send_on_radios("status", c.radios):
            spec = c.radio(id)
            found.append(
                (
                    id,
                    self._radios.get(id),
                    c.status_interval_min if spec is None else beacon_interval(c.status_interval_min, spec),
                )
            )
        return found

    def _counts_from(self, id: RadioId) -> datetime | None:
        """Return when the radio's interval counts from: its last timed slot or send, else when it joined.

        None means due from the start."""
        if (own := self._anchors.get(id) or self.sent_on.get(id)) is not None:
            return own
        return self._joined.setdefault(id, self.last_sent_at)

    def _due_at(self, id: RadioId, radio: AirRadio | None, minutes: int) -> datetime:
        """Return when the radio's next timed report goes: in its slot, never before the start, after its pause."""
        now = self.clock()
        if self._started is None or now < self._started:  # a clock set back starts the wait anew
            self._started = now
        since = self._counts_from(id)
        slot = self._started if since is None else max(since + timedelta(minutes=minutes), self._started)
        most = 0 if radio is None else radio.limits.beacon_jitter_sec
        if most > 0 and id not in self._shares:
            self._shares[id] = pause.share(self.jitter, most)
        self._slots[id] = (slot, min(most, minutes * 60))
        return slot + pause.capped(self._shares.get(id, 0.0), most, minutes * 60)

    def on_radio(self, id: RadioId) -> tuple[datetime | None, datetime | None, int]:
        """Return the radio's last send, its next timed send, and its interval in minutes.

        The next send is None if not timed; the interval is 0 if the status does not go there."""
        c = self._config()
        spec = c.radio(id)
        minutes = (
            next((m for target, _, m in self._targets(c) if target == id), 0)
            if spec is not None and spec.enabled and not spec.removed
            else 0
        )
        last = self.sent_on.get(id)
        timed = minutes > 0 and c.beacon_on and c.status_choice != "off" and last is not None
        radio = next((radio for target, radio, _ in self._targets(c) if target == id), None)
        return last, self._due_at(id, radio, minutes) if timed else None, minutes

    # ---- one poll
    async def poll(self) -> None:
        """Read the radio or take the static text, and send a report when due."""
        c = self._config()
        text = await self._current(c)
        self._text, self._text_at = text, self.clock()
        if text:
            self._offer(text, c)

    def _tick(self) -> None:
        """Send what is due with the text of the latest poll; the radio is not read."""
        c = self._config()
        if c.beacon_on and (text := self._cached(c)):
            self._offer(text, c, ticked=True)

    def _cached(self, c: Config) -> str | None:
        """Return the status text without reading the radio; None for none or a reading too old."""
        if c.status_rig_address is None:
            return c.station_status if c.status_choice == "text" else None
        if self._text_at is None or self.clock() - self._text_at > timedelta(seconds=2 * self.poll_sec):
            return None
        return self._text

    async def _current(self, c: Config) -> str | None:
        """Return the current status text, or None for no status (off, or the radio is away)."""
        address = c.status_rig_address
        if address is not None:
            return await self._from_rig(c, address)
        self._set_state("unused", "")
        return c.station_status if c.status_choice == "text" else None

    async def send_now(self) -> str:
        """Send the status now, ignoring the interval; return "" when sent, else the Reason."""
        c = self._config()
        if c.status_choice == "off":
            return Reason("the status is off", "status.off")
        if reason := self._interlock.refused("status"):
            return reason
        text = await self._current(c)
        if text is None:
            return (
                Reason("the radio does not answer", "status.rig_away")
                if self._rig_problem
                else Reason("the status has no radio to come from: set Rigctld", "status.no_rig")
            )
        if not text:
            return NO_TEXT
        return self._try(text)

    async def _from_rig(self, c: Config, address: tuple[str, int]) -> str | None:
        where = f"rigctld at {address[0]}:{address[1]}"
        try:
            reading = await self._read(*address)
        except RigError as e:
            self._rig_problem = f"{where}: {e}"
            self._set_state("off", f"{self._rig_problem}: no status while it is away")
            return None
        self._set_state("on", f"{where}: the radio answers ({freq_text(reading.hz)} {reading.mode})")
        return clipped(fill_template(c.status_template, freq_text(reading.hz), reading.mode))

    def _set_state(self, state: RigState, words: str) -> None:
        """Record the rig state; log it once per change (a warning when the radio goes away)."""
        if state != self.rig_state:
            self.rig_state = state
            if words:
                (log.warning if state == "off" else log.info)("%s", words)

    def _offer(self, text: str, c: Config, ticked: bool = False) -> None:
        """Send the report on the radios whose time has come; the timer skips a radio that refused it lately."""
        if not c.beacon_on:
            # beacon off means no automatic status; send_now still sends
            return
        now, targets = self.clock(), self._targets(c)
        for gone in self._joined.keys() - {id for id, _, _ in targets}:
            # a radio that left joins again at the next interval, not at once
            del self._joined[gone]
        due = [
            (id, radio)
            for id, radio, minutes in targets
            if not (ticked and now < self._retry_at.get(id, now)) and now >= self._due_at(id, radio, minutes)
        ]
        if due:
            self._try(text, due, timed=True)

    def _try(self, text: str, targets: list[tuple[RadioId, AirRadio | None]] | None = None, timed: bool = False) -> str:
        """Send the status on each target (all targets if none given).

        Return "" if it went out on a radio, else the reason; each is logged once per radio."""
        if reason := self._interlock.refused("status"):
            return reason
        if targets is None:
            targets = [(id, radio) for id, radio, _ in self._targets(self._config())]
        if not targets:
            self._tell(0, NO_RADIO)
            return NO_RADIO
        reasons = [self._send_on(id, radio, text, timed) for id, radio in targets]
        return "" if "" in reasons else reasons[0]

    def _send_on(self, id: RadioId, radio: AirRadio | None, text: str, timed: bool = False) -> str:
        """Send the status on one radio; return "" when sent, else the reason (logged once)."""
        if radio is None:
            self._tell(id, NO_RADIO)
            return NO_RADIO
        try:
            # built for this radio: no path and a frame cap on HF; None if longer than it carries
            frame = self._frames.status(text, radio)
        except BeaconError as e:
            reason = Reason.of(e, f"the settings make no status: {e}")
            self._tell(id, reason, warn=True)
            return self._held(id, reason, timed)
        if frame is None:
            return self._held(id, NO_TEXT, timed)
        if not radio.usable:
            self._tell(id, f"{radio.why_unusable()}: the status waits")
            return radio.why_unusable()
        if not radio.send_frame(frame):
            reason = Reason("the TNC did not take the status frame", "radio.not_taken", radio=radio.id, name=radio.name)
            self._tell(id, reason, warn=True)
            return self._held(id, reason, timed)
        now = self.clock()
        self.last_sent_at, self.last_text, self.sent_on[id] = now, text, now
        self._anchors[id] = pause.anchor(self._slots.pop(id, None) if timed else None, now)
        self._shares.pop(id, None)
        self._retry_at.pop(id, None)
        self._told.pop(id, None)
        self._told.pop(0, None)
        self._remembered.put(
            {
                STATUS_SENT: stamp(now),
                STATUS_TEXT: text,
                **({memory_key_of(id): stamp(now)} if is_pick(self._radios) else {}),
            }
        )
        log.info("status sent: %s", frame.tnc2())
        return ""

    def _held(self, id: RadioId, reason: str, timed: bool) -> str:
        """Return the reason; the timer does not try a refused timed report again before the next poll."""
        if timed:
            self._retry_at[id] = self.clock() + timedelta(seconds=self.poll_sec)
        return reason

    def _tell(self, id: RadioId, reason: str, warn: bool = False) -> None:
        if reason != self._told.get(id, ""):
            self._told[id] = reason
            (log.warning if warn else log.info)("no status sent: %s", reason)

    # ---- what ?APRSS answers with
    def status_frame(self, radio: AirRadio | Radio | None = None) -> ax25.Frame | None:
        """Return the last status as a frame stamped now for `radio`, or None if none was sent.

        `radio` defaults to the first sending radio. Raise BeaconError if no frame can be made."""
        if not self.last_text:
            return None
        target = self._radio() if radio is None else air_of(radio, self._config, old=self._old)
        if target is None:
            raise BeaconError.of(NO_RADIO)
        return self._frames.status(self.last_text, target)
