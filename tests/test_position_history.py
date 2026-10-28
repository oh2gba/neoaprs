"""The positions over the last hours for the replay of the map (`position_history`, neoaprs/web/replaywire.py): the packet log finds every position heard in the span (the sender inside a third-party packet,
an object or item by its name, a killed one left out), and ours under our call, but not the copies of others' packets the digipeater sent; the points of a station are thinned; and the page that asked is
answered, with an error for hours out of range."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.aprsisline import parse_is_line
from neoaprs.clock import iso
from neoaprs.geo import thinned
from neoaprs.packetlog import PacketLog
from neoaprs.store import DB_NAME
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.replaywire import PositionHistoryMsg
from neoaprs.web.views import replay_tracks
from tests.support.clock import FixedClock
from tests.support.env import Env
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
    found = await log.position_history(T0 - minute, "OH2GBA")
    assert [(station, at - T0, round(lat, 4)) for station, at, lat, _ in found] == [
        ("OH2RDG", timedelta(0), 60.1667), ("OH2RDG", minute, 60.1833), ("OH2GBA", 3 * minute, 60.2), ("LEADER", 4 * minute, 60.2167), ("AID", 6 * minute, 60.2333),
        ("OH7ABC", 7 * minute, 60.25), ("OH7XYZ", 9 * minute, 60.2667), ("OH7DEF", 10 * minute, 60.2833)]
    assert [station for station, *_ in await log.position_history(T0 - minute, "OH2GBA", count=2)] == ["OH7XYZ", "OH7DEF"], "the latest, when there are more than the count"
    assert await log.position_history(T0 + 11 * minute, "OH2GBA") == []


def test_a_track_is_thinned_and_keeps_its_last_point() -> None:
    second = timedelta(seconds=1)
    track = [(T0, 60.0, 25.0), (T0 + 10 * second, 60.001, 25.0), (T0 + 40 * second, 60.00005, 25.0), (T0 + 60 * second, 60.001, 25.0), (T0 + 70 * second, 60.002, 25.0)]
    assert thinned(track, 10, 30) == [track[0], track[3], track[4]], "too soon (10 s), too near (5 m), kept (60 s and 111 m), the last always"
    assert thinned(track[:1], 10, 30) == track[:1]
    assert thinned([], 10, 30) == []
    still = [(T0 + i * 600 * second, 60.0, 25.0) for i in range(10)]
    assert thinned(still, 10, 30) == [still[0], still[-1]], "a station that never moved: where it was first heard, and last"


def test_the_tracks_of_the_answer_are_by_station_and_rounded() -> None:
    found = [("OH2RDG", T0, 60.1234567, 24.9876543), ("LEADER", T0, 60.2, 24.9), ("OH2RDG", T0 + timedelta(minutes=1), 60.2, 24.9)]
    assert replay_tracks(found) == {"OH2RDG": [[iso(T0), 60.12346, 24.98765], [iso(T0 + timedelta(minutes=1)), 60.2, 24.9]], "LEADER": [[iso(T0), 60.2, 24.9]]}


async def test_the_page_that_asked_is_answered_with_the_tracks_of_the_span(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page, other = await e.ws(), await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    now = e.now()
    for minutes, lat in ((-90, "6009.00"), (-30, "6010.00"), (-29, "6010.00"), (-20, "6011.00")):
        assert e.ctl.packetlog.append(position("OH2RDG", lat, now + timedelta(minutes=minutes)))
    await e.settled()
    await page.send({"cmd": "position_history", "hours": 1})
    answer = PositionHistoryMsg.model_validate_json(json.dumps(await page.expect("position_history")))
    assert answer.hours == 1 and answer.start == iso(now - timedelta(hours=1))
    assert answer.stations["OH2RDG"] == [(iso(now - timedelta(minutes=30)), 60.16667, 24.93333), (iso(now - timedelta(minutes=20)), 60.18333, 24.93333)], "the same place a minute after is left out"
    assert other.of("position_history") == [], "only the page that asked is answered"
    await e.stop()


@pytest.mark.parametrize("hours", [0, 25, "3"])
async def test_hours_out_of_range_are_an_error(tmp_path: Path, hours: object) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "position_history", "hours": hours})
    assert (await page.expect("error"))["text"].startswith("position_history")
    assert page.of("position_history") == []
    await e.stop()
