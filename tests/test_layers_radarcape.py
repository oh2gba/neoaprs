"""Tests for the layers service with a Radarcape as the aircraft source (neoaprs/services/layers.py
`Radarcape`): timing, back-off, the cut by guard, and the rules of the own receiver.
"""
import asyncio
import json
import logging
from dataclasses import replace
from typing import Any

import pytest

from neoaprs import nodevices
from neoaprs.services.layers import Layers
from neoaprs.updatefetch import FeedAnswer
from tests.support.env import remember_stop, until
from tests.support.fakelayers import layers_server
from tests.support.virtualtime import virtual_time
from tests.test_layers import HOME, Net, Settings, clock, layers

PLACE = "/aircraftlist.json?knownposonly=1"


def cape_row(id: str, lat: float = 60.3, lon: float = 24.9, **extra: Any) -> dict[str, Any]:
    return {"uti": 1794812336, "hex": id, "fli": "FIN7AB", "lat": lat, "lon": lon, "alt": 8000, "gda": "A", "spd": 220, "trk": 90, "lla": 0, "cat": "A3", "typ": "A321", **extra}


def cape(*rows: dict[str, Any]) -> bytes:
    return json.dumps(list(rows)).encode()


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for
    every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")


@pytest.mark.parametrize(("address", "url"), [("cape.local", "http://cape.local" + PLACE), ("192.168.1.160:8080", "http://192.168.1.160:8080" + PLACE)], ids=["host", "port"])
async def test_a_radarcape_is_asked_at_its_one_place_at_the_start_and_then_only_while_a_page_looks_every_5_seconds(address: str, url: str) -> None:
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(200, cape(cape_row("461f2a"), cape_row("4601f6"))))
        service = await layers(net, Settings(map_aircraft="radarcape", map_aircraft_host=address))
        await asyncio.sleep(60)
        assert net.asked == [url], "once at the start, for its state in Settings"
        state = service.states()[0].receiver
        assert service.states()[0].source == "radarcape" and state is not None and (state.state, state.things) == ("receiving", 2)
        service.watch("aircraft", True)
        await asyncio.sleep(21)
        assert net.asked[1:] == [url] * 5, "every 5 seconds while a page looks"
        assert [thing.id for thing in service.table("aircraft").things] == ["461f2a", "4601f6"] and not service.table("aircraft").away
        service.watch("aircraft", False)
        await asyncio.sleep(60)
        assert len(net.asked) == 6


async def test_a_radarcape_with_no_address_is_not_looked_for_and_its_state_is_no_answer(caplog: pytest.LogCaptureFixture) -> None:
    async with virtual_time():
        net = Net()
        with caplog.at_level(logging.INFO, "neoaprs.layers"):
            service = await layers(net, Settings(map_aircraft="radarcape", map_aircraft_host=""))
            service.watch("aircraft", True)
            await asyncio.sleep(300)
        state = service.states()[0].receiver
        assert net.asked == [] and state is not None and state.state == "no_answer" and service.table("aircraft").away
        assert [r.getMessage() for r in caplog.records if r.name == "neoaprs.layers"] == ["the Radarcape without an address: no answer"]


async def test_a_radarcape_that_fails_waits_twice_as_long_each_time_up_to_a_minute_and_says_no_answer_once(caplog: pytest.LogCaptureFixture) -> None:
    async with virtual_time():
        times: list[float] = []

        def nothing(url: str) -> None:
            times.append(asyncio.get_running_loop().time())
        with caplog.at_level(logging.INFO, "neoaprs.layers"):
            service = await layers(Net(nothing), Settings(map_aircraft="radarcape", map_aircraft_host="cape.local"))
            start = asyncio.get_running_loop().time()
            service.watch("aircraft", True)
            await asyncio.sleep(200)
        assert [round(t - start) for t in times] == [0, 10, 30, 70, 130, 190]
        state = service.states()[0].receiver
        assert state is not None and state.state == "no_answer"
        assert [r.getMessage() for r in caplog.records if r.name == "neoaprs.layers"] == ["the Radarcape at cape.local: no answer"]


async def test_an_answer_that_is_not_a_radarcapes_list_is_no_answer() -> None:
    async with virtual_time():
        readsb_file = json.dumps({"now": 1794812336, "aircraft": [{"hex": "aaaaaa", "lat": 60.3, "lon": 24.9}]}).encode()
        service = await layers(Net(lambda url: FeedAnswer(200, readsb_file)), Settings(map_aircraft="radarcape", map_aircraft_host="cape.local"))
        await asyncio.sleep(1)
        state = service.states()[0].receiver
        assert state is not None and state.state == "no_answer"


async def test_a_radarcape_is_cut_by_nothing_but_the_guard_of_2000_newest() -> None:
    far = [cape_row("c00001", 30.0, -90.0), cape_row("c00002", -33.9, 151.2)]
    many = [cape_row(f"d{n:05x}", 60.0, 25.0, lla=n // 100) for n in range(2500)]
    async with virtual_time():
        bodies = [cape(*far), cape(*many)]
        service = await layers(Net(lambda url: FeedAnswer(200, bodies.pop(0) if bodies else cape())), Settings(map_aircraft="radarcape", map_aircraft_host="cape.local", map_radius_km=10))
        await asyncio.sleep(1)
        assert {thing.id for thing in service.table("aircraft").things} == {"c00001", "c00002"}, "thousands of km away: all shown"
        service.watch("aircraft", True)
        await asyncio.sleep(5)
        kept = service.table("aircraft").things
        assert len(kept) == 2000 and {thing.id for thing in kept} == {f"d{n:05x}" for n in range(2000)}, "the newest positions"
        state = service.states()[0].receiver
        assert state is not None and state.things == 2500, "the state says how many it gave"


async def test_a_radarcape_is_asked_with_the_update_check_off_as_an_own_receiver_is_and_its_aircraft_age_out_after_60_s() -> None:
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(200, cape(cape_row("aaaaaa", lla=50), cape_row("bbbbbb", lla=70))))
        service = await layers(net, Settings(map_aircraft="radarcape", map_aircraft_host="cape.local"), environ={"NEOAPRS_UPDATE_CHECK": "0"})
        await asyncio.sleep(1)
        assert net.asked == ["http://cape.local" + PLACE] and [thing.id for thing in service.table("aircraft").things] == ["aaaaaa"]


async def test_a_change_between_the_two_own_receivers_at_the_same_address_makes_the_source_again_and_asks_the_new_place() -> None:
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(200, cape(cape_row("aaaaaa"))) if url.endswith(PLACE) else None)
        settings = Settings(map_aircraft="receiver", map_aircraft_host="cape.local:8080")
        service = await layers(net, settings)
        await asyncio.sleep(1)
        assert service.states()[0].receiver is not None and service.states()[0].receiver.state == "no_answer"
        settings.config = replace(settings.config, map_aircraft="radarcape")
        service.config_changed(settings.config)
        await asyncio.sleep(1)
        assert net.asked[-1] == "http://cape.local:8080" + PLACE
        state = service.states()[0].receiver
        assert state is not None and state.state == "receiving" and service.table("aircraft").source == "radarcape"


# ---- a fake Radarcape on the loopback

async def test_a_fake_radarcape_on_this_computer_is_asked_its_list_without_the_station_and_its_aircraft_reach_the_table(under_the_switch: None) -> None:
    device = await layers_server()
    device.route(PLACE, body=cape(cape_row("461f2a", typ="AT75", cat="A2"), cape_row("4601f6", gda="G")))
    service = Layers(Settings(map_aircraft="radarcape", map_aircraft_host=device.address, station_call="OH2GBA-7"), lambda: HOME, "0.21.0", "linux", environ={})
    remember_stop(service.stop)
    await service.start()
    service.watch("aircraft", True)
    await until(lambda: len(device.requests) >= 2, 15.0)
    assert set(device.paths()) == {PLACE}
    assert "OH2GBA" not in json.dumps(device.requests), "the call is in neither the place asked nor the headers"
    (plane,) = service.table("aircraft").things
    assert (plane.id, plane.designator, plane.category) == ("461f2a", "AT75", "A2"), "the one on the ground is left out"


async def test_under_the_no_devices_switch_a_radarcape_that_is_not_on_this_computer_is_no_answer(under_the_switch: None) -> None:
    service = Layers(Settings(map_aircraft="radarcape", map_aircraft_host="192.0.2.160"), lambda: HOME, "0.21.0", "linux", clock=clock, environ={})
    remember_stop(service.stop)
    await service.start()
    await until(lambda: (state := service.states()[0].receiver) is not None and state.state == "no_answer", 15.0)
