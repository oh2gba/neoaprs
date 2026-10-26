"""The world of the Dummy radio: made-up APRS traffic around the station, for trying NeoAPRS out without a radio. A `Scene` is pure (no radio, no clock of its own, no I/O): asked for what is on the air by `due(now)`,
it gives the frames that have come due, and told what we sent (`react`) it queues what the world answers. dummyline.py plays it on the Tnc's line.

Every call here is made up on the ITU's Q prefix: the series QAA to QZZ is never allocated to any country, so none of these calls is, or can ever be, a real station's. A packet with such a source is never anyone's.
The scene has fixed stations (a house, a club shack, a cottage), three cars and a walker on routes round the station, a weather station that reports every five minutes, two digipeaters with PHG that repeat the
others (a path with `*`), two objects, a bulletin now and then, and a status. The stations that take messages (`=` positions) answer one: an ack after a moment and the text "Hello from the dummy radio" a few seconds
later. What we send is not carried anywhere; a position of ours is played back as a digipeater repeating it, now and then. The first transmissions come within half a minute of the start, and then a few packets a minute."""
import heapq
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, parse_message

from .dummyframes import PATH, ack, air, bulletin, compressed, cosine_day, fixed, is_position, mice, message, object_report, repeated, status, walking, weather
from .dummyroutes import DELIVERY_ROUND, PARK_PATH, RING_ROAD, TOWN_LOOP, Route, around

HELSINKI = (60.1699, 24.9384)                  # the centre when the station has no position yet
HELLO = "Hello from the dummy radio"
DIGIPEATERS = ("Q2DIG-2", "Q7DIG-1")           # the first repeats the cars and the house, the second the van, the walker, the cottage and the weather
ACK_AFTER_SEC = 1.5
ANSWER_AFTER_SEC = (3.5, 6.0)                  # the text of an answer comes this long after the message
REPEAT_AFTER_SEC = (0.8, 1.8)                  # a digipeater sends a frame again this long after it heard it
ECHO_CHANCE = 0.6                              # of our positions after the first, which is always repeated


@dataclass
class Actor:
    """A station that sends by itself: every `every_sec` (give or take a seventh), `make` gives its frames of the moment; `digi` is the digipeater that repeats the first of them."""
    call: str
    every_sec: float
    first_sec: float                           # the first transmission comes this long after the start
    make: Callable[[datetime], list[ax25.Frame]]
    digi: str | None = None
    answers: bool = False                      # it takes a message and answers it
    path: str = PATH                           # what it asks for when it sends a message
    next_at: datetime | None = None


class Scene:
    def __init__(self, centre: tuple[float, float] | None, now: datetime, seed: int = 1) -> None:
        self.centre = centre or HELSINKI
        self.started = now
        self._rng = random.Random(seed)
        self._queue: list[tuple[datetime, int, ax25.Frame]] = []
        self._count = 0
        self._ids = 0
        self._sent_positions = 0
        self._answered: set[tuple[str, str]] = set()
        self.actors: list[Actor] = self._build()

    def where(self, east_km: float, north_km: float) -> tuple[float, float]:
        return around(self.centre, east_km, north_km)

    # ---- what is on the air
    def due(self, now: datetime) -> list[ax25.Frame]:
        """The frames that have come due by `now`, in the order of the air."""
        for actor in self.actors:
            if actor.next_at is not None and actor.next_at <= now:
                self._send(actor, now)
        out: list[ax25.Frame] = []
        while self._queue and self._queue[0][0] <= now:
            out.append(heapq.heappop(self._queue)[2])
        return out

    def _send(self, actor: Actor, now: datetime) -> None:
        frames = actor.make(now)
        for frame in frames:
            self._put(now, frame)
        if actor.digi is not None and frames and self._rng.random() < 0.85:
            self._put(now + self._after(REPEAT_AFTER_SEC), repeated(frames[0], actor.digi))
        actor.next_at = now + timedelta(seconds=actor.every_sec * self._rng.uniform(0.86, 1.14))

    def _put(self, at: datetime, frame: ax25.Frame) -> None:
        self._count += 1
        heapq.heappush(self._queue, (at, self._count, frame))

    def _after(self, seconds: tuple[float, float]) -> timedelta:
        return timedelta(seconds=self._rng.uniform(*seconds))

    # ---- what the world does with what we send
    def react(self, frame: ax25.Frame, now: datetime) -> None:
        """We sent `frame`. A message to a station that takes messages is acked and answered; a position of ours is repeated by a digipeater now and then; anything else goes nowhere."""
        if frame.info[:1] == b":":
            self._answer(frame, now)
        elif is_position(frame.info) and not str(frame.source).startswith("Q"):
            self._sent_positions += 1
            if self._sent_positions == 1 or self._rng.random() < ECHO_CHANCE:
                self._put(now + self._after((1.2, 2.4)), repeated(frame, DIGIPEATERS[0]))

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
            self._put(now + timedelta(seconds=ACK_AFTER_SEC), air(talker.call, ack(us, read.msg_id), talker.path))
        key = (talker.call, read.msg_id or read.text)
        if key not in self._answered:
            self._answered.add(key)
            self._ids += 1
            self._put(now + self._after(ANSWER_AFTER_SEC), air(talker.call, message(us, HELLO, str(self._ids)), talker.path))

    # ---- who is there
    def _build(self) -> list[Actor]:
        actors = [*self._houses(), *self._movers(), *self._services()]
        for actor in actors:
            actor.next_at = self.started + timedelta(seconds=actor.first_sec)
        return actors

    def _houses(self) -> list[Actor]:
        def at(east: float, north: float, call: str, symbol: str, comment: str) -> Callable[[datetime], list[ax25.Frame]]:
            lat, lon = self.where(east, north)
            return lambda now: [air(call, fixed(lat, lon, symbol, comment, True))]

        return [
            Actor("Q1ABC", 420, 4, at(2.1, 1.4, "Q1ABC", "/-", "Home station, 2 m FM"), DIGIPEATERS[0], True),
            Actor("Q1CLB", 480, 9, at(-1.8, 0.6, "Q1CLB", "/K", "Radio club shack, open on Thursdays"), None, True),
            Actor("Q8QTH", 540, 14, at(5.2, -3.4, "Q8QTH", "/-", "Lake cottage"), DIGIPEATERS[1], True),
        ]

    def _movers(self) -> list[Actor]:
        return [
            self._mover("Q4CAR-9", "/>", "]Commuting=", TOWN_LOOP, 46, 40, 3, DIGIPEATERS[0], mic_e=True, tocall="APK004"),
            self._mover("Q5VAN-7", "/v", "Delivery round", DELIVERY_ROUND, 55, 50, 7, DIGIPEATERS[1], tocall="APOT21"),
            self._mover("Q6CAR-1", "/>", "Ring road", RING_ROAD, 72, 45, 11, DIGIPEATERS[0], mic_e=True, answers=False),
            self._mover("Q7WLK-7", "/[", "Dog walk", PARK_PATH, 4.5, 60, 16, DIGIPEATERS[1], tocall="APDR16", plain=True),
        ]

    def _mover(self, call: str, symbol: str, comment: str, route: Route, kmh: float, every: float, first: float, digi: str, mic_e: bool = False, tocall: str = "APRS", plain: bool = False, answers: bool = True) -> Actor:
        phase = self._rng.uniform(0, route.length_km)

        def make(now: datetime) -> list[ax25.Frame]:
            east, north, course = route.at(phase + kmh * (now - self.started).total_seconds() / 3600)
            lat, lon = self.where(east, north)
            speed = kmh * (0.9 + 0.1 * math.sin((now - self.started).total_seconds() / 37))
            if mic_e:
                destination, info = mice(lat, lon, symbol, comment, course, speed)
                return [air(call, info, PATH, destination)]
            info = walking(lat, lon, symbol, comment, course, speed) if plain else compressed(lat, lon, symbol, comment, course, speed)
            return [air(call, info, PATH, tocall)]

        return Actor(call, every, first, make, digi, answers=answers)

    def _services(self) -> list[Actor]:
        def beacon(call: str, phg: str, east: float, north: float) -> Callable[[datetime], list[ax25.Frame]]:
            lat, lon = self.where(east, north)
            return lambda now: [air(call, fixed(lat, lon, "/#", f"PHG{phg} Fill-in digi"), "WIDE2-1")]

        return [Actor("Q2DIG-2", 600, 6, beacon("Q2DIG-2", "5230", -1.5, 1.0)), Actor("Q7DIG-1", 600, 11, beacon("Q7DIG-1", "5340", 3.0, -1.5)), self._weather(), *self._club()]

    def _weather(self) -> Actor:
        lat, lon = self.where(-4.1, -2.2)

        def make(now: datetime) -> list[ax25.Frame]:
            minute = now.timestamp() / 60
            wind = 5 + 3 * math.sin(minute / 17)
            info = weather(lat, lon, "Backyard WX", int(200 + 40 * math.sin(minute / 90)), wind, wind * 1.6 + 1, 8 + 5 * cosine_day(now, 13), 0.0, 0.4, int(68 - 14 * cosine_day(now, 13)), 1012 + 3 * math.sin(minute / 700))
            return [air("Q3WX", info, "WIDE1-1")]

        return Actor("Q3WX", 300, 12, make, DIGIPEATERS[1])

    def _club(self) -> list[Actor]:
        def objects(name: str, symbol: str, comment: str, east: float, north: float) -> Callable[[datetime], list[ax25.Frame]]:
            lat, lon = self.where(east, north)
            return lambda now: [air("Q1CLB", object_report(name, now, lat, lon, symbol, comment))]

        def text(call: str, info: bytes) -> Callable[[datetime], list[ax25.Frame]]:
            return lambda now: [air(call, info)]

        return [
            Actor("Q1CLB", 600, 17, objects("FIELDDAY", "/;", "Field day on Saturday at 10:00", 4.6, 3.9)),
            Actor("Q1CLB", 600, 23, objects("PARKING", "/P", "Parking, free at weekends", -2.0, 0.2)),
            Actor("Q1CLB", 1200, 28, text("Q1CLB", bulletin("BLN1", "Net on Thursday at 20:00 on 145.500 MHz, all welcome"))),
            Actor("Q1ABC", 900, 21, text("Q1ABC", status("Listening on 144.800 MHz"))),
        ]
