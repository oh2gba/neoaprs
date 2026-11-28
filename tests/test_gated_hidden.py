"""Show Internet packets heard by radio (`igate/show_gated`): off, the packets an iGate put on the air
from the internet (`via` rf-gated) are shown nowhere, except a message or ack to our own call; they
stay in the database and come back when the tick goes on. Direct and digipeated packets are untouched.
A daemon whose radio is fed the three kinds, as the TNC hands them over.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from neoaprs.clock import iso, utc
from neoaprs.packet import IS, RF, RF_GATED, Decoded, Message, Packet, Position, Status, ThirdParty, Via
from neoaprs.route import received_text, through_gateway
from neoaprs.shown import Shown
from neoaprs.stationbook import StationBook
from neoaprs.web.packetwindow import PacketWindow
from tests.support.air import message_info, on_air
from tests.support.env import Env, until
from tests.support.wsclient import WsClient

DIRECT = on_air("OH2AIR", b"=6011.00N/02456.00E-direct", path="WIDE1-1")
DIGIPEATED = on_air("OH2DIG", b"=6012.00N/02457.00E>digipeated", path="OH2RCH-2*,WIDE2-1")
BOTH = on_air("OH2BTH", b"=6013.00N/02458.00E-both ways", path="WIDE1-1")


def gated(source: str, info: bytes) -> bytes:
    """A third-party packet: OH2IGT puts `source`'s internet packet on the air."""
    return on_air("OH2IGT", b"}" + source.encode() + b">APRS,TCPIP,OH2IGT*:" + info, path="WIDE1-1")


GATED_PLACE = gated("OH2NET", b"=6014.00N/02459.00E>from the internet")
GATED_OVERHEARD = gated("OH2NET", message_info("OH2AIR", "hi there", "7"))
GATED_TO_US = gated("OH2MSG", message_info("OH2GBA", "hello", "1"))
GATED_BOTH = gated("OH2BTH", b">a status from the internet")
HEARD = (DIRECT, DIGIPEATED, BOTH, GATED_PLACE, GATED_OVERHEARD, GATED_TO_US, GATED_BOTH)


async def start(tmp_path: Path, show: bool = True) -> tuple[Env, WsClient]:
    e = Env(tmp_path, web=True, settings={} if show else {"igate/show_gated": "false"})
    await e.start()
    page = await e.ws()
    await page.until(lambda: "packets" in page.topics and "stations" in page.topics and "messages" in page.topics)
    for frame in HEARD:
        e.feed(frame)
    await until(lambda: len([p for p in e.ctl.stationbook.stations() if p.call == "OH2BTH" and p.packets == 2]) == 1)
    await until(lambda: e.ctl.stationbook.get("OH2MSG") is not None and e.ctl.stationbook.get("OH2NET") is not None)
    await e.settled()
    return e, page


async def tick(page: WsClient, on: bool) -> None:
    await page.send({"cmd": "set_config", "values": {"igate/show_gated": str(on).lower()}})


def heard(page: WsClient) -> list[str]:
    return sorted(r["tnc2"] for r in page.topics["packets"].values() if r["direction"] == "in")


def overheard(page: WsClient) -> list[str]:
    return sorted(f"{m['from_call']} {m['state']}" for m in page.topics["messages"].values() if m["direction"] == "in")


async def answer(page: WsClient, command: dict[str, Any]) -> dict[str, Any]:
    told = len(page.of(command["cmd"]))
    await page.send(command)
    await page.until(lambda: len(page.of(command["cmd"])) > told)
    return page.of(command["cmd"])[-1]


ALL_STATIONS = {"OH2GBA", "OH2AIR", "OH2DIG", "OH2BTH", "OH2NET", "OH2MSG"}
RADIO_STATIONS = {"OH2GBA", "OH2AIR", "OH2DIG", "OH2BTH"}


async def test_the_tick_is_on_by_default_and_everything_heard_is_shown(tmp_path: Path) -> None:
    e, page = await start(tmp_path)
    assert e.ctl.config.igate_show_gated
    assert page.topics["config"]["values"]["igate/show_gated"] == "true"
    await page.until(lambda: len(heard(page)) == len(HEARD))
    assert set(page.topics["stations"]) == ALL_STATIONS
    await page.until(lambda: overheard(page) == ["OH2MSG received", "OH2NET overheard"])
    both = page.topics["stations"]["OH2BTH"]
    assert (both["packets"], both["heard_rf"], both["heard_rf_gated"]) == (2, 1, 1)
    await e.stop()


async def test_unticked_the_gated_packets_and_stations_heard_only_so_go_from_every_list_and_come_back_when_ticked(
    tmp_path: Path,
) -> None:
    e, page = await start(tmp_path)
    await page.until(lambda: len(heard(page)) == len(HEARD))

    await tick(page, False)
    await page.until(lambda: "OH2NET" not in page.topics["stations"])
    assert set(page.topics["stations"]) == RADIO_STATIONS, "OH2MSG, heard only in a gated message, is not listed"
    both = page.topics["stations"]["OH2BTH"]
    assert (
        both["packets"],
        both["heard_rf"],
        both["heard_rf_gated"],
        both["last_rf_gated_at"],
        both["packets_hour"],
        both["position_via"],
        round(both["lat"], 2),
        both["last_heard"],
    ) == (1, 1, 0, None, 1, "rf", 60.22, both["last_rf_at"])
    await page.until(lambda: len(heard(page)) == 4)
    assert [
        r["sender"] for r in page.topics["packets"].values() if r["direction"] == "in" and r["via"] == "rf-gated"
    ] == ["OH2MSG"], "the message to us stays in the Packets list"
    await page.until(lambda: overheard(page) == ["OH2MSG received"])
    assert len(await e.packets()) >= len(HEARD), "the database keeps every one"
    assert e.ctl.stationbook.get("OH2NET") is not None

    await tick(page, True)
    await page.until(lambda: set(page.topics["stations"]) == ALL_STATIONS)
    await page.until(lambda: len(heard(page)) == len(HEARD))
    await page.until(lambda: overheard(page) == ["OH2MSG received", "OH2NET overheard"])
    assert page.topics["stations"]["OH2BTH"]["packets"] == 2
    await e.stop()


async def test_a_gated_packet_heard_while_unticked_is_kept_and_shown_once_the_tick_is_on(tmp_path: Path) -> None:
    e, page = await start(tmp_path, show=False)
    await page.until(lambda: len(heard(page)) == 4 and set(page.topics["stations"]) == RADIO_STATIONS)
    e.feed(gated("OH2NEW", b"=6015.00N/02455.00E>later"))
    await until(lambda: e.ctl.stationbook.get("OH2NEW") is not None)
    e.feed(on_air("OH2LST", b">heard last", path="WIDE1-1"))
    await page.until(lambda: "OH2LST" in page.topics["stations"])
    assert "OH2NEW" not in page.topics["stations"] and len(heard(page)) == 5
    await tick(page, True)
    await page.until(lambda: "OH2NEW" in page.topics["stations"] and len(heard(page)) == len(HEARD) + 2)
    await e.stop()


async def test_the_counts_the_traffic_the_replay_and_the_track_leave_the_gated_packets_out_while_unticked(
    tmp_path: Path,
) -> None:
    e, page = await start(tmp_path)

    async def shown() -> tuple[object, ...]:
        hours = await answer(page, {"cmd": "packet_history", "call": "OH2IGT", "hours": 1})
        stats = await answer(page, {"cmd": "packet_stats"})
        net = await answer(page, {"cmd": "station_traffic", "call": "OH2NET"})
        msg = await answer(page, {"cmd": "station_traffic", "call": "OH2MSG"})
        replay = await answer(page, {"cmd": "position_history", "hours": 1})
        return (
            sum(hours["counts"]),
            sum(sum(row["counts"]) for row in stats["heard"]),
            len(net["packets"]),
            len(msg["packets"]),
            sorted(set(replay["stations"]) - {"OH2GBA"}),
        )

    assert await shown() == (4, len(HEARD), 2, 2, ["OH2AIR", "OH2BTH", "OH2DIG", "OH2NET"])
    await page.send({"cmd": "station_track", "call": "OH2NET"})
    assert len((await page.expect("station_track"))["points"]) == 1

    await tick(page, False)
    await until(lambda: not e.ctl.config.igate_show_gated)
    assert await shown() == (0, 3, 0, 2, ["OH2AIR", "OH2BTH", "OH2DIG"]), "the message to us is still its traffic"
    await page.send({"cmd": "station_track", "call": "OH2NET"})
    assert (await page.expect("error"))["code"] == "station.unknown"
    await e.stop()


async def test_an_alert_on_a_station_is_not_fired_by_its_gated_packets_while_unticked(tmp_path: Path) -> None:
    e, page = await start(tmp_path, show=False)
    await page.send({"cmd": "set_station_alert", "call": "OH2ALR", "on_air": True, "within_km": None, "direct": False})
    await until(lambda: "OH2ALR" in e.ctl.stationalerts.alerts())
    e.feed(gated("OH2ALR", b">from the internet"))
    await until(lambda: e.ctl.stationbook.get("OH2ALR") is not None)
    e.feed(on_air("OH2ALR", b">on the air", path="WIDE1-1"))
    told = await page.expect("station_alert")
    assert (told["call"], told["kind"]) == ("OH2ALR", "on_air")
    station = e.ctl.stationbook.get("OH2ALR")
    assert station is not None and station.last_rf_at is not None and told["at"] == iso(station.last_rf_at)
    await page.quiet()
    assert len(page.of("station_alert")) == 1
    await e.stop()


async def test_a_restart_with_the_tick_off_still_hides_them_and_counts_the_hour_without_them(tmp_path: Path) -> None:
    first, page = await start(tmp_path, show=False)
    await first.stop()
    second = Env(tmp_path, web=True)
    await second.start()
    page = await second.ws()
    await page.until(lambda: "stations" in page.topics and "packets" in page.topics)
    assert not second.ctl.config.igate_show_gated
    assert set(page.topics["stations"]) == RADIO_STATIONS
    both = page.topics["stations"]["OH2BTH"]
    assert (both["packets"], both["heard_rf_gated"], both["packets_hour"]) == (1, 0, 1)
    assert len(heard(page)) == 4
    await second.stop()


# ---- the station and the packets as the tick leaves them
T0 = utc(2026, 10, 21, 12, 0, 0)
GATE = ThirdParty("OH2AAA", "APRS", ("TCPIP", "OH2IGT*"))


def packet_of(decoded: Decoded, at: datetime, via: Via, source: str = "OH2AAA") -> Packet:
    gated_in = via == RF_GATED
    return Packet(
        at,
        "in",
        b"",
        "OH2IGT" if gated_in else source,
        "APRS",
        ("WIDE1-1",),
        b"",
        decoded,
        via=via,
        third_party=GATE if gated_in else None,
    )


def place(lat: float) -> Position:
    return Position(lat, 24.0, "/", ">")


def test_a_station_heard_only_as_an_igate_put_it_on_the_air_is_not_shown_and_one_heard_both_ways_without_those_packets() -> (
    None
):
    book = StationBook()
    book.take(packet_of(place(60.0), T0, RF_GATED))
    station = book.get("OH2AAA")
    assert station is not None and station.without_gated() is None
    assert Shown(gated=False).station(station) is None and Shown().station(station) is station
    book.take(packet_of(Status("on the air"), T0 + timedelta(minutes=1), RF))
    view = book.get("OH2AAA").without_gated()  # type: ignore[union-attr]
    assert view is not None
    assert (view.packets, view.heard_rf, view.heard_rf_gated, view.last_heard, view.hour.total) == (
        1,
        1,
        0,
        T0 + timedelta(minutes=1),
        1,
    )
    assert (view.lat, view.position_via, view.track, view.symbol_code) == (None, None, [], ""), (
        "the position came from the internet"
    )
    book.take(packet_of(place(61.0), T0 + timedelta(minutes=2), RF))
    view = book.get("OH2AAA").without_gated()  # type: ignore[union-attr]
    assert view is not None and (view.lat, view.position_via) == (61.0, "rf")


def test_with_both_ticks_off_a_station_heard_from_aprs_is_and_through_an_igate_is_not_shown() -> None:
    book = StationBook()
    book.take(packet_of(place(60.0), T0, RF_GATED))
    book.take(packet_of(Status("x"), T0 + timedelta(minutes=1), IS))
    station = book.get("OH2AAA")
    assert station is not None
    assert Shown(internet=False, gated=False).station(station) is None
    shown = Shown(internet=True, gated=False).station(station)
    assert shown is not None and (shown.packets, shown.heard_is, shown.lat) == (1, 1, None)
    assert Shown(internet=False, gated=True).station(station) is not None


def test_a_message_or_ack_to_our_call_is_shown_whatever_the_tick_and_one_to_another_is_not() -> None:
    shown = Shown(gated=False, own="OH2GBA")
    assert shown.packet(packet_of(Message("OH2GBA", "hi", "1"), T0, RF_GATED))
    assert shown.packet(packet_of(Message("oh2gba", "", ack_id="1"), T0, RF_GATED))
    assert not shown.packet(packet_of(Message("OH2ZZZ", "hi", "1"), T0, RF_GATED))
    assert not shown.packet(packet_of(place(60.0), T0, RF_GATED))
    assert shown.packet(packet_of(place(60.0), T0, RF)) and Shown(own="OH2GBA").packet(
        packet_of(place(60.0), T0, RF_GATED)
    )


def test_the_window_shows_the_latest_packets_of_the_view_the_tick_chose_and_keeps_the_others() -> None:
    window = PacketWindow(size=2)
    window.own = "OH2GBA"
    window.add(packet_of(place(60.0), T0, RF))
    window.add(packet_of(Message("OH2GBA", "hi", "1"), T0, RF_GATED))
    for n in range(3):
        window.add(packet_of(place(61.0), T0 + timedelta(seconds=n), RF_GATED))
    assert list(window.whole()) == ["4", "5"]
    window.gated = False
    assert list(window.whole()) == ["1", "2"], "the radio's packet and the message to us, pushed out of the other view"
    window.internet = False
    assert list(window.whole()) == ["1", "2"]
    window.gated = True
    assert list(window.whole()) == ["4", "5"]


def test_a_route_text_tells_a_packet_an_igate_put_on_the_air() -> None:
    assert through_gateway(received_text(("WIDE1-1",), "OH2IGT"))
    assert through_gateway(received_text(("OH2RCH-2*", "WIDE2*"), "OH2IGT"))
    assert not through_gateway(received_text(("OH2RCH-2*", "WIDE2-1")))
    assert not through_gateway(received_text(()))
