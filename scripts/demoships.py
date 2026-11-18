"""Made-up ships for the map's layers of the demo daemon (scripts/demotraffic.py, scripts/demo-daemon --traffic): Fintraffic's two answers (`/api/ais/v1/locations`, GeoJSON, and `/api/ais/v1/vessels`, a list) with
eight ships off Helsinki, and an own AIS receiver, a TCP server on 127.0.0.1:7392 that sends `!AIVDM` lines of types 1, 5, 18 and 24 for six ships once a second.

The ships sail circles round a point of their own and move between two answers; one of each set lies at anchor (the diamond: it says no heading). Pure code but for `serve`, which is the receiver."""
import math
import socketserver
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

HOST = "127.0.0.1"
AIS_PORT = 7392
SEA = (60.12, 24.97)                              # the Gulf of Finland off Helsinki
KM_PER_DEG_LAT = 111.2
STATIC_EVERY_SEC = 10                             # what a ship says of itself is sent this often (and at once on a connection)


@dataclass(frozen=True)
class Craft:
    """One made-up ship: it sails a circle of `radius_km` round a point `north_km` and `east_km` from the sea's middle, once in `period_sec` (negative: the other way round); radius 0 is at anchor."""
    mmsi: int
    name: str
    kind: int
    destination: str
    north_km: float
    east_km: float
    radius_km: float
    period_sec: float
    class_b: bool = False

    def at(self, t: float) -> tuple[float, float]:
        angle = 2 * math.pi * t / self.period_sec + self.mmsi % 7
        north, east = self.north_km + self.radius_km * math.cos(angle), self.east_km + self.radius_km * math.sin(angle)
        return SEA[0] + north / KM_PER_DEG_LAT, SEA[1] + east / (KM_PER_DEG_LAT * math.cos(math.radians(SEA[0])))

    def motion(self, t: float) -> tuple[float, float]:
        """Speed in knots and course in degrees; (0, 0) at anchor."""
        if self.radius_km == 0:
            return 0.0, 0.0
        (la, lo), (lb, lb2) = self.at(t), self.at(t + 1.0)
        north, east = (lb - la) * KM_PER_DEG_LAT, (lb2 - lo) * KM_PER_DEG_LAT * math.cos(math.radians(la))
        return round(math.hypot(north, east) * 3600 / 1.852, 1), round(math.degrees(math.atan2(east, north)) % 360, 1)


CRAFT = (
    Craft(230111000, "FINLANDIA", 60, "TALLINN", 5, 5, 8, 900),
    Craft(230222000, "AURA", 70, "ROSTOCK", -8, 12, 10, -1200),
    Craft(230333000, "BOTNIA", 80, "HELSINKI", 12, -10, 6, 700),
    Craft(230444000, "SEA LARK", 37, "", -4, -6, 3, 500, class_b=True),
    Craft(230555000, "ULLA", 30, "PORVOO", 15, 20, 9, -800),
    Craft(230666000, "WAVE RIDER", 36, "", 0, 0, 0, 1, class_b=True),
    Craft(230777000, "HAMINA", 70, "KOTKA", -15, -20, 0, 1),
    Craft(230888000, "TOLLO", 52, "HELSINKI", 20, -25, 5, 600),
)
AT_SEA = CRAFT[:6]                                # the six that the receiver sends (one at anchor: WAVE RIDER)


def locations(t: float) -> dict[str, Any]:
    """Fintraffic's `/locations` at the time t (seconds since 1970)."""
    features = []
    for ship in CRAFT:
        lat, lon = ship.at(t)
        knots, course = ship.motion(t)
        features.append({"mmsi": ship.mmsi, "type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                         "properties": {"mmsi": ship.mmsi, "sog": knots, "cog": course, "navStat": 1 if knots == 0 else 0, "heading": 511 if knots == 0 else round(course), "timestampExternal": int(t * 1000)}})
    return {"type": "FeatureCollection", "dataUpdatedTime": "2026-11-18T12:00:00Z", "features": features}


def vessels(t: float) -> list[dict[str, Any]]:
    """Fintraffic's `/vessels`."""
    return [{"mmsi": ship.mmsi, "name": ship.name, "shipType": ship.kind, "destination": ship.destination, "callSign": "OHX", "timestamp": int(t * 1000)} for ship in CRAFT]


# ---- AIS sentences (the encoder of what a receiver would send)

def _bits(fields: list[tuple[int, int]]) -> str:
    return "".join(format(value & ((1 << width) - 1), f"0{width}b") for value, width in fields)


def _text(value: str, chars: int) -> list[tuple[int, int]]:
    return [(ord(c) - 64 if ord(c) >= 64 else ord(c), 6) for c in value.upper().ljust(chars, "@")[:chars]]


def _sentences(fields: list[tuple[int, int]], seq: int) -> list[str]:
    bits = _bits(fields)
    fill = (-len(bits)) % 6
    bits += "0" * fill
    data = "".join(chr((code := int(bits[at:at + 6], 2)) + (48 if code < 40 else 56)) for at in range(0, len(bits), 6))
    pieces = [data[at:at + 40] for at in range(0, len(data), 40)]
    out = []
    for number, piece in enumerate(pieces, 1):
        body = f"AIVDM,{len(pieces)},{number},{seq if len(pieces) > 1 else ''},B,{piece},{fill if number == len(pieces) else 0}"
        total = 0
        for char in body:
            total ^= ord(char)
        out.append(f"!{body}*{total:02X}")
    return out


def position_lines(ship: Craft, t: float) -> list[str]:
    lat, lon = ship.at(t)
    knots, course = ship.motion(t)
    heading = 511 if knots == 0 else round(course) % 360
    fields = [(round(knots * 10), 10), (0, 1), (round(lon * 600000), 28), (round(lat * 600000), 27), (round(course * 10), 12), (heading, 9), (60, 6)]
    if ship.class_b:
        return _sentences([(18, 6), (0, 2), (ship.mmsi, 30), (0, 8), *fields, (0, 2), (0, 8)], 0)
    return _sentences([(1, 6), (0, 2), (ship.mmsi, 30), (1 if knots == 0 else 0, 4), (0, 8), *fields, (0, 2), (0, 3), (0, 1), (0, 19)], 0)


def static_lines(ship: Craft, seq: int) -> list[str]:
    if ship.class_b:
        head = [(24, 6), (0, 2), (ship.mmsi, 30)]
        return [*_sentences([*head, (0, 2), *_text(ship.name, 20), (0, 8)], 0), *_sentences([*head, (1, 2), (ship.kind, 8), *_text("SAAB", 7), *_text("OH1X", 7), (0, 30), (0, 6)], 0)]
    return _sentences([(5, 6), (0, 2), (ship.mmsi, 30), (0, 2), (9316983, 30), *_text("OHX", 7), *_text(ship.name, 20), (ship.kind, 8), (0, 30), (1, 4), (0, 20), (68, 8),
                       *_text(ship.destination, 20), (0, 1), (0, 1)], seq)


class Receiver(socketserver.BaseRequestHandler):
    """One connection of the made-up AIS receiver: what each ship says of itself at once and every ten seconds, and every ship's position every second, until the other end closes."""

    def handle(self) -> None:
        sent = 0
        try:
            while True:
                t = time.time()
                lines = [line for ship in AT_SEA for line in position_lines(ship, t)]
                if sent % STATIC_EVERY_SEC == 0:
                    lines = [line for n, ship in enumerate(AT_SEA) for line in static_lines(ship, n % 10)] + lines
                self.request.sendall("".join(line + "\r\n" for line in lines).encode())
                sent += 1
                time.sleep(1.0)
        except OSError:
            pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True


def serve(port: int) -> Server | None:
    """The made-up receiver listening on the port of this computer, in a thread of its own; None when the port is in use (said on standard error)."""
    try:
        server = Server((HOST, port), Receiver)
    except OSError as e:
        print(f"demotraffic: refused: the port {port} of this computer is in use ({e.strerror}); stop what listens there", file=sys.stderr)
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
