#!/usr/bin/env python3
"""Made-up traffic for the demo daemon's map layers (scripts/demo-daemon --traffic).

An HTTP server on 127.0.0.1:7391 answers an own receiver's aircraft file, a Radarcape's list, the
two aircraft services' paths and Fintraffic's two ship paths, with sixteen aircraft flying circles
round the demo's Espoo and eight ships (scripts/demoships.py); an own AIS receiver listens on
127.0.0.1:7392. The aircraft cover every kind of mark: ground, emergency, no track, no flight,
climbing and descending, and each emitter category.

  scripts/demotraffic.py [--port PORT] [--ais-port PORT]

Once it listens it writes one line on standard output (what demo-daemon waits for) and one on
standard error saying what to type in Settings, Map. A port in use is a refusal (exit 2)."""

import argparse
import json
import math
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import demoships

HOST = "127.0.0.1"
PORT = 7391
CENTRE = (60.2231, 24.7152)  # the demo's station (scripts/demoscene.py)
KM_PER_DEG_LAT = 111.2
# The first place the daemon tries (layerthing.py AIRCRAFT_PLACES).
RECEIVER_PATH = "/tar1090/data/aircraft.json"
# A Radarcape's list (layerthing.py RADARCAPE_PLACE).
RADARCAPE_PATH = "/aircraftlist.json"
SERVICE_PATH = re.compile(r"^/(api/v3|v2)/lat/-?\d+(\.\d+)?/lon/-?\d+(\.\d+)?/dist/\d+$")


@dataclass(frozen=True)
class Flight:
    """One made-up aircraft flying a circle of `radius_km` round a point offset from the centre.

    `period_sec` is one lap (negative: the other way)."""

    hex: str
    north_km: float
    east_km: float
    radius_km: float
    period_sec: float
    feet: int | str
    fields: tuple[tuple[str, Any], ...] = ()
    track: bool = True

    def at(self, t: float) -> tuple[float, float]:
        angle = 2 * math.pi * t / self.period_sec + int(self.hex[-2:], 16)
        north, east = self.north_km + self.radius_km * math.cos(angle), self.east_km + self.radius_km * math.sin(angle)
        return CENTRE[0] + north / KM_PER_DEG_LAT, CENTRE[1] + east / (
            KM_PER_DEG_LAT * math.cos(math.radians(CENTRE[0]))
        )

    def row(self, t: float) -> dict[str, Any]:
        lat, lon = self.at(t)
        later = self.at(t + 1.0)
        north = (later[0] - lat) * KM_PER_DEG_LAT
        east = (later[1] - lon) * KM_PER_DEG_LAT * math.cos(math.radians(lat))
        knots = math.hypot(north, east) * 3600 / 1.852
        row: dict[str, Any] = {
            "hex": self.hex,
            "type": "adsb_icao",
            "alt_baro": self.feet,
            "gs": round(knots, 1),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "seen_pos": 0.3,
            "seen": 0.1,
            "rssi": -18.4,
            "squawk": "2000",
            "emergency": "none",
            "category": "A3",
            **dict(self.fields),
        }
        if self.track:
            row["track"] = round(math.degrees(math.atan2(east, north)) % 360, 1)
        return row


FLIGHTS = (
    Flight(
        "461f2a",
        10,
        15,
        25,
        900,
        8000,
        (
            ("flight", "FIN7AB  "),
            ("r", "OH-LZA"),
            ("t", "A321"),
            ("desc", "AIRBUS A-321"),
            ("category", "A3"),
            ("baro_rate", 1800),
        ),
    ),
    Flight(
        "4601f6",
        -15,
        5,
        20,
        -700,
        3500,
        (("flight", "FIN50A  "), ("r", "OH-ATI"), ("t", "AT75"), ("desc", "ATR-72-500"), ("category", "A2")),
    ),
    Flight(
        "4ab822",
        30,
        -20,
        35,
        1500,
        34000,
        (("flight", "SAS1734 "), ("r", "SE-RJA"), ("t", "A20N"), ("desc", "AIRBUS A-320neo"), ("geom_rate", 0)),
    ),
    Flight(
        "3c4b2f",
        -25,
        40,
        40,
        -1800,
        37000,
        (("flight", "DLH2RT  "), ("r", "D-AINK"), ("t", "A20N"), ("desc", "AIRBUS A-320neo"), ("baro_rate", -2112)),
    ),
    Flight(
        "511a22",
        5,
        -35,
        15,
        600,
        2500,
        (("flight", "ESF31   "), ("r", "ES-PWB"), ("t", "C172"), ("desc", "CESSNA 172 Skyhawk"), ("category", "A1")),
    ),
    Flight(
        "46080c",
        -5,
        -10,
        10,
        400,
        1500,
        (("flight", "OHHEL   "), ("r", "OH-HVA"), ("t", "EC35"), ("desc", "EUROCOPTER EC-135"), ("category", "A7")),
    ),
    Flight(
        "4ca7b1",
        45,
        30,
        30,
        -1200,
        39000,
        (("flight", "RYR8QP  "), ("r", "EI-EBA"), ("t", "B738"), ("desc", "BOEING 737-800")),
    ),
    Flight(
        "440d11",
        -35,
        -30,
        25,
        1100,
        12000,
        (("flight", "AUA7HK  "), ("r", "OE-LBA"), ("t", "A320"), ("desc", "AIRBUS A-320")),
    ),
    # on the ground at the field: never shown
    Flight(
        "4601a9",
        0,
        0,
        0.001,
        3600,
        "ground",
        (("flight", "FIN3GR  "), ("r", "OH-LVA"), ("t", "A319"), ("desc", "AIRBUS A-319"), ("gs", 0.0)),
    ),
    Flight(
        "461e1a",
        20,
        50,
        20,
        800,
        6000,
        (
            ("flight", "FIN9XE  "),
            ("r", "OH-LWB"),
            ("t", "A359"),
            ("desc", "AIRBUS A-350-900"),
            ("squawk", "7700"),
            ("emergency", "general"),
            ("category", "A5"),
        ),
    ),
    # says no track: the diamond
    Flight(
        "4608a3",
        -40,
        10,
        15,
        -900,
        4500,
        (("flight", "NOR77   "), ("r", "OH-NOR"), ("t", "PA28"), ("desc", "PIPER PA-28"), ("category", "A1")),
        track=False,
    ),
    # no flight, only its registration
    Flight(
        "460f11",
        15,
        -50,
        12,
        500,
        3000,
        (("r", "OH-CEX"), ("t", "DA40"), ("desc", "DIAMOND DA-40"), ("category", "A1")),
    ),
    Flight(
        "3c4dd1",
        50,
        -10,
        30,
        1600,
        36000,
        (("flight", "DLH4CX  "), ("r", "D-ABYA"), ("t", "B748"), ("desc", "BOEING 747-8"), ("category", "A5")),
    ),
    Flight(
        "4690b1",
        -20,
        -45,
        4,
        700,
        2500,
        (("flight", "OH829   "), ("r", "OH-829"), ("t", "AS21"), ("desc", "SCHLEICHER ASK-21"), ("category", "B1")),
    ),
    Flight("4690c2", 8, 25, 2, 3000, 1500, (("r", "OH-BAL"), ("t", "BALL"), ("desc", "BALLOON"), ("category", "B2"))),
    Flight("4690d3", -8, 20, 1, 300, 300, (("t", "ZZZZ"), ("desc", "UNMANNED AIRCRAFT"), ("category", "B6"))),
)


def aircraft(t: float) -> list[dict[str, Any]]:
    return [flight.row(t) for flight in FLIGHTS]


def receiver_file(t: float) -> dict[str, Any]:
    """An own receiver's aircraft.json at the time t (seconds since 1970)."""
    return {"now": round(t, 1), "messages": int(t) % 1_000_000, "aircraft": aircraft(t)}


# (departure, destination) codes as a Radarcape lists them: both known, one unknown, one only.
ROUTES_OF_RADARCAPE: dict[str, tuple[str | None, str | None]] = {
    "461f2a": ("ESSA", "EFHK"),
    "4ab822": ("ESXX", "EFHK"),
    "3c4b2f": (None, "EGLL"),
}


def radarcape_row(row: dict[str, Any], t: float) -> dict[str, Any]:
    """Return one aircraft of readsb's form in a Radarcape's form (hex in capitals, A or G,
    `vrt`)."""
    ground = row["alt_baro"] == "ground"
    flight = row.get("flight", "").strip() or None
    alert = row["squawk"] in ("7500", "7600", "7700")
    return {
        "uti": int(t),
        "ns": int(t * 1e9) % 1_000_000_000,
        "hex": row["hex"].upper(),
        "fli": flight,
        "src": "A",
        "ava": "A",
        "lat": row["lat"],
        "lon": row["lon"],
        "alt": 0 if ground else row["alt_baro"],
        "gda": "G" if ground else "A",
        "spd": round(row["gs"]) if "track" in row else None,
        "trk": round(row["track"]) if "track" in row else None,
        "vrt": row.get("baro_rate", row.get("geom_rate")),
        "cat": row.get("category"),
        "org": ROUTES_OF_RADARCAPE.get(row["hex"], (None, None))[0],
        "dst": ROUTES_OF_RADARCAPE.get(row["hex"], (None, None))[1],
        "typ": row.get("t"),
        "reg": row.get("r"),
        "dis": None,
        "squ": row["squawk"],
        "lla": 0,
        "alr": 3 if alert else 0,
    }


def radarcape_list(t: float) -> list[dict[str, Any]]:
    """A Radarcape's aircraftlist.json at the time t."""
    return [radarcape_row(row, t) for row in aircraft(t)]


def service_answer(t: float) -> dict[str, Any]:
    """The answer of adsb.fi or adsb.lol at the time t."""
    ms = int(t * 1000)
    listed = aircraft(t)
    return {"ac": listed, "msg": "No error", "now": ms, "total": len(listed), "ctime": ms, "ptime": 0}


def answer(path: str, t: float) -> Any:
    """What a path answers at the time t; None: not found."""
    if path == RECEIVER_PATH:
        return receiver_file(t)
    if path == RADARCAPE_PATH:
        return radarcape_list(t)
    if SERVICE_PATH.match(path):
        return service_answer(t)
    return None


def ships(path: str, t: float) -> Any:
    """Fintraffic's two paths: the positions (GeoJSON) and the ships' own words (a list)."""
    return (
        demoships.locations(t)
        if path == "/api/ais/v1/locations"
        else demoships.vessels(t)
        if path == "/api/ais/v1/vessels"
        else None
    )


ROUTES: list[Callable[[str, float], Any]] = [answer, ships]  # tried in turn


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        body = next((found for route in ROUTES if (found := route(path, time.time())) is not None), None)
        if body is None:
            self.send_error(404)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass


def serve(port: int) -> ThreadingHTTPServer | None:
    """Return the server listening on the port, or None (said on stderr) if the port is in use."""
    try:
        return ThreadingHTTPServer((HOST, port), Handler)
    except OSError as e:
        print(
            f"demotraffic: refused: the port {port} of this computer is in use ({e.strerror}); stop what listens there",
            file=sys.stderr,
        )
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=PORT, help=f"the HTTP port (default {PORT})")
    parser.add_argument(
        "--ais-port",
        type=int,
        default=demoships.AIS_PORT,
        help=f"the port of the made-up AIS receiver (default {demoships.AIS_PORT})",
    )
    args = parser.parse_args(argv)
    server = serve(args.port)
    if server is None:
        return 2
    receiver = demoships.serve(args.ais_port)
    if receiver is None:
        server.server_close()
        return 2
    print(f"listening on {HOST}:{args.port}", flush=True)
    print(
        f"demotraffic: in Settings, Map, Aircraft, Radarcape or My own receiver: {HOST}:{args.port}; Ships, My own receiver: {HOST}:{args.ais_port}",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        receiver.shutdown()
        receiver.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
