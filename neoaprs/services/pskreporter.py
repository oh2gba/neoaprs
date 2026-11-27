"""Report the stations a Mercury radio hears directly to PSK Reporter, as its map's mode NEOAPRS.

Only a radio with `psk_report` ticked and a `psk_dial` reports; the pace and the rules of the
datagrams are pskdev.html's (docs/pskreporter.md). Nothing raises into the radio path.
"""

import asyncio
import logging
import math
import os
import random
import socket
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from neoaprs import VERSION, nodevices
from neoaprs.aprslocator import grid_of
from neoaprs.callsign import CallsignError, call_problem, parse_call
from neoaprs.clock import Clock, StepWatch, utcnow
from neoaprs.config import Config
from neoaprs.packet import DUMMY, RF, Packet, Position
from neoaprs.pskreport import TEMPLATES, Receiver, Report, Template, datagram, fitting
from neoaprs.radiospec import RadioId, RadioSpec
from neoaprs.services.updatecheck import ENV_SWITCH
from neoaprs.station import Station
from neoaprs.tasks import TaskSet
from neoaprs.tncprofile import MERCURY

log = logging.getLogger("neoaprs.pskreporter")

HOST, PORT = "report.pskreporter.info", 4739
ENV_TARGET = "NEOAPRS_PSKREPORTER"  # host:port in the place of HOST and PORT, for tests and the probe
SOFTWARE = f"NeoAPRS {VERSION}"
# pskdev.html: a datagram at most every five minutes, the time not tied to the clock; a call at most
# once in five minutes; the descriptors in the first three datagrams and then hourly
SEND_EVERY_SEC = 300.0
JITTER_SEC = 30.0
CALL_EVERY_SEC = 300.0
TEMPLATES_EVERY_SEC = 3600.0
TEMPLATES_FIRST = 3
QUEUE_MAX = 500
NO_POSITION_EVERY_SEC = 24 * 3600.0
TICK_SEC = 1.0
# the amateur bands in Hz, for "once per band"; another dial is a band of its own
BANDS: tuple[tuple[int, int, str], ...] = (
    (1_800_000, 2_000_000, "160m"),
    (3_500_000, 4_000_000, "80m"),
    (5_250_000, 5_450_000, "60m"),
    (7_000_000, 7_300_000, "40m"),
    (10_100_000, 10_150_000, "30m"),
    (14_000_000, 14_350_000, "20m"),
    (18_068_000, 18_168_000, "17m"),
    (21_000_000, 21_450_000, "15m"),
    (24_890_000, 24_990_000, "12m"),
    (28_000_000, 29_700_000, "10m"),
    (50_000_000, 54_000_000, "6m"),
)


def band_of(hz: int) -> str:
    return next((name for low, high, name in BANDS if low <= hz <= high), f"{hz} Hz")


def dial_hz(dial: str) -> int | None:
    """Return the dial `28.1800 MHz USB` in Hz, None for empty text or a dial of another form."""
    try:
        return round(float(dial.split()[0]) * 1_000_000) if dial.strip() else None
    except ValueError:
        return None


def base_of(call: str) -> str | None:
    """Return the call without its SSID if it is an amateur call we may report, else None."""
    if call_problem(call):
        return None
    try:
        return parse_call(call)[0]
    except CallsignError:
        return None


def reporting_dial(spec: RadioSpec | None) -> int | None:
    """Return the dial in Hz of a Mercury radio that reports, else None."""
    if spec is None or spec.type != MERCURY.key or spec.removed or not spec.enabled or not spec.value("psk_report"):
        return None
    return dial_hz(str(spec.value("psk_dial")))


def heard_directly(packet: Packet) -> bool:
    """Return whether the packet came on the radio from the station itself: no hop used, not gated."""
    return (
        packet.direction == "in"
        and packet.via == RF
        and packet.third_party is None
        and not any(hop.endswith("*") for hop in packet.path)
    )


def sender_grid(packet: Packet, station: Station | None) -> str | None:
    """Return the locator of the packet's position, else of the station's last one heard on a radio."""
    decoded = packet.decoded
    if isinstance(decoded, Position):
        return grid_of(decoded.lat, decoded.lon)
    place = None if station is None else station.radio
    if place is not None and place.via != DUMMY:
        return grid_of(place.lat, place.lon)
    return None


@dataclass
class Waiting:
    radio: RadioId
    report: Report


class _Socket(asyncio.DatagramProtocol):
    """The session's socket; an error the network reports makes it anew at the next round."""

    def __init__(self, failed: Callable[[Exception], None]) -> None:
        self.failed = failed

    def error_received(self, exc: Exception) -> None:
        self.failed(exc)


class PskReporter:
    def __init__(
        self,
        config: Callable[[], Config],
        position: Callable[[], tuple[float, float] | None],
        station: Callable[[str], Station | None],
        clock: Clock = utcnow,
        environ: Mapping[str, str] = os.environ,
        rng: random.Random | None = None,
    ) -> None:
        self._config, self._position, self._station = config, position, station
        self._clock, self._environ = clock, environ
        self._rng = rng or random.Random()  # noqa: S311  (the session id and the pause, no secret)
        self.session = self._rng.getrandbits(32)
        self.tick_sec = TICK_SEC
        self.queue: deque[Waiting] = deque()
        self._reported: dict[tuple[str, str], datetime] = {}
        self._due: datetime | None = None
        self._last_sent: datetime | None = None
        self._templates_at: datetime | None = None
        self._with_templates = 0
        self.sequence = 0  # the reports sent in this session
        self.sent: dict[RadioId, int] = {}
        self.last_sent: dict[RadioId, datetime] = {}
        self._transport: asyncio.DatagramTransport | None = None
        self._family: int | None = None
        self._renew = False
        self._state = ""
        self._no_position_at: datetime | None = None
        self._reporting = False
        self._dropping = False
        self._steps = StepWatch()
        self._tasks = TaskSet(log, "PSK Reporter")

    async def start(self) -> None:
        if not self._tasks:
            self._steps.moved(self._clock)
            self._tasks.spawn(self._run(), "pskreporter")

    def _follow_steps(self) -> None:
        """A stepped clock moves what waits by the step, so each wait keeps its length; the reports keep their time."""
        if not (step := self._steps.moved(self._clock)):
            return
        self._due, self._last_sent, self._templates_at, self._no_position_at = (
            None if t is None else t + step
            for t in (self._due, self._last_sent, self._templates_at, self._no_position_at)
        )
        self._reported = {key: at + step for key, at in self._reported.items()}

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        self._close()

    def state(self, radio: RadioId) -> dict[str, Any]:
        """Return the radio's reports sent and the last time, for the support file."""
        last = self.last_sent.get(radio)
        return {
            "psk_reports_sent": self.sent.get(radio, 0),
            "psk_last_sent": None if last is None else last.isoformat(),
        }

    def settings_changed(self, config: Config) -> None:
        """Drop what may no longer be reported; note a radio switched on while the station has no position."""
        reporting = any(reporting_dial(spec) is not None for spec in config.radios)
        if reporting and not self._reporting:
            self._no_position_at = None
            self._has_position(self._clock())
        self._reporting = reporting
        self._keep_allowed(config)

    def _keep_allowed(self, config: Config) -> None:
        """Keep the waiting reports whose radio still reports on their dial, while the station has a call
        and a position; drop the others at once."""
        if base_of(config.station_call) is None:
            if self.queue:
                self._note("no_call", "PSK Reporter: the station has no call to report under, so nothing is reported")
            self.queue.clear()
        elif self._position() is None:
            self.queue.clear()
        kept = [w for w in self.queue if reporting_dial(config.radio(w.radio)) == w.report.frequency_hz]
        if len(kept) != len(self.queue):
            self.queue = deque(kept)
        if not self.queue:
            self._due = None

    def on_packet(self, packet: Packet) -> None:
        """Queue a report of the station heard, if the radio reports and the station may be reported."""
        if not packet.on_air:
            return
        try:
            self._take(packet)
        except Exception:
            log.exception("PSK Reporter: the packet %s could not be taken", packet.source)

    def _take(self, packet: Packet) -> None:
        self._follow_steps()
        config = self._config()
        hz = reporting_dial(config.radio(packet.radio_id) if packet.radio_id is not None else None)
        if hz is None or not heard_directly(packet):
            return
        call, ours = base_of(packet.source), base_of(config.station_call)
        if call is None or ours is None or call == ours or not self._has_position(packet.heard_at):
            return
        snr = None if packet.snr is None or not math.isfinite(packet.snr) else round(packet.snr)
        key = (call, band_of(hz))
        before = self._reported.get(key)
        if before is not None and packet.heard_at - before < timedelta(seconds=CALL_EVERY_SEC):
            return
        self._reported[key] = packet.heard_at
        self._forget_old(packet.heard_at)
        grid = sender_grid(packet, self._station(packet.source))
        assert packet.radio_id is not None
        self._queue(Waiting(packet.radio_id, Report(call, hz, int(packet.heard_at.timestamp()), grid, snr)))

    def _queue(self, waiting: Waiting) -> None:
        if len(self.queue) >= QUEUE_MAX:
            self.queue.popleft()
            if not self._dropping:
                log.warning("PSK Reporter: %d reports wait to be sent: the oldest are dropped", QUEUE_MAX)
            self._dropping = True
        self.queue.append(waiting)
        if self._due is None:
            first = self._next(self._clock())
            earliest = None if self._last_sent is None else self._last_sent + timedelta(seconds=SEND_EVERY_SEC)
            self._due = first if earliest is None else max(first, earliest)

    def _forget_old(self, now: datetime) -> None:
        old = now - timedelta(seconds=CALL_EVERY_SEC)
        for key in [key for key, at in self._reported.items() if at < old]:
            del self._reported[key]

    def _has_position(self, now: datetime) -> bool:
        if self._position() is not None:
            return True
        if self._no_position_at is None or now - self._no_position_at >= timedelta(seconds=NO_POSITION_EVERY_SEC):
            log.info("PSK Reporter: the station has no position, so nothing is reported")
            self._no_position_at = now
        return False

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_sec)
            self._follow_steps()
            now = self._clock()
            if self._due is None or now < self._due:
                continue
            self._due = None
            try:
                await self._send_all(now)
            except Exception as e:
                self._note("broken", f"PSK Reporter: a round of reports failed ({e!r}); the next round tries again")
                log.debug("PSK Reporter: the failed round", exc_info=True)
            if self.queue and self._due is None:
                self._due = self._next(now)

    def _next(self, now: datetime) -> datetime:
        return now + timedelta(seconds=SEND_EVERY_SEC + self._rng.uniform(0, JITTER_SEC))

    async def _send_all(self, now: datetime) -> None:
        """Send what waits: the first datagram, and more at once only while each is full; the rest and
        what could not be sent wait for the next round."""
        self._keep_allowed(self._config())
        position, call, target = self._position(), base_of(self._config().station_call), self._target()
        if position is None or call is None or target is None:
            self.queue.clear()  # (nothing of it can go: the call, the position and the target say why in the log)
            return
        receiver = Receiver(call, grid_of(*position), SOFTWARE)
        first = True
        while self.queue:
            templates = self._templates_due(now)
            waiting = list(self.queue)
            count = max(1, fitting(receiver, [w.report for w in waiting], templates))
            if not first and count >= len(waiting):
                self._due = self._next(now)  # pskdev.html: sooner only "if the packet becomes full"
                return
            batch = waiting[:count]
            data = datagram(
                int(now.timestamp()), self.sequence, self.session, receiver, [w.report for w in batch], templates
            )
            if not await self._send(data, target):
                self._due = self._next(now)
                return
            for _ in batch:
                self.queue.popleft()
            self._sent(now, batch, bool(templates))
            first = False

    def _templates_due(self, now: datetime) -> tuple[Template, ...]:
        hourly = self._templates_at is not None and now - self._templates_at >= timedelta(seconds=TEMPLATES_EVERY_SEC)
        return TEMPLATES if self._with_templates < TEMPLATES_FIRST or hourly else ()

    def _sent(self, now: datetime, batch: list[Waiting], templates: bool) -> None:
        self.sequence += len(batch)
        self._last_sent = now
        self._dropping = False
        if templates:
            self._with_templates += 1
            self._templates_at = now
        for waiting in batch:
            self.sent[waiting.radio] = self.sent.get(waiting.radio, 0) + 1
            self.last_sent[waiting.radio] = now
        log.debug("PSK Reporter: %d reports sent", len(batch))

    def _target(self) -> tuple[str, int] | None:
        """Return where the datagrams go; None where nothing may be sent (a test, the no-devices switch)."""
        given = self._environ.get(ENV_TARGET, "").strip()
        if not given:
            if self._environ.get(ENV_SWITCH) == "0":
                self._note("off", f"PSK Reporter: nothing is sent while {ENV_SWITCH}=0 and {ENV_TARGET} is not set")
                return None
            host, port = HOST, PORT
        else:
            host, _, number = given.rpartition(":")
            if not host or not number.isdigit() or not 0 < int(number) < 65536:
                self._note("target", f"PSK Reporter: {ENV_TARGET}={given!r} is not host:port; nothing is sent")
                return None
            host, port = host.strip("[]"), int(number)
        return None if nodevices.host_refused(host, "PSK Reporter", logging.INFO) else (host, port)

    def _failed(self, error: Exception) -> None:
        """The network refused a datagram: the socket is made anew, its family looked up again, next round."""
        self._note("failed", f"PSK Reporter: the network refused a datagram ({error}); the socket is made anew")
        self._renew = True

    def _close(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport, self._family, self._renew = None, None, False

    async def _send(self, data: bytes, target: tuple[str, int]) -> bool:
        """Send one datagram on the session's socket; return whether it went."""
        if self._renew or (self._transport is not None and self._transport.is_closing()):
            self._close()
        loop = asyncio.get_running_loop()
        try:
            found = await loop.getaddrinfo(*target, type=socket.SOCK_DGRAM)
        except OSError as e:
            self._note("unresolved", f"PSK Reporter: {target[0]} could not be looked up ({e}); the reports wait")
            return False
        address = next((info[4] for info in found if self._family in (None, info[0])), None)
        try:
            if address is None:
                raise OSError(f"{target[0]} has no address of the family of the session's socket")
            if self._transport is None:
                family = next(info[0] for info in found if info[4] == address)
                # a client socket: it sends
                local = ("::", 0) if family == socket.AF_INET6 else ("0.0.0.0", 0)  # noqa: S104
                self._transport, _ = await loop.create_datagram_endpoint(
                    lambda: _Socket(self._failed), local_addr=local, family=family
                )
                self._family = family
            self._transport.sendto(data, address)
        except OSError as e:
            self._note("failed", f"PSK Reporter: a datagram could not be sent to {target[0]} ({e}); the reports wait")
            self._close()
            return False
        self._note("sent", f"PSK Reporter: reports go to {target[0]} port {target[1]}")
        return True

    def _note(self, state: str, words: str) -> None:
        """Log a change of the state once; the same state again is not logged."""
        if state != self._state:
            log.info("%s", words)
            self._state = state
