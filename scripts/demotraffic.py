#!/usr/bin/env python3
"""Made-up traffic for the map's layers of the demo daemon (scripts/demo-daemon --traffic), so that the layers can be looked at in the browser pane without a receiver and without asking any service: an HTTP
server on 127.0.0.1:7391 that answers an own aircraft receiver's file (`/tar1090/data/aircraft.json`, readsb's form: `now` in seconds and the list `aircraft`) and the paths of the two aircraft services
(`/api/v3/lat/../lon/../dist/..` of adsb.fi, `/v2/lat/../lon/../dist/..` of adsb.lol: `now` in milliseconds and the list `ac`), which the daemon asks in their place with NEOAPRS_LAYERS_URL=http://127.0.0.1:7391.

Ships as well: Fintraffic's two paths (`/api/ais/v1/locations`, `/api/ais/v1/vessels`) are answered by the same server with eight made-up ships off Helsinki (scripts/demoships.py), and an own AIS receiver listens on
127.0.0.1:7392 and sends `!AIVDM` lines for six of them.

Twelve aircraft fly circles round the demo's Espoo (60.2231 N 24.7152 E) and move each second: one stands on the ground (it must not show), one squawks 7700, one says no track (the diamond), one has no flight, only
its registration.

  scripts/demotraffic.py [--port PORT] [--ais-port PORT]

Once it listens it writes one line on its standard output (what demo-daemon waits for) and one on its standard error that says what to type in Settings, Map for My own receiver. A port in use is a refusal that
says so (exit 2)."""
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
CENTRE = (60.2231, 24.7152)                       # the demo's station (scripts/demoscene.py)
KM_PER_DEG_LAT = 111.2
RECEIVER_PATH = "/tar1090/data/aircraft.json"           # the first place the daemon tries (neoaprs/layerthing.py AIRCRAFT_PLACES)
SERVICE_PATH = re.compile(r"^/(api/v3|v2)/lat/-?\d+(\.\d+)?/lon/-?\d+(\.\d+)?/dist/\d+$")


@dataclass(frozen=True)
class Flight:
    """One made-up aircraft: it flies a circle of `radius_km` round a point `north_km` and `east_km` from the centre, once in `period_sec` (negative: the other way round)."""
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
        return CENTRE[0] + north / KM_PER_DEG_LAT, CENTRE[1] + east / (KM_PER_DEG_LAT * math.cos(math.radians(CENTRE[0])))

    def row(self, t: float) -> dict[str, Any]:
        lat, lon = self.at(t)
        later = self.at(t + 1.0)
        north = (later[0] - lat) * KM_PER_DEG_LAT
        east = (later[1] - lon) * KM_PER_DEG_LAT * math.cos(math.radians(lat))
        knots = math.hypot(north, east) * 3600 / 1.852
        row: dict[str, Any] = {"hex": self.hex, "type": "adsb_icao", "alt_baro": self.feet, "gs": round(knots, 1), "lat": round(lat, 6), "lon": round(lon, 6), "seen_pos": 0.3, "seen": 0.1, "rssi": -18.4,
                               "squawk": "2000", "emergency": "none", "category": "A3", **dict(self.fields)}
        if self.track:
            row["track"] = round(math.degrees(math.atan2(east, north)) % 360, 1)
        return row


FLIGHTS = (
    Flight("461f2a", 10, 15, 25, 900, 8000, (("flight", "FIN7AB  "), ("r", "OH-LZA"), ("t", "A321"), ("desc", "AIRBUS A-321"))),
    Flight("4601f6", -15, 5, 20, -700, 3500, (("flight", "FIN50A  "), ("r", "OH-ATI"), ("t", "AT75"), ("desc", "ATR-72-500"), ("category", "A2"))),
    Flight("4ab822", 30, -20, 35, 1500, 34000, (("flight", "SAS1734 "), ("r", "SE-RJA"), ("t", "A20N"), ("desc", "AIRBUS A-320neo"))),
    Flight("3c4b2f", -25, 40, 40, -1800, 37000, (("flight", "DLH2RT  "), ("r", "D-AINK"), ("t", "A20N"), ("desc", "AIRBUS A-320neo"))),
    Flight("511a22", 5, -35, 15, 600, 2500, (("flight", "ESF31   "), ("r", "ES-PWB"), ("t", "C172"), ("desc", "CESSNA 172 Skyhawk"), ("category", "A1"))),
    Flight("46080c", -5, -10, 10, 400, 1500, (("flight", "OHHEL   "), ("r", "OH-HVA"), ("t", "EC35"), ("desc", "EUROCOPTER EC-135"), ("category", "A7"))),
    Flight("4ca7b1", 45, 30, 30, -1200, 39000, (("flight", "RYR8QP  "), ("r", "EI-EBA"), ("t", "B738"), ("desc", "BOEING 737-800"))),
    Flight("440d11", -35, -30, 25, 1100, 12000, (("flight", "AUA7HK  "), ("r", "OE-LBA"), ("t", "A320"), ("desc", "AIRBUS A-320"))),
    Flight("4601a9", 0, 0, 0.001, 3600, "ground", (("flight", "FIN3GR  "), ("r", "OH-LVA"), ("t", "A319"), ("desc", "AIRBUS A-319"), ("gs", 0.0))),          # on the ground at the field: never shown
    Flight("461e1a", 20, 50, 20, 800, 6000, (("flight", "FIN9XE  "), ("r", "OH-LWB"), ("t", "A359"), ("desc", "AIRBUS A-350-900"), ("squawk", "7700"), ("emergency", "general"))),
    Flight("4608a3", -40, 10, 15, -900, 4500, (("flight", "NOR77   "), ("r", "OH-NOR"), ("t", "PA28"), ("desc", "PIPER PA-28")), track=False),       # says no track: the diamond
    Flight("460f11", 15, -50, 12, 500, 3000, (("r", "OH-CEX"), ("t", "DA40"), ("desc", "DIAMOND DA-40"), ("category", "A1"))),                     # no flight, only its registration
)


def aircraft(t: float) -> list[dict[str, Any]]:
    return [flight.row(t) for flight in FLIGHTS]


def receiver_file(t: float) -> dict[str, Any]:
    """An own receiver's aircraft.json at the time t (seconds since 1970)."""
    return {"now": round(t, 1), "messages": int(t) % 1_000_000, "aircraft": aircraft(t)}


def service_answer(t: float) -> dict[str, Any]:
    """The answer of adsb.fi or adsb.lol at the time t."""
    ms = int(t * 1000)
    listed = aircraft(t)
    return {"ac": listed, "msg": "No error", "now": ms, "total": len(listed), "ctime": ms, "ptime": 0}


def answer(path: str, t: float) -> dict[str, Any] | None:
    """What a path answers at the time t; None: not found."""
    if path == RECEIVER_PATH:
        return receiver_file(t)
    if SERVICE_PATH.match(path):
        return service_answer(t)
    return None


def ships(path: str, t: float) -> Any:
    """Fintraffic's two paths: the positions (GeoJSON) and the ships' own words (a list)."""
    return demoships.locations(t) if path == "/api/ais/v1/locations" else demoships.vessels(t) if path == "/api/ais/v1/vessels" else None


ROUTES: list[Callable[[str, float], Any]] = [answer, ships]       # (what answers a path, in turn)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802  (the name http.server calls)
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

    def log_message(self, format: str, *args: Any) -> None:          # (quiet: the daemon asks every few seconds)
        pass


def serve(port: int) -> ThreadingHTTPServer | None:
    """The server listening on the port of this computer; None when the port is in use (said on standard error)."""
    try:
        return ThreadingHTTPServer((HOST, port), Handler)
    except OSError as e:
        print(f"demotraffic: refused: the port {port} of this computer is in use ({e.strerror}); stop what listens there", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=PORT, help=f"the HTTP port (default {PORT})")
    parser.add_argument("--ais-port", type=int, default=demoships.AIS_PORT, help=f"the port of the made-up AIS receiver (default {demoships.AIS_PORT})")
    args = parser.parse_args(argv)
    server = serve(args.port)
    if server is None:
        return 2
    receiver = demoships.serve(args.ais_port)
    if receiver is None:
        server.server_close()
        return 2
    print(f"listening on {HOST}:{args.port}", flush=True)
    print(f"demotraffic: in Settings, Map, Aircraft, My own receiver: {HOST}:{args.port}; Ships, My own receiver: {HOST}:{args.ais_port}", file=sys.stderr, flush=True)
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
