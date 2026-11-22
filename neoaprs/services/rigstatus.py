"""Our status report: when it is sent, and what it says.

`status/source` says where the status comes from: `rig`, `text` or `off` (empty: `rig` while `status/rigctld` is set, else `text` while `station/status` is not empty, else `off`; `Config.status_choice`). With `rig` (host:port of a Hamlib rigctld in `status/rigctld`) the status is made from the radio: every POLL_SEC a fresh short connection asks for the frequency and the mode (neoaprs/rigctld.py) and
`status/template` is filled in ({freq} as `14.074 MHz`, {mode} as rigctld names it: USB, LSB, CW, FM ...). A radio that is off (`RPRT -n`), a refused connection or no answer in time is "off": nothing is sent,
and the log says so once for as long as it lasts, not at every poll. With `text` the status is the static text `station/status` ("unused"); with `off` there is none ("unused" too).

One rule for both: a status report goes out when `status/interval_min` has passed since the last one sent (or none was ever sent), whether what it says has changed or not: a static text goes out again at every interval, and a radio's frequency and
mode are read afresh each time. So nothing goes inside the interval however the dial moves, and nothing while the radio is off. The time and the text of the last report are kept in the rows `status/last_sent_at` and `status/last_text`
(written after each send) and read at the start, so a restart sends nothing inside the interval. The report is the frame the station's one maker of frames makes (services/beaconframe.py, `BeaconFrames.status`: `>`
and the time as `DDHHMMz`, then the text, by the beacon's destination and the radio's path) for each radio it goes on. `last_text` is what `?APRSS` answers with (`status_frame()`, for the radio the
question came on) and what the page shows as the current status. `send_now()` sends one at once, whatever the interval (the page's "Send status now"), by the same checks of the interlock,
the length and the radio, on each radio the status goes on that takes it now, and the interval counts from it on each of them.

The radios it goes on are neoaprs/beaconrule.py's `send_on_radios("status", ...)`, the status's Send on in the beacon's pattern (each radio's own "status" tick, unticked by default; with one radio that can
send, that one; with several the ticked ones exactly, and none while none is). The text is read once a poll and is the same on every radio (one rigctld for the
station). On each radio the status goes at `status/interval_min` raised to that radio's own floor (beaconrule.beacon_interval, the beacon's: 30 minutes on HF and LoRa), counted from its last send there:
one report per interval per radio, kept in the radio's own row `radio/<id>/status_last_sent_at`; a radio with no send of
its own yet counts from the station's latest report (`status/last_sent_at`), so that a radio ticked later joins at the next interval, also one that was a radio of the status before. A radio that is not connected, silent or would not
take the frame is waited for (tried at every poll, as the beacon waits), and a report longer than the radio carries whole is not sent there (BeaconFrames.status). A radio that only receives is never one. No automatic status report goes while the beacon is off (`beacon/interval_min` is 0: quietly, as nothing is due; `send_now` still sends), and one that was held back goes at the first poll after the beacon is on if the
interval has passed. A report that cannot go (there is no radio, it is not connected or it is silent, would not take it, the settings make no frame) is told once for each reason and tried again at the next poll.

The radios come as the registry's (`RadioPick`), or in the old shape of services/common.Radio (the old set of two, a Tnc, a test's stub), which is then the one radio the report goes on, at the interval
itself; the frames as the one maker, or as a beacon made the old way, whose maker is then the one (W3 deletes the old shapes).
"""
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Literal

from neoaprs import ax25
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
NO_TEXT = Reason("there is no status text", "status.no_text")
RigState = Literal["off", "on", "unused"]
Reader = Callable[[str, int], Awaitable[Reading]]


def memory_key_of(radio: RadioId) -> str:
    """The row a radio keeps the last status sent on it in (services/memory.py): its own, `radio/<id>/status_last_sent_at`."""
    return radio_state_key(radio, "status_last_sent_at")


def freq_text(hz: int) -> str:
    """The frequency as `14.074 MHz`: megahertz with three decimals, rounded to the kHz."""
    khz = (hz + 500) // 1000
    return f"{khz // 1000}.{khz % 1000:03d} MHz"


def clipped(text: str, max_length: int = MAX_STATUS) -> str:
    """The text as a status may carry it: only printable ASCII (what the radio names a mode with anything else, and `|` and `~`, becomes `?`), cut to at most `max_length` characters."""
    return "".join(c if over_the_air_problem(c) == "" else "?" for c in text)[:max_length]


class RigStatus:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, frames: BeaconFrames | Beacon, clock: Clock = utcnow, poll_sec: float = POLL_SEC, read: Reader = read_rig,
                 memory: Memory | None = None) -> None:
        self._radios = radios
        self._config = config
        self._interlock = Interlock(config)
        self._frames = frames.frames if isinstance(frames, Beacon) else frames
        self._old = isinstance(frames, Beacon) or not is_pick(radios)      # the old call (until W3): a radio that has rules is read as the old shape, by the station's beacon/path
        self.clock = clock
        self.poll_sec = poll_sec
        self._read = read
        self.last_sent_at: datetime | None = None               # when the latest status report went out, as the row kept it after a restart
        self.last_text = ""                                     # what it said; empty until one has gone (or was kept)
        self.rig_state: RigState = "unused"
        self.sent_on: dict[RadioId, datetime] = {}              # when the latest report went out on each radio, as its row kept it after a restart
        self._joined: dict[RadioId, datetime | None] = {}       # for a radio with no send of its own: the station's latest report when it was first a radio of the status, which its interval counts from
        self._told: dict[RadioId, str] = {}                     # the reason a report was not sent on each radio, as last told (NO_RADIO under 0)
        self._rig_problem = ""                                  # why the radio gave no reading the last time
        self._remembered = Remembered(memory)
        self._tasks = TaskSet(log, "status")

    # ---- the life
    async def start(self) -> None:
        if self._tasks:
            return
        if self.last_sent_at is None and not self.last_text:               # (nothing sent in this run: what the row kept is the latest)
            self.last_sent_at = await self._remembered.get_time(STATUS_SENT, self.clock())
            self.last_text = await self._remembered.get(STATUS_TEXT) or ""
        if is_pick(self._radios):
            for spec in live(self._config().radios):
                if spec.id not in self.sent_on and (at := await self._remembered.get_time(memory_key_of(spec.id), self.clock())) is not None:
                    self.sent_on[spec.id] = at
        self._tasks.spawn(self._run(), "rigstatus")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()

    async def _run(self) -> None:
        await every(self.poll_sec, self.poll, "the status poll", at_start=True)

    @property
    def frames(self) -> BeaconFrames:
        """The maker of its frames: the station's one."""
        return self._frames

    def _radio(self) -> AirRadio | None:
        """The radio ?APRSS is answered for when none is named (a test's: the daemon names the radio the question came on): the first radio that can send (None while there is none), or the radio of the
        old shape it was given."""
        return first_sender(self._radios) if is_pick(self._radios) else air_of(self._radios, self._config, old=True)

    def _targets(self, c: Config) -> list[tuple[RadioId, AirRadio | None, int]]:
        """The radios the report goes on (beaconrule.send_on_radios), by position, each with the interval in force on it in minutes: `status/interval_min` raised to its own floor; the registry's radio is
        None for one it does not run. The radio of the old shape alone, at the interval itself."""
        if not is_pick(self._radios):
            radio = air_of(self._radios, self._config, old=True)
            return [(radio.id, radio, c.status_interval_min)]
        found: list[tuple[RadioId, AirRadio | None, int]] = []
        for id in send_on_radios("status", c.radios):
            spec = c.radio(id)
            found.append((id, self._radios.get(id), c.status_interval_min if spec is None else beacon_interval(c.status_interval_min, spec)))
        return found

    def _counts_from(self, id: RadioId) -> datetime | None:
        """When the interval on the radio counts from: its own last send; for one that has none, the station's latest report when it first was a radio of the status (None: due now)."""
        if (own := self.sent_on.get(id)) is not None:
            return own
        return self._joined.setdefault(id, self.last_sent_at)

    def on_radio(self, id: RadioId) -> tuple[datetime | None, datetime | None, int]:
        """The status on one radio, for its row on the wire: when it last went out there (None before one), when the next timed one is due there (None while none is: not a radio of the status, the beacon
        or the status off, none sent there yet), and the interval in force on it in minutes (0 while the status does not go on it)."""
        c = self._config()
        spec = c.radio(id)
        minutes = next((m for target, _, m in self._targets(c) if target == id), 0) if spec is not None and spec.enabled and not spec.removed else 0
        last = self.sent_on.get(id)
        timed = minutes > 0 and c.beacon_on and c.status_choice != "off" and last is not None
        return last, last + timedelta(minutes=minutes) if timed and last is not None else None, minutes

    # ---- one poll
    async def poll(self) -> None:
        """Reads the radio (or takes the static text) and sends a status report when the rule says so."""
        c = self._config()
        text = await self._current(c)
        if text:
            self._offer(text, c)

    async def _current(self, c: Config) -> str | None:
        """What the status says now: the text, the radio's reading filled into the template, or None for no status (off, or a radio that is away)."""
        address = c.status_rig_address
        if address is not None:
            return await self._from_rig(c, address)
        self._set_state("unused", "")
        return c.station_status if c.status_choice == "text" else None

    async def send_now(self) -> str:
        """Sends the status now, inside the interval; the interval counts from now. "" when it went out, else why not, as a Reason with its code (the interlock, the Tnc, the radio away, no text, a text the
        settings cannot send)."""
        c = self._config()
        if c.status_choice == "off":
            return Reason("the status is off", "status.off")
        if reason := self._interlock.refused("status"):
            return reason
        text = await self._current(c)
        if text is None:
            return Reason("the radio does not answer", "status.rig_away") if self._rig_problem else Reason("the status has no radio to come from: set Rigctld", "status.no_rig")
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
        """The state of the radio; the log says it once when it changes (a warning for the radio going away, else a line of information)."""
        if state != self.rig_state:
            self.rig_state = state
            if words:
                (log.warning if state == "off" else log.info)("%s", words)

    def _offer(self, text: str, c: Config) -> None:
        if not c.beacon_on:
            return                                                   # (the radio's beacon Off is no automatic status; Status now still sends)
        now, targets = self.clock(), self._targets(c)
        for gone in self._joined.keys() - {id for id, _, _ in targets}:
            del self._joined[gone]                                   # (a radio that is no longer one joins again at the next interval, not at once)
        due = [(id, radio) for id, radio, minutes in targets if (since := self._counts_from(id)) is None or now - since >= timedelta(minutes=minutes)]
        if due:
            self._try(text, due)

    def _try(self, text: str, targets: list[tuple[RadioId, AirRadio | None]] | None = None) -> str:
        """Sends the status on each of the radios (all the status goes on when none are given); "" when it went out on one, else the reason (told in the log once for each radio, as the poll tells it)."""
        if reason := self._interlock.refused("status"):
            return reason
        if targets is None:
            targets = [(id, radio) for id, radio, _ in self._targets(self._config())]
        if not targets:
            self._tell(0, NO_RADIO)
            return NO_RADIO
        reasons = [self._send_on(id, radio, text) for id, radio in targets]
        return "" if "" in reasons else reasons[0]

    def _send_on(self, id: RadioId, radio: AirRadio | None, text: str) -> str:
        """Sends the status on one radio; "" when it went out, else the reason (told once)."""
        if radio is None:
            self._tell(id, NO_RADIO)
            return NO_RADIO
        try:
            frame = self._frames.status(text, radio)                       # (for the radio it goes on: no path and the frame cap on HF; none longer than it carries)
        except BeaconError as e:
            reason = Reason.of(e, f"the settings make no status: {e}")
            self._tell(id, reason, warn=True)
            return reason
        if frame is None:
            return NO_TEXT
        if not radio.usable:
            self._tell(id, f"{radio.why_unusable()}: the status waits")
            return radio.why_unusable()
        if not radio.send_frame(frame):
            reason = Reason("the TNC did not take the status frame", "radio.not_taken", radio=radio.id, name=radio.name)
            self._tell(id, reason, warn=True)
            return reason
        now = self.clock()
        self.last_sent_at, self.last_text, self.sent_on[id] = now, text, now
        self._told.pop(id, None)
        self._told.pop(0, None)
        self._remembered.put({STATUS_SENT: stamp(now), STATUS_TEXT: text, **({memory_key_of(id): stamp(now)} if is_pick(self._radios) else {})})
        log.info("status sent: %s", frame.tnc2())
        return ""

    def _tell(self, id: RadioId, reason: str, warn: bool = False) -> None:
        if reason != self._told.get(id, ""):
            self._told[id] = reason
            (log.warning if warn else log.info)("no status sent: %s", reason)

    # ---- what ?APRSS answers with
    def status_frame(self, radio: AirRadio | Radio | None = None) -> ax25.Frame | None:
        """The frame of the status as it was last sent, with the time of now, for `radio` (the one the question came on; the first radio that can send when none is named); None while none has been sent. Raises BeaconError when
        the settings make no frame, or there is no radio to make it for."""
        if not self.last_text:
            return None
        target = self._radio() if radio is None else air_of(radio, self._config, old=self._old)
        if target is None:
            raise BeaconError.of(NO_RADIO)
        return self._frames.status(self.last_text, target)
