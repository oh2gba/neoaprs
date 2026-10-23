"""The weather log (neoaprs/weatherlog.py, weathersql.py) on a real database thread: what goes in comes out equal, the series of a station and its latest, the care, and the one-time making of the log from the
packets already kept, whose weather is plain comment text."""
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.aprsweather import Weather
from neoaprs.packetlog import PacketLog
from neoaprs.store import DB_NAME
from neoaprs.weatherlog import WeatherLog, report_of, weather_of, weather_row
from tests.support.clock import FixedClock
from tests.support.storedb import sql, store_at
from tests.support.weather import REAL, T0, WX, heard, report


async def opened(tmp_path: Path) -> tuple[WeatherLog, PacketLog]:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    return WeatherLog(store.db, clock), PacketLog(store.db, clock)


async def settled(log: WeatherLog) -> None:
    assert log.db is not None
    await log.db.barrier()


def test_an_observation_gives_its_row_and_the_row_gives_it_back() -> None:
    row = weather_row("OH2MUI", T0, WX)
    assert row == ("OH2MUI", "2026-10-21T12:00:00.000000Z", 107, 1.6, 1.6, 10.0, 85, 1028.4, 0.3, 4.1, 3.3, None, REAL)
    assert weather_of(row) == ("OH2MUI", T0, WX)
    sparse = Weather(temp_c=-5.0, raw="t023")
    assert weather_of(weather_row("OH2XYZ", T0, sparse)) == ("OH2XYZ", T0, sparse)


async def test_every_weather_packet_heard_is_kept_and_no_other(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    assert log.take(report()) is True
    assert log.take(heard(b"_10090556t050", "OH2NJR")) is True
    assert log.take(heard(b"!6024.43N/02352.73E>no weather")) is False
    assert log.take(heard(b"!6024.43N/02352.73E_Hello")) is False
    assert log.take(report(direction="out")) is False, "what we sent is not heard weather"
    await settled(log)
    assert await log.count() == 2
    [(at, found)] = await log.series("OH2MUI", T0 - timedelta(hours=1))
    assert (at, found) == (T0, WX)
    [(_, positionless)] = await log.series("OH2NJR", T0 - timedelta(hours=1))
    assert positionless.temp_c == pytest.approx(10.0) and positionless.raw == "t050"


async def test_the_series_of_a_station_is_oldest_first_from_the_time_asked_and_the_latest_is_the_newest(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    for minutes, temp in ((30, "t050"), (0, "t040"), (10, "t045"), (20, "t048")):
        log.take(report(temp, "OH2MUI", T0 + timedelta(minutes=minutes)))
    log.take(report("t090", "OH2NJR", T0 + timedelta(minutes=5)))
    await settled(log)
    series = await log.series("OH2MUI", T0 + timedelta(minutes=10))
    assert [(at - T0).seconds // 60 for at, _ in series] == [10, 20, 30]
    assert [w.temp_c for _, w in await log.series("OH2MUI", T0)] == pytest.approx([4.4, 7.2, 8.9, 10.0], abs=0.05)
    assert await log.series("OH2NONE", T0) == []
    latest = await log.latest("OH2MUI")
    assert latest is not None and latest[0] == T0 + timedelta(minutes=30) and latest[1].temp_c == pytest.approx(10.0)
    assert await log.latest("OH2NONE") is None
    every = await log.latest_all()
    assert set(every) == {"OH2MUI", "OH2NJR"} and every["OH2MUI"][0] == T0 + timedelta(minutes=30) and every["OH2NJR"][1].temp_c == pytest.approx(32.2, abs=0.05)


async def test_prune_removes_what_is_older_than_the_days_kept(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    log.take(report(at=T0 - timedelta(days=40)))
    log.take(report(at=T0 - timedelta(days=2)))
    await settled(log)
    assert await log.prune(30) == 1
    assert [at for at, _ in await log.series("OH2MUI", T0 - timedelta(days=100))] == [T0 - timedelta(days=2)]


async def test_the_hottest_and_the_coldest_a_report_can_say_are_kept(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    log.take(report("t999g999r999p999P999h99b99999L999"))           # 999 degrees F is 537 C: the most the fields can say
    log.take(report("t-99c360s999"))
    await settled(log)
    assert await log.count() == 2
    assert [w.temp_c for _, w in await log.series("OH2MUI", T0 - timedelta(days=1))] == pytest.approx([537.2, -72.8], abs=0.05)


async def test_the_log_made_from_the_packets_kept_reads_each_weather_packet_again(tmp_path: Path) -> None:
    log, packets = await opened(tmp_path)
    wrapped = heard(b"}OH2HCY-3>APRX29,TCPIP,OH7JHF-1*:@210945z6024.43N/02352.73E_96/001g006t048h79b10285Inkoo", "OH7JHF-1", T0 + timedelta(minutes=2), old=True)
    for p in (report(at=T0, old=True), heard(b"_10090556c220s004t077", "OH2NJR", T0 + timedelta(minutes=1), old=True), wrapped, report("t080", at=T0 - timedelta(days=40), old=True),
              report("t090", direction="out", old=True), heard(b"!6024.43N/02352.73E>car", "OH2CAR", T0), heard(b"!!0000000001FF000427C70001", "OH2ULT", T0, old=True), heard(b"!6024.43N/02352.73E_Hello", "OH2HI", T0)):
        packets.append(p)
    assert packets.db is not None
    await packets.db.barrier()
    assert wrapped.third_party is not None and "weather" not in wrapped.summary
    assert await log.backfill(30) == 3
    assert await log.count() == 3
    assert [(at, w.temp_c) for at, w in await log.series("OH2MUI", T0 - timedelta(days=100))] == [(T0, 10.0)]
    assert [w.raw for _, w in await log.series("OH2NJR", T0 - timedelta(days=100))] == ["c220s004t077"]
    assert [(at, w.pressure_hpa) for at, w in await log.series("OH2HCY-3", T0 - timedelta(days=100))] == [(T0 + timedelta(minutes=2), 1028.5)], "the sender inside a third-party packet, not the iGate"
    assert await log.series("OH7JHF-1", T0 - timedelta(days=100)) == []


async def test_nothing_to_make_the_log_from_is_nothing(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    assert await log.backfill(30) == 0 and await log.count() == 0
    assert await WeatherLog().backfill(30) == 0 and await WeatherLog().latest_all() == {}


async def test_a_packet_kept_gives_the_weather_the_parser_reads_in_it() -> None:
    p = report(old=True)
    assert report_of("OH2MUI", "APRX29", p.raw, T0) == ("OH2MUI", WX)
    assert report_of("OH2MUI", "APRX29", heard(b">status").raw, T0) is None


async def test_the_table_is_the_weather_table_of_the_schema(tmp_path: Path) -> None:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    names = [r[1] for r in await sql(store, "PRAGMA table_info(weather)")]
    assert names == ["station", "at", "wind_dir", "wind_kmh", "gust_kmh", "temp_c", "humidity", "pressure_hpa", "rain_1h_mm", "rain_24h_mm", "rain_today_mm", "luminosity", "raw"]
