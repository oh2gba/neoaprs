"""`neoaprs gps-replay [--at LAT,LON] [--kmh N] [--port P] [--interval S]`: a gpsd that is not one, on a TCP port of the loopback, which reports a synthetic drive, so that the daemon can beacon as a car would without a car or a receiver:

    neoaprs gps-replay                                              # prints 127.0.0.1:2948 as its first line
    neoaprs db set gps/source gpsd; neoaprs db set gps/host 127.0.0.1:2948      # or the same on the page's Beacon tab

The drive (neoaprs/cli/gpstrip.py) starts at `--at` (60.43,24.145 by default) and is a rectangle of straight legs and corners at `--kmh` (50 by default), with a stop in the middle of the last leg, driven round and
round. A client that sends `?WATCH={"enable":true,"json":true}`, as the daemon does, is sent a TPV report each INTERVAL seconds (a second by default; a smaller number drives faster than real time) and a SKY report every fifth.
The drive goes on only while a client watches, and from where it stopped. Ctrl-C ends it."""
import argparse
import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .gpstrip import Sample, Trip
from .output import ctrl_break_is_ctrl_c, say

HOST = "127.0.0.1"
DEFAULT_PORT = 2948
DEFAULT_AT = "60.43,24.145"
SKY_EVERY = 5                           # a SKY report after this many TPV reports
SATELLITES = 9
VERSION = {"class": "VERSION", "release": "3.25", "rev": "neoaprs gps-replay", "proto_major": 3, "proto_minor": 14}
DEVICES = {"class": "DEVICES", "devices": [{"class": "DEVICE", "path": "/dev/gps-replay", "driver": "NMEA0183", "activated": "2026-01-01T00:00:00.000Z"}]}
WATCH = {"class": "WATCH", "enable": True, "json": True, "nmea": False, "raw": 0, "scaled": False, "timing": False, "split24": False, "pps": False}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs gps-replay", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--at", default=DEFAULT_AT, metavar="LAT,LON", help=f"where the drive starts, decimal degrees (default {DEFAULT_AT})")
    p.add_argument("--kmh", type=float, default=50.0, help="the cruising speed in km/h (default 50)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, metavar="P", help=f"the TCP port to listen on, on {HOST} (default {DEFAULT_PORT}; 0 takes a free one)")
    p.add_argument("--interval", type=float, default=1.0, metavar="S", help="seconds between two reports, each a second of driving (default 1.0)")
    return p


def position(text: str) -> tuple[float, float]:
    """LAT,LON from the command line; ValueError when it is not a place on the earth."""
    lat, lon = (float(part) for part in text.split(","))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"{text!r} is not a place on the earth")
    return lat, lon


def tpv(sample: Sample, now: datetime) -> dict[str, object]:
    """The TPV report of a gpsd for this sample."""
    return {"class": "TPV", "device": "/dev/gps-replay", "mode": 3, "time": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "lat": round(sample.lat, 9), "lon": round(sample.lon, 9),
            "altHAE": round(sample.altitude_m + 20.0, 1), "altMSL": sample.altitude_m, "alt": sample.altitude_m, "track": float(sample.course_deg), "speed": round(sample.speed_ms, 3), "climb": 0.0}


def sky() -> dict[str, object]:
    return {"class": "SKY", "device": "/dev/gps-replay", "nSat": SATELLITES + 3, "uSat": SATELLITES, "hdop": 1.1, "satellites": [{"PRN": n, "used": n <= SATELLITES} for n in range(1, SATELLITES + 4)]}


def line(report: Mapping[str, object]) -> bytes:
    return json.dumps(report, separators=(",", ":")).encode() + b"\n"


class FakeGpsd:
    """The server: a client that has asked to watch is sent the drive."""

    def __init__(self, trip: Trip, interval: float, port: int = DEFAULT_PORT, ready: asyncio.Future[int] | None = None) -> None:
        self.trip, self.interval, self.port, self.ready = trip, interval, port, ready
        self.watchers: list[asyncio.StreamWriter] = []
        self.reports = 0

    async def run(self) -> None:
        server = await asyncio.start_server(self._serve, HOST, self.port)
        try:
            self.port = server.sockets[0].getsockname()[1]
            if self.ready is not None:
                self.ready.set_result(self.port)
            while True:
                await asyncio.sleep(self.interval)
                if self.watchers:                                    # (the drive waits for somebody to watch it, and goes on from where it was)
                    await self._report()
        finally:
            server.close()
            for client in list(self.watchers):
                client.close()
            await server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        say("gps-replay: a client connected")
        writer.write(line(VERSION))
        try:
            while data := await reader.readline():
                if data.strip().startswith(b"?WATCH=") and b'"enable":true' in data.replace(b" ", b""):
                    writer.write(line(DEVICES) + line(WATCH))
                    if writer not in self.watchers:
                        self.watchers.append(writer)
                    say("gps-replay: the client is watching")
                await writer.drain()
        except OSError:
            pass
        finally:
            if writer in self.watchers:
                self.watchers.remove(writer)
            writer.close()
            say("gps-replay: the client went away")

    async def _report(self) -> None:
        sample = self.trip.step()
        self.reports += 1
        data = line(tpv(sample, datetime.now(UTC))) + (line(sky()) if self.reports % SKY_EVERY == 0 else b"")
        for client in list(self.watchers):
            try:
                client.write(data)
                await client.drain()
            except OSError:
                self.watchers.remove(client)


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    ctrl_break_is_ctrl_c()
    try:
        lat, lon = position(args.at)
    except ValueError as e:
        say(f"gps-replay: --at: {e}")
        return 2
    if args.kmh <= 0 or args.interval <= 0:
        say("gps-replay: --kmh and --interval must be above 0")
        return 2

    async def serve() -> None:
        ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        task = asyncio.ensure_future(FakeGpsd(Trip(lat, lon, args.kmh), args.interval, args.port, ready).run())
        waiting: set[asyncio.Future[Any]] = {task, ready}
        await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            task.result()                                           # (the port could not be listened on: the error is raised here)
        port = ready.result()
        print(f"{HOST}:{port}", flush=True)
        say(f"gps-replay: a drive from {lat:g},{lon:g} at {args.kmh:g} km/h; give the daemon gps/source gpsd, gps/host {HOST}:{port}; Ctrl-C ends it")
        await task

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        say("gps-replay: stopped")
    except OSError as e:
        say(f"gps-replay: cannot listen on {HOST}:{args.port}: {e}")
        return 1
    return 0
