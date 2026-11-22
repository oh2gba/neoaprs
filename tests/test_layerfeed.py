"""Tests for pages that look at a traffic layer (neoaprs/web/layerfeed.py, `layer_look`,
`layer_things`): the table is sent at once, the service is told when looking starts and stops, and
lagging pages are skipped.
"""
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neoaprs.layerthing import Layer, LayerTable, Thing
from neoaprs.web.hub import BEHIND
from neoaprs.web.layerfeed import LayerLooks, table_message, thing_row
from tests.support.env import Env, until
from tests.support.fakelayers import layers_server
from tests.test_layers import plane, sky
from tests.test_levelfeed import page

AT = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
PLANE = Thing("461f2a", 60.3, 24.9, AT, 225, 420.4, "FIN7AB", False, 2438, "OH-LZA", "AIRBUS A-321")


class Service:
    def __init__(self) -> None:
        self.watched: list[tuple[Layer, bool]] = []
        self.things: tuple[Thing, ...] = (PLANE,)

    def watch(self, layer: Layer, on: bool) -> None:
        self.watched.append((layer, on))

    def table(self, layer: Layer) -> LayerTable:
        return LayerTable(layer, "receiver", False, self.things if layer == "aircraft" else ())


def sent(client: Any) -> list[dict[str, Any]]:
    return [m for m in client.sent if m["type"] == "layer_things"]


def test_a_page_that_looks_is_sent_the_table_at_once_and_every_table_after_it() -> None:
    service = Service()
    looks = LayerLooks(service)
    conn, client = page()
    looks.look(conn, "aircraft", True)
    assert sent(client) == [{"type": "layer_things", "layer": "aircraft", "source": "receiver", "away": False, "things": [{
        "id": "461f2a", "lat": 60.3, "lon": 24.9, "at": "2026-11-18T12:00:00Z", "heading_deg": 225, "speed_kmh": 420.4, "name": "FIN7AB", "emergency": False, "altitude_m": 2438, "vertical_ms": None, "registration": "OH-LZA",
        "type": "AIRBUS A-321", "category": "", "designator": "", "ship_type": None, "course_deg": None, "destination": "",
        "origin": "", "origin_place": "", "destination_place": ""}]}]
    looks.told(LayerTable("aircraft", "receiver", True, ()))
    looks.told(LayerTable("ships", "fintraffic", False, ()))
    assert [m["away"] for m in sent(client)] == [False, True], "the ships' table goes to nobody: this page does not look at them"


def test_three_pages_are_one_look_for_the_service_and_the_last_one_that_stops_ends_it() -> None:
    service = Service()
    looks = LayerLooks(service)
    pages = [page()[0] for _ in range(3)]
    for conn in pages:
        looks.look(conn, "aircraft", True)
    looks.look(pages[0], "aircraft", True)
    assert service.watched == [("aircraft", True)] and looks.pages("aircraft") == 3
    looks.look(pages[0], "aircraft", False)
    looks.forget(pages[1])
    assert service.watched == [("aircraft", True)]
    looks.look(pages[2], "aircraft", False)
    looks.look(pages[2], "aircraft", False)
    assert service.watched == [("aircraft", True), ("aircraft", False)] and looks.pages("aircraft") == 0


def test_a_page_that_is_behind_is_sent_no_table_and_one_that_has_closed_is_not_taken() -> None:
    service = Service()
    looks = LayerLooks(service)
    slow, slow_client = page(BEHIND + 1)
    looks.look(slow, "aircraft", True)
    looks.told(service.table("aircraft"))
    assert sent(slow_client) == []
    gone, gone_client = page()
    gone.closed = True
    looks.look(gone, "ships", True)
    assert sent(gone_client) == [] and looks.pages("ships") == 0 and ("ships", True) not in service.watched


def test_the_message_of_an_empty_table_has_its_source_and_no_things() -> None:
    assert table_message(LayerTable("ships", "none", False, ())) == {"type": "layer_things", "layer": "ships", "source": "none", "away": False, "things": []}


# ---- on the wire

async def test_the_topic_map_says_both_layers_and_a_look_at_a_layer_without_a_source_stands_and_is_served_once_one_is_chosen(tmp_path: Path) -> None:
    receiver = await layers_server()
    receiver.route("/tar1090/data/aircraft.json", body=sky(plane("461f2a")))
    e = Env(tmp_path / "data", web=True)
    await e.start()
    tab = await e.ws()
    value = (await tab.expect("state", "map"))["value"]
    assert value["layers"] == [{"layer": "aircraft", "source": "none", "offered": ["none", "adsbfi", "adsblol", "radarcape", "receiver"], "receiver": None},
                               {"layer": "ships", "source": "none", "offered": ["none", "fintraffic", "receiver"], "receiver": None}], "the station of the tests is at Helsinki: Fintraffic is offered"
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    first = await tab.expect("layer_things")
    assert (first["source"], first["things"]) == ("none", [])
    await tab.send({"cmd": "set_config", "values": {"map/aircraft": "receiver", "map/aircraft_host": receiver.address}})
    await tab.until(lambda: any(m["type"] == "layer_things" and m["things"] for m in tab.messages), 10.0)
    await tab.until(lambda: tab.topics["map"]["layers"][0]["receiver"] is not None and tab.topics["map"]["layers"][0]["receiver"]["state"] == "receiving", 10.0)
    layer = tab.topics["map"]["layers"][0]
    assert layer["source"] == "receiver" and layer["receiver"]["things"] == 1 and set(layer["receiver"]) == {"state", "things", "heard_at"}, "nothing of its address"
    other = await e.ws()
    await other.expect("state", "map")
    await other.quiet(0.5)
    assert not [m for m in other.messages if m["type"] == "layer_things"], "a page that does not look is sent no table"
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": False})
    await tab.quiet(0.3)
    assert e.ctl.layers._watched == set()
    await e.stop()


async def test_a_page_that_closes_looks_no_more(tmp_path: Path) -> None:
    e = Env(tmp_path / "data", web=True, settings={"map/aircraft": "receiver", "map/aircraft_host": "127.0.0.1:9"})
    await e.start()
    tab = await e.ws()
    await tab.send({"cmd": "layer_look", "layer": "aircraft", "on": True})
    await tab.expect("layer_things")
    assert e.ctl.layers._watched == {"aircraft"}
    await tab.aclose()
    await until(lambda: e.ctl.layers._watched == set())
    await e.stop()


def test_an_aircraft_is_sent_with_the_places_of_its_two_airports_and_a_ship_never_with_one() -> None:
    flying = replace(PLANE, origin="ESSA", destination="EFHK")
    row = thing_row(flying, "aircraft")
    assert (row["origin"], row["origin_place"], row["destination"], row["destination_place"]) == ("ESSA", "Stockholm", "EFHK", "Helsinki")
    unknown = thing_row(replace(PLANE, origin="ZZZZ", destination=""), "aircraft")
    assert (unknown["origin"], unknown["origin_place"], unknown["destination"], unknown["destination_place"]) == ("ZZZZ", "", "", ""), "a code the table does not know has no place; none has none"
    ship = thing_row(replace(PLANE, destination="EFHK"), "ships")
    assert (ship["destination"], ship["destination_place"], ship["origin_place"]) == ("EFHK", "", ""), "a ship's destination is its own words, never looked up as an airport"


def test_an_aircraft_is_sent_with_its_vertical_speed_in_metres_a_second_and_null_when_not_told_and_for_a_ship() -> None:
    assert thing_row(replace(PLANE, vertical_ms=-10.7), "aircraft")["vertical_ms"] == -10.7
    assert thing_row(PLANE, "aircraft")["vertical_ms"] is None and thing_row(PLANE, "ships")["vertical_ms"] is None
