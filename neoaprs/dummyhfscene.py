"""The world of the Dummy HF radio: made-up traffic of the kind an HF channel carries.

Fixed stations hundreds of kilometres away beacon direct; one answers a message at HF pace.
Each frame carries the SNR a Mercury would report (`reading_of`).
"""

import heapq
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, parse_message

from .dummyframes import ack, air, fixed, message
from .mercury import DELIVERY_SEC
from .radiotype import HF_BEACON_JITTER_SEC
from .reading import Reading

DIRECT = ""  # no digipeaters on HF
HELLO = "Hello from the dummy Mercury radio"
# A message reaches the station a frame's time after it is sent; its ack takes as long back.
ACK_AFTER_SEC = 2 * DELIVERY_SEC
# The answer follows the ack after the pace a station keeps between frames.
ANSWER_AFTER_SEC = (ACK_AFTER_SEC + 6.0, ACK_AFTER_SEC + 14.0)
# First beacons, spread so that no two key together.
FIRST_BEACONS_SEC = (8.0, 26.0, 47.0, 71.0, 94.0, 118.0)
FADING_DB = 3.0  # a frame's SNR strays this far either way
# DATAC3 decodes from -4 dB; Mercury's estimate stops at 12 dB.
SNR_RANGE_DB = (-4.0, 12.0)


@dataclass(frozen=True)
class Station:
    call: str
    lat: float
    lon: float
    symbol: str
    comment: str
    every_sec: float
    snr_db: float  # level its frames come in at, before the fading
    answers: bool = False


# 150 to 1100 km from Helsinki; Turku answers messages.
STATIONS: tuple[Station, ...] = (
    Station("Q3TKU", 60.4518, 22.2666, "/-", "Turku, 50 W to a dipole", 1800, 8.0, answers=True),
    Station("Q1KUO", 62.8924, 27.6770, "/-", "Kuopio, QRV on 40 m", 2700, 5.0),
    Station("Q5OUL", 65.0121, 25.4651, "/y", "Oulu, vertical on the roof", 3600, 3.0),
    Station("Q2STO", 59.3293, 18.0686, "/-", "Stockholm, Mercury HF", 2400, 6.0),
    Station("Q4HAM", 53.5511, 9.9937, "/-", "Hamburg, 100 W dipole", 3600, 1.0),
    Station("Q6WAW", 52.2297, 21.0122, "/y", "Warszawa, 20 m up", 3000, -1.0),
)


@dataclass
class Actor:
    station: Station
    next_at: datetime


class HfScene:
    def __init__(self, centre: tuple[float, float] | None, now: datetime, seed: int = 1) -> None:
        self.centre = centre
        self.started = now
        self._rng = random.Random(seed)  # noqa: S311  (made-up stations, same per seed)
        # Separate stream: traffic times must not depend on frames read.
        self._fading = random.Random(seed + 1)  # noqa: S311  (SNR of each frame; nothing secret)
        self._queue: list[tuple[datetime, int, ax25.Frame]] = []
        self._count = 0
        self._ids = 0
        self._answered: set[tuple[str, str]] = set()
        self.actors = [
            Actor(station, now + timedelta(seconds=first))
            for station, first in zip(STATIONS, FIRST_BEACONS_SEC, strict=True)
        ]

    @property
    def description(self) -> str:
        return f"{len(self.actors)} distant stations, {', '.join(a.station.call for a in self.actors)}"

    def due(self, now: datetime) -> list[ax25.Frame]:
        for actor in self.actors:
            if actor.next_at <= now:
                self._beacon(actor, now)
        out: list[ax25.Frame] = []
        while self._queue and self._queue[0][0] <= now:
            out.append(heapq.heappop(self._queue)[2])
        return out

    def reading_of(self, frame: ax25.Frame) -> Reading:
        """Return the SNR of a frame: its station's level plus fading, within SNR_RANGE_DB."""
        level = next((a.station.snr_db for a in self.actors if a.station.call == str(frame.source)), 0.0)
        low, high = SNR_RANGE_DB
        return Reading(snr=round(min(high, max(low, level + self._fading.uniform(-FADING_DB, FADING_DB))), 1))

    def _beacon(self, actor: Actor, now: datetime) -> None:
        s = actor.station
        self._put(now, air(s.call, fixed(s.lat, s.lon, s.symbol, s.comment, True), DIRECT))
        actor.next_at = now + timedelta(seconds=s.every_sec + self._rng.uniform(0, HF_BEACON_JITTER_SEC))

    def _put(self, at: datetime, frame: ax25.Frame) -> None:
        self._count += 1
        heapq.heappush(self._queue, (at, self._count, frame))

    def react(self, frame: ax25.Frame, now: datetime) -> None:
        """React to a frame we sent: a message to the answering station is acked and answered."""
        if frame.info[:1] != b":":
            return
        try:
            read = parse_message(frame.info[1:])
        except MessageError:
            return
        talker = next((a.station for a in self.actors if a.station.answers and a.station.call == read.addressee), None)
        if talker is None or read.ack_id or read.rej_id:
            return
        us = str(frame.source)
        if read.msg_id:
            self._put(now + timedelta(seconds=ACK_AFTER_SEC), air(talker.call, ack(us, read.msg_id), DIRECT))
        key = (talker.call, read.msg_id or read.text)
        if key not in self._answered:
            self._answered.add(key)
            self._ids += 1
            self._put(
                now + timedelta(seconds=self._rng.uniform(*ANSWER_AFTER_SEC)),
                air(talker.call, message(us, HELLO, str(self._ids)), DIRECT),
            )
