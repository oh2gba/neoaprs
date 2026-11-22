"""The iGate: what the radio hears goes to APRS-IS, and nothing from APRS-IS is ever put on the air.

Without a valid passcode it only listens. Packets heard on the air go through igaterules.py. Our
position goes out as `OURCALL>APZNEO,TCPIP*:`, the only path a client may use (aprs-is.net).
"""
import asyncio
import logging
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal, NamedTuple

from neoaprs import TOCALL, ax25
from neoaprs.aprsis import FILTER_MOVE_KM, UNVERIFIED, AprsIs, range_filter
from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.geo import distance_km
from neoaprs.hourcount import HourCount
from neoaprs.igaterules import DUPLICATE, FRAME, NOT_AIR, OFFLINE, REASON_WORDS, Dropped, gate_of
from neoaprs.packet import GATEABLE, DuplicateKey, Packet
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import RadioTypeError
from neoaprs.recent import Recent
from neoaprs.services.common import ConfigSource
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet, cancel_all, every

log = logging.getLogger("neoaprs.igate")

POSITION_SEC = 1800.0
MOBILE_EVERY_SEC = 60.0
SUMMARY_SEC = 3600.0
TICK_SEC = 1.0
IgateStateName = Literal["off", "connecting", "connected", "listening", "unverified"]
IgateReason = Literal["", "no_server", "no_call", "unreachable", "offline", "not_server", "lost", "unverified"]


def dummy_on(config: Config) -> bool:
    """Whether an enabled radio is of a Dummy type (`RadioType.dummy`), which makes up traffic."""
    return any(_dummy(spec) for spec in config.enabled_radios)


def _dummy(spec: RadioSpec) -> bool:
    try:
        return spec.rtype.dummy
    except RadioTypeError:
        return False


class Wanted(NamedTuple):
    enabled: bool
    host: str
    port: int
    call: str
    password: str


class Igate:
    def __init__(self, link: AprsIs, config: ConfigSource, position: Callable[[], bytes], where: Callable[[], tuple[float, float] | None], clock: Clock = utcnow, duplicate_sec: float = DIGI_DUPLICATE_SEC,
                 position_sec: float = POSITION_SEC, mobile_every_sec: float = MOBILE_EVERY_SEC, summary_sec: float = SUMMARY_SEC, tick_sec: float = TICK_SEC) -> None:
        self._link = link
        self._config = config
        self._position = position                                    # raises ValueError if there is none
        self._where = where                                          # latitude and longitude, or None
        self._filter_at: tuple[float, float] | None = None
        self._filter_km = 0
        self._read_mark = (0, 0)
        self.clock = clock
        self.position_sec, self.mobile_every_sec, self.summary_sec, self.tick_sec = position_sec, mobile_every_sec, summary_sec, tick_sec
        self.changed: Signal[[]] = Signal("igate.changed")
        self.gated = 0
        self.dropped: Counter[str] = Counter()
        self.last_gated_at: datetime | None = None
        self._hour_gated = 0
        self._hour_dropped: Counter[str] = Counter()
        self.gated_hour = HourCount()
        self._summary_due: datetime | None = None
        self._seen: Recent[DuplicateKey] = Recent(duplicate_sec)
        # With a Dummy radio on, nothing of ours goes to APRS-IS: it would claim we are on the air.
        self.made_up: Callable[[], bool] = lambda: dummy_on(self._config())
        self._position_due: datetime | None = None
        self._position_sent: datetime | None = None
        self._was_verified = False
        self._applied: Wanted | None = None
        self._apply_task: asyncio.Task[None] | None = None
        self._running = False
        self._tasks = TaskSet(log, "igate")

    async def start(self) -> None:
        if self._tasks:
            return
        self._summary_due = self.clock() + timedelta(seconds=self.summary_sec)
        self.apply()
        self._tasks.spawn(self._run(), "igate-tick")

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        self._apply_task = None
        self._running = False
        await self._link.stop()

    def settings_changed(self) -> None:
        """Reconnect (or disconnect) if the switch, server, call or password changed."""
        if self._applied is not None and self._wanted() != self._applied:
            self.apply()
        elif self._link.verified and self._position_due is None and not self._config().mobile:
            self._position_due = self.clock()  # a station that stopped moving
        self._refresh_filter()
        self.changed.emit()

    def apply(self) -> None:
        """(Re)connect with the current settings in a task, cancelling one still under way."""
        self._applied = self._wanted()
        self._refresh_filter()
        self._apply_task = self._tasks.spawn(self._apply(self._apply_task, self._applied), "igate-apply")

    def _wanted(self) -> Wanted:
        c = self._config()
        host, port = c.igate_address or ("", 0)
        return Wanted(c.igate_enabled, host, port, c.station_call, c.igate_password)

    async def _apply(self, previous: "asyncio.Task[None] | None", wanted: Wanted) -> None:
        if previous is not None:
            await cancel_all([previous])
        await self._link.stop()
        self._was_verified = False
        self._read_mark = (0, 0)
        if wanted.enabled:
            log.info("igate: on, %s; logging in to %s:%d as %s", "a receive-only iGate" if wanted.password else "listening only, no passcode", wanted.host, wanted.port, wanted.call or "(no call set)")
            self._running = True
            self._link.configure(wanted.host, wanted.port, wanted.call, wanted.password)
            await self._link.start()
        elif self._running:
            self._running = False
            log.info("igate: off")
        self.changed.emit()

    async def _run(self) -> None:
        await every(self.tick_sec, self.tick, "the iGate ticker")

    def tick(self) -> None:
        """Do what is due: refresh the filter, send our position, log the hourly summary."""
        now = self.clock()
        if self._config().igate_enabled:
            self._refresh_filter()
        if self._position_due is not None and now >= self._position_due and not self._config().mobile:
            self._send_position(now)
        if self._summary_due is not None and now >= self._summary_due:
            self._summary_due = now + timedelta(seconds=self.summary_sec)
            if self._config().igate_enabled:
                log.info("%s", self.summary())
                self._log_read()
            self._hour_gated, self._hour_dropped = 0, Counter()

    @property
    def state(self) -> IgateStateName:
        if not self._config().igate_enabled:
            return "off"
        if self._link.unverified:
            return "unverified"
        if self._link.verified:
            return "connected"
        return "listening" if self._link.listening else "connecting"

    @property
    def problem(self) -> str:
        """Why it is not logged in; empty while connected, listening or off."""
        state = self.state
        if state in ("off", "connected", "listening"):
            return ""
        return UNVERIFIED if state == "unverified" else self._link.problem or self._link.last_error

    @property
    def reason(self) -> IgateReason:
        """`problem` as a code; empty when `problem` is."""
        state = self.state
        if state in ("off", "connected", "listening"):
            return ""
        return "unverified" if state == "unverified" else self._link.reason

    @property
    def server_name(self) -> str:
        return self._link.server_name

    def link_changed(self) -> None:
        """Called when the connection's state moved; a newly verified login sends our position."""
        verified = self._link.verified
        if verified and not self._was_verified:
            self._send_position(self.clock())
        self._was_verified = verified
        self.changed.emit()

    def _refresh_filter(self) -> None:
        """Set the range filter when our position is known and after a move over FILTER_MOVE_KM."""
        here, km = self._where(), self._config().map_radius_km
        if here is None or (self._filter_at is not None and km == self._filter_km and distance_km(*self._filter_at, *here) <= FILTER_MOVE_KM):
            return
        self._filter_at, self._filter_km = here, km
        self._link.set_filter(range_filter(*here, km))

    def _log_read(self) -> None:
        """Log the hour's APRS-IS reads in one line."""
        read, unreadable = self._link.read, self._link.unreadable
        packets, none = read - self._read_mark[0], unreadable - self._read_mark[1]
        self._read_mark = (read, unreadable)
        if packets or none:
            log.info("igate: %d packets read from APRS-IS in the last hour, %d were no packet", packets, none)

    def summary(self) -> str:
        """The hour in one line: "igate: 812 packets gated in the last hour, 40 not gated: ..."."""
        n = self._hour_gated
        text = f"igate: {'1 packet' if n == 1 else f'{n} packets'} gated in the last hour"
        missed = sum(self._hour_dropped.values())
        if missed:
            text += f", {missed} not gated: " + ", ".join(f"{count} {REASON_WORDS.get(reason, reason)}" for reason, count in self._hour_dropped.most_common())
        return text

    def on_packet(self, packet: Packet) -> None:
        """Gate a packet heard on the radio if its channel is in `GATEABLE`; ignore sent packets."""
        if packet.direction != "in" or not self._wanted_to_gate():
            return
        if packet.via not in GATEABLE:
            return self._drop(NOT_AIR)  # internet packets would loop; Dummy traffic stays off
        if not self._link.verified:
            return self._drop(OFFLINE)
        try:
            frame = ax25.decode(packet.raw)
        except ax25.Ax25Error:
            return self._drop(FRAME)
        gate = gate_of(frame, self._link.call)
        if isinstance(gate, Dropped):
            return self._drop(gate.reason)
        now = self.clock()
        if self._seen.lately(gate.key, now):
            return self._drop(DUPLICATE)
        self._seen.note(gate.key, now)
        line = gate.line(self._link.call)
        if not self._link.send_line(line):
            return self._drop(OFFLINE)
        self.gated += 1
        self._hour_gated += 1
        self.gated_hour.note(now)
        self.last_gated_at = now
        log.debug("igate: gated %s", line.decode("latin-1"))
        self.changed.emit()

    def _wanted_to_gate(self) -> bool:
        """Whether it gates at all: on, with a passcode the server has not refused."""
        c = self._config()
        return c.igate_enabled and c.igate_password != "" and not self._link.unverified

    def _drop(self, reason: str) -> None:
        self.dropped[reason] += 1
        self._hour_dropped[reason] += 1
        self.changed.emit()

    def beacon_sent(self, frame: ax25.Frame) -> None:
        """Send a moving station's beacon position to APRS-IS, at most every MOBILE_EVERY_SEC."""
        now = self.clock()
        if not self._config().mobile or not self._link.verified or self.made_up():
            return
        if self._position_sent is not None and (now - self._position_sent).total_seconds() < self.mobile_every_sec:
            return
        self._put_position(frame.info, now)

    def _send_position(self, now: datetime) -> None:
        """Send a fixed station's position from the settings; retry in a minute if there is none."""
        if self._config().mobile or not self._link.verified:
            self._position_due = None
            return
        if self.made_up():
            self._position_due = now + timedelta(seconds=MOBILE_EVERY_SEC)
            return
        try:
            info = self._position()
        except ValueError as e:
            self._position_due = now + timedelta(seconds=MOBILE_EVERY_SEC)
            log.debug("igate: no position to send to APRS-IS: %s", e)
            return
        self._put_position(info, now)

    def _put_position(self, info: bytes, now: datetime) -> None:
        line = f"{self._link.call}>{TOCALL},TCPIP*:".encode("ascii") + info
        self._position_due = now + timedelta(seconds=self.position_sec)
        if self._link.send_line(line):
            self._position_sent = now
            log.info("igate: our position sent to APRS-IS")
            log.debug("igate: sent %s", line.decode("latin-1"))
