"""A GPS for the tests: NMEA sentences with their checksums, a fake gpsd on a free port of the loopback, and a stand-in for the GPS service that the beacon is given.

    nmea("GPRMC,123519,A,...")                    # "$GPRMC,...*6A\\r\\n": the checksum is worked out
    rmc(60.43, 24.145, knots=27.0, course=270.0)  # a valid RMC sentence for a place; valid=False gives status V
    gga(60.43, 24.145, altitude=31.4, satellites=9)
    gpsd = await fake_gpsd()                      # gpsd.address is the setting gps/host; stopped when the test is over
    gpsd.send(tpv(60.43, 24.145, speed=15.0))     # a report to every client that is connected
    FakeFixes(fix)                                # what the beacon needs of the GPS service: .fix, .why
"""
import asyncio
import json
from datetime import datetime
from functools import reduce
from typing import Any

from neoaprs.gpsfix import Fix
from tests.support.env import remember_stop
from tests.support.fakes import FakeLineServer


def nmea(body: str) -> str:
    """The sentence `body` (between the `$` and the `*`) with its checksum and line end."""
    return f"${body}*{reduce(lambda a, c: a ^ ord(c), body, 0):02X}\r\n"


def _degrees(value: float, width: int, hemispheres: str) -> tuple[str, str]:
    """ddmm.mmmm (or dddmm.mmmm) and N/S (E/W) of a coordinate."""
    whole = int(abs(value))
    minutes = (abs(value) - whole) * 60
    return f"{whole:0{width}d}{minutes:07.4f}", hemispheres[0] if value >= 0 else hemispheres[1]


def _place(lat: float, lon: float) -> str:
    (la, ns), (lo, ew) = _degrees(lat, 2, "NS"), _degrees(lon, 3, "EW")
    return f"{la},{ns},{lo},{ew}"


def rmc(lat: float, lon: float, knots: float = 0.0, course: float | None = 0.0, valid: bool = True, time: str = "123519", date: str = "251026") -> str:
    """A GPRMC sentence; with `valid` False its status is V (no fix) and the position is empty."""
    course_text = "" if course is None else f"{course:.1f}"
    if not valid:
        return nmea(f"GPRMC,{time},V,,,,,,,{date},,,N")
    return nmea(f"GPRMC,{time},A,{_place(lat, lon)},{knots:.1f},{course_text},{date},,,A")


def gga(lat: float, lon: float, altitude: float = 31.4, satellites: int = 9, quality: int = 1, time: str = "123519") -> str:
    """A GPGGA sentence; quality 0 is no fix."""
    if quality == 0:
        return nmea(f"GPGGA,{time},,,,,0,00,99.99,,,,,,")
    return nmea(f"GPGGA,{time},{_place(lat, lon)},{quality},{satellites:02d},0.9,{altitude:.1f},M,19.5,M,,")


def tpv(lat: float | None, lon: float | None, speed: float | None = 0.0, track: float | None = 0.0, mode: int = 3, alt: float | None = 31.4, **extra: Any) -> dict[str, Any]:
    """A gpsd TPV report (speed in metres per second)."""
    report: dict[str, Any] = {"class": "TPV", "device": "/dev/ttyUSB1", "mode": mode, "time": "2026-10-25T12:00:00.000Z"}
    for key, value in (("lat", lat), ("lon", lon), ("speed", speed), ("track", track), ("altMSL", alt)):
        if value is not None:
            report[key] = value
    return {**report, **extra}


def sky(used: int = 9, seen: int = 12) -> dict[str, Any]:
    return {"class": "SKY", "device": "/dev/ttyUSB1", "uSat": used, "nSat": seen}


class FakeGpsd(FakeLineServer):
    """The part of gpsd the daemon talks to: a VERSION line on connect, a WATCH answer to `?WATCH=...`, then whatever the test `send`s."""

    def __init__(self, greet: bool = True) -> None:
        super().__init__()
        self.on_client = self._greet if greet else None
        self.responder = self._answer

    async def _greet(self, writer: Any) -> None:
        writer.write(json.dumps({"class": "VERSION", "release": "3.25", "proto_major": 3}).encode() + b"\n")

    def _answer(self, line: str) -> bytes:
        return b'{"class":"WATCH","enable":true,"json":true}\n' if line.startswith("?WATCH=") else b""

    async def start_on(self, port: int) -> "FakeGpsd":
        """Listens on this port (one a test has been trying to reach) instead of a free one."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = port
        remember_stop(self.stop)
        return self

    @property
    def address(self) -> str:
        """The setting gps/host that reaches this server."""
        return f"127.0.0.1:{self.port}"

    def send(self, report: dict[str, Any]) -> None:
        for client in self.clients:
            if not client.is_closing():
                client.write(json.dumps(report).encode() + b"\n")

    def send_raw(self, data: bytes) -> None:
        """Bytes to every client as they are (NMEA sentences, for a receiver behind a TCP serial server)."""
        for client in self.clients:
            if not client.is_closing():
                client.write(data)

    @property
    def url(self) -> str:
        """The setting gps/device that reaches this server as a serial port."""
        return f"socket://127.0.0.1:{self.port}"

    def hang_up(self) -> None:
        """Closes every connection (gpsd was stopped)."""
        for client in self.clients:
            client.close()
        self.clients.clear()

    @property
    def watching(self) -> bool:
        return any(line.startswith("?WATCH=") and '"enable":true' in line.replace(" ", "") for line in self.received)


async def fake_gpsd(greet: bool = True) -> FakeGpsd:
    """A fake gpsd listening on a free port, stopped by stop_all() when the test is over. With `greet` False it says nothing on connect: a receiver behind a TCP serial server (`url`)."""
    server = FakeGpsd(greet)
    await server.start()
    remember_stop(server.stop)
    return server


class FakeFixes:
    """What the beacon needs of the GPS service (services/mobilebeacon.py `Positions`): the fix to send, and why there is none."""

    def __init__(self, fix: Fix | None = None, why: str = "the receiver has no position fix yet") -> None:
        self.fix, self.why = fix, why

    def current(self) -> Fix | None:
        return self.fix

    def why_none(self) -> str:
        return self.why


def fix_at(at: datetime, lat: float = 60.43, lon: float = 24.145, speed_kmh: float | None = 0.0, course_deg: int | None = 0, altitude_m: float | None = 31.4, satellites: int | None = 9) -> Fix:
    return Fix(lat, lon, at, speed_kmh, course_deg, altitude_m, satellites)
