"""The ALOHA circle (neoaprs/aloha.py, neoaprs/services/aloha.py): the method of WB4APR's text on made-up stations at known distances (due north of the position, 1 km = 1/111.195 degree), the kinds of station, what is left out,
the edges (no position, too few stations, one at the position), the service that works it out again, and the value on the wire. The circle of a radio (rule 3.8) counts the stations that radio heard, and
the service draws the main radio's while its type shares a 1200 baud channel (FM), none for an HF main radio or none at all."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from pathlib import Path

import pytest

from neoaprs.aloha import circle, counted, kind_of
from neoaprs.clock import utc
from neoaprs.geo import KM_PER_DEGREE
from neoaprs.packet import Other, Packet, ThirdParty
from neoaprs.policy import ALOHA_PACKETS, ALOHA_WINDOW_MIN
from neoaprs.radiospec import FM_ID, HF_ID, RadioHeard, RadioId
from neoaprs.radiotypes.common import FM_ALLOWED, HF_ALLOWED
from neoaprs.services.aloha import Aloha
from neoaprs.stationbook import Station, StationBook
from neoaprs.stationnotes import note_heard
from tests.support.clock import FixedClock
from tests.support.env import Env

NOW = utc(2026, 10, 21, 12, 0, 0)
HOME = (60.0, 24.0)


def at_km(call: str, km: float, code: str = "-", table: str = "/", **kw: object) -> Station:
    """A station `km` north of HOME, heard just now."""
    heard = kw.pop("last_heard", NOW)
    return Station(call, first_heard=NOW, last_heard=heard, last_rf_at=heard, heard_rf=1, lat=HOME[0] + km / KM_PER_DEGREE, lon=HOME[1], symbol_table=table, symbol_code=code, last_position_at=NOW, **kw)  # type: ignore[arg-type]


def homes(count: int, first_km: float = 1.0, step_km: float = 1.0) -> list[Station]:
    return [at_km(f"OH2H{n:03d}", first_km + n * step_km) for n in range(count)]


def test_the_circle_ends_at_the_station_where_the_load_reaches_1800_packets() -> None:
    stations = homes(900)                                       # home stations: 2 packets each, 1 km apart from 1 km to 900 km
    found = circle(HOME, stations, NOW)
    assert found is not None
    assert found.stations == 900 and found.radius_km == pytest.approx(900.0, abs=0.01)
    assert circle(HOME, homes(899), NOW) is None                # 1798 packets: the channel is not full
    found = circle(HOME, stations + homes(50, 2000.0), NOW)
    assert found is not None and found.stations == 900          # the stations beyond the edge do not move it


def test_the_stations_are_taken_from_the_nearest_whatever_the_order_they_are_given_in() -> None:
    stations = homes(900)
    assert circle(HOME, list(reversed(stations)), NOW) == circle(HOME, stations, NOW)


def test_the_weights_of_the_kinds_add_up() -> None:
    moving = [at_km(f"OH2M{n:02d}", 1.0 + n, code=">", speed_kmh=60.0) for n in range(120)]       # a car in motion: 15 packets
    found = circle(HOME, moving, NOW)
    assert found is not None and found.stations == 120 and found.radius_km == pytest.approx(120.0, abs=0.01)    # 120 x 15 = 1800
    parked = [at_km(f"OH2P{n:02d}", 1.0 + n, code=">", speed_kmh=0.0) for n in range(258)]        # a car not moving: 7 packets
    found = circle(HOME, parked, NOW)
    assert found is not None and found.stations == 258          # 257 x 7 = 1799
    weather = [at_km(f"OH2W{n:03d}", 1.0 + n, code="_") for n in range(300)]                       # a weather station: 6 packets
    found = circle(HOME, weather, NOW)
    assert found is not None and found.stations == 300


def test_every_digipeater_makes_the_stations_beyond_it_count_once_more() -> None:
    near_digi = [at_km("OH2RCH-2", 1.0, code="#")]                                               # 3 packets, then C is 2
    others = [at_km(f"OH2H{n:03d}", 2.0 + n) for n in range(450)]                              # 2 x 2 = 4 packets each
    found = circle(HOME, near_digi + others, NOW)
    assert found is not None and found.stations == 1 + 450      # 3 + 449 x 4 = 1799, the 450th home station makes 1803
    assert found.radius_km == pytest.approx(451.0, abs=0.01)
    assert circle(HOME, near_digi + others[:449], NOW) is None
    two = [at_km("OH2RCH-2", 1.0, code="#"), at_km("OH2RCH-3", 2.0, code="#", table="1")]
    found = circle(HOME, two + [at_km(f"OH2H{n:03d}", 3.0 + n) for n in range(400)], NOW)           # 3, then 3 x 2, then 6 per home station
    assert found is not None and found.stations == 2 + 299      # 9 + 298 x 6 = 1797, the 299th home station makes 1803


def test_the_digipeater_adds_its_own_packets_before_the_count_rises() -> None:
    stations = [at_km("OH2RCH-2", 1.0, code="#"), at_km("OH2H001", 2.0)]
    total_first = 3 * 1 + 2 * 2
    assert total_first == 7 and circle(HOME, stations, NOW) is None


def test_the_kinds_by_symbol_and_speed() -> None:
    assert kind_of(at_km("A", 1, code="#")) == "digi"
    assert kind_of(at_km("A", 1, code="#", table="1")) == "digi"
    assert kind_of(at_km("A", 1, code="_")) == "weather"
    assert kind_of(at_km("A", 1, code="-")) == "home"
    assert kind_of(at_km("A", 1, code=">")) == "mobile"
    assert kind_of(at_km("A", 1, code=">", speed_kmh=3.0)) == "mobile"
    assert kind_of(at_km("A", 1, code=">", speed_kmh=40.0)) == "moving"
    assert kind_of(at_km("A", 1, code="b", speed_kmh=20.0)) == "moving"       # a bicycle
    assert kind_of(at_km("A", 1, code="-", speed_kmh=40.0)) == "home"        # a house does not move
    assert kind_of(at_km("A", 1, code="-", table="/")) == "home"


def test_a_station_that_is_not_on_the_channel_is_left_out() -> None:
    stations = homes(900)
    assert circle(HOME, stations, NOW) is not None
    old = utc(2026, 10, 21, 10, 59, 0)                                                          # an hour and a minute ago
    assert circle(HOME, [replace_heard(s, old) for s in stations], NOW) is None
    just = utc(2026, 10, 21, 11, 0, 0)                                                       # exactly the window ago: still counted
    assert ALOHA_WINDOW_MIN == 60 and circle(HOME, [replace_heard(s, just) for s in stations], NOW) is not None
    assert circle(HOME, [replace_heard(s, NOW, kind="object") for s in stations], NOW) is None
    gated = [replace_heard(s, NOW, last_rf_at=None, heard_rf=0, heard_rf_gated=1, last_rf_gated_at=NOW) for s in stations]
    assert circle(HOME, gated, NOW) is None                                                     # (an iGate put them on the air: they are not on the channel from where they are)
    internet = [replace_heard(s, NOW, last_rf_at=None, heard_rf=0, heard_is=1, last_is_at=NOW) for s in stations]
    assert circle(HOME, internet, NOW) is None                                                  # (nor are those received from the internet)
    assert circle(HOME, [replace_heard(s, NOW, last_is_at=NOW, heard_is=5) for s in stations], NOW) is not None       # (heard on the radio as well: they count)
    made_up = [replace_heard(s, NOW, last_rf_at=None, heard_rf=0, heard_dummy=1, last_dummy_at=NOW) for s in stations]
    assert circle(HOME, made_up, NOW) is not None                                               # (the Dummy radio's stations are on its channel: the program can be tried)
    me = [replace_heard(s, NOW, is_me=True) for s in stations]
    assert circle(HOME, me, NOW) is None
    nopos = [Station(s.call, first_heard=NOW, last_heard=NOW) for s in stations]
    assert circle(HOME, nopos, NOW) is None


def replace_heard(s: Station, heard: datetime, **kw: object) -> Station:
    out = Station(s.call, first_heard=NOW, last_heard=heard, last_rf_at=heard, heard_rf=1, lat=s.lat, lon=s.lon, symbol_table=s.symbol_table, symbol_code=s.symbol_code)
    for key, value in kw.items():
        setattr(out, key, value)
    return out


def heard_on(stations: list[Station], *radios: RadioId, at: datetime = NOW) -> list[Station]:
    """The stations as heard by these radios at `at` (the station book's `heard_by`)."""
    for station in stations:
        station.heard_by = {radio: RadioHeard(1, at) for radio in radios}
    return stations


def test_the_circle_of_a_radio_counts_the_stations_that_radio_heard() -> None:
    fm, hf = heard_on(homes(450), FM_ID), heard_on(homes(450, first_km=451.0), HF_ID)
    found = circle(HOME, fm + hf, NOW)
    assert found is not None and found.stations == 900, "without a radio named: every station of the air, as before"
    assert circle(HOME, fm + hf, NOW, FM_ID) is None, "the FM radio's channel has half of them: not full"
    assert circle(HOME, fm + heard_on(homes(450, first_km=451.0), FM_ID, HF_ID), NOW, FM_ID) is not None, "a station both radios heard is on the FM channel"
    late = heard_on(homes(450, first_km=451.0), FM_ID, at=NOW - timedelta(minutes=ALOHA_WINDOW_MIN + 1))
    for station in late:
        station.heard_by[HF_ID] = RadioHeard(1, NOW)
    assert circle(HOME, fm + late, NOW, FM_ID) is None, "heard on the air lately, but on FM too long ago"


def test_the_service_draws_the_main_radios_circle_while_its_type_shares_a_channel() -> None:
    clock = FixedClock(NOW)
    book = StationBook(clock)
    book.seed(heard_on(homes(900), FM_ID))
    book.set_me("OH2GBA", *HOME)
    main: list[object] = [SimpleNamespace(id=FM_ID, allowed=FM_ALLOWED)]
    aloha = Aloha(book, clock, main=lambda: main[0])           # type: ignore[arg-type, return-value]
    aloha.refresh()
    assert aloha.radius_km == 900.0, "the FM radio heard them"
    main[0] = SimpleNamespace(id=HF_ID, allowed=HF_ALLOWED)
    aloha.refresh()
    assert aloha.radius_km is None, "an HF main radio has no 1200 baud channel"
    main[0] = None
    aloha.refresh()
    assert aloha.radius_km is None, "no radio, no circle"
    main[0] = SimpleNamespace(id=HF_ID, allowed=FM_ALLOWED)
    aloha.refresh()
    assert aloha.radius_km is None, "a main radio of a shared channel that heard none of them"


def test_no_position_and_no_stations_give_no_circle() -> None:
    assert circle(None, homes(900), NOW) is None
    assert circle(HOME, [], NOW) is None


def test_stations_at_our_own_position_do_not_make_a_circle_of_nothing() -> None:
    assert circle(HOME, [at_km(f"OH2H{n:03d}", 0.0) for n in range(900)], NOW) is None


def test_the_load_that_fills_the_channel_is_the_one_of_the_text() -> None:
    assert ALOHA_PACKETS == 1800


def test_the_service_works_the_circle_out_and_tells_when_it_changes() -> None:
    clock = FixedClock(NOW)
    book = StationBook(clock)
    book.seed(homes(900))
    aloha = Aloha(book, clock)
    told: list[float | None] = []
    aloha.changed.connect(lambda: told.append(aloha.radius_km))
    aloha.refresh()
    assert aloha.radius_km is None and told == []               # no position of ours yet
    book.set_me("OH2GBA", *HOME)
    aloha.refresh()
    aloha.refresh()
    assert aloha.radius_km == 900.0 and told == [900.0]         # (and a second refresh with nothing new tells nothing)
    clock.advance(2 * 3600)
    aloha.refresh()
    assert aloha.radius_km is None and told == [900.0, None]    # the stations were heard too long ago


async def test_the_service_runs_on_its_timer() -> None:
    clock = FixedClock(NOW)
    book = StationBook(clock)
    book.seed(homes(900))
    book.set_me("OH2GBA", *HOME)
    aloha = Aloha(book, clock, every_sec=0.01)
    await aloha.start()
    try:
        assert aloha.radius_km == 900.0
        clock.advance(2 * 3600)
        for _ in range(500):
            if aloha.radius_km is None:
                break
            await asyncio.sleep(0.01)
        assert aloha.radius_km is None
    finally:
        await aloha.stop()


async def test_the_page_is_told_the_radius_in_the_topic_map_and_when_our_position_moves(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, radio=False)
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: "map" in page.topics)
    assert page.topics["map"]["aloha_km"] is None
    lat, lon = e.ctl.config.station_position or (0.0, 0.0)
    now = e.ctl.clock()
    stations = [Station(f"OH2H{n:03d}", first_heard=now, last_heard=now, last_rf_at=now, heard_rf=1, lat=lat + (1.0 + n) / KM_PER_DEGREE, lon=lon, symbol_code="-", symbol_table="/", last_position_at=now,
                        heard_by={FM_ID: RadioHeard(1, now)}) for n in range(900)]                   # (heard by radio 1, the main radio, as the book counts them)
    e.ctl.stationbook.seed(stations)
    e.ctl.aloha.refresh()
    await page.until(lambda: page.topics["map"]["aloha_km"] is not None)
    assert page.topics["map"]["aloha_km"] == pytest.approx(900.0, abs=0.1)


async def test_the_stations_the_hf_radio_heard_make_no_circle_on_the_map(tmp_path: Path) -> None:
    """The composition root gives the circle the main radio (app.py `Aloha(..., main=...)`): 900 stations heard over HF alone make no circle round an FM station (rule 3.8)."""
    e = Env(tmp_path, web=True, radio=False)
    await e.start(connected=False)
    lat, lon = e.ctl.config.station_position or (0.0, 0.0)
    now = e.ctl.clock()
    e.ctl.stationbook.seed([Station(f"OH2H{n:03d}", first_heard=now, last_heard=now, last_rf_at=now, heard_rf=1, lat=lat + (1.0 + n) / KM_PER_DEGREE, lon=lon, symbol_code="-", symbol_table="/",
                                    last_position_at=now, heard_by={HF_ID: RadioHeard(1, now)}) for n in range(900)])
    e.ctl.aloha.refresh()
    assert e.ctl.aloha.radius_km is None


def test_a_station_only_an_igate_put_on_a_radios_channel_is_not_in_that_radios_circle() -> None:
    """Heard direct on the HF radio and, on the FM radio, only in an iGate's third-party packet (stationnotes.note_heard, as the book notes them): not on the FM channel, though the FM radio heard it last."""
    s = at_km("OH1ABC", 5.0)
    note_heard(s, Packet(NOW - timedelta(minutes=5), "in", b"", "OH1ABC", "APRS", (), b">hello", Other("status", ">hello"), radio_id=HF_ID))
    note_heard(s, Packet(NOW - timedelta(minutes=1), "in", b"", "OH2IGATE", "APRS", ("WIDE2-1",), b">hello", Other("status", ">hello"), ThirdParty("OH1ABC", "APRS"), "rf-gated", radio_id=FM_ID))
    since = NOW - timedelta(minutes=ALOHA_WINDOW_MIN)
    assert s.heard_on(FM_ID).last_at == NOW - timedelta(minutes=1) and counted(s, since, HF_ID), "the FM radio heard of it, the HF radio heard it"
    assert not counted(s, since, FM_ID), "not on the FM channel from where it is (before: counted)"
    note_heard(s, Packet(NOW, "in", b"", "OH1ABC", "APRS", ("OH2RCH-2*", "WIDE2*"), b">hello", Other("status", ">hello"), radio_id=FM_ID))
    assert counted(s, since, FM_ID), "heard by a digipeater on the FM channel: it is on it"
