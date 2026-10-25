"""The GPS inside the whole daemon, the radio a fake TNC on the loopback and a fake gpsd: a mobile station beacons from the fix and sends the compressed frame on the line, its own row on the map and the distances follow
it, the ALOHA circle is worked out again, `?APRSP` is answered with the live position, no fix means no frame (never the home position), a stale fix is not used, the page is told by the topic `gps`, and the settings
start and stop the feed."""
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.aprsposition import parse_position
from neoaprs.geo import distance_km
from neoaprs.packet import Position
from neoaprs.services.aloha import Aloha
from neoaprs.source import Source
from neoaprs.web.gpswire import GpsState
from tests.support.air import message_info, on_air, said
from tests.support.env import Env, idle_for, quick_start, until
from tests.support.gps import FakeGpsd, fake_gpsd, tpv


async def started(tmp_path: Path, gpsd: FakeGpsd, **changes: object) -> Env:
    """A daemon with its radio connected and a GPS read from the fake gpsd, the beacon mobile."""
    e = await quick_start(tmp_path, beacon=True, web=True)
    values = {"gps_source": "gpsd", "gps_host": gpsd.address, "station_symbol_code": ">", **changes}
    assert await e.ctl.save_config(replace(e.ctl.config, **values))                 # type: ignore[arg-type]
    await until(lambda: gpsd.watching and e.ctl.gps_feed.state is Source.State.CONNECTED)
    return e


def me(e: Env):                                                                   # type: ignore[no-untyped-def]
    row = e.ctl.stationbook.me
    assert row is not None
    return row


async def test_a_mobile_station_beacons_its_first_fix_as_a_compressed_position_and_its_row_is_at_the_fix(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    assert (me(e).lat, me(e).lon) == (60.17, 24.94), "at home until there is a fix"
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0, alt=31.4))
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=//w5#TW?M>eM[/A=000103mobile".replace("mobile", "NeoAPRS") and frame.is_ui
    assert e.ctl.beacon.last_reason == "start"
    row = me(e)
    assert (row.lat, row.lon, row.course_deg, row.speed_kmh, row.altitude_m, row.is_me) == (60.43, 24.145, 270, pytest.approx(54.0), 31.4, True)
    assert e.ctl.stationbook.me_position == (60.43, 24.145)
    [sent] = [p for p in await e.packets() if p.direction == "out"]
    assert isinstance(sent.decoded, Position) and sent.decoded.compressed and sent.decoded.altitude_m is not None
    await e.stop()


async def test_the_row_and_the_distances_follow_the_gps_every_few_seconds_and_ten_metres(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    e.feed(on_air("OH2RDG", b"!6043.00N/02408.70E-far"))                            # a station at 60.7167 N 24.145 E: 60 km from home, 31.8 km from the fix
    await until(lambda: e.ctl.stationbook.get("OH2RDG") is not None)
    book = e.ctl.stationbook
    station = book.get("OH2RDG")
    assert station is not None
    home = book.distance_km(station)
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0))
    await until(lambda: me(e).lat == 60.43)
    assert home == pytest.approx(distance_km(60.17, 24.94, 60.7167, 24.145), abs=0.1)
    assert book.distance_km(station) == pytest.approx(distance_km(60.43, 24.145, 60.7167, 24.145), abs=0.1)
    e.now.advance(2)                                                                 # type: ignore[attr-defined]
    gpsd.send(tpv(60.44, 24.145, speed=15.0, track=270.0))
    await until(lambda: e.ctl.gps.fix is not None and e.ctl.gps.fix.lat == 60.44)
    await idle_for(0.05)
    assert me(e).lat == 60.43, "two seconds after the row was put: not yet"
    e.now.advance(4)                                                                 # type: ignore[attr-defined]
    gpsd.send(tpv(60.45, 24.145, speed=15.0, track=270.0))
    await until(lambda: me(e).lat == 60.45)
    await e.stop()


async def test_the_alohas_circle_is_worked_out_again_when_the_row_moves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[float, float] | None] = []
    real = Aloha.refresh

    def counting(self: Aloha) -> None:
        calls.append(self._book.me_position)
        real(self)
    monkeypatch.setattr(Aloha, "refresh", counting)
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    calls.clear()
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0))
    await until(lambda: (60.43, 24.145) in calls)
    await e.stop()


async def test_with_no_fix_nothing_is_sent_and_the_row_stays_at_home(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.beacon")
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    gpsd.send(tpv(None, None, mode=1))
    await idle_for(0.3)
    assert e.ctl.beacon.last_sent is None and e.ctl.beacon.next_due is None
    assert not e.ctl.beacon.send_now() and "no beacon" in e.ctl.beacon.problem
    assert e.ctl.gps.state == "no_fix" and (me(e).lat, me(e).lon) == (60.17, 24.94)
    assert await e.packets() == []
    await e.stop()


async def test_a_fix_that_grows_stale_is_not_beaconed_and_the_home_position_is_not_sent_instead(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0))
    await said(e)
    e.now.advance(121)                                                               # type: ignore[attr-defined]
    await until(lambda: e.ctl.gps.state == "stale")
    await idle_for(0.2)
    assert e.ctl.beacon.next_due is None
    assert not e.ctl.beacon.send_now() and "GPS fix is 121 s old" in e.ctl.beacon.problem
    assert len([p for p in await e.packets() if p.direction == "out"]) == 1
    assert (me(e).lat, me(e).lon) == (60.43, 24.145), "the row stays where we were last seen, not at home"
    gpsd.send(tpv(60.5, 24.2, speed=15.0, track=270.0))
    await until(lambda: e.ctl.beacon.last_reason == "time")           # (the fix is back: the beacon that was long due goes, the position of now)
    out = [p.decoded for p in await e.packets() if p.direction == "out"]
    assert sorted(round(d.lat, 3) for d in out if isinstance(d, Position)) == [60.43, 60.5]
    await e.stop()


async def test_aprsp_is_answered_with_the_live_position(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0))
    await said(e)
    e.now.advance(40)                                                                # type: ignore[attr-defined]
    gpsd.send(tpv(60.46, 24.150, speed=15.0, track=270.0))
    await until(lambda: e.ctl.gps.fix is not None and e.ctl.gps.fix.lat == 60.46)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP")))
    [answer] = await said(e)
    position = parse_position(answer.info[1:], e.now())
    assert position.compressed and (position.lat, position.lon) == (pytest.approx(60.46, abs=1e-5), pytest.approx(24.150, abs=1e-5))
    await e.stop()


async def test_the_settings_of_a_station_that_stays_leave_the_home_position_and_the_plain_beacon(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0))
    await said(e)
    assert await e.ctl.save_config(replace(e.ctl.config, gps_source="off"))
    assert (me(e).lat, me(e).lon, me(e).course_deg) == (60.17, 24.94, None)
    assert e.ctl.beacon.frame().info == b"=6010.20N/02456.40E>NeoAPRS"
    await e.stop()


async def test_the_feed_is_started_and_stopped_with_the_settings_and_the_daemon(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    assert e.ctl.gps_feed.kind == "gpsd" and e.ctl.gps_feed.target == gpsd.address
    assert await e.ctl.save_config(replace(e.ctl.config, gps_source="off"))
    await until(lambda: e.ctl.gps_feed.state is Source.State.STOPPED)
    assert e.ctl.gps.state == "off"
    await e.stop()
    assert e.ctl.gps_feed.state is Source.State.STOPPED


async def test_a_daemon_with_no_gps_runs_no_feed(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, beacon=True)
    assert e.ctl.gps_feed.state is Source.State.STOPPED and e.ctl.gps.state == "off"
    await e.stop()


# ---- the page

async def test_the_page_is_told_the_gps_the_fix_and_the_beacon(tmp_path: Path) -> None:
    gpsd = await fake_gpsd()
    e = await started(tmp_path, gpsd)
    page = await e.ws()
    await page.until(lambda: "gps" in page.topics)
    first = GpsState.model_validate(page.topics["gps"])
    assert (first.source, first.state, first.mobile, first.lat, first.last_beacon_reason) == ("gpsd", "no_fix", True, None, "")
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0, alt=31.4))
    await said(e)
    await page.until(lambda: page.topics["gps"]["last_beacon_reason"] == "start")
    state = GpsState.model_validate(page.topics["gps"])
    assert (state.state, state.problem, state.lat, state.lon, state.altitude_m, state.course_deg, state.fix_at) == ("fix", "", 60.43, 24.145, 31.4, 270, "2026-10-21T12:00:00Z")
    assert state.speed_kmh == pytest.approx(54.0) and state.last_beacon_at == "2026-10-21T12:00:00Z"
    assert state.next_beacon_at == "2026-10-21T12:01:51Z", "111 seconds at 54 km/h"
    e.now.advance(130)                                                               # type: ignore[attr-defined]
    await page.until(lambda: page.topics["gps"]["state"] == "stale")
    stale = GpsState.model_validate(page.topics["gps"])
    assert stale.problem and stale.next_beacon_at is None and stale.lat == 60.43
    await e.stop()


async def test_the_page_is_told_when_the_gps_source_turns_the_beacon_mobile(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, beacon=True, web=True)
    page = await e.ws()
    await page.until(lambda: "gps" in page.topics)
    assert page.topics["gps"]["mobile"] is False and page.topics["gps"]["state"] == "off"
    assert await e.ctl.save_config(replace(e.ctl.config, gps_source="serial", beacon_moving_as="bicycle"))
    await page.until(lambda: page.topics["gps"]["mobile"] is True)
    assert page.topics["config"]["values"]["gps/source"] == "serial" and page.topics["config"]["defaults"]["gps/source"] == "off"
    assert page.topics["config"]["values"]["beacon/moving_as"] == "bicycle" and page.topics["config"]["defaults"]["beacon/moving_as"] == "car"
    assert page.topics["config"]["defaults"]["gps/host"] == "127.0.0.1:2947" and "beacon/mobile" not in page.topics["config"]["values"] and "smart/fast_kmh" not in page.topics["config"]["values"]
    await e.stop()
