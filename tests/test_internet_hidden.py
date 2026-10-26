"""Internet stations off hides the internet and keeps it (neoaprs/web/topics.py, `Station.radio_view`, neoaprs/web/packetwindow.py): while `igate/enabled` is off the pages are shown no station known only from APRS-IS and no packet from it, and a station heard both
ways has its radio side only (no internet count or time, the position the radio gave); the database keeps everything, and turning the setting on shows it all again without a restart."""
from datetime import timedelta
from pathlib import Path

from neoaprs.packet import IS
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
