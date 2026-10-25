"""`neoaprs gps-replay` (neoaprs/cli/gpsreplaycmd.py, neoaprs/cli/gpstrip.py): the synthetic drive, the fake gpsd that reports it, the daemon's own feed reading it, a mobile beacon that follows it as a car's would, and the
command as a process."""
import asyncio
import json
import socket
import subprocess
import sys
import time
from datetime import timedelta

import pytest

from neoaprs.cli import gpsreplaycmd
from neoaprs.cli.gpsreplaycmd import FakeGpsd, position, sky, tpv
from neoaprs.cli.gpstrip import ACCEL_MS2, CORNER_MS, DECEL_MS2, LAP, START_SEC, STOP_SEC, Trip
from neoaprs.clock import utc
from neoaprs.geo import distance_km
from neoaprs.gpsfeed import GpsFeed
from neoaprs.gpsfix import Fix, fix_from_gpsd, satellites_of_sky
from neoaprs.services.beacon import Beacon
from neoaprs.services.gps import Gps
from neoaprs.source import Backoff, Source
from tests.conftest import ROOT
from tests.support.clock import FixedClock
from tests.support.env import idle_for, remember_stop, until
from tests.support.proc import NEW_GROUP, interrupt
from tests.support.rig import ServiceRig

HELSINKI = (60.43, 24.145)


def drive(kmh: float = 50.0, seconds: int = 700) -> list:                       # type: ignore[type-arg]
    trip = Trip(*HELSINKI, kmh)
    return [trip.step() for _ in range(seconds)]


# ---- the drive

def test_the_car_stands_still_then_sets_off_and_accelerates_gently_to_its_speed() -> None:
    samples = drive()
    assert [s.speed_ms for s in samples[:START_SEC]] == [0.0] * START_SEC
    speeds = [s.speed_ms for s in samples]
    assert max(speeds) == pytest.approx(50 / 3.6)
    assert all(b - a <= ACCEL_MS2 + 1e-9 for a, b in zip(speeds, speeds[1:])), "it speeds up by no more than 1.5 m/s each second"
    assert all(a - b <= DECEL_MS2 + 1e-9 for a, b in zip(speeds, speeds[1:])), "and slows down by no more than 2"
    first = samples[0]
    assert (first.lat, first.lon) == HELSINKI


def test_it_goes_round_a_rectangle_north_east_south_and_west() -> None:
    courses: list[int] = []
    for s in drive():
        if s.speed_ms > 1 and (not courses or courses[-1] != s.course_deg):
            courses.append(s.course_deg)
    cardinal = [c for c in courses if c in (0, 90, 180, 270)]
    assert cardinal[:5] == [0, 90, 180, 270, 0], cardinal
    assert {c for c in courses} - {0, 90, 180, 270} <= set(range(0, 360)), "between the legs it turns through the angles in between"


def test_it_slows_for_each_corner_and_stops_in_the_middle_of_the_last_leg_for_ninety_seconds() -> None:
    samples = drive(seconds=420)
    still = [i for i, s in enumerate(samples) if s.speed_ms == 0.0 and i >= START_SEC]
    assert STOP_SEC <= len(still) <= STOP_SEC + 1 and still == list(range(still[0], still[0] + len(still))), "one stop of 90 seconds in a row"
    assert samples[still[0] - 1].course_deg == 270, "on the last leg, going west"
    corners = [i for i in range(1, len(samples)) if samples[i].course_deg != samples[i - 1].course_deg and samples[i].speed_ms > 0]
    assert len(corners) >= 6
    for i in corners:                                                          # the car is near the corner's speed when the heading starts to change
        assert min(s.speed_ms for s in samples[max(0, i - 3):i + 1]) <= CORNER_MS + DECEL_MS2, i


def test_the_stop_is_half_way_along_the_last_leg_and_the_laps_go_on() -> None:
    samples = drive(seconds=1100)
    stop_at = next(s for i, s in enumerate(samples) if i > START_SEC and s.speed_ms == 0.0)
    assert distance_km(stop_at.lat, stop_at.lon, *HELSINKI) == pytest.approx(0.41, abs=0.03), "about 400 m east of the start on its parallel: half way along the leg that runs west to it"
    assert abs(stop_at.lat - HELSINKI[0]) < 0.0003
    stops = [i for i in range(1, len(samples)) if samples[i].speed_ms == 0.0 and samples[i - 1].speed_ms > 0]
    assert len(stops) == 3 and stops[1] - stops[0] == stops[2] - stops[1], "a stop on each lap, a lap apart"


def test_the_positions_are_continuous_and_the_lap_closes() -> None:
    samples = drive(seconds=900)
    steps = [distance_km(a.lat, a.lon, b.lat, b.lon) * 1000 for a, b in zip(samples, samples[1:])]
    assert max(steps) <= 50 / 3.6 + 0.01, "never farther than the speed in a second"
    lap = next(i for i in range(START_SEC + 60, len(samples)) if distance_km(samples[i].lat, samples[i].lon, *HELSINKI) < 0.03 and i > START_SEC + 200)
    assert lap > START_SEC + 200


def test_the_drive_is_the_same_each_time_and_the_speed_is_the_one_asked_for() -> None:
    assert drive(50.0, 300) == drive(50.0, 300)
    assert max(s.speed_ms for s in drive(90.0, 200)) == pytest.approx(25.0)
    assert LAP[0].heading_deg == 0


# ---- what the gpsd says

def test_the_reports_are_those_of_a_gpsd_and_the_daemon_reads_them() -> None:
    sample = Trip(*HELSINKI, 50.0)
    for _ in range(40):
        s = sample.step()
    report = tpv(s, utc(2026, 10, 25, 12, 0, 0))
    assert report["class"] == "TPV" and report["mode"] == 3 and report["time"] == "2026-10-25T12:00:00.000Z"
    fix = fix_from_gpsd(json.loads(json.dumps(report)), utc(2026, 10, 25, 12, 0, 0), satellites_of_sky(sky()))
    assert fix is not None and (fix.lat, fix.lon) == (pytest.approx(s.lat, abs=1e-8), pytest.approx(s.lon, abs=1e-8))
    assert fix.speed_kmh == pytest.approx(s.speed_ms * 3.6, abs=0.01) and fix.course_deg == s.course_deg and fix.altitude_m == 31.0 and fix.satellites == 9


def test_a_place_on_the_command_line_is_latitude_and_longitude() -> None:
    assert position("60.43,24.145") == (60.43, 24.145) and position("-33.8,151.2") == (-33.8, 151.2)
    for bad in ("60.43", "91,0", "0,181", "a,b", ""):
        with pytest.raises(ValueError):
            position(bad)


async def serve(interval: float = 0.01, kmh: float = 50.0) -> FakeGpsd:
    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    server = FakeGpsd(Trip(*HELSINKI, kmh), interval, 0, ready)
    task = asyncio.ensure_future(server.run())

    async def stop() -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    remember_stop(stop)
    await ready
    return server


async def test_a_client_is_greeted_and_is_sent_the_drive_only_after_it_asks_to_watch() -> None:
    server = await serve()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    try:
        assert json.loads(await asyncio.wait_for(reader.readline(), 5))["class"] == "VERSION"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reader.readline(), 0.1)
        writer.write(b'?WATCH={"enable":true,"json":true};\n')
        await writer.drain()
        classes = [json.loads(await asyncio.wait_for(reader.readline(), 5))["class"] for _ in range(8)]
        assert classes[:2] == ["DEVICES", "WATCH"] and "TPV" in classes and classes.count("SKY") <= 1
    finally:
        writer.close()
        await writer.wait_closed()


async def test_the_drive_waits_for_somebody_to_watch_it_and_goes_on_from_where_it_was() -> None:
    server = await serve(0.01)
    await idle_for(0.2)
    assert server.reports == 0, "nobody watches: the car stands at the start"
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(b'?WATCH={"enable":true,"json":true}\n')
    await writer.drain()
    await until(lambda: server.reports >= 5)
    writer.close()
    await writer.wait_closed()
    await until(lambda: not server.watchers)
    stopped_at = server.reports
    await idle_for(0.2)
    assert server.reports == stopped_at


async def test_the_daemons_feed_reads_the_drive_with_the_satellites() -> None:
    server = await serve(0.005)
    feed = GpsFeed(FixedClock(), Backoff([0.05]))
    feed.configure("gpsd", f"127.0.0.1:{server.port}", 4800)
    fixes: list[Fix] = []
    feed.fixed.connect(fixes.append)
    remember_stop(feed.stop)
    await feed.start()
    await until(lambda: len(fixes) >= 30 and any(f.satellites == 9 for f in fixes))
    assert feed.state is Source.State.CONNECTED and all(f.altitude_m == 31.0 for f in fixes)
    assert fixes[0].speed_kmh == 0.0 and max(f.speed_kmh or 0 for f in fixes) > 10


class TripClock:
    """A clock that is a second on for each report of the fake gpsd."""

    def __init__(self, server: FakeGpsd) -> None:
        self.server = server
        self.start = utc(2026, 10, 25, 12, 0, 0)

    def __call__(self):                                                                # type: ignore[no-untyped-def]
        return self.start + timedelta(seconds=self.server.reports)


async def test_a_mobile_beacon_follows_the_drive_as_a_cars_would_start_corners_and_time() -> None:
    server = await serve(0.004)
    clock = TripClock(server)
    rig = ServiceRig(clock=clock, station_symbol_code=">", beacon_interval_min=30, gps_source="gpsd", gps_host=f"127.0.0.1:{server.port}")      # type: ignore[arg-type]
    feed = GpsFeed(clock, Backoff([0.05]))
    gps = Gps(feed, lambda: rig.config, clock)
    feed.fixed.connect(gps.take)
    feed.changed.connect(gps.feed_changed)
    beacon = Beacon(rig.tnc, lambda: rig.config, clock, tick_sec=0.002, gps=gps)
    sent: list[tuple[int, str]] = []
    send_now = beacon.send_now

    def noting(reason: str = "request") -> bool:
        sent_now = send_now(reason)
        if sent_now:
            sent.append((server.reports, reason))
        return sent_now
    beacon.send_now = noting                                                          # type: ignore[method-assign]
    remember_stop(beacon.stop)
    await gps.start()
    await beacon.start()
    remember_stop(gps.stop)
    await until(lambda: server.reports >= 420, 30.0)
    assert sent, "something was sent"
    reasons = [r for _, r in sent]
    assert beacon.mobile.last is not None
    assert reasons[0] == "start" and "turn" in reasons and "time" in reasons, reasons
    assert all(b - a >= 14 for (a, _), (b, _) in zip(sent, sent[1:])), "never closer than the turn time"
    stopped = [i for i, sample in enumerate(drive(seconds=420)) if sample.speed_ms == 0.0 and i >= START_SEC]
    assert [t for t, _ in sent if stopped[0] + 2 < t < stopped[-1]] == [], "nothing is sent while it stands in the middle of the last leg"
    assert [r for _, r in sent if r == "time"] and sent[-1][0] > stopped[-1], "and it sends again once it has set off"


# ---- the command

def test_the_command_says_what_it_is_for_and_refuses_a_place_that_is_not_one() -> None:
    out = subprocess.run([sys.executable, "-m", "neoaprs", "gps-replay", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "--at LAT,LON" in out.stdout and "2948" in out.stdout
    bad = subprocess.run([sys.executable, "-m", "neoaprs", "gps-replay", "--at", "95,0"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and "not a place on the earth" in bad.stderr
    bad = subprocess.run([sys.executable, "-m", "neoaprs", "gps-replay", "--kmh", "0"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2


def test_as_a_process_it_prints_the_address_and_reports_the_drive_to_a_plain_socket_and_ends_on_ctrl_c() -> None:
    proc = subprocess.Popen([sys.executable, "-m", "neoaprs", "gps-replay", "--port", "0", "--interval", "0.02", "--at", "61.5,25.5"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    try:
        assert proc.stdout is not None
        address = proc.stdout.readline().strip()
        host, port = address.rsplit(":", 1)
        assert host == "127.0.0.1" and int(port) > 0
        lines: list[dict[str, object]] = []
        deadline = time.monotonic() + 20
        with socket.create_connection((host, int(port)), timeout=5) as client:
            client.sendall(b'?WATCH={"enable":true,"json":true}\n')
            buffer = b""
            while len([r for r in lines if r["class"] == "TPV"]) < 12 and time.monotonic() < deadline:
                buffer += client.recv(4096)
                *done, buffer = buffer.split(b"\n")
                lines += [json.loads(line) for line in done]
        tpvs = [r for r in lines if r["class"] == "TPV"]
        assert lines[0]["class"] == "VERSION" and len(tpvs) >= 12 and (tpvs[0]["lat"], tpvs[0]["lon"]) == (61.5, 25.5) and any(r["class"] == "SKY" for r in lines)
    finally:
        interrupt(proc)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise AssertionError(f"gps-replay did not end 30 s after the interrupt; it said: {proc.communicate()[1]}") from None
    assert proc.returncode == 0 and "a drive from 61.5,25.5 at 50 km/h" in err and "a client connected" in err and "stopped" in err


def test_the_default_port_is_2948_and_the_host_the_loopback() -> None:
    assert (gpsreplaycmd.HOST, gpsreplaycmd.DEFAULT_PORT) == ("127.0.0.1", 2948)
