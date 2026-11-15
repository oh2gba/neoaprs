"""The world of the Dummy LoRa radio: made-up stations of a LoRa APRS network round the station, for trying a LoRa radio in NeoAPRS without a board. A `LoraScene` is pure, as the Dummy radio's `Scene` is
(dummyscene.py): asked what is on the air by `due(now)` it gives the frames that have come due, told what we sent by `react` it queues what the world answers; dummyworlds.py plays it on the Tnc's line as a
board would, in TNC2 text (`board_line`, `board_air`; neoaprs/tnc2line.py).

What a LoRa APRS network sounds like (aprs-reference/lora-plan.md, section 2): a few stations within some tens of kilometres, each beaconing every few minutes to every quarter of an hour (the firmwares'
default is 15 minutes), a home iGate on a hill that repeats what asks for WIDE1-1 as the boards' own digipeater does (the first element of the path, WIDE1-1 unused, becomes its call with a star; nothing else is
repeated), trackers in a car and on a bike, and a home station that takes messages and answers one, at the pace of a frame of two to four seconds each way. A frame of ours that asks for WIDE1-1 is repeated by
the iGate, so that the operator sees it go out. Every frame comes with the signal-to-noise ratio and the strength a board measures of it (`reading_of`): those of the station that put it on the air (the iGate
for a repeat), each station's own level with a few dB of fading from one frame to the next, within what a board at SF12 decodes. A comment in UTF-8 is among them, as the trackers send them.

Every call is made up on the ITU's Q prefix, for the same reason as the Dummy radio's (dummyscene.py: QAA to QZZ is no country's), on letters the other Dummy worlds do not use; each Dummy LoRa radio has a world of
its own by its seed (the radio's id): the calls of `dummyscene.call_of` and every place turned round the station, as the Dummy radio's world is."""
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
PATH = "WIDE1-1"                               # what every station of the network asks for: the nearest digipeater, once
TOCALL = "APLRT1"                              # the destination a LoRa tracker sends to (an iGate's is APLRG1)
IGATE = "Q9LRG-10"                             # the iGate on the hill, which repeats WIDE1-1
HOME, CAR, BIKE = "Q9KOT", "Q9TRK-7", "Q9BKE-12"        # the home station that takes messages, the car tracker and the bike tracker
ACK_AFTER_SEC = 5.0                            # a message reaches the station a frame's time after it went, and its ack takes as long back
ANSWER_AFTER_SEC = (11.0, 17.0)                # the text of the answer, after the station's own pause between two frames
REPEAT_AFTER_SEC = (2.5, 4.0)                  # the iGate sends a frame again once the frame has ended and it has listened for a moment
FADING_DB = 4.0                                # how far a frame's readings stray from its station's own level, either way
SNR_RANGE_DB = (-20.0, 12.0)                   # what a board at SF12 decodes from, and where its estimate stops rising
RSSI_RANGE_DBM = (-135.0, -40.0)


def board_line(packet: bytes) -> bytes:
    """What a board writes on its line for a LoRa packet it heard: the packet's text, after the header, ended by a carriage return and a line feed as the iGate writes TNC2 to its clients; nothing for a
    packet without the header (the board hands no such packet on)."""
    return packet[len(HEADER):] + b"\r\n" if packet.startswith(HEADER) else b""


def board_air(frame: ax25.Frame) -> bytes | None:
    """The LoRa packet a board sends for a frame the computer handed it: the header and the frame's text; None when it is longer than a LoRa packet can be (the board sends nothing)."""
    packet = air_of(frame)
    return packet if fits(packet) else None


@dataclass
class Actor:
    """A station that sends by itself, every `every_sec` (give or take a seventh), what `make` gives at the moment; its own level of signal and whether it takes messages."""
    call: str
    every_sec: float
    first_sec: float
    make: Callable[[datetime], list[ax25.Frame]]
    rssi_dbm: float
    snr_db: float
    answers: bool = False
    next_at: datetime | None = None


def calls(seed: int) -> frozenset[str]:
    """The calls the world of `seed` makes its stations up under (dummyscene.call_of): what a radio that leaves the world takes along."""
    return frozenset(call_of(call, seed) for call in (IGATE, HOME, CAR, BIKE))


class LoraScene:
    def __init__(self, centre: tuple[float, float] | None, now: datetime, seed: int = 1) -> None:
        self.centre = centre or HELSINKI
        self.started = now
        self.seed = seed
        turn = math.radians(TURN_DEG * (seed - 1) % 360)
        self._turn = (math.cos(turn), math.sin(turn))
        self.igate = call_of(IGATE, seed)
        self._rng = random.Random(seed)  # noqa: S311  (the made-up stations of the Dummy LoRa radio, the same for the same seed: nothing secret is drawn)
        self._fading = random.Random(seed + 1)  # noqa: S311  (the same, for the readings of each frame: apart, so that the times of the traffic do not depend on how many frames were read)
        self._queue: list[tuple[datetime, int, ax25.Frame]] = []
        self._count = 0
        self._ids = 0
        self._answered: set[tuple[str, str]] = set()
        self.actors = self._build()

    @property
    def description(self) -> str:
        """For the log: what the scene makes up, and where."""
        return f"a LoRa network of {len(self.actors)} stations round {self.centre[0]:.4f}, {self.centre[1]:.4f}, {', '.join(a.call for a in self.actors)}"

    def where(self, east_km: float, north_km: float) -> tuple[float, float]:
        """The place that far east and north of the centre, in this world (turned round the centre for a seed after the first)."""
        cos, sin = self._turn
        return around(self.centre, east_km * cos + north_km * sin, north_km * cos - east_km * sin)

    # ---- what is on the air
    def due(self, now: datetime) -> list[ax25.Frame]:
        """The frames that have come due by `now`, in the order of the air."""
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
        """The SNR and the strength of a frame of the scene: those of the station that sent it on the air (the last digipeater it went through, else its source), with the fading of the moment."""
        sent_by = next((format(a) for a in reversed(frame.path) if a.repeated), str(frame.source)).removesuffix("*")
        actor = next((a for a in self.actors if a.call == sent_by), None)
        rssi, snr = (actor.rssi_dbm, actor.snr_db) if actor is not None else (RSSI_RANGE_DBM[0] + 10, SNR_RANGE_DB[0] + 5)
        fade = self._fading.uniform(-FADING_DB, FADING_DB)
        return Reading(snr=round(min(SNR_RANGE_DB[1], max(SNR_RANGE_DB[0], snr + fade)), 1), rssi=round(min(RSSI_RANGE_DBM[1], max(RSSI_RANGE_DBM[0], rssi + fade))))

    def _repeat(self, frame: ax25.Frame, now: datetime) -> None:
        """The iGate repeats a frame whose path begins with WIDE1-1 unused and which no digipeater has repeated yet."""
        first = frame.path[0] if frame.path else None
        if first is not None and (first.call, first.ssid, first.repeated) == ("WIDE1", 1, False) and not any(a.repeated for a in frame.path) and str(frame.source) != self.igate:
            self._put(now + timedelta(seconds=self._rng.uniform(*REPEAT_AFTER_SEC)), repeated(frame, self.igate))

    def _put(self, at: datetime, frame: ax25.Frame) -> None:
        self._count += 1
        heapq.heappush(self._queue, (at, self._count, frame))

    # ---- what the world does with what we send
    def react(self, frame: ax25.Frame, now: datetime) -> None:
        """We sent `frame` (as the board put it on the air). A message to the station that takes messages is acked and answered; a frame that asks for WIDE1-1 is repeated by the iGate; nothing else answers."""
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
            self._put(now + timedelta(seconds=self._rng.uniform(*ANSWER_AFTER_SEC)), air(talker.call, message(us, HELLO, str(self._ids)), PATH))

    # ---- who is there
    def _build(self) -> list[Actor]:
        def at(call: str, east: float, north: float, symbol: str, comment: str, path: str, tocall: str = TOCALL) -> Callable[[datetime], list[ax25.Frame]]:
            lat, lon = self.where(east, north)
            return lambda now: [air(call, fixed(lat, lon, symbol, comment, True), path, tocall)]

        igate, home = self.igate, call_of(HOME, self.seed)
        actors = [
            Actor(igate, 900, 5, at(igate, 3.2, 4.1, "L&", "LoRa iGate and digipeater, 433.775 MHz", "", "APLRG1"), -82, 9.0),
            Actor(home, 900, 15, at(home, -6.5, 2.8, "/-", "Home station on LoRa APRS", PATH), -104, 4.0, answers=True),
            self._mover(call_of(CAR, self.seed), "/>", "LoRa tracker", RING_ROAD, 60, 120, 25, -112, -2.0),
            self._mover(call_of(BIKE, self.seed), "/b", "Pyöräilemässä, LoRa tracker", TOWN_LOOP, 18, 240, 40, -118, -7.0),
        ]
        for actor in actors:
            actor.next_at = self.started + timedelta(seconds=actor.first_sec)
        return actors

    def _mover(self, call: str, symbol: str, comment: str, route: Route, kmh: float, every: float, first: float, rssi: float, snr: float) -> Actor:
        phase = self._rng.uniform(0, route.length_km)

        def make(now: datetime) -> list[ax25.Frame]:
            east, north, course = route.at(phase + kmh * (now - self.started).total_seconds() / 3600)
            lat, lon = self.where(east, north)
            return [air(call, b"=" + compressed_position(lat, lon, symbol[0], symbol[1], course, kmh) + comment.encode("utf-8"), PATH, TOCALL)]      # (the comment as the trackers send it: UTF-8)

        return Actor(call, every, first, make, rssi, snr)
