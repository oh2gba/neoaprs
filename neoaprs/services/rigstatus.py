"""Our status report: when it is sent, and what it says.

With `status/rigctld` set (host:port of a Hamlib rigctld) the status is made from the radio: every POLL_SEC a fresh short connection asks for the frequency and the mode (neoaprs/rigctld.py) and
`status/template` is filled in ({freq} as `14.074 MHz`, {mode} as rigctld names it: USB, LSB, CW, FM ...). A radio that is off (`RPRT -n`), a refused connection or no answer in time is "off": nothing is sent,
and the log says so once for as long as it lasts, not at every poll. With `status/rigctld` empty the status is the static text `station/status` ("unused").

One rule for both: a status report goes out when `status/interval_min` has passed since the last one sent (or none was ever sent) and what it says has changed since then: the frequency to the kHz and
the mode for a radio, the text for the static status. So nothing goes inside the interval however the dial moves, nothing when it is the same, nothing while the radio is off, and a static text goes out
once and again only when it is edited (at the next poll after the interval). The time and the text of the last report are kept in the rows `status/last_sent_at` and `status/last_text` (written after each
send) and read at the start, so a restart sends nothing inside the interval and, after it, only a status that differs from the one kept. The report is the frame `Beacon.status_frame` makes (`>` and the time as `DDHHMMz`, then the text) sent through the Tnc by the
beacon's destination and path. `last_text` is what `?APRSS` answers with (`status_frame()`) and what the page shows as the current status. A report that cannot go (the Tnc is not connected or the radio is silent, would not take it, the
settings make no frame) is told once for each reason and tried again at the next poll.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Literal, Protocol

from neoaprs import ax25
from neoaprs.clock import Clock, utcnow
from neoaprs.config import MAX_STATUS, STATUS_SENT, STATUS_TEXT, Config, fill_template
from neoaprs.configtypes import over_the_air_problem
from neoaprs.interlock import Interlock
from neoaprs.rigctld import Reading, RigError, read_rig
from neoaprs.services.beacon import BeaconError
from neoaprs.services.memory import Memory, Remembered, stamp
from neoaprs.source import Source
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.status")

POLL_SEC = 30.0
RigState = Literal["off", "on", "unused"]
Key = tuple[str, str] | tuple[str, int, str]                   # what a status says: ("text", the text) or ("rig", kHz, mode)
Reader = Callable[[str, int], Awaitable[Reading]]


class Radio(Protocol):
    """What the status needs of the Tnc."""
    @property
    def state(self) -> Source.State: ...
    @property
    def usable(self) -> bool: ...
    def why_unusable(self) -> str: ...
    def send_frame(self, frame: ax25.Frame) -> bool: ...


class Frames(Protocol):
    """What the status needs of the beacon: the frame of a report."""
    def status_frame(self, text: str) -> ax25.Frame | None: ...


def freq_text(hz: int) -> str:
    """The frequency as `14.074 MHz`: megahertz with three decimals, rounded to the kHz."""
    khz = (hz + 500) // 1000
    return f"{khz // 1000}.{khz % 1000:03d} MHz"


def clipped(text: str, max_length: int = MAX_STATUS) -> str:
    """The text as a status may carry it: only printable ASCII (what the radio names a mode with anything else, and `|` and `~`, becomes `?`), cut to at most `max_length` characters."""
    return "".join(c if over_the_air_problem(c) == "" else "?" for c in text)[:max_length]


class RigStatus:
    def __init__(self, tnc: Radio, config: Callable[[], Config], beacon: Frames, clock: Clock = utcnow, poll_sec: float = POLL_SEC, read: Reader = read_rig,
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
        self._last_key: Key | None = None
        self._told = ""                                         # the reason a report was not sent, as last told
        self._remembered = Remembered(memory)
        self._tasks = TaskSet(self._task_failed)

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

    @staticmethod
    def _task_failed(task: "asyncio.Task[None]") -> None:
        log.error("status task %s failed: %r", task.get_name(), task.exception())

    async def _run(self) -> None:
        while True:
            try:
                await self.poll()
            except Exception:                                    # (a poll that fails must not end the timer)
                log.exception("the status poll failed")
            await asyncio.sleep(self.poll_sec)

    # ---- one poll
    async def poll(self) -> None:
        """Reads the radio (or takes the static text) and sends a status report when the rule says so."""
        c = self._config()
        address = c.status_rig_address
        if address is None:
            self._set_state("unused", "")
            offer: tuple[Key, str] | None = (("text", c.station_status), c.station_status)
        else:
            offer = await self._from_rig(c, address)
        if offer is not None and offer[1]:
            self._offer(offer[0], offer[1], c.status_interval_min)

    async def _from_rig(self, c: Config, address: tuple[str, int]) -> tuple[Key, str] | None:
        where = f"rigctld at {address[0]}:{address[1]}"
        try:
            reading = await self._read(*address)
        except RigError as e:
            self._set_state("off", f"{where}: {e}: no status while it is away")
            return None
        self._set_state("on", f"{where}: the radio answers ({freq_text(reading.hz)} {reading.mode})")
        return ("rig", (reading.hz + 500) // 1000, reading.mode), clipped(fill_template(c.status_template, freq_text(reading.hz), reading.mode))

    def _set_state(self, state: RigState, words: str) -> None:
        """The state of the radio; the log says it once when it changes (a warning for the radio going away, else a line of information)."""
        if state != self.rig_state:
            self.rig_state = state
            if words:
                (log.warning if state == "off" else log.info)("%s", words)

    def _offer(self, key: Key, text: str, interval_min: int) -> None:
        now = self.clock()
        if self._unchanged(key, text) or (self.last_sent_at is not None and now - self.last_sent_at < timedelta(minutes=interval_min)):
            return
        if self._interlock.refused("status"):
            return
        try:
            frame = self._beacon.status_frame(text)
        except BeaconError as e:
            self._tell(f"the settings make no status: {e}", warn=True)
            return
        if frame is None:
            return
        if not self._tnc.usable:
            self._tell(f"{self._tnc.why_unusable()}: the status waits")
        elif not self._tnc.send_frame(frame):
            self._tell("the TNC did not take the status frame", warn=True)
        else:
            self.last_sent_at, self.last_text, self._last_key, self._told = now, text, key, ""
            self._remembered.put({STATUS_SENT: stamp(now), STATUS_TEXT: text})
            log.info("status sent: %s", frame.tnc2())

    def _unchanged(self, key: Key, text: str) -> bool:
        """What the status says is what it said: the same frequency to the kHz and mode (or text) as the report sent in this run, or, after a restart, the same text as the one kept."""
        return key == self._last_key if self._last_key is not None else text == self.last_text

    def _tell(self, reason: str, warn: bool = False) -> None:
        if reason != self._told:
            self._told = reason
            (log.warning if warn else log.info)("no status sent: %s", reason)

    # ---- what ?APRSS answers with
    def status_frame(self) -> ax25.Frame | None:
        """The frame of the status as it was last sent, with the time of now; None while none has been sent. Raises BeaconError when the settings make no frame."""
        return self._beacon.status_frame(self.last_text)
