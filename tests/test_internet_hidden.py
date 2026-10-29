"""Internet stations off hides the internet and keeps it (neoaprs/web/topics.py, `Station.radio_view`, neoaprs/web/packetwindow.py): while `igate/enabled` is off the pages are shown no station known only from APRS-IS and no packet from it, and a station heard both
ways has its radio side only (no internet count or time, the position the radio gave); the database keeps everything, and turning the setting on shows it all again without a restart."""
import random
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs.aprsextension import Extensions
from neoaprs.aprsstorm import Storm
from neoaprs.clock import utc
from neoaprs.packet import IS, RF, Decoded, Message, Packet, Position, Status, Via
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from tests.support.air import from_internet, on_air
from tests.support.env import Env, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.wsclient import WsClient

RADIO_AT = b"=6101.00N/02501.00E-by radio"
NET_AT = b"=6012.34N/02456.78E-by the net"


async def start(tmp_path: Path, enabled: bool = True) -> tuple[Env, WsClient]:
    """A daemon with the internet stations on (a fake APRS-IS server), in which OH2BT was heard on the radio and then from the internet, OH2NET only from the internet and OH2AIR only on the radio; and a page."""
    server = await fake_aprsis()
    e = Env(tmp_path, web=True, settings={"igate/enabled": str(enabled).lower(), "igate/server": server.address, "igate/password": "19628"})
    await e.start()
    page = await e.ws()
    await page.until(lambda: "packets" in page.topics and "stations" in page.topics)
    e.feed(on_air("OH2BT", RADIO_AT, path="OH2RCH-2*,WIDE2-1"))
    e.feed(on_air("OH2AIR", RADIO_AT))
    await until(lambda: e.ctl.stationbook.get("OH2BT") is not None and e.ctl.stationbook.get("OH2AIR") is not None)
    later = e.now() + timedelta(minutes=5)
    e.ctl.hear_internet(from_internet("OH2BT", NET_AT, later))
    e.ctl.hear_internet(from_internet("OH2NET", NET_AT, later))
    await until(lambda: e.ctl.stationbook.get("OH2NET") is not None)
    return e, page


async def switch(page: WsClient, on: bool) -> None:
    await page.send({"cmd": "set_config", "values": {"igate/enabled": str(on).lower()}})


async def test_turning_the_internet_off_hides_what_only_it_knows_and_leaves_the_radio_side_of_the_rest_and_turning_it_on_shows_it_again(tmp_path: Path) -> None:
    e, page = await start(tmp_path)
    await page.until(lambda: "OH2NET" in page.topics["stations"] and page.topics["stations"]["OH2BT"]["heard_is"] == 1)
    both = page.topics["stations"]["OH2BT"]
    assert (both["position_via"], round(both["lat"], 3), both["last_is_at"] is not None, both["packets"]) == ("is", 60.206, True, 2)
    assert sorted(r["via"] for r in page.topics["packets"].values()) == ["is", "is", "rf", "rf"]

    await switch(page, False)
    await page.until(lambda: "OH2NET" not in page.topics["stations"])
    assert set(page.topics["stations"]) == {"OH2GBA", "OH2BT", "OH2AIR"}
    both = page.topics["stations"]["OH2BT"]
    assert (both["heard_is"], both["last_is_at"], both["packets"], both["position_via"], round(both["lat"], 3), round(both["lon"], 3), len(both["track"]), both["last_heard"]) == (0, None, 1, "rf", 61.017, 25.017, 1, both["last_rf_at"])
    assert (both["heard_rf"], both["last_route"], both["can_message"], both["last_comment"]) == (1, "via OH2RCH-2", True, "by radio")
    await page.until(lambda: {r["via"] for r in page.topics["packets"].values()} == {"rf"})
    assert len(page.topics["packets"]) == 2

    packets = await e.packets()
    assert sorted(p.via for p in packets) == ["is", "is", "rf", "rf"], "everything is still in the database"
    assert e.ctl.stationbook.get("OH2NET") is not None and e.ctl.stationbook.get("OH2BT").heard_is == 1  # type: ignore[union-attr]

    await switch(page, True)
    await page.until(lambda: "OH2NET" in page.topics["stations"] and page.topics["stations"]["OH2BT"]["heard_is"] == 1)
    both = page.topics["stations"]["OH2BT"]
    assert (both["position_via"], round(both["lat"], 3), both["packets"], len(both["track"])) == ("is", 60.206, 2, 2)
    await page.until(lambda: len(page.topics["packets"]) == 4)
    await e.stop()


async def test_a_packet_that_comes_while_the_internet_is_hidden_is_not_shown_and_the_window_keeps_the_radios_packets_the_internet_would_push_out(tmp_path: Path) -> None:
    e, page = await start(tmp_path, enabled=False)
    await page.until(lambda: len(page.topics["packets"]) == 2 and "OH2BT" in page.topics["stations"])
    assert set(page.topics["stations"]) == {"OH2GBA", "OH2BT", "OH2AIR"} and len(page.topics["packets"]) == 2
    e.ctl.hear_internet(from_internet("OH2NET", NET_AT, e.now() + timedelta(minutes=9)))
    await e.settled()
    await page.send({"cmd": "ping"})
    await page.expect("pong")
    assert "OH2NET" not in page.topics["stations"] and len(page.topics["packets"]) == 2
    window = e.server.api.topics.window  # type: ignore[union-attr]
    for n in range(window.size + 5):
        e.ctl.hear_internet(from_internet(f"OH2X{n:02d}", NET_AT, e.now() + timedelta(minutes=10, seconds=n)))
    await e.settled()
    assert len(window.rows) <= 2 * window.size and len(window.whole()) == 2, "the internet's packets are kept for showing them again, the radio's are not pushed out"
    await switch(page, True)
    await page.until(lambda: len(page.topics["packets"]) == window.size)
    assert {r["via"] for r in page.topics["packets"].values()} == {IS}
    await e.stop()


async def test_a_restart_with_the_internet_off_still_shows_a_station_heard_both_ways_where_the_radio_put_it(tmp_path: Path) -> None:
    first, page = await start(tmp_path)
    await switch(page, False)
    await page.until(lambda: "OH2NET" not in page.topics["stations"])
    await first.settled()
    await first.stop()
    second = Env(tmp_path, web=True)
    await second.start()
    page = await second.ws()
    await page.until(lambda: "stations" in page.topics)
    assert not second.ctl.config.igate_enabled
    assert set(page.topics["stations"]) == {"OH2GBA", "OH2BT", "OH2AIR"}
    both = page.topics["stations"]["OH2BT"]
    assert (both["heard_is"], both["position_via"], round(both["lat"], 3), both["packets"], len(both["track"])) == (0, "rf", 61.017, 1, 1)
    assert both["packets_hour"] == 1
    await second.stop()


# ---- the radio view of a station is the station a book that heard only the radio would hold
T0 = utc(2026, 10, 21, 12, 0, 0)


def heard(decoded: Decoded, at: datetime, via: Via) -> Packet:
    return Packet(at, "in", b"", "OH2AAA", "APRS", ("OH2RCH-2*",) if via != IS else (), b"", decoded, via=via)


def place(lat: float, lon: float, code: str = ">", comment: str = "", **more: object) -> Position:
    return Position(lat, lon, "/", code, comment, **more)  # type: ignore[arg-type]


def view_of(book: StationBook) -> Station:
    station = book.get("OH2AAA")
    assert station is not None
    view = station.radio_view()
    assert view is not None
    return view


def test_the_radio_view_of_a_station_whose_only_position_came_from_the_internet_has_no_trace_of_it() -> None:
    book = StationBook()
    book.take(heard(place(60.1, 24.9, "-", "internet only comment", extensions=Extensions(range_km=40.0), storm=Storm("HC"), sign="55"), T0, IS))
    book.take(heard(Status("on the air"), T0 + timedelta(minutes=1), RF))
    view = view_of(book)
    assert (view.lat, view.lon, view.last_position_at, view.position_via, view.track) == (None, None, None, None, [])
    assert (view.symbol_table, view.symbol_code, view.last_comment, view.extensions, view.storm, view.sign) == ("", "", "", None, None, None)
    assert view.last_status == "on the air" and view.packets == 1
    whole = book.get("OH2AAA")
    assert whole is not None and (whole.symbol_code, whole.last_comment, whole.sign) == ("-", "internet only comment", "55"), "the station itself is as it was"


def test_the_radio_view_keeps_what_the_radios_position_said_when_a_later_one_from_the_internet_says_otherwise() -> None:
    book = StationBook()
    book.take(heard(place(60.0, 24.0, ">", "by radio", extensions=Extensions(range_km=40.0), storm=Storm("TS"), sign="12"), T0, RF))
    book.take(heard(place(61.0, 25.0, "-", "by the net", sign="99"), T0 + timedelta(minutes=1), IS))
    view = view_of(book)
    assert (view.lat, view.symbol_code, view.last_comment, view.extensions, view.storm, view.sign) == (60.0, ">", "by radio", Extensions(range_km=40.0), Storm("TS"), "12")


def test_the_track_of_the_radio_view_has_the_positions_heard_on_the_radio_before_the_first_packet_from_the_internet_even_when_that_had_no_position() -> None:
    book = StationBook()
    book.take(heard(place(60.0, 24.0), T0, RF))
    book.take(heard(place(60.01, 24.01), T0 + timedelta(minutes=10), RF))
    book.take(heard(Status("x"), T0 + timedelta(minutes=11), IS))
    book.take(heard(place(60.02, 24.02), T0 + timedelta(minutes=20), RF))
    station = book.get("OH2AAA")
    assert station is not None and len(station.track) == 3
    assert [(lat, lon) for _, lat, lon in view_of(book).track] == [(60.0, 24.0), (60.01, 24.01), (60.02, 24.02)]


def test_a_position_from_the_internet_before_the_radios_does_not_start_the_radios_track() -> None:
    book = StationBook()
    book.take(heard(place(61.0, 25.0), T0, IS))
    book.take(heard(place(60.0, 24.0), T0 + timedelta(minutes=10), RF))
    assert len(book.get("OH2AAA").track) == 2 and [(lat, lon) for _, lat, lon in view_of(book).track] == [(60.0, 24.0)]  # type: ignore[union-attr]


RADIO_FIELDS = ("symbol_table", "symbol_code", "extensions", "storm", "sign", "altitude_m", "course_deg", "speed_kmh", "lat", "lon", "last_position_at", "position_via", "last_comment", "packets", "heard_rf", "heard_rf_gated",
                "heard_is", "last_heard", "last_path")


def session(seed: int) -> tuple[StationBook, StationBook]:
    """A book that heard a random run of packets of one station, from the radio and the internet, and one that heard only those of the radio."""
    rnd = random.Random(seed)
    everything, radio = StationBook(), StationBook()
    at = T0
    for _ in range(rnd.randint(1, 14)):
        at += timedelta(seconds=rnd.choice([1, 20, 400, 4000]))
        kind = rnd.choice(["position", "position", "status", "message"])
        decoded: Decoded = Status(rnd.choice(["s1", "s2"])) if kind == "status" else Message("OH2ZZZ", "hi")
        if kind == "position":
            decoded = place(60 + rnd.random(), 24 + rnd.random(), rnd.choice([">", "-"]), rnd.choice(["a", "b"]), speed_kmh=rnd.choice([None, 10.0]), extensions=rnd.choice([None, Extensions(range_km=20.0), Extensions(range_km=60.0)]),
                            storm=rnd.choice([None, Storm("TS")]), sign=rnd.choice([None, "12"]))
        packet = heard(decoded, at, rnd.choice([IS, IS, RF]))
        everything.take(packet)
        if packet.via != IS:
            radio.take(packet)
    return everything, radio


def test_the_radio_view_equals_the_station_of_a_book_that_heard_only_the_radio_in_a_thousand_random_runs() -> None:
    wrong: list[tuple[int, str]] = []
    for seed in range(1000):
        everything, radio = session(seed)
        view, expected = everything.get("OH2AAA").radio_view(), radio.get("OH2AAA")  # type: ignore[union-attr]
        if expected is None or view is None:
            assert expected is None and view is None, seed
            continue
        wrong += [(seed, name) for name in RADIO_FIELDS if getattr(view, name) != getattr(expected, name)]
        if view.track != expected.track:
            wrong.append((seed, "track"))
        if view.hour.total != expected.hour.total:
            wrong.append((seed, "hour"))
    assert wrong == []
