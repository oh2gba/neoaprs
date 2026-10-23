"""A day on the air for the screenshots and the project page: a made-up neighbourhood in the Helsinki area, played through a real daemon, so that every number the page shows is what the daemon computed.

`DemoRadio` is a KISS TNC on a TCP port of the loopback (like `neoaprs replay`, which plays the bundled TH-D7 capture, and which this scene starts with); nothing here opens a serial port or sends anything but to that port.
`history(...)` runs a daemon (the Controller) in this process on a clock that is moved back in time: stations moving along their roads, two weather stations reporting for 24 hours, messages that are acked, retried
or fail, a bulletin board, email through the gateway, our own beacon, and our own objects, items and bulletins (made with the daemon's own services, on the air by their own schedule as the clock moves). The daemon is stopped afterwards and the data folder holds the day; `scripts/screenshots.py` then starts a daemon of its own on it.

Every call except the sample capture's is made up (`OH2Zxx`, a range nobody holds); the places are real, the movements are not.
"""
import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from neoaprs import ax25, kiss
from neoaprs.aprsmessage import format_ack, format_message
from neoaprs.clock import utcnow
from neoaprs.controller import Controller
from neoaprs.message import MessageRecord
from neoaprs.source import Source

HOST = "127.0.0.1"
ME = "OH2GBA"
HOME = (60.2231, 24.7152)                              # Espoo
SAMPLE = Path(__file__).resolve().parent.parent / "neoaprs" / "samples" / "thd7.kiss"
PATH = "WIDE1-1,WIDE2-1"


class DemoRadio:
    """A TNC on a TCP port of the loopback: `feed` sends KISS bytes to whoever is connected (kept until someone is), what the daemon writes is decoded into `sent`."""

    def __init__(self) -> None:
        self.port = 0
        self.sent: list[ax25.Frame] = []
        self.on_frame: Callable[[ax25.Frame], None] | None = None       # called with each frame the daemon writes (the air's answer to it)
        self._clients: list[asyncio.StreamWriter] = []
        self._pending = bytearray()
        self._server: asyncio.Server | None = None

    @property
    def url(self) -> str:
        return f"socket://{HOST}:{self.port}"

    async def start(self, preferred: int = 8001) -> None:
        """Listens on `preferred` (Direwolf's KISS port, which is what the settings then show) when it is free, else on any free port."""
        try:
            self._server = await asyncio.start_server(self._serve, HOST, preferred)
        except OSError:
            self._server = await asyncio.start_server(self._serve, HOST, 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.append(writer)
        if self._pending:
            writer.write(bytes(self._pending))
            self._pending.clear()
        decoder = kiss.KissDecoder()
        try:
            while data := await reader.read(4096):
                for f in decoder.feed(data):
                    try:
                        frame = ax25.decode(f.payload)
                    except ax25.Ax25Error:
                        continue
                    self.sent.append(frame)
                    if self.on_frame is not None:
                        self.on_frame(frame)
        except OSError:
            pass
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            writer.close()

    def feed(self, data: bytes) -> None:
        if not self._clients:
            self._pending.extend(data)
            return
        for client in self._clients:
            client.write(data)

    @property
    def connected(self) -> bool:
        return bool(self._clients)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        for client in list(self._clients):
            client.close()
        if self._server is not None:
            await self._server.wait_closed()


def on_air(source: str, info: bytes, path: str = "WIDE1-1", destination: str = "APRS") -> bytes:
    """A frame from `source` as the TNC hands it over; a star on a digipeater says the frame went through it, none says it came direct."""
    return kiss.encode(ax25.encode(ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path.split(",") if p), info=info)))


def _dm(value: float, degrees_width: int, plus: str, minus: str) -> str:
    sign = plus if value >= 0 else minus
    value = abs(value)
    whole = int(value)
    minutes = (value - whole) * 60
    return f"{whole:0{degrees_width}d}{minutes:05.2f}{sign}"


def position(lat: float, lon: float, symbol: str, comment: str = "", course: int | None = None, knots: float | None = None) -> bytes:
    """An uncompressed position without time stamp: `!6012.34N/02456.78E>090/012comment`."""
    motion = f"{course % 360:03d}/{int(round(knots or 0)):03d}" if course is not None else ""
    return f"!{_dm(lat, 2, 'N', 'S')}{symbol[0]}{_dm(lon, 3, 'E', 'W')}{symbol[1]}{motion}{comment}".encode()


def weather_report(lat: float, lon: float, comment: str, direction: int, wind_kmh: float, gust_kmh: float, temp_c: float, rain_mm_h: float, rain_24h_mm: float, rain_today_mm: float,
                   humidity: int, hpa: float) -> bytes:
    """A position with the weather symbol and its fields (wind in mph, temperature in degrees F, rain in hundredths of an inch, pressure in tenths of a hPa)."""
    def mph(kmh: float) -> int:
        return int(round(kmh / 1.609344))

    def hundredths(mm: float) -> int:
        return int(round(mm / 0.254))

    temp_f = int(round(temp_c * 9 / 5 + 32))
    temp = f"t{temp_f:03d}" if temp_f >= 0 else f"t-{-temp_f:02d}"
    fields = f"{direction % 360:03d}/{mph(wind_kmh):03d}g{mph(gust_kmh):03d}{temp}r{hundredths(rain_mm_h):03d}p{hundredths(rain_24h_mm):03d}P{hundredths(rain_today_mm):03d}h{humidity % 100:02d}b{int(round(hpa * 10)):05d}"
    return f"!{_dm(lat, 2, 'N', 'S')}/{_dm(lon, 3, 'E', 'W')}_{fields}{comment}".encode()


def along(points: list[tuple[float, float]], count: int) -> list[tuple[float, float, int]]:
    """`count` places spread evenly along a line through `points`, each with the course (degrees) of the stretch it is on."""
    def leg(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(b[0] - a[0], (b[1] - a[1]) * math.cos(math.radians(a[0])))

    legs = [leg(a, b) for a, b in zip(points, points[1:])]
    total = sum(legs)
    out = []
    for i in range(count):
        left = total * i / (count - 1)
        for (a, b), length in zip(zip(points, points[1:]), legs):
            if left <= length or b == points[-1]:
                f = min(1.0, left / length)
                course = int(math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(a[0])), b[0] - a[0]))) % 360
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, course))
                break
            left -= length
    return out


class Clock:
    """The daemon's clock, set `minutes` before the real time."""

    def __init__(self) -> None:
        self.shift = timedelta(0)

    def __call__(self) -> datetime:
        return utcnow() + self.shift

    def ago(self, minutes: float) -> None:
        self.shift = -timedelta(minutes=minutes)


@dataclass
class Event:
    ago: float                                                   # minutes before now
    action: Callable[["Scene"], Awaitable[None]]


class Scene:
    """The daemon, its clock and its radio, with the verbs the day is written in."""

    def __init__(self, ctl: Controller, radio: DemoRadio, clock: Clock) -> None:
        self.ctl, self.radio, self.clock = ctl, radio, clock
        self.heard_back: dict[str, list[tuple[str, ...]]] = {}        # by the text of a message: for each attempt, the copies the air returns (a path with its stars, or ~IGATE for a copy gated back from the internet)
        self._attempts: dict[bytes, int] = {}
        radio.on_frame = self._air

    def _air(self, frame: ax25.Frame) -> None:
        """What the air does with a message of ours: a digipeater repeats it, as heard with its has-been-repeated bits, and an iGate may put a copy on the air from the internet. Acks are not repeated."""
        body = frame.info
        if str(frame.source) != ME or not body.startswith(b":") or body[11:14] in (b"ack", b"rej"):
            return
        number = self._attempts[body] = self._attempts.get(body, 0) + 1
        plan = self.heard_back.get(body[11:].split(b"{")[0].decode(), [("OH2RCH-2*,WIDE2-1",)])
        for copy in plan[min(number, len(plan)) - 1]:
            if copy.startswith("~"):
                gate = copy[1:]
                inner = f"{ME}>{frame.destination},TCPIP,{gate}*:".encode()
                self.radio.feed(on_air(gate, b"}" + inner + body, ""))
            else:
                self.radio.feed(on_air(ME, body, copy, str(frame.destination)))

    async def hear(self, source: str, info: bytes, path: str = "OH2RCH-2*") -> None:
        before = self.ctl.tnc.stats.packets
        self.radio.feed(on_air(source, info, path))
        await _until(lambda: self.ctl.tnc.stats.packets > before)

    async def hear_frames(self, data: bytes) -> None:
        count = len(kiss.KissDecoder().feed(data))
        before = self.ctl.tnc.stats.packets
        self.radio.feed(data)
        await _until(lambda: self.ctl.tnc.stats.packets >= before + count)

    async def say_to_me(self, source: str, text: str, msg_id: str, path: str = "OH2RCH-2*") -> None:
        await self.hear(source, b":" + format_message(ME, text, msg_id), path)

    async def send(self, to: str, text: str, ack_after_sec: float | None = 6, ack_path: str = "OH2RCH-2*", tries: int = 1, wrap: str | None = None,
                   heard: list[tuple[str, ...]] | None = None) -> None:
        """We send a message; the other station acks it after some seconds of the clock, at our `tries`th transmission, or never (None: the attempts run out and it fails)."""
        if heard is not None:
            self.heard_back[text] = heard
        record = await self.ctl.messaging.send(to, text)
        await asyncio.sleep(0.15)                                  # (the first attempt is on the air, and its copy is heard, before the clock moves)
        assert record.msg_id is not None
        number = record.id

        def current() -> MessageRecord:
            held = self.ctl.messaging.get(number)
            assert held is not None
            return held

        if ack_after_sec is None:
            while current().state == "sending":
                self.clock.shift += timedelta(minutes=2)
                await asyncio.sleep(0.12)
            return
        for attempt in range(2, tries + 1):
            self.clock.shift += timedelta(minutes=2)
            await _until(lambda attempt=attempt: current().attempts >= attempt)
            await asyncio.sleep(0.15)
        self.clock.shift += timedelta(seconds=ack_after_sec)
        info = b":" + format_ack(ME, record.msg_id)
        if wrap:
            await self.hear(wrap, b"}" + to.encode() + b">APRS,TCPIP," + wrap.encode() + b"*:" + info, "")
        else:
            await self.hear(to, info, ack_path)
        await _until(lambda: current().state == "acked")


    def own_due(self) -> bool:
        """Is an object or a bulletin of ours due, or being sent (by the clock of the day)?"""
        now = self.clock()
        due = [self.ctl.ownobjects.next_at(o.name) for o in self.ctl.ownobjects.records()] + [self.ctl.ownbulletins.next_at(b.slot) for b in self.ctl.ownbulletins.records()]
        return any(when is not None and when <= now for when in due)

    async def own_object(self, name: str, kind: str, lat: float, lon: float, symbol: str, comment: str, path: str | None = None) -> None:
        """We make an object or an item (the Objects tab's `object_set`); it is on the air once this returns."""
        self.ctl.ownobjects.set(name, kind, lat, lon, symbol[0], symbol[1], comment, path=path)
        await _until(lambda: (held := self.ctl.ownobjects.get(name)) is not None and held.sent >= 1)

    async def own_bulletin(self, slot: str, text: str) -> None:
        """We post a bulletin or an announcement (the Bulletins tab's `bulletin_post`); it is on the air once this returns."""
        self.ctl.ownbulletins.post(slot, text)
        await _until(lambda: (held := self.ctl.ownbulletins.get(slot)) is not None and held.sent >= 1)

    async def keep_schedule(self) -> None:
        """Lets what is due of ours go out before the clock moves on, so that each has been sent as often as its schedule says (the decay of an object, the early copies of a bulletin)."""
        await _until(lambda: not self.own_due(), 20)


async def _until(condition: Callable[[], object], timeout_sec: float = 8.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("the daemon did not take what the radio said")
        await asyncio.sleep(0.01)


# ---- the day

def _weather_station(call: str, lat: float, lon: float, comment: str, base_c: float, base_hpa: float, local_hour_now: float, path: str) -> list[Event]:
    """24 hours of reports every 10 minutes: the temperature follows the sun, the pressure sinks and a front brings rain and wind some hours ago."""
    events: list[Event] = []
    rain_total = 0.0
    for step in range(144, 0, -1):
        ago = step * 10 - 5
        hour = (local_hour_now - ago / 60) % 24
        temp = base_c + 3.2 * math.sin((hour - 9) / 24 * 2 * math.pi) - (0.8 if 5 < ago / 60 < 9 else 0) + 0.15 * math.sin(step * 1.7)
        front = math.exp(-((ago / 60 - 7.0) / 2.2) ** 2)                                       # the front passed 7 hours ago
        rain = round(max(0.0, 2.4 * front - 0.25 + 0.15 * math.sin(step * 2.3)), 1)
        rain_total += rain / 6
        hpa = base_hpa + 6.5 * (1 - ago / 1440) - 3.0 * front + 0.2 * math.sin(step / 5)
        wind = 6 + 14 * front + 2.5 * math.sin(step / 3.1)
        gust = wind * 1.7 + 2
        direction = int(215 - 60 * front + 8 * math.sin(step / 4))
        humidity = int(min(99, 72 + 22 * front + 8 * math.sin((hour - 3) / 24 * 2 * math.pi) * -1))
        info = weather_report(lat, lon, comment, direction, max(wind, 0.5), gust, temp, rain * 3, rain_total, rain_total * 0.7, humidity, hpa)
        events.append(Event(ago, lambda s, c=call, i=info: s.hear(c, i, path)))
    return events


def _mover(call: str, symbol: str, comment: str, points: list[tuple[float, float]], count: int, start_ago: float, end_ago: float, knots: float, path: str) -> list[Event]:
    events = []
    for i, (lat, lon, course) in enumerate(along(points, count)):
        ago = start_ago + (end_ago - start_ago) * i / (count - 1)
        info = position(lat, lon, symbol, comment, course, knots)
        events.append(Event(ago, lambda s, c=call, f=info, p=path: s.hear(c, f, p)))
    return events


def _fixed(call: str, ago: float, symbol: str, lat: float, lon: float, comment: str, path: str = "OH2RCH-2*", repeats: int = 1, every: float = 30) -> list[Event]:
    info = position(lat, lon, symbol, comment)
    return [Event(ago + i * every, lambda s: s.hear(call, info, path)) for i in range(repeats)]


def _text(source: str, ago: float, text: str, msg_id: str, path: str = "OH2RCH-2*") -> Event:
    return Event(ago, lambda s: s.say_to_me(source, text, msg_id, path))


def _out(ago: float, to: str, text: str, **options: object) -> Event:
    return Event(ago, lambda s: s.send(to, text, **options))     # type: ignore[arg-type]


def _gateway(ago: float, text: str, msg_id: str, igate: str = "OH2ZIG-10") -> Event:
    """A message from the email gateway EMAIL-2 to us, put on the air by an iGate as a third-party frame."""
    return Event(ago, lambda s: s.hear(igate, b"}EMAIL-2>APRS,TCPIP," + igate.encode() + b"*:" + b":" + format_message(ME, text, msg_id), ""))


def _board(source: str, ago: float, slot: str, text: str, path: str = "OH2RCH-2*") -> Event:
    return Event(ago, lambda s: s.hear(source, b":" + format_message(slot, text), path))


async def _path_of_the_partner(s: Scene) -> None:
    """Messages to the friend go by a path of their own: the digipeater next door, then the one on the hill that our radio does not hear."""
    await s.ctl.prefbook.set_path("OH2ZPK", "OH2RCH-2,OH2RDG")


def events(local_hour_now: float) -> list[Event]:
    day: list[Event] = []
    # The stations of the sample capture: three digipeaters/stations of Kirkkonummi, Helsinki and Sipoo, and a D-STAR node
    day.append(Event(1380, lambda s: s.hear_frames(SAMPLE.read_bytes())))
    day.append(Event(1370, _path_of_the_partner))
    day += _fixed("OH2RDG", 25, "N#", 60.1245, 24.4970, "PHG8470/R,W,T,Wn,Tn Kirkkonummi", repeats=6, every=35)
    day += _fixed("OH2RDS", 47, "N#", 60.2777, 25.2543, "PHG8470/R,W,T,Wn,Tn Sipoo", repeats=5, every=40)
    day += _fixed("OH2RCH-2", 9, "/#", 60.2000, 24.9600, "PHG7470/W2 Helsinki Kumpula digi", path="", repeats=8, every=20)
    day += _fixed("OH2RDK-7", 63, "/&", 60.1650, 24.9467, "432.500 MHz", repeats=4, every=50)
    day += _fixed("OH2ZIG-10", 18, "/&", 60.4030, 25.0970, "RX iGate Tuusula", path="OH2RCH-2*,OH2RDK-7*", repeats=5, every=25)
    day += _fixed("OH2ZPK", 36, "/-", 60.2934, 25.0378, "Jari, Vantaa, 2 m net Tue 20:00", path="OH2RCH-2*", repeats=5, every=75)
    day += _fixed("OH2ZVT-7", 330, "/>", 60.4160, 24.3220, "Vihti, parked", path="OH2RDG*", repeats=2, every=20)
    day += _fixed("OH2RDG-3", 41, "/r", 60.1330, 24.5240, "Kirkkonummi 145.650 repeater", path="OH2RDG*", repeats=2, every=60)
    # Two weather stations, 24 hours of reports each
    day += _weather_station("OH2ZWA", 60.1840, 24.8280, "Otaniemi WX", 6.4, 1015.0, local_hour_now, "OH2RCH-2*")
    day += _weather_station("OH2ZWB", 59.9770, 24.4210, "Porkkala WX", 7.4, 1014.0, local_hour_now, "")
    # Stations on the move
    day += _mover("OH2ZMA-9", "/>", "Pekka on the road", [(60.1180, 24.4350), (60.1330, 24.5600), (60.1490, 24.6450), (60.1610, 24.7300), (60.1700, 24.7900), (60.1660, 24.8450), (60.1640, 24.8800)], 26, 100, 4, 46, "OH2RCH-2*")
    day += _mover("OH3ZHK-7", "/[", "Hiking in Nuuksio", [(60.3100, 24.5000), (60.3140, 24.5060), (60.3180, 24.5040), (60.3215, 24.5120), (60.3240, 24.5200)], 14, 115, 8, 2, "WIDE1-1")
    day += _mover("OH2ZSV-5", "/Y", "s/y Tuuli, Gulf of Finland", [(60.0600, 24.7000), (60.0800, 24.8200), (60.1050, 24.9100), (60.1250, 24.9650)], 20, 300, 12, 6, "OH2RCH-2*")
    day += _mover("OH2ZBK-8", "/b", "Rannikkoreitti", [(60.1800, 24.6200), (60.1840, 24.6600), (60.1900, 24.7000)], 10, 70, 28, 7, "OH2RCH-2*")
    # Messages
    day.append(_out(1000, "OH2ZXA", "Hello, are you there?", ack_after_sec=None,
                    heard=[("OH2RCH-2*,WIDE2-1", "~OH2ZIG-10"), (), ("OH2RCH-2*,WIDE2-1",), (), (), ()]))
    day.append(_text("OH2ZMA-9", 300, "Test from the car, do you copy?", "07"))
    day.append(_out(298, "OH2ZMA-9", "Copy 5/9, you show on the map", ack_after_sec=5))
    day.append(Event(240, lambda s: s.hear("OH2ZMA-9", b":" + format_message("OH2ZPK", "Moi Jari, tonight at 20?", "03"), "OH2RCH-2*")))
    day.append(_text("OH2ZPK", 190, "Moi John! Are you QRV on the 2 m net tonight?", "41", "OH2RCH-2*"))
    day.append(_out(175, "OH2ZPK", "Moi Jari! Yes, 144.800 at 20:00", ack_after_sec=7, heard=[("OH2RCH-2*,OH2RDG*",)]))
    day.append(_text("OH2ZPK", 160, "Great. I take the TH-D7 to the lake on Saturday", "42", "OH2RCH-2*,OH2RDK-7*"))
    day.append(_out(150, "OH2ZPK", "Nice! Beacon every 5 min so I can follow you on the map", ack_after_sec=8, ack_path="OH2RDG*", tries=2,
                    heard=[(), ("OH2RCH-2*,OH2RDG",)]))
    day.append(_text("OH3ZHK-7", 95, "At the Nuuksio car park, 3 km to the lookout", "17", "WIDE1-1"))
    day.append(_out(90, "OH3ZHK-7", "Enjoy! Send a position from the top", ack_after_sec=9, ack_path=""))
    day.append(_text("OH2ZPK", 40, "Heading out now, my signal is on the map soon", "43", "OH2RCH-2*"))
    day.append(_out(38, "OH2ZPK", "73, have a good trip!", ack_after_sec=6, heard=[("OH2RCH-2*,OH2RDG",)]))
    day.append(_text("OH3ZHK-7", 20, "Lookout reached, 144.800 loud and clear here", "18", "WIDE1-1"))
    day.append(_out(12, "OH2ZPK", "Did you get the new antenna up?", ack_after_sec=10, heard=[("OH2RCH-2*,OH2RDG*",)]))
    day.append(_text("OH2ZPK", 6, "Yes! 5 dB more on 2 m, will tell you tonight", "44", "OH2RCH-2*,OH2RDK-7*"))
    # Email through the gateway: its acks and replies come as third-party frames from an iGate. One mail never gets its ack (it shows "Not confirmed"), and the gateway forwards a mail to us
    day.append(_out(300, "EMAIL-2", "me jane@example.com", ack_after_sec=12, wrap="OH2ZIG-10", ack_path=""))
    day.append(_gateway(298, "Shortcut me set to jane@example.com", "g1"))
    day.append(_out(250, "EMAIL-2", "me New antenna is up: 5 dB more on 2 m!", ack_after_sec=None))
    day.append(_out(150, "EMAIL-2", "me Back at the shack by 18, QRV on 2 m", ack_after_sec=14, wrap="OH2ZIG-10", ack_path=""))
    day.append(_out(100, "EMAIL-2", "get", ack_after_sec=9, wrap="OH2ZIG-10", ack_path=""))
    day.append(_gateway(97, "jane@example.com Great, see you at the net tonight! 73 Jane", "g2"))
    day.append(_out(14, "EMAIL-2", "bob@example.org Hamfest in Espoo on Saturday 10:00, see you there", ack_after_sec=11, wrap="OH2ZIG-10", ack_path=""))
    day.append(_gateway(8, "Msg sent to bob@example.org", "g3"))
    # The message board
    day.append(_board("OH2ZIG-10", 250, "BLN1", "2 m net every Tuesday 20:00 on 144.800 MHz FM, all welcome"))
    day.append(_board("OH2ZPK", 130, "BLNA", "Strong winds on the coast tonight, check your antennas"))
    day.append(_board("OH2RDS", 100, "QST", "QST de OH2RDS: the digi is back on the air after antenna work"))
    day.append(_board("OH2ZMA-9", 33, "BLN3HAMS", "Hamfest in Espoo on Saturday 10:00, talk-in 145.500"))
    # Our own beacon and status
    day.append(Event(40, lambda s: _send_beacon(s)))
    # Objects, items and bulletins of our own: a net-control point, a meeting place for Saturday and an item for the hamfest, and two on the board
    day.append(Event(171, lambda s: s.own_bulletin("BLN2", "2 m net tonight 20:00 on 144.800 MHz, net control OH2GBA")))
    day.append(Event(92, lambda s: s.own_object("NETCTRL", "object", 60.2208, 24.8085, "/-", "2 m net Tue 20:00, 144.800 MHz")))
    day.append(Event(68, lambda s: s.own_object("HAMFEST", "item", 60.2052, 24.6720, "/K", "Hamfest Sat 10:00, talk-in 145.500")))
    day.append(Event(53, lambda s: s.own_bulletin("BLNL", "Field day at the lake on Saturday 10:00, see item MEETSPOT")))
    day.append(Event(27, lambda s: s.own_object("MEETSPOT", "item", 60.1585, 24.7110, "/;", "Meeting place, car park by the shore")))
    return sorted(day, key=lambda e: -e.ago)


async def _send_beacon(s: Scene) -> None:
    """Our beacon goes out, and the digipeater is heard repeating it a minute later (which is when our own station is last heard)."""
    before = len(s.radio.sent)
    assert s.ctl.beacon.send_now("timer"), s.ctl.beacon.problem
    await _until(lambda: len(s.radio.sent) > before)
    frame = s.radio.sent[-1]
    s.clock.shift += timedelta(minutes=1)
    heard = ax25.Frame(frame.destination, frame.source, (ax25.Address.parse("OH2RCH-2*"),), info=frame.info)
    s.radio.feed(kiss.encode(ax25.encode(heard)))
    await asyncio.sleep(0.3)


async def history(data_dir: Path, radio: DemoRadio) -> int:
    """Plays the day through a daemon on `data_dir` (its settings are in the database already) and stops it; how many events were played."""
    os.environ["NEOAPRS_UPDATE_CHECK"] = "0"                    # (a made-up day: the daemon does not ask the version page)
    local = datetime.now(timezone(timedelta(hours=3)))          # (Finland in the summer time of October)
    local_hour_now = local.hour + local.minute / 60
    clock = Clock()
    clock.ago(1450)
    ctl = Controller(data_dir, clock=clock, port=radio.url)
    ctl.messaging.tick_sec = 0.03
    ctl.ownobjects.tick_sec = ctl.ownbulletins.tick_sec = 0.03   # (our own objects and bulletins go out as soon as the moved clock says so, a few frames of the day in a second)
    ctl.sender.spacing_sec = 0.2
    await ctl.start()
    await _until(lambda: ctl.tnc.state is Source.State.CONNECTED and radio.connected, 30)
    await asyncio.sleep(3.5)                                    # (the TNC settles after the open)
    scene = Scene(ctl, radio, clock)
    played = 0
    for event in events(local_hour_now):
        clock.ago(event.ago)
        await event.action(scene)
        await scene.keep_schedule()
        played += 1
    await asyncio.sleep(0.5)
    assert ctl.db is not None
    await ctl.db.barrier()
    await ctl.stop()
    return played
