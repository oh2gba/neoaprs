"""The receive-only iGate, switched on by `igate/enabled` (off unless the operator turns it on): what the radio hears is put on APRS-IS, and nothing that APRS-IS says is ever put on the air.

That is built in, not promised. This service has no radio: its constructor takes the connection (neoaprs/aprsis.py, which writes lines to a server and throws away what the server sends back), the settings and a function that
gives the bytes of our position, and nothing else; it imports neither the Tnc nor `Radio` nor the sender. The one place a packet comes from is `on_packet`, which the composition root connects to the packets heard on the radio.

Each packet heard (direction in, `Packet.via` in `packet.GATEABLE`: not one from the internet or made up by the Dummy radio, which are counted as not gated, "not from the air") goes through the rules of neoaprs/igaterules.py (the specification's, with where each comes from): it is gated as `SOURCE>DEST,PATH,qAO,OURCALL:INFO`, or counted as not gated with the reason.
Besides those a packet is not gated when the connection is not logged in and verified (`offline`), and when the same source, destination (without its SSID) and information field was gated in the last DUPLICATE_SEC seconds
(`duplicate`: the digipeaters repeat a packet and it is heard more than once; servers also drop a copy within 30 seconds, so the copy would be wasted; the specification asks for nothing of the kind, and WB2OSZ's
"Successful APRS IGate Operation" says Dire Wolf stopped doing it at the request of a server author, so the window is a constant to set to 0).

Our own position goes to APRS-IS so that the iGate shows on maps, as `OURCALL>APZNEO,TCPIP*:` and the information field of the beacon (the only path a client's own packet has: https://www.aprs-is.net/Connecting.aspx):
for a station that stays, when the login is verified and every POSITION_SEC (30 minutes) after, if there is a position and a call; for a moving station (`gps/source` is not `off`) every beacon that goes out on the radio is sent too,
at most every MOBILE_EVERY_SEC (a minute). The packet is built from the settings by `position` (the beacon's `position_info`), which asks no transmit interlock: nothing is transmitted.

Counts: `gated`, `dropped` by reason, `last_gated_at`; every hour the log says them in one line at INFO, and each gated packet is a DEBUG line. The password is never in the log. `state` is `off`, `connecting` (not logged in yet, or
waiting for what is missing: `problem` says what), `connected` or `unverified` (the server did not accept the password)."""
import asyncio
import logging
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal, NamedTuple

from neoaprs import TOCALL, ax25
from neoaprs.aprsis import AprsIs
from neoaprs.clock import Clock, utcnow
from neoaprs.igaterules import DUPLICATE, FRAME, NOT_AIR, OFFLINE, REASON_WORDS, Dropped, gate_of
from neoaprs.packet import GATEABLE, Packet
from neoaprs.services.common import ConfigSource
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet, cancel_all

log = logging.getLogger("neoaprs.igate")

DUPLICATE_SEC = 30.0
POSITION_SEC = 1800.0
MOBILE_EVERY_SEC = 60.0
SUMMARY_SEC = 3600.0
TICK_SEC = 1.0
_SEEN_MAX = 2000                                    # the most (source, destination, information field) kept for the duplicate check
IgateStateName = Literal["off", "connecting", "connected", "unverified"]
Key = tuple[str, str, bytes]


class Wanted(NamedTuple):
    enabled: bool
    host: str
    port: int
    call: str
    password: str


class Igate:
    def __init__(self, link: AprsIs, config: ConfigSource, position: Callable[[], bytes], clock: Clock = utcnow, duplicate_sec: float = DUPLICATE_SEC, position_sec: float = POSITION_SEC,
                 mobile_every_sec: float = MOBILE_EVERY_SEC, summary_sec: float = SUMMARY_SEC, tick_sec: float = TICK_SEC) -> None:
        self._link = link
        self._config = config
        self._position = position                                    # the information field of our position packet; raises ValueError when there is none to send
        self.clock = clock
        self.duplicate_sec, self.position_sec, self.mobile_every_sec, self.summary_sec, self.tick_sec = duplicate_sec, position_sec, mobile_every_sec, summary_sec, tick_sec
        self.changed: Signal[[]] = Signal("igate.changed")
        self.gated = 0
        self.dropped: Counter[str] = Counter()
        self.last_gated_at: datetime | None = None
        self._hour_gated = 0
        self._hour_dropped: Counter[str] = Counter()
        self._summary_due: datetime | None = None
        self._seen: dict[Key, datetime] = {}
        self._position_due: datetime | None = None
        self._position_sent: datetime | None = None
        self._was_verified = False
        self._applied: Wanted | None = None
        self._apply_task: asyncio.Task[None] | None = None
        self._running = False
        self._tasks = TaskSet(log, "igate")

    # ---- the life
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
        """The settings were saved: a changed switch, server, call or password connects afresh (or disconnects)."""
        if self._applied is not None and self._wanted() != self._applied:
            self.apply()
        elif self._link.verified and self._position_due is None and not self._config().mobile:
            self._position_due = self.clock()                    # (a station that began to stay where it is: its position goes at the next tick)
        self.changed.emit()

    def apply(self) -> None:
        """(Re)connects with the settings as they are now, in a task; one that is still under way is ended first."""
        self._applied = self._wanted()
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
        if wanted.enabled:
            log.info("igate: on, a receive-only iGate; logging in to %s:%d as %s", wanted.host, wanted.port, wanted.call or "(no call set)")
            self._running = True
            self._link.configure(wanted.host, wanted.port, wanted.call, wanted.password)
            await self._link.start()
        elif self._running:
            self._running = False
            log.info("igate: off")
        self.changed.emit()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_sec)
            self.tick()

    def tick(self) -> None:
        """What is due by the clock: our position, and the summary of the hour."""
        now = self.clock()
        if self._position_due is not None and now >= self._position_due and not self._config().mobile:
            self._send_position(now)
        if self._summary_due is not None and now >= self._summary_due:
            self._summary_due = now + timedelta(seconds=self.summary_sec)
            if self._config().igate_enabled:
                log.info("%s", self.summary())
            self._hour_gated, self._hour_dropped = 0, Counter()

    # ---- the state
    @property
    def state(self) -> IgateStateName:
        if not self._config().igate_enabled:
            return "off"
        if self._link.unverified:
            return "unverified"
        return "connected" if self._link.verified else "connecting"

    @property
    def problem(self) -> str:
        """Why it is not logged in: what is missing, or why the connection is down; empty while it is connected and while it is off."""
        return "" if self.state in ("off", "connected") else self._link.problem or self._link.last_error

    @property
    def server_name(self) -> str:
        return self._link.server_name

    def link_changed(self) -> None:
        """The connection's state moved (connected by the composition root): a login that has just been verified sends our position."""
        verified = self._link.verified
        if verified and not self._was_verified:
            self._send_position(self.clock())
        self._was_verified = verified
        self.changed.emit()

    def summary(self) -> str:
        """The hour in one line: "igate: 812 packets gated in the last hour, 40 not gated: 31 TCPIP, 6 duplicate, 3 query"."""
        n = self._hour_gated
        text = f"igate: {'1 packet' if n == 1 else f'{n} packets'} gated in the last hour"
        missed = sum(self._hour_dropped.values())
        if missed:
            text += f", {missed} not gated: " + ", ".join(f"{count} {REASON_WORDS.get(reason, reason)}" for reason, count in self._hour_dropped.most_common())
        return text

    # ---- what the radio hears
    def on_packet(self, packet: Packet) -> None:
        """A packet was heard on the radio, or sent by it (only a heard one is gated, and only one whose channel is in `packet.GATEABLE`)."""
        if packet.direction != "in" or not self._config().igate_enabled:
            return
        if packet.via not in GATEABLE:
            return self._drop(NOT_AIR)                           # (a packet from the internet would go round in a circle, a made-up one of the Dummy radio must never reach the network)
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
        if self._duplicate(gate.key, now):
            return self._drop(DUPLICATE)
        line = gate.line(self._link.call)
        if not self._link.send_line(line):
            return self._drop(OFFLINE)                          # (the connection went down between the check and the write)
        self.gated += 1
        self._hour_gated += 1
        self.last_gated_at = now
        log.debug("igate: gated %s", line.decode("latin-1"))
        self.changed.emit()

    def _drop(self, reason: str) -> None:
        self.dropped[reason] += 1
        self._hour_dropped[reason] += 1
        self.changed.emit()

    def _duplicate(self, key: Key, now: datetime) -> bool:
        """Whether this packet was gated a moment ago; remembers it as gated now."""
        window = timedelta(seconds=self.duplicate_sec)
        if len(self._seen) > _SEEN_MAX:
            self._seen = {k: t for k, t in self._seen.items() if now - t < window}
        before = self._seen.get(key)
        if before is not None and now - before < window:
            return True
        self._seen[key] = now
        return False

    # ---- our own position
    def beacon_sent(self, frame: ax25.Frame) -> None:
        """A beacon of ours went out on the radio: a moving station's position goes to APRS-IS too, at most every MOBILE_EVERY_SEC."""
        now = self.clock()
        if not self._config().mobile or not self._link.verified:
            return
        if self._position_sent is not None and (now - self._position_sent).total_seconds() < self.mobile_every_sec:
            return
        self._put_position(frame.info, now)

    def _send_position(self, now: datetime) -> None:
        """The position of a station that stays, from the settings; tried again in a minute when there is none yet."""
        if self._config().mobile or not self._link.verified:
            self._position_due = None
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
