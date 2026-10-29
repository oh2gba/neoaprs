"""The positions over the last hours for the replay of the map (`position_history`, neoaprs/web/replaywire.py): the packet log finds every position heard in the span (the sender inside a third-party packet,
an object or item by its name, a killed one left out), and ours under our call, but not the copies of others' packets the digipeater sent; the points of a station are thinned; and the page that asked is
answered, with an error for hours out of range. While Internet stations (`igate/enabled`) is off no packet that came from APRS-IS is read, whenever it came: a station heard both ways keeps what the
radio heard, an iGate's third-party packet heard on the radio stays, and so does ours; the count of packets read is of what is shown. A longer span is thinned more (a week of a busy feed stays a few MB), begins at the oldest packet the log keeps when it reaches back further, and its
thinning stays inside the gap the page drives a station across."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs.aprsisline import parse_is_line
from neoaprs.clock import iso
from neoaprs.geo import Thinning, thinned
from neoaprs.packetcodec import PacketRow, packet_row, stamp
from neoaprs.packetlog import PacketLog
from neoaprs.packetsql import PACKET_COLUMNS
from neoaprs.store import DB_NAME
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.policy import LOG_KEEP_DAYS
from neoaprs.web.replaywire import GLIDE_MAX_MIN, SPAN_DAYS, PositionHistoryMsg
from neoaprs.web.wirebase import HISTORY_MAX_HOURS as MAX_HOURS
from neoaprs.web.views import REPLAY_THINNING, replay_thinning, replay_tracks
from tests.support.clock import FixedClock
from tests.support.env import Env, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.storedb import store_at
from tests.support.weather import T0, heard


def position(source: str, lat: str, at, direction: str = "in"):
    return heard(f"!{lat}N/02456.00E-test".encode(), source, at, direction)


async def test_the_log_finds_the_positions_of_the_span_by_station(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    minute = timedelta(minutes=1)
    for packet in (
        position("OH2RDG", "6010.00", T0 - 90 * minute),                                          # before the span
        position("OH2RDG", "6010.00", T0),
        position("OH2RDG", "6011.00", T0 + minute),
        position("OH2RDG", "6011.00", T0 + 2 * minute, direction="out"),                          # the digipeater's copy: not ours
        position("OH2GBA", "6012.00", T0 + 3 * minute, direction="out"),                          # our beacon
        heard(b";LEADER   *092345z6013.00N/02456.00E>convoy", "OH2XYZ", T0 + 4 * minute),
        heard(b";GONE     _092345z6013.00N/02456.00E>killed", "OH2XYZ", T0 + 5 * minute),
        heard(b")AID!6014.00N/02456.00EA aid", "OH2GBA", T0 + 6 * minute, direction="out"),       # an item of ours, by its name
        heard(b"}OH7ABC>APRS,TCPIP,OH2GTE*:!6015.00N/02456.00E-gated", "OH2GTE", T0 + 7 * minute),
        heard(b":OH2GBA   :hello{7", "OH2RDG", T0 + 8 * minute),                                  # no position
        parse_is_line("OH7XYZ>APRS,TCPIP*,qAC,T2:!6016.00N/02456.00E-from the internet", T0 + 9 * minute),
        parse_is_line("OH2IGT>APRS,TCPIP*,qAR,OH2IGT:}OH7DEF>APRS,TCPIP,OH2IGT*:!6017.00N/02456.00E-inside", T0 + 10 * minute),
    ):
        assert log.append(packet)
    found = await log.position_history(T0 - minute, "OH2GBA", lambda: Thinning(0, 0))
    assert {station: [(at - T0, round(lat, 4)) for at, lat, _ in points] for station, points in found.tracks.items()} == {
        "OH2RDG": [(timedelta(0), 60.1667), (minute, 60.1833)], "OH2GBA": [(3 * minute, 60.2)], "LEADER": [(4 * minute, 60.2167)], "AID": [(6 * minute, 60.2333)],
        "OH7ABC": [(7 * minute, 60.25)], "OH7XYZ": [(9 * minute, 60.2667)], "OH7DEF": [(10 * minute, 60.2833)]}
    assert found.begins == T0 - 90 * minute, "whole from the oldest packet the log keeps"
    latest = await log.position_history(T0 - minute, "OH2GBA", lambda: Thinning(0, 0), count=2)
    assert list(latest.tracks) == ["OH7XYZ", "OH7DEF"], "the latest, when there are more than the count"
    assert latest.begins == T0 + 9 * minute, "whole from the first of them"
    assert (await log.position_history(T0 + 11 * minute, "OH2GBA", lambda: Thinning(0, 0))).tracks == {}


def test_a_track_is_thinned_and_keeps_its_last_point_and_where_it_was_before_it_moved() -> None:
    second = timedelta(seconds=1)
    track = [(T0, 60.0, 25.0), (T0 + 10 * second, 60.001, 25.0), (T0 + 40 * second, 60.00005, 25.0), (T0 + 60 * second, 60.001, 25.0), (T0 + 70 * second, 60.002, 25.0)]
    assert thinned(track, 10, 30) == [track[0], track[2], track[3], track[4]], "too soon (10 s); too near (5 m) but where it still was before it moved (111 m, kept); the last always"
    assert thinned(track[:1], 10, 30) == track[:1]
    assert thinned([], 10, 30) == []
    still = [(T0 + i * 600 * second, 60.0, 25.0) for i in range(10)]
    assert thinned(still, 10, 30) == [still[0], still[-1]], "a station that never moved: where it was first heard, and last"
    parked = [(T0 + i * 1800 * second, 60.0, 25.0) for i in range(5)] + [(T0 + 7260 * second, 60.01, 25.0), (T0 + 7320 * second, 60.02, 25.0)]
    assert thinned(parked, 300, 300) == [parked[0], parked[4], parked[5], parked[6]], "parked two hours, then off: it waits at the parking place until it was last heard there"
    fast = [(T0 + i * 30 * second, 60.0 + i * 0.005, 25.0) for i in range(21)]
    assert thinned(fast, 300, 300) == fast[::10], "driving with a beacon every 30 s: a point every five minutes, nothing put back"


def test_the_longer_the_span_the_coarser_the_thinning_and_always_inside_the_glide() -> None:
    assert [replay_thinning(hours) for hours in (1, 24, 48, 72, MAX_HOURS)] == [(10, 30), (10, 30), (200, 120), (200, 120), (300, 300)]
    assert MAX_HOURS == LOG_KEEP_DAYS * 24 and SPAN_DAYS[-1] == LOG_KEEP_DAYS, "the longest span is all the packet log keeps"
    assert all(seconds * 3 <= GLIDE_MAX_MIN * 60 for _, _, seconds in REPLAY_THINNING), "a thinned trip still glides: its points are well inside the page's gap"


def test_the_tracks_of_the_answer_are_by_station_and_rounded() -> None:
    found = {"OH2RDG": [(T0, 60.1234567, 24.9876543), (T0 + timedelta(minutes=1), 60.2, 24.9)], "LEADER": [(T0, 60.2, 24.9)]}
    assert replay_tracks(found) == {"OH2RDG": [[iso(T0), 60.12346, 24.98765], [iso(T0 + timedelta(minutes=1)), 60.2, 24.9]], "LEADER": [[iso(T0), 60.2, 24.9]]}


def week_of_a_feed(now, fixed: int, cars: int) -> list[PacketRow]:
    """A week of an APRS-IS feed as rows of the packet log: `fixed` stations that beacon every 10 minutes from one place, and `cars` that each drive three hours a day at 90 km/h with a beacon a minute and
    are parked the rest of the day with one every 30 minutes. A packet made once by the parser and copied with another time, source and place (the parser for each would take minutes)."""
    template = packet_row(position("OH2RDG", "6010.00", now))
    decoded = json.loads(template.decoded)
    rows: list[PacketRow] = []

    def add(at, source: str, lat: float, lon: float) -> None:
        rows.append(template._replace(heard_at=stamp(at), source=source, decoded=json.dumps({**decoded, "lat": lat, "lon": lon})))

    start = now - timedelta(days=7)
    for n in range(fixed):
        for i in range(7 * 24 * 6):
            add(start + timedelta(minutes=10 * i, seconds=n), f"OH{n:04d}", 60 + n / 1000, 25.0)
    for n in range(cars):
        for day in range(7):
            morning = start + timedelta(days=day, hours=7, seconds=n)
            for i in range(180):                                                        # driving, a beacon each minute
                add(morning + timedelta(minutes=i), f"OH{n:03d}-9", 60.5 + n / 100 + i * 0.0135, 25.5)
            for i in range(42):                                                         # then parked, a beacon each half hour
                add(morning + timedelta(hours=3, minutes=30 * i), f"OH{n:03d}-9", 60.5 + n / 100 + 179 * 0.0135, 25.5)
    return sorted(rows, key=lambda row: row.heard_at)


async def test_a_week_of_a_feed_is_thinned_to_what_shows_and_stays_small(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    now = e.now()
    rows = week_of_a_feed(now, fixed=40, cars=6)
    await e.ctl.packetlog.db.write(lambda conn: conn.executemany(f"INSERT INTO packet ({', '.join(PACKET_COLUMNS)}) VALUES ({', '.join('?' * len(PACKET_COLUMNS))})", rows))
    await page.send({"cmd": "position_history", "hours": MAX_HOURS})
    sent = await page.expect("position_history")
    answer = PositionHistoryMsg.model_validate_json(json.dumps(sent))
    assert (answer.start, answer.end, len(answer.stations)) == (iso(now - timedelta(hours=MAX_HOURS)), iso(now), 46)
    assert all(len(answer.stations[f"OH{n:04d}"]) == 2 for n in range(40)), "a fixed station: where it was first heard, and last"
    car = answer.stations["OH000-9"]
    assert 7 * 36 <= len(car) <= 7 * 40, "a car: a point every five minutes of its three hours a day, and where it stopped and was last heard parked"
    drives = [datetime.fromisoformat(b[0]) - datetime.fromisoformat(a[0]) for a, b in zip(car, car[1:], strict=False) if 0 < abs(b[1] - a[1]) < 0.1]
    assert len(drives) > 7 * 30 and max(drives) <= timedelta(minutes=GLIDE_MAX_MIN), "on the road it goes from point to point within the glide"
    assert len(json.dumps(sent)) < 250_000
    await e.stop()


async def test_the_page_that_asked_is_answered_with_the_tracks_of_the_span(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page, other = await e.ws(), await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    now = e.now()
    for minutes, lat in ((-90, "6009.00"), (-30, "6010.00"), (-29.75, "6010.00"), (-20, "6011.00")):
        assert e.ctl.packetlog.append(position("OH2RDG", lat, now + timedelta(minutes=minutes)))
    await e.settled()
    await page.send({"cmd": "position_history", "hours": 1})
    answer = PositionHistoryMsg.model_validate_json(json.dumps(await page.expect("position_history")))
    assert (answer.hours, answer.start, answer.end) == (1, iso(now - timedelta(hours=1)), iso(now))
    assert answer.stations["OH2RDG"] == [(iso(now - timedelta(minutes=30)), 60.16667, 24.93333), (iso(now - timedelta(minutes=20)), 60.18333, 24.93333)], "the same place 15 s after is left out"
    assert other.of("position_history") == [], "only the page that asked is answered"
    await page.send({"cmd": "position_history", "hours": 24})
    await page.until(lambda: len(page.of("position_history")) == 2)
    assert page.of("position_history")[-1]["start"] == iso(now - timedelta(minutes=90)), "a span that reaches back further than the log begins at the oldest packet kept"
    await e.stop()


async def test_without_the_internet_the_log_reads_what_was_on_the_air_and_ours(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    minute = timedelta(minutes=1)
    for packet in (
        position("OH2RDG", "6010.00", T0),                                                                          # heard on the radio ...
        parse_is_line("OH2RDG>APRS,TCPIP*,qAC,T2:!6011.00N/02456.00E-and from the internet", T0 + minute),        # ... and the same station over APRS-IS
        position("OH2RDG", "6012.00", T0 + 2 * minute),
        position("OH2GBA", "6013.00", T0 + 3 * minute, direction="out"),                                           # our beacon
        heard(b")AID!6014.00N/02456.00EA aid", "OH2GBA", T0 + 4 * minute, direction="out"),                        # an item of ours
        heard(b"}OH7ABC>APRS,TCPIP,OH2GTE*:!6015.00N/02456.00E-gated", "OH2GTE", T0 + 5 * minute),                 # an iGate put it on the air: heard on the radio
        parse_is_line("OH7XYZ>APRS,TCPIP*,qAC,T2:!6016.00N/02456.00E-from the internet", T0 + 6 * minute),
        parse_is_line("OH2IGT>APRS,TCPIP*,qAR,OH2IGT:}OH7DEF>APRS,TCPIP,OH2IGT*:!6017.00N/02456.00E-inside", T0 + 7 * minute),
    ):
        assert log.append(packet)
    ours = await log.position_history(T0 - minute, "OH2GBA", lambda: Thinning(0, 0), internet=False)
    assert {station: [at - T0 for at, _, _ in points] for station, points in ours.tracks.items()} == {
        "OH2RDG": [timedelta(0), 2 * minute], "OH2GBA": [3 * minute], "AID": [4 * minute], "OH7ABC": [5 * minute]}, "a station heard both ways keeps what the radio heard, an iGate's packet stays"
    everything = await log.position_history(T0 - minute, "OH2GBA", lambda: Thinning(0, 0))
    assert set(everything.tracks) == {"OH2RDG", "OH2GBA", "AID", "OH7ABC", "OH7XYZ", "OH7DEF"} and len(everything.tracks["OH2RDG"]) == 3
    latest = await log.position_history(T0 - minute, "OH2GBA", lambda: Thinning(0, 0), count=2, internet=False)
    assert (list(latest.tracks), latest.begins) == (["AID", "OH7ABC"], T0 + 4 * minute), "the count is of what is shown: the internet's later packets take no room"


async def test_the_replay_shows_the_internet_only_while_internet_stations_is_on(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = Env(tmp_path, web=True, settings={"igate/enabled": "true", "igate/server": server.address, "igate/password": "19628"})
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    now = e.now()
    for packet in (position("OH2RDG", "6010.00", now - timedelta(minutes=30)), position("OH2GBA", "6011.00", now - timedelta(minutes=25), direction="out"),
                   parse_is_line("OH7XYZ>APRS,TCPIP*,qAC,T2:!6016.00N/02456.00E-from the internet", now - timedelta(minutes=20))):
        assert e.ctl.packetlog.append(packet)
    await e.settled()
    await page.send({"cmd": "position_history", "hours": 1})
    assert set((await page.expect("position_history"))["stations"]) == {"OH2RDG", "OH2GBA", "OH7XYZ"}
    await page.send({"cmd": "set_config", "values": {"igate/enabled": "false"}})
    await until(lambda: not e.ctl.config.igate_enabled)
    await page.send({"cmd": "position_history", "hours": 1})
    await page.until(lambda: len(page.of("position_history")) == 2)
    assert set(page.of("position_history")[-1]["stations"]) == {"OH2RDG", "OH2GBA"}, "the internet's packets are still in the log, and left out"
    await e.stop()


@pytest.mark.parametrize("hours", [0, MAX_HOURS + 1, "3"])
async def test_hours_out_of_range_are_an_error(tmp_path: Path, hours: object) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "position_history", "hours": hours})
    assert (await page.expect("error"))["text"].startswith("position_history")
    assert page.of("position_history") == []
    await e.stop()
