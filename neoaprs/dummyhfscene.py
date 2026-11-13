"""The world of the Dummy HF radio: made-up traffic of the kind an HF channel carries, for trying the HF side of NeoAPRS without a radio and without another station on the air. An `HfScene` is pure, as the Dummy
radio's `Scene` is (dummyscene.py): asked what is on the air by `due(now)` it gives the frames that have come due, told what we sent by `react` it queues what the world answers; dummyline.py plays either on the Tnc's line.

What an HF channel sounds like, in the rules of radiorules.py: a handful of fixed stations hundreds of kilometres away (the stations an HF net hears are the distant ones, never the neighbours), each at its own
place in Finland and in Europe, each with a timed beacon every half hour to an hour plus the random pause every HF beacon adds, every frame direct (no digipeater repeats anything on HF), and every station
takes messages; the nearest answers one, with an ack a frame's time each way later and a reply after it, so that messaging over HF can be tried with its real pace. The first beacons come within the first two
minutes of the start, one every few tens of seconds, so that the map fills while the operator watches; after that the channel is as quiet as a real one. Nothing of ours is repeated back: there is no digipeater.

Every call is made up on the ITU's Q prefix, which the dummy radio uses for the same reason (dummyscene.py): QAA to QZZ is allocated to no country, so no call here is, or can ever be, a real station's, however
much its letters say where the station is meant to be."""
import heapq
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, parse_message

from .dummyframes import ack, air, fixed, message
from .mercury import DELIVERY_SEC
from .radiorules import HF_BEACON_JITTER_SEC

DIRECT = ""                                    # the path of every frame on HF
HELLO = "Hello from the dummy HF radio"
ACK_AFTER_SEC = 2 * DELIVERY_SEC               # a message reaches the station a frame's time after it is handed in, and its ack takes as long back (the bench measured about 10 s from send to ack)
ANSWER_AFTER_SEC = (ACK_AFTER_SEC + 6.0, ACK_AFTER_SEC + 14.0)       # the text of the answer: a second frame of the station's, after the pace a station keeps between two frames of its own
FIRST_BEACONS_SEC = (8.0, 26.0, 47.0, 71.0, 94.0, 118.0)              # when each station's first beacon comes: within two minutes, spread so that no two key together


@dataclass(frozen=True)
class Station:
    """A fixed station of the HF net: its made-up call, where it is (a real place, so that the distances are those of an HF net), its symbol, its comment, and its beacon's interval."""
    call: str
    lat: float
    lon: float
    symbol: str
    comment: str
    every_sec: float
    answers: bool = False


# Oulu, Kuopio and Turku in Finland; Stockholm, Hamburg and Warsaw in Europe: 150 to 1100 km from Helsinki, the distances an HF net has. The nearest, Turku, answers a message.
STATIONS: tuple[Station, ...] = (
    Station("Q3TKU", 60.4518, 22.2666, "/-", "Turku, 50 W to a dipole", 1800, answers=True),
    Station("Q1KUO", 62.8924, 27.6770, "/-", "Kuopio, QRV on 40 m", 2700),
    Station("Q5OUL", 65.0121, 25.4651, "/y", "Oulu, vertical on the roof", 3600),
    Station("Q2STO", 59.3293, 18.0686, "/-", "Stockholm, Mercury HF", 2400),
    Station("Q4HAM", 53.5511, 9.9937, "/-", "Hamburg, 100 W dipole", 3600),
    Station("Q6WAW", 52.2297, 21.0122, "/y", "Warszawa, 20 m up", 3000),
)


@dataclass
class Actor:
    station: Station
    next_at: datetime


class HfScene:
    def __init__(self, centre: tuple[float, float] | None, now: datetime, seed: int = 1) -> None:
        self.centre = centre                   # (where we are is of no account to stations hundreds of kilometres away; kept so that the scene is made as the Dummy radio's is)
        self.started = now
        self._rng = random.Random(seed)  # noqa: S311  (the made-up stations of the Dummy radio, the same for the same seed: nothing secret is drawn)
        self._queue: list[tuple[datetime, int, ax25.Frame]] = []
        self._count = 0
        self._ids = 0
        self._answered: set[tuple[str, str]] = set()
        self.actors = [Actor(station, now + timedelta(seconds=first)) for station, first in zip(STATIONS, FIRST_BEACONS_SEC, strict=True)]

    @property
    def description(self) -> str:
        """For the log: what the scene makes up."""
        return f"{len(self.actors)} distant stations, {', '.join(a.station.call for a in self.actors)}"

    # ---- what is on the air
    def due(self, now: datetime) -> list[ax25.Frame]:
        """The frames that have come due by `now`, in the order of the air."""
        for actor in self.actors:
            if actor.next_at <= now:
                self._beacon(actor, now)
        out: list[ax25.Frame] = []
        while self._queue and self._queue[0][0] <= now:
            out.append(heapq.heappop(self._queue)[2])
        return out

    def _beacon(self, actor: Actor, now: datetime) -> None:
        s = actor.station
        self._put(now, air(s.call, fixed(s.lat, s.lon, s.symbol, s.comment, True), DIRECT))
        actor.next_at = now + timedelta(seconds=s.every_sec + self._rng.uniform(0, HF_BEACON_JITTER_SEC))        # (the interval, then the random pause every HF beacon adds, radiorules.py)

    def _put(self, at: datetime, frame: ax25.Frame) -> None:
        self._count += 1
        heapq.heappush(self._queue, (at, self._count, frame))

    # ---- what the world does with what we send
    def react(self, frame: ax25.Frame, now: datetime) -> None:
        """We sent `frame`. A message to the station that answers is acked and answered at the pace of HF; everything else goes nowhere (nothing on HF repeats a frame)."""
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
            self._put(now + timedelta(seconds=self._rng.uniform(*ANSWER_AFTER_SEC)), air(talker.call, message(us, HELLO, str(self._ids)), DIRECT))

