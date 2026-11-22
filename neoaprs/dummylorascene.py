"""The world of the Dummy LoRa radio: made-up stations of a LoRa APRS network round the station.

A few stations: an iGate repeating WIDE1-1, trackers and a station that takes messages. Each
radio's seed gives its own world; dummyworlds.py plays it in TNC2 text as a board would.
"""

import heapq
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, parse_message

from .aprsposition import compressed_position
from .dummyframes import ack, air, fixed, message, repeated
from .dummyroutes import RING_ROAD, TOWN_LOOP, Route, around
from .dummyscene import HELSINKI, TURN_DEG, call_of
from .reading import Reading
from .tnc2line import HEADER, air_of, fits

HELLO = "Hello from the dummy LoRa radio"
PATH = "WIDE1-1"  # what every station asks for
TOCALL = "APLRT1"  # a LoRa tracker's destination (an iGate's is APLRG1)
IGATE = "Q9LRG-10"  # repeats WIDE1-1
HOME, CAR, BIKE = "Q9KOT", "Q9TRK-7", "Q9BKE-12"  # HOME takes messages
# A message reaches the station a frame's time after it went; the ack takes as long back.
ACK_AFTER_SEC = 5.0
ANSWER_AFTER_SEC = (11.0, 17.0)  # after the station's pause between two frames
REPEAT_AFTER_SEC = (2.5, 4.0)  # the iGate repeats after the frame ended and it listened
FADING_DB = 4.0  # a frame's readings stray this far either way
# A board at SF12 decodes from -20 dB; its estimate stops rising at 12 dB.
SNR_RANGE_DB = (-20.0, 12.0)
RSSI_RANGE_DBM = (-135.0, -40.0)


def board_line(packet: bytes) -> bytes:
    """Return what a board writes for a heard LoRa packet: the text after the header, then CR LF."""
    return packet[len(HEADER) :] + b"\r\n" if packet.startswith(HEADER) else b""


def board_air(frame: ax25.Frame) -> bytes | None:
    """Return the LoRa packet a board sends for a frame, or None if it is too long for LoRa."""
    packet = air_of(frame)
    return packet if fits(packet) else None


@dataclass
class Actor:
    """A station that sends what `make` gives every `every_sec` (give or take a seventh)."""

    call: str
    every_sec: float
    first_sec: float
    make: Callable[[datetime], list[ax25.Frame]]
    rssi_dbm: float
    snr_db: float
    answers: bool = False
    next_at: datetime | None = None


def calls(seed: int) -> frozenset[str]:
    """Return the calls the world of `seed` makes its stations up under (dummyscene.call_of)."""
    return frozenset(call_of(call, seed) for call in (IGATE, HOME, CAR, BIKE))


class LoraScene:
    def __init__(self, centre: tuple[float, float] | None, now: datetime, seed: int = 1) -> None:
        self.centre = centre or HELSINKI
        self.started = now
        self.seed = seed
        self._turn_deg = TURN_DEG * (seed - 1) % 360
        self._turn = (math.cos(math.radians(self._turn_deg)), math.sin(math.radians(self._turn_deg)))
        self.igate = call_of(IGATE, seed)
        self._rng = random.Random(seed)  # noqa: S311  (made-up stations, same per seed)
        # Separate stream: traffic times must not depend on frames read.
        self._fading = random.Random(seed + 1)  # noqa: S311  (readings of each frame)
        self._queue: list[tuple[datetime, int, ax25.Frame]] = []
        self._count = 0
        self._ids = 0
        self._answered: set[tuple[str, str]] = set()
        self.actors = self._build()

    @property
    def description(self) -> str:
        return f"a LoRa network of {len(self.actors)} stations round {self.centre[0]:.4f}, {self.centre[1]:.4f}, {', '.join(a.call for a in self.actors)}"

    def where(self, east_km: float, north_km: float) -> tuple[float, float]:
        """Return the place east and north of the centre, turned for later seeds."""
        cos, sin = self._turn
        return around(self.centre, east_km * cos + north_km * sin, north_km * cos - east_km * sin)

    def due(self, now: datetime) -> list[ax25.Frame]:
        for actor in self.actors:
            if actor.next_at is not None and actor.next_at <= now:
                for frame in actor.make(now):
                    self._put(now, frame)
                    self._repeat(frame, now)
                actor.next_at = now + timedelta(seconds=actor.every_sec * self._rng.uniform(0.86, 1.14))
        out: list[ax25.Frame] = []
        while self._queue and self._queue[0][0] <= now:
            out.append(heapq.heappop(self._queue)[2])
        return out

    def reading_of(self, frame: ax25.Frame) -> Reading:
        """Return the SNR and RSSI of a frame: the last digipeater's or source's, plus fading."""
        sent_by = next((format(a) for a in reversed(frame.path) if a.repeated), str(frame.source)).removesuffix("*")
        actor = next((a for a in self.actors if a.call == sent_by), None)
        rssi, snr = (
            (actor.rssi_dbm, actor.snr_db) if actor is not None else (RSSI_RANGE_DBM[0] + 10, SNR_RANGE_DB[0] + 5)
        )
        fade = self._fading.uniform(-FADING_DB, FADING_DB)
        return Reading(
            snr=round(min(SNR_RANGE_DB[1], max(SNR_RANGE_DB[0], snr + fade)), 1),
            rssi=round(min(RSSI_RANGE_DBM[1], max(RSSI_RANGE_DBM[0], rssi + fade))),
        )

    def _repeat(self, frame: ax25.Frame, now: datetime) -> None:
        """Queue the iGate's repeat of a frame whose path starts with an unused WIDE1-1."""
        first = frame.path[0] if frame.path else None
        if (
            first is not None
            and (first.call, first.ssid, first.repeated) == ("WIDE1", 1, False)
            and not any(a.repeated for a in frame.path)
            and str(frame.source) != self.igate
        ):
            self._put(now + timedelta(seconds=self._rng.uniform(*REPEAT_AFTER_SEC)), repeated(frame, self.igate))

    def _put(self, at: datetime, frame: ax25.Frame) -> None:
        self._count += 1
        heapq.heappush(self._queue, (at, self._count, frame))

    def react(self, frame: ax25.Frame, now: datetime) -> None:
        """React to a frame we sent: a message to HOME is answered, WIDE1-1 is repeated."""
        if frame.info[:1] == b":":
            self._answer(frame, now)
        self._repeat(frame, now)

    def _answer(self, frame: ax25.Frame, now: datetime) -> None:
        try:
            read = parse_message(frame.info[1:])
        except MessageError:
            return
        talker = next((a for a in self.actors if a.answers and a.call == read.addressee), None)
        if talker is None or read.ack_id or read.rej_id:
            return
        us = str(frame.source)
        if read.msg_id:
            self._put(now + timedelta(seconds=ACK_AFTER_SEC), air(talker.call, ack(us, read.msg_id), PATH))
        key = (talker.call, read.msg_id or read.text)
        if key not in self._answered:
            self._answered.add(key)
            self._ids += 1
            self._put(
                now + timedelta(seconds=self._rng.uniform(*ANSWER_AFTER_SEC)),
                air(talker.call, message(us, HELLO, str(self._ids)), PATH),
            )

    def _build(self) -> list[Actor]:
        def at(
            call: str, east: float, north: float, symbol: str, comment: str, path: str, tocall: str = TOCALL
        ) -> Callable[[datetime], list[ax25.Frame]]:
            lat, lon = self.where(east, north)
            return lambda now: [air(call, fixed(lat, lon, symbol, comment, True), path, tocall)]

        igate, home = self.igate, call_of(HOME, self.seed)
        actors = [
            Actor(
                igate,
                900,
                5,
                at(igate, 3.2, 4.1, "L&", "LoRa iGate and digipeater, 433.775 MHz", "", "APLRG1"),
                -82,
                9.0,
            ),
            Actor(home, 900, 15, at(home, -6.5, 2.8, "/-", "Home station on LoRa APRS", PATH), -104, 4.0, answers=True),
            self._mover(call_of(CAR, self.seed), "/>", "LoRa tracker", RING_ROAD, 60, 120, 25, -112, -2.0),
            self._mover(
                call_of(BIKE, self.seed), "/b", "Pyöräilemässä, LoRa tracker", TOWN_LOOP, 18, 240, 40, -118, -7.0
            ),
        ]
        for actor in actors:
            actor.next_at = self.started + timedelta(seconds=actor.first_sec)
        return actors

    def _mover(
        self,
        call: str,
        symbol: str,
        comment: str,
        route: Route,
        kmh: float,
        every: float,
        first: float,
        rssi: float,
        snr: float,
    ) -> Actor:
        phase = self._rng.uniform(0, route.length_km)

        def make(now: datetime) -> list[ax25.Frame]:
            east, north, course = route.at(phase + kmh * (now - self.started).total_seconds() / 3600)
            lat, lon = self.where(east, north)
            course = (course + self._turn_deg) % 360  # turned with its places
            return [
                air(
                    call,
                    b"=" + compressed_position(lat, lon, symbol[0], symbol[1], course, kmh) + comment.encode("utf-8"),
                    PATH,
                    TOCALL,
                )
            ]

        return Actor(call, every, first, make, rssi, snr)
