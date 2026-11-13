"""Our status report: when it is sent, and what it says.

`status/source` says where the status comes from: `rig`, `text` or `off` (empty: `rig` while `status/rigctld` is set, else `text` while `station/status` is not empty, else `off`; `Config.status_choice`). With `rig` (host:port of a Hamlib rigctld in `status/rigctld`) the status is made from the radio: every POLL_SEC a fresh short connection asks for the frequency and the mode (neoaprs/rigctld.py) and
`status/template` is filled in ({freq} as `14.074 MHz`, {mode} as rigctld names it: USB, LSB, CW, FM ...). A radio that is off (`RPRT -n`), a refused connection or no answer in time is "off": nothing is sent,
and the log says so once for as long as it lasts, not at every poll. With `text` the status is the static text `station/status` ("unused"); with `off` there is none ("unused" too).

One rule for both: a status report goes out when `status/interval_min` has passed since the last one sent (or none was ever sent), whether what it says has changed or not: a static text goes out again at every interval, and a radio's frequency and
mode are read afresh each time. So nothing goes inside the interval however the dial moves, and nothing while the radio is off. The time and the text of the last report are kept in the rows `status/last_sent_at` and `status/last_text`
(written after each send) and read at the start, so a restart sends nothing inside the interval. The report is the frame `Beacon.status_frame` makes (`>` and the time as `DDHHMMz`, then the text) sent through the Tnc by the
beacon's destination and path. `last_text` is what `?APRSS` answers with (`status_frame()`) and what the page shows as the current status. `send_now()` sends one at once, whatever the interval (the page's "Send status now"), by the same checks of the interlock,
the length and the Tnc, and the interval counts from it. No automatic status report goes while the beacon is off (`beacon/interval_min` is 0: quietly, as nothing is due; `send_now` still sends), and one that was held back goes at the first poll after the beacon is on if the
interval has passed. A report that cannot go (the Tnc is not connected or the radio is silent, would not take it, the settings make no frame) is told once for each reason and tried again at the next poll.
"""
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Literal, Protocol

from neoaprs import ax25
from neoaprs.clock import Clock, utcnow
from neoaprs.config import STATUS_SENT, STATUS_TEXT, Config
from neoaprs.configstatus import MAX_STATUS, fill_template
from neoaprs.configtypes import over_the_air_problem
from neoaprs.interlock import Interlock
from neoaprs.rigctld import Reading, RigError, read_rig
from neoaprs.services.beacon import BeaconError
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.memory import Memory, Remembered, stamp
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.status")

POLL_SEC = 30.0
RigState = Literal["off", "on", "unused"]
Reader = Callable[[str, int], Awaitable[Reading]]


class Frames(Protocol):
    """What the status needs of the beacon: the frame of a report, built for the radio it goes on."""
    def status_frame(self, text: str, radio: Radio | None = None) -> ax25.Frame | None: ...


def freq_text(hz: int) -> str:
    """The frequency as `14.074 MHz`: megahertz with three decimals, rounded to the kHz."""
    khz = (hz + 500) // 1000
    return f"{khz // 1000}.{khz % 1000:03d} MHz"


def clipped(text: str, max_length: int = MAX_STATUS) -> str:
    """The text as a status may carry it: only printable ASCII (what the radio names a mode with anything else, and `|` and `~`, becomes `?`), cut to at most `max_length` characters."""
    return "".join(c if over_the_air_problem(c) == "" else "?" for c in text)[:max_length]


class RigStatus:
    def __init__(self, tnc: Radio, config: ConfigSource, beacon: Frames, clock: Clock = utcnow, poll_sec: float = POLL_SEC, read: Reader = read_rig,
                 memory: Memory | None = None) -> None:
        self._tnc = tnc
        self._config = config
        self._interlock = Interlock(config)
        self._beacon = beacon
        self.clock = clock
        self.poll_sec = poll_sec
        self._read = read
        self.last_sent_at: datetime | None = None               # when the latest status report went out, as the row kept it after a restart
        self.last_text = ""                                     # what it said; empty until one has gone (or was kept)
        self.rig_state: RigState = "unused"
        self._told = ""                                         # the reason a report was not sent, as last told
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
        self._tasks.spawn(self._run(), "rigstatus")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._remembered.flush()

    async def _run(self) -> None:
        await every(self.poll_sec, self.poll, "the status poll", at_start=True)

    # ---- one poll
    async def poll(self) -> None:
        """Reads the radio (or takes the static text) and sends a status report when the rule says so."""
        c = self._config()
        text = await self._current(c)
        if text:
            self._offer(text, c.status_interval_min)

    async def _current(self, c: Config) -> str | None:
        """What the status says now: the text, the radio's reading filled into the template, or None for no status (off, or a radio that is away)."""
        address = c.status_rig_address
        if address is not None:
            return await self._from_rig(c, address)
        self._set_state("unused", "")
        return c.station_status if c.status_choice == "text" else None

    async def send_now(self) -> str:
        """Sends the status now, inside the interval; the interval counts from now. "" when it went out, else why not (the interlock, the Tnc, the radio away, no text, a text the settings cannot send)."""
        c = self._config()
        if c.status_choice == "off":
            return "the status is off"
        if reason := self._interlock.refused("status"):
            return reason
        text = await self._current(c)
        if text is None:
            return self._rig_problem or "the status has no radio to come from: set status/rigctld"
        if not text:
            return "there is no status text"
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

    def _offer(self, text: str, interval_min: int) -> None:
        if self._config().beacon_interval() == 0:
            return                                                   # (the radio's beacon Off is no automatic status; Status now still sends)
        now = self.clock()
        if self.last_sent_at is not None and now - self.last_sent_at < timedelta(minutes=interval_min):
            return
        self._try(text)

    def _try(self, text: str) -> str:
        """Sends the status through the Tnc; "" when it went out, else the reason (told in the log once, as the poll tells it)."""
        if reason := self._interlock.refused("status"):
            return reason
        try:
            frame = self._beacon.status_frame(text, self._tnc)             # (for the radio it goes on: no path and the frame cap when that is the HF radio, the FM one being off)
        except BeaconError as e:
            reason = f"the settings make no status: {e}"
            self._tell(reason, warn=True)
            return reason
        if frame is None:
            return "there is no status text"
        if not self._tnc.usable:
            self._tell(f"{self._tnc.why_unusable()}: the status waits")
            return self._tnc.why_unusable()
        if not self._tnc.send_frame(frame):
            reason = "the TNC did not take the status frame"
            self._tell(reason, warn=True)
            return reason
        now = self.clock()
        self.last_sent_at, self.last_text, self._told = now, text, ""
        self._remembered.put({STATUS_SENT: stamp(now), STATUS_TEXT: text})
        log.info("status sent: %s", frame.tnc2())
        return ""

    def _tell(self, reason: str, warn: bool = False) -> None:
        if reason != self._told:
            self._told = reason
            (log.warning if warn else log.info)("no status sent: %s", reason)

    # ---- what ?APRSS answers with
    def status_frame(self, radio: Radio | None = None) -> ax25.Frame | None:
        """The frame of the status as it was last sent, with the time of now, for `radio` (the one the question came on; the default radio when none is named); None while none has been sent. Raises BeaconError when
        the settings make no frame."""
        return self._beacon.status_frame(self.last_text, radio or self._tnc)
