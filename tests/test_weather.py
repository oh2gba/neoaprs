"""Weather through the whole daemon: a report on the air reaches the station book, the weather log and the page; the log is made from the packets already kept when the daemon starts with none; the page asks
for the series of a station (`weather_series`); and the tracks the packet table holds are back on the map after a restart."""
import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import iso
from neoaprs.station import Station
from neoaprs.stationbook import TRACK_MAX
from tests.support.air import on_air
from tests.support.env import Env
from tests.support.weather import REAL, WX, heard, report
from neoaprs.web.stationwire import StationRow
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.weatherwire import WeatherSeriesMsg

STATION = Station("OH2MUI", first_heard=report().heard_at, last_heard=report().heard_at, symbol_table="/", symbol_code="_", lat=60.4, lon=23.9, last_position_at=report().heard_at)


async def test_a_report_on_the_air_is_in_the_book_the_log_and_the_stations_topic(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: "OH2GBA" in page.topics.get("stations", {}))
    e.feed(on_air("OH2MUI", b"@210945z6024.43N/02352.73E_" + REAL.encode() + b" RX Igate & WX station", "APRX29", "OH2RCH-2*"))
    await page.until(lambda: "OH2MUI" in page.topics["stations"])
    row = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2MUI"]))
    assert row.weather is not None and (row.weather.temp_c, row.weather.wind_dir, row.weather.humidity, row.weather.pressure_hpa) == (10.0, 107, 85, 1028.4)
    assert row.weather_at == iso(e.now()) and row.symbol_code == "_" and row.last_comment == "RX Igate & WX station"
    await e.settled()
    [(at, found)] = await e.ctl.weatherlog.series("OH2MUI", e.now() - timedelta(hours=1))
    assert (at, found) == (e.now(), WX)
    assert [p.summary for p in await e.packets()][0].startswith("position 60.4072 23.8788 /_ weather: wind 107° 2 km/h")


async def test_a_station_without_weather_has_a_null_weather_on_the_wire(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await e.play()
    await page.until(lambda: len(page.topics["stations"]) == 5)
    rows = [StationRow.model_validate_json(json.dumps(r)) for r in page.topics["stations"].values()]
    assert all(r.weather is None and r.weather_at is None for r in rows)


async def test_the_log_is_made_from_the_packets_kept_when_the_daemon_starts_with_none_and_only_then(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    first = Env(tmp_path, radio=False)
    await first.start()
    for minutes in (0, 10, 20):
        first.ctl.packetlog.append(report(f"107/001g001t0{50 + minutes // 10}h85b10284", at=first.now() + timedelta(minutes=minutes - 30), old=True))
    first.ctl.packetlog.save_station(STATION)
    await first.settled()
    assert await first.ctl.weatherlog.count() == 0
    await first.stop()
    caplog.set_level(logging.INFO, "neoaprs.controller")
    second = Env(tmp_path, radio=False)
    await second.start()
    assert await second.ctl.weatherlog.count() == 3
    assert [w.temp_c for _, w in await second.ctl.weatherlog.series("OH2MUI", second.now() - timedelta(hours=1))] == pytest.approx([10.0, 10.6, 11.1], abs=0.05)
    station = second.ctl.stationbook.get("OH2MUI")
    assert station is not None and station.weather is not None and station.weather.temp_c == pytest.approx(11.1, abs=0.05) and station.weather_at == second.now() - timedelta(minutes=10)
    assert any("the weather log was empty: 3 observations" in r.getMessage() for r in caplog.records)
    await second.stop()
    third = Env(tmp_path, radio=False)
    await third.start()
    assert await third.ctl.weatherlog.count() == 3, "a log that holds something is not made again"
    await third.stop()


async def test_a_start_with_no_weather_packets_leaves_the_log_empty(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    await e.start()
    assert await e.ctl.weatherlog.count() == 0 and e.ctl.stationbook.get("OH2MUI") is None
    await e.stop()


async def test_the_series_is_asked_for_by_call_and_hours_and_answered_to_the_page_that_asked(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page, other = await e.ws(), await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    for minutes, fields in ((-300, "g010t050r001h85b10284"), (-30, "c090s010g015t-05h00b10132"), (-5, "t050")):
        e.ctl.weatherlog.take(report(fields, at=e.now() + timedelta(minutes=minutes)))
    await e.settled()
    await page.send({"cmd": "weather_series", "call": "OH2MUI", "hours": 1})
    answer = WeatherSeriesMsg.model_validate_json(json.dumps(await page.expect("weather_series")))
    assert (answer.call, answer.hours) == ("OH2MUI", 1)
    assert [list(p) for p in answer.points] == [[iso(e.now() - timedelta(minutes=30)), -20.6, 1013.2, 16.1, 24.1, None, 100], [iso(e.now() - timedelta(minutes=5)), 10.0, None, None, None, None, None]]
    await page.send({"cmd": "weather_series", "call": "OH2MUI", "hours": 24})
    assert len((await page.expect("weather_series"))["points"]) == 3
    await page.send({"cmd": "weather_series", "call": "OH2NONE", "hours": 168})
    assert (await page.expect("weather_series"))["points"] == []
    assert other.of("weather_series") == [], "only the page that asked is answered"


@pytest.mark.parametrize("command", [{"cmd": "weather_series", "call": "OH2MUI", "hours": 0}, {"cmd": "weather_series", "call": "OH2MUI", "hours": 169}, {"cmd": "weather_series", "call": "", "hours": 24},
                                     {"cmd": "weather_series", "call": "OH2MUI"}, {"cmd": "weather_series", "hours": 24}, {"cmd": "weather_series", "call": "OH2MUI", "hours": "24"}])
async def test_a_series_asked_for_wrongly_is_an_error_and_changes_nothing(tmp_path: Path, command: dict[str, object]) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.send(command)
    assert (await page.expect("error"))["text"].startswith("weather_series")
    assert page.of("weather_series") == []


async def test_the_tracks_the_packet_table_holds_are_on_the_map_after_a_restart(tmp_path: Path) -> None:
    first = Env(tmp_path, radio=False)
    await first.start()
    start = first.now() - timedelta(hours=1)
    for n in range(60):
        first.ctl.packetlog.append(heard(b"!%02d%05.2fN/02456.00E>drive" % (60, 10 + n * 0.1), "OH2GAX-9", start + timedelta(minutes=n)))
    first.ctl.packetlog.save_station(Station("OH2GAX-9", first_heard=start, last_heard=first.now(), symbol_table="/", symbol_code=">", lat=60.0, lon=24.9, last_position_at=first.now(), packets=60))
    await first.settled()
    await first.stop()
    second = Env(tmp_path, radio=False, web=True)
    await second.start()
    station = second.ctl.stationbook.get("OH2GAX-9")
    assert station is not None and len(station.track) == TRACK_MAX
    assert [t for t, _, _ in station.track] == sorted(t for t, _, _ in station.track) and station.track[-1][0] == start + timedelta(minutes=59)
    assert station.track[0][0] == start + timedelta(minutes=10)
    assert second.ctl.stationbook.me is not None and second.ctl.stationbook.me.track == []
    page = await second.ws()
    await page.until(lambda: "OH2GAX-9" in page.topics.get("stations", {}))
    row = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2GAX-9"]))
    assert len(row.track) == TRACK_MAX and row.track[-1][0] == iso(start + timedelta(minutes=59))
    assert page.topics["stations"]["OH2GBA"]["track"] == []


async def test_the_tracks_leave_out_what_is_older_than_the_days_kept_and_the_positions_that_are_not_ours_to_place(tmp_path: Path) -> None:
    first = Env(tmp_path, radio=False)
    await first.start()
    now = first.now()
    first.ctl.packetlog.append(heard(b"!6010.00N/02456.00E>old", "OH2OLD", now - timedelta(days=40)))
    first.ctl.packetlog.append(heard(b"!6011.00N/02456.00E>new", "OH2OLD", now - timedelta(days=1)))
    first.ctl.packetlog.append(heard(b"!6012.00N/02456.00E>x", "OH2OLD", now - timedelta(days=1) + timedelta(minutes=1), direction="out"))
    first.ctl.packetlog.append(heard(b";WXPOST   *092345z6013.00N/02456.00E_220/004g005t077", "OH2OBJ", now - timedelta(hours=2)))
    first.ctl.packetlog.append(heard(b"}OH2INN>APRS,TCPIP,OH7JHF-1*:!6014.00N/02456.00E>in", "OH7JHF-1", now - timedelta(hours=1)))
    for s in (Station("OH2OLD", first_heard=now, last_heard=now, lat=60.0, lon=24.0, last_position_at=now), Station("WXPOST", first_heard=now, last_heard=now, kind="object", lat=60.2, lon=24.9, last_position_at=now),
              Station("OH2INN", first_heard=now, last_heard=now, lat=60.2, lon=24.9, last_position_at=now), Station("OH7JHF-1", first_heard=now, last_heard=now, lat=60.2, lon=24.9, last_position_at=now)):
        first.ctl.packetlog.save_station(s)
    await first.settled()
    await first.stop()
    second = Env(tmp_path, radio=False)
    await second.start()
    book = second.ctl.stationbook
    assert [(round(lat, 3)) for _, lat, _ in book.get("OH2OLD").track] == [60.183]                      # type: ignore[union-attr]
    assert [round(lat, 3) for _, lat, _ in book.get("WXPOST").track] == [60.217], "an object has the track of its own name"          # type: ignore[union-attr]
    assert [round(lat, 3) for _, lat, _ in book.get("OH2INN").track] == [60.233] and [t for t in book.get("OH7JHF-1").track][0][1] == 60.2    # type: ignore[union-attr]
    await second.stop()
