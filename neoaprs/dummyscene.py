"""The world of the Dummy radio: made-up APRS traffic around the station, with no radio.

A `Scene` is pure (no radio, no clock, no I/O): `due(now)` gives the frames come due, `react`
queues the answers. Calls are on the Q prefix, which no country has; each radio's seed has a world.
"""
import heapq
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, parse_message

from .dummyqru import answer as qru_answer
from .dummyframes import PATH, ack, address, air, bulletin, compressed, cosine_day, fixed, is_position, mice, message, object_report, repeated, status, walking, weather
from .dummyqru import SERVER
from .dummyroutes import DELIVERY_ROUND, PARK_PATH, RING_ROAD, TOWN_LOOP, Route, around
from .reading import NO_READING, Reading

HELSINKI = (60.1699, 24.9384)  # the centre when the station has no position yet
HELLO = "Hello from the dummy radio"
# the first repeats the cars and the house, the second the van, the walker, the cottage and the
# weather
DIGIPEATERS = ("Q2DIG-2", "Q7DIG-1")
ACK_AFTER_SEC = 1.5
ANSWER_AFTER_SEC = (3.5, 6.0)  # seconds after the message
REPEAT_AFTER_SEC = (0.8, 1.8)  # a digipeater repeats a frame this long after hearing it
# chance that our positions after the first are repeated (the first always is)
ECHO_CHANCE = 0.6
# each seed after the first turns the world clockwise round the station by this much, so two Dummy
# radios' stations are not at the same places
TURN_DEG = 55
NAME_MAX = 9  # the longest name of an object


def call_of(call: str, seed: int) -> str:
    """Return the call a made-up station has in the world of `seed`.

    Seed 1 keeps its own; else the digit after the Q moves on per seed (Q1ABC is Q3ABC for 3)."""
    turns = seed - 1
    if turns == 0:
        return call
    base, dash, ssid = call.partition("-")
    return f"Q{(int(base[1]) + turns) % 10}{base[2:-1]}{chr((ord(base[-1]) - ord('A') + turns // 10) % 26 + ord('A'))}{dash}{ssid}"


def name_of(name: str, seed: int) -> str:
    """Return the name an object of the made-up club has in the world of `seed`.

    Its own for seed 1, else with the seed at its end (FIELDDAY3), cut to NAME_MAX."""
    return name if seed == 1 else f"{name[:NAME_MAX - len(str(seed))]}{seed}"


@dataclass
class Actor:
    """A station that sends by itself every `every_sec` (give or take a seventh).

    `digi` is the digipeater that repeats the first of them.
    """
    call: str
    every_sec: float
    first_sec: float  # the first transmission comes this long after the start
    make: Callable[[datetime], list[ax25.Frame]]
    digi: str | None = None
    answers: bool = False  # it takes a message and answers it
    path: str = PATH  # what it asks for when it sends a message
    next_at: datetime | None = None


class Scene:
    def __init__(self, centre: tuple[float, float] | None, now: datetime, seed: int = 1) -> None:
        self.centre = centre or HELSINKI
        self.started = now
        self.seed = seed
        self._turn_deg = TURN_DEG * (seed - 1) % 360
        self._turn = (math.cos(math.radians(self._turn_deg)), math.sin(math.radians(self._turn_deg))) if self._turn_deg else (1.0, 0.0)
        self.digipeaters = (self.call(DIGIPEATERS[0]), self.call(DIGIPEATERS[1]))
        self._rng = random.Random(seed)  # noqa: S311  (made-up stations, same per seed)
        self._queue: list[tuple[datetime, int, ax25.Frame]] = []
        self._count = 0
        self._ids = 0
        self._sent_positions = 0
        self._answered: set[tuple[str, str]] = set()
        self.actors: list[Actor] = self._build()

    def where(self, east_km: float, north_km: float) -> tuple[float, float]:
        """Return the place that far east and north of the centre, turned by the world's angle."""
        cos, sin = self._turn
        return around(self.centre, east_km * cos + north_km * sin, north_km * cos - east_km * sin)

    def call(self, call: str) -> str:
        """Return the call of the station in this world (`call_of`)."""
        return call_of(call, self.seed)

    @property
    def description(self) -> str:
        """Return where the traffic is made, for the log."""
        return f"traffic round {self.centre[0]:.4f}, {self.centre[1]:.4f}"

    def reading_of(self, frame: ax25.Frame) -> Reading:
        """Return None: the Dummy radio stands for a KISS TNC, which measures nothing."""
        return NO_READING

    # ---- what is on the air
    def due(self, now: datetime) -> list[ax25.Frame]:
        """Return the frames that have come due by `now`, in on-air order."""
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
        """React to `frame` we sent: a message is acked and answered, a position may be repeated."""
        if frame.info[:1] == b":":
            self._answer(frame, now)
        elif is_position(frame.info) and not str(frame.source).startswith("Q"):
            self._sent_positions += 1
            if self._sent_positions == 1 or self._rng.random() < ECHO_CHANCE:
                self._put(now + self._after((1.2, 2.4)), repeated(frame, self.digipeaters[0]))

    def _answer(self, frame: ax25.Frame, now: datetime) -> None:
        try:
            read = parse_message(frame.info[1:])
        except MessageError:
            return
        if read.addressee == "QRU":
            for after, reply in qru_answer(read.text, str(frame.source), now, self.where, lambda name: name_of(name, self.seed)):
                self._put(now + timedelta(seconds=after), self._from_club(reply))
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

    def _from_club(self, frame: ax25.Frame) -> ax25.Frame:
        """Return a QRU server frame (dummyqru.py) as this world's club sends it."""
        club = self.call(SERVER)
        return frame if club == SERVER else replace(frame, source=address(club), info=frame.info.replace(SERVER.encode("ascii"), club.encode("ascii")))

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

        home, club, cottage = self.call("Q1ABC"), self.call("Q1CLB"), self.call("Q8QTH")
        return [
            Actor(home, 420, 4, at(2.1, 1.4, home, "/-", "Home station, 2 m FM"), self.digipeaters[0], True),
            Actor(club, 480, 9, at(-1.8, 0.6, club, "/K", "Radio club shack, open on Thursdays"), None, True),
            Actor(cottage, 540, 14, at(5.2, -3.4, cottage, "/-", "Lake cottage"), self.digipeaters[1], True),
        ]

    def _movers(self) -> list[Actor]:
        return [
            self._mover("Q4CAR-9", "/>", "]Commuting=", TOWN_LOOP, 46, 40, 3, self.digipeaters[0], mic_e=True, tocall="APK004"),
            self._mover("Q5VAN-7", "/v", "Delivery round", DELIVERY_ROUND, 55, 50, 7, self.digipeaters[1], tocall="APOT21"),
            self._mover("Q6CAR-1", "/>", "Ring road", RING_ROAD, 72, 45, 11, self.digipeaters[0], mic_e=True, answers=False),
            self._mover("Q7WLK-7", "/[", "Dog walk", PARK_PATH, 4.5, 60, 16, self.digipeaters[1], tocall="APDR16", plain=True),
        ]

    def _mover(self, call: str, symbol: str, comment: str, route: Route, kmh: float, every: float, first: float, digi: str, mic_e: bool = False, tocall: str = "APRS", plain: bool = False, answers: bool = True) -> Actor:
        call = self.call(call)
        phase = self._rng.uniform(0, route.length_km)

        def make(now: datetime) -> list[ax25.Frame]:
            east, north, course = route.at(phase + kmh * (now - self.started).total_seconds() / 3600)
            lat, lon = self.where(east, north)
            course = (course + self._turn_deg) % 360
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

        first, second = self.digipeaters
        return [Actor(first, 600, 6, beacon(first, "5230", -1.5, 1.0)), Actor(second, 600, 11, beacon(second, "5340", 3.0, -1.5)), self._weather(), *self._club()]

    def _weather(self) -> Actor:
        lat, lon = self.where(-4.1, -2.2)
        call = self.call("Q3WX")

        def make(now: datetime) -> list[ax25.Frame]:
            minute = now.timestamp() / 60
            wind = 5 + 3 * math.sin(minute / 17)
            info = weather(lat, lon, "Backyard WX", int(200 + 40 * math.sin(minute / 90)), wind, wind * 1.6 + 1, 8 + 5 * cosine_day(now, 13), 0.0, 0.4, int(68 - 14 * cosine_day(now, 13)), 1012 + 3 * math.sin(minute / 700))
            return [air(call, info, "WIDE1-1")]

        return Actor(call, 300, 12, make, self.digipeaters[1])

    def _club(self) -> list[Actor]:
        home, club = self.call("Q1ABC"), self.call("Q1CLB")

        def objects(name: str, symbol: str, comment: str, east: float, north: float) -> Callable[[datetime], list[ax25.Frame]]:
            lat, lon = self.where(east, north)
            return lambda now: [air(club, object_report(name_of(name, self.seed), now, lat, lon, symbol, comment))]

        def text(call: str, info: bytes) -> Callable[[datetime], list[ax25.Frame]]:
            return lambda now: [air(call, info)]

        return [
            Actor(club, 600, 17, objects("FIELDDAY", "/;", "Field day on Saturday at 10:00", 4.6, 3.9)),
            Actor(club, 600, 23, objects("PARKING", "/P", "Parking, free at weekends", -2.0, 0.2)),
            Actor(club, 1200, 28, text(club, bulletin("BLN1", "Net on Thursday at 20:00 on 145.500 MHz, all welcome"))),
            Actor(home, 900, 21, text(home, status("Listening on 144.800 MHz"))),
        ]
