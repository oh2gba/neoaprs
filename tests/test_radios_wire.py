"""The radios on the wire (breakdown 1.11, wave 4): the topic `radios` (every radio by id, removed ones too, at most four times a second), the commands that name a radio (`radio_add`, `radio_remove`, `radio_change`,
`station_radio`, the paths of a station by radio, Ask and Local info on a named radio, an object's radios, `list_ports` and `find_radio` for a radio, the modem's commands), a radio's own settings through
`set_config` (`radio/<id>/<key>`, `station/main_radio`), and every refusal with its code, the key it is about and the holder's name where a device is held. Over the page's socket of a real daemon."""
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from neoaprs.claims import Claim
from neoaprs.radiospec import FM_ID, HF_ID, RadioSpec
from neoaprs.web import handlers as web_handlers
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.tncwire import RadioRow
from neoaprs.serialprobe import PortInfo, claim_value
from tests.support.env import Env
from tests.support.wireworld import heard
from tests.support.wsclient import WsClient

ROW = TypeAdapter(RadioRow)


async def started(tmp_path: Path, settings: dict[str, str] | None = None) -> tuple[Env, WsClient]:
    e = Env(tmp_path, radio=False, web=True, settings=settings)
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return e, page


async def refused(page: WsClient, command: dict[str, Any]) -> dict[str, Any]:
    """The error a command is answered with."""
    before = len(page.of("error"))
    await page.send(command)
    await page.until(lambda: len(page.of("error")) > before)
    return page.of("error")[-1]


async def added(page: WsClient, type: str, name: str = "") -> int:
    before = len(page.of("radio_added"))
    await page.send({"cmd": "radio_add", "type": type, **({"name": name} if name else {})})
    await page.until(lambda: len(page.of("radio_added")) > before)
    id = int(page.of("radio_added")[-1]["id"])
    await page.until(lambda: str(id) in page.topics["radios"])
    return id


async def test_the_topic_has_every_radio_and_a_radio_added_changed_and_removed_is_told_with_its_row(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    radios = page.topics["radios"]
    assert set(radios) == {str(s.id) for s in e.ctl.config.radios} and all(ROW.validate_python(row) for row in radios.values())
    assert radios["1"]["kind"] == "fm" and radios["1"]["type"] == "kenwood-tnc2" and radios["1"]["can"]["find"] and radios["1"]["allowed"]["paths"]
    id = await added(page, "dummy", "Shack")
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    row = page.topics["radios"][str(id)]
    assert (row["name"], row["kind"], row["type"], row["number"], row["dummy"], row["enabled"], row["removed"], row["problem"]) == ("Shack", "fm", "dummy", 2, True, True, False, None)
    assert row["choices"] == {"beacon": True, "path": "", "digipeat": False} and row["beacon"]["interval_min"] == 0 and row["limits"] == {"max_frame": None, "beacon_min_min": 20}
    await page.send({"cmd": "radio_change", "radio": id, "name": "Mobile", "position": 1})
    await page.until(lambda: page.topics["radios"][str(id)]["name"] == "Mobile" and page.topics["radios"][str(id)]["position"] == 1)
    assert e.ctl.config.radio(id).name == "Mobile", "stored and in force"            # type: ignore[union-attr]
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"] and page.topics["radios"][str(id)]["state"] == "stopped")
    await page.send({"cmd": "radio_remove", "radio": id})
    await page.until(lambda: page.topics["radios"][str(id)]["removed"])
    gone = page.topics["radios"][str(id)]
    assert (gone["enabled"], gone["state"], gone["lines"], gone["holds"], gone["name"]) == (False, "stopped", [], [], "Mobile"), "a removed radio keeps its row and its name"
    await e.stop()


async def test_every_refusal_of_the_radio_commands_has_its_code(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    cases: list[tuple[dict[str, Any], str, dict[str, Any]]] = [
        ({"cmd": "radio_add", "type": "pigeon"}, "radio.unknown_type", {"type": "pigeon"}),
        ({"cmd": "radio_add", "type": "dummy", "name": "SHACK"}, "radio.name_taken", {"name": "SHACK", "radio": id}),
        ({"cmd": "radio_add", "type": "dummy", "name": "much too long"}, "radio.name_form", {"max": 8, "name": "much too long"}),
        ({"cmd": "radio_change", "radio": id, "name": "Mö"}, "radio.name_form", {"max": 8, "name": "Mö"}),
        ({"cmd": "radio_change", "radio": id, "type": "mercury"}, "radio.type_kind", {"type": "mercury", "kind": "FM", "name": "Shack"}),
        ({"cmd": "radio_change", "radio": 9, "name": "Gone"}, "radio.unknown", {"radio": 9}),
        ({"cmd": "radio_remove", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "radio_tune", "radio": 9, "on": True}, "radio.unknown", {"radio": 9}),
        ({"cmd": "radio_tune", "radio": id, "on": True}, "radio.no_modem", {"name": "Shack"}),
        ({"cmd": "radio_key_test", "radio": id}, "radio.no_modem", {"name": "Shack"}),
        ({"cmd": "list_ports", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "find_radio", "radio": id}, "radio.no_line", {"name": "Shack"}),
        ({"cmd": "station_radio", "call": "OH2XYZ", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "set_station_path", "call": "OH2XYZ", "path": "WIDE1-1", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "object_set", "name": "MARK", "kind": "object", "lat": 60, "lon": 25, "symbol_table": "/", "symbol_code": ">", "comment": "", "course_deg": None, "speed_kmh": None, "path": None, "qru_group": "",
          "on_request": False, "radios": [FM_ID, 9]}, "radio.unknown", {"radio": 9}),
    ]
    for command, code, params in cases:
        error = await refused(page, command)
        assert (error["cmd"], error["code"], error["params"]) == (command["cmd"], code, params), command
    taken = await refused(page, {"cmd": "radio_add", "type": "dummy", "name": "SHACK"})
    assert taken["text"] == "radio_add: the name 'SHACK' is another radio's already: give this one another", "the page names a radio by its name, not by an id"
    assert (await refused(page, {"cmd": "radio_change", "radio": id, "type": "mercury"}))["text"] == "radio_change: the Shack radio takes only a type of its own kind (FM)", "no key, no type's key"
    await page.send({"cmd": "radio_change", "radio": FM_ID, "enabled": False})
    await page.until(lambda: not page.topics["radios"]["1"]["enabled"])
    for command in ({"cmd": "radio_change", "radio": id, "enabled": False}, {"cmd": "radio_remove", "radio": id}):
        error = await refused(page, command)
        assert (error["code"], error["params"]) == ("radio.last_enabled", {"name": "Shack"}), "the last radio that is on stays on"
    await e.stop()


async def test_a_radios_own_settings_ride_set_config_and_each_refusal_names_its_key(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "kiss-tcp")
    await page.until(lambda: f"radio/{id}/tcp_port" in page.topics["config"]["radio_values"])
    values = page.topics["config"]["radio_values"]
    assert values[f"radio/{id}/tcp_port"] == "8001" and values["station/main_radio"] == "" and page.topics["config"]["radio_defaults"][f"radio/{id}/tcp_port"] == "8001"
    assert not [key for key in page.topics["config"]["values"] if key.startswith("radio/") or key == "station/main_radio"], "the form of before is shown none of them"
    await page.send({"cmd": "set_config", "values": {f"radio/{id}/tcp_port": "8002", "station/comment": "both at once"}})
    await page.until(lambda: page.topics["config"]["radio_values"][f"radio/{id}/tcp_port"] == "8002")
    assert page.topics["config"]["values"]["station/comment"] == "both at once" and e.ctl.config.radio(id).settings["tcp_port"] == "8002"      # type: ignore[union-attr]
    assert dict((await e.ctl.store.radios())[-1].settings) == {"tcp_port": "8002"}, "stored in the radio's own rows"
    cases = [({f"radio/{id}/tcp_port": "70000"}, f"radio/{id}/tcp_port", "setting.range"), ({f"radio/{id}/tcp_port": "x"}, f"radio/{id}/tcp_port", "setting.not_whole"),
             ({"radio/9/port": "COM3"}, "radio/9/port", "radio.unknown"), ({f"radio/{id}/sound_card": "x"}, f"radio/{id}/sound_card", "radio.no_setting"),
             ({f"radio/{id}/last_port": "x"}, f"radio/{id}/last_port", "radio.no_setting"), ({"station/main_radio": "9"}, "station/main_radio", "radio.unknown"),
             ({"station/main_radio": "x"}, "station/main_radio", "setting.not_whole")]
    for values_, key, code in cases:
        error = await refused(page, {"cmd": "set_config", "values": {**values_, "station/comment": "not stored"}})
        assert (error["key"], error["code"]) == (key, code), values_
    assert e.ctl.config.station_comment == "both at once", "nothing of a refused save is stored"
    await page.send({"cmd": "set_config", "values": {"station/main_radio": str(id)}})
    await page.until(lambda: page.topics["config"]["radio_values"]["station/main_radio"] == str(id))
    assert e.ctl.config.main_choice == e.ctl.config.main_radio == id
    await page.send({"cmd": "status"})
    await page.until(lambda: page.of("status")[-1]["main_radio"] == id and page.of("status")[-1]["email_radio"] == id, timeout=8)
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"])
    assert e.ctl.config.main_choice == id and e.ctl.config.main_radio == FM_ID, "a main radio chosen while it is off is not the main one"
    await e.stop()


async def test_a_device_another_radio_holds_is_refused_with_the_holders_name_and_shown_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "kiss", "Mobile")
    e.ctl.radios.claims.hold(Claim("serial", claim_value("COM7") or "", FM_ID))             # (held as the table holds a device: by the name its search resolved)
    error = await refused(page, {"cmd": "set_config", "values": {f"radio/{id}/port": "COM7"}})
    assert (error["key"], error["code"], error["params"]) == (f"radio/{id}/port", "radio.resource_held", {"resource": "serial", "holder": "FM"})
    monkeypatch.setattr(web_handlers, "available_ports", lambda: [PortInfo("COM7", "USB Serial Port (COM7)", "USB VID:PID=0403:6001", 0x0403, 0x6001), PortInfo("COM8", "Bluetooth", "BTHENUM", None, None)])
    monkeypatch.setattr(web_handlers, "paired_bluetooth_ports", lambda: [])
    await page.send({"cmd": "list_ports", "radio": id})
    ports = (await page.expect("ports"))["ports"]
    assert [(p["device"], p["held_by"]) for p in ports] == [("COM7", FM_ID), ("COM8", None)]
    from neoaprs.mercurycards import SoundCard
    monkeypatch.setattr(web_handlers, "hf_is_mercury", lambda config: True)
    monkeypatch.setattr(e.ctl.mercury, "sound_cards", lambda: [SoundCard("plughw:CARD=A", "A"), SoundCard("plughw:CARD=B", "B"), SoundCard("plughw:CARD=C", "C")])
    e.ctl.radios.claims.hold(Claim("sound_card", "plughw:CARD=A", id))
    e.ctl.radios.claims.hold(Claim("sound_card", "plughw:CARD=B", 2))
    await page.send({"cmd": "list_ports"})
    cards = (await page.expect("ports"))["sound_cards"]
    assert [(c["id"], c["held_by"], c["pick"]) for c in cards] == [("plughw:CARD=A", id, False), ("plughw:CARD=B", 2, True), ("plughw:CARD=C", None, False)], "each card with who holds it; the proposal (for radio 2) leaves out what another radio holds"
    await e.stop()


async def test_a_station_is_given_a_radio_and_a_path_on_it_and_its_row_says_both(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    row = page.topics["stations"]["OH2XYZ"]
    assert (row["radio_choice"], row["radio_now"], row["paths"], row["heard"]) == (None, FM_ID, {}, {"1": {"count": 1, "last_at": row["last_heard"]}})
    await page.send({"cmd": "station_radio", "call": "OH2XYZ", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["radio_choice"] == id)
    assert page.topics["stations"]["OH2XYZ"]["radio_now"] == id and page.topics["stations"]["OH2XYZ"]["message_radio"] == "", "a radio of no word of before"
    await page.send({"cmd": "set_station_path", "call": "OH2XYZ", "path": "OH2RCH-2", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["paths"] == {str(id): "OH2RCH-2"})
    assert "OH2XYZ" not in page.topics["station_prefs"], "radio 1's entry is not touched"
    await page.send({"cmd": "clear_station_path", "call": "OH2XYZ", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["paths"] == {})
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["radio_choice"] is None, timeout=8)
    assert page.topics["stations"]["OH2XYZ"]["radio_now"] == FM_ID, "a radio that is off is no choice"
    await page.send({"cmd": "station_radio", "call": "OH2XYZ", "radio": None})
    await page.until(lambda: e.ctl.radios.choice("OH2XYZ") is None)
    await e.stop()


async def test_ask_and_local_info_go_on_the_radio_named_and_a_radio_that_is_off_is_refused_with_its_name(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    assert page.topics["general"]["by_radio"] == []
    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True, "radio": id})
    await page.until(lambda: [a["radio"] for a in page.topics["general"]["asked"]] == [id])
    two = await added(page, "dummy", "Two")
    await page.until(lambda: page.topics["radios"][str(two)]["state"] == "connected")
    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True, "radio": two})
    await page.until(lambda: [(a["radio"], a["kind"]) for a in page.topics["general"]["by_radio"]] == [(id, "aprs"), (two, "aprs")])
    assert [a["radio"] for a in page.topics["general"]["asked"]] == [two], "the field of before: the latest of each kind; the wait of each radio is its own"
    await page.send({"cmd": "qru_ask", "text": "INFO", "radio": id})
    await page.until(lambda: page.topics["qru"]["asked"] is not None and page.topics["qru"]["asked"]["radio"] == id)
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"])
    for command in ({"cmd": "general_query", "kind": "wx", "path": None, "rf_only": True, "radio": id}, {"cmd": "qru_ask", "text": "INFO 50", "radio": id}):
        error = await refused(page, command)
        assert (error["code"], error["params"]) == ("radio.off", {"name": "Shack"}), "a radio switched off is said to be off, not to be unplugged"
    assert (await refused(page, {"cmd": "qru_ask", "text": "INFO", "radio": 9}))["code"] == "radio.unknown"
    await e.stop()


async def test_an_object_goes_on_the_radios_named_and_its_row_says_them(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    base = {"cmd": "object_set", "kind": "object", "lat": 60, "lon": 25, "symbol_table": "/", "symbol_code": ">", "comment": "", "course_deg": None, "speed_kmh": None, "path": None, "qru_group": "", "on_request": True}
    await page.send({**base, "name": "BOTH", "radios": [FM_ID, id]})
    await page.send({**base, "name": "OLD", "radio": "fm"})
    await page.until(lambda: {"BOTH", "OLD"} <= set(page.topics["own_objects"]))
    assert page.topics["own_objects"]["BOTH"]["radios"] == [FM_ID, id] and page.topics["own_objects"]["OLD"]["radios"] == [FM_ID] and page.topics["own_objects"]["OLD"]["radio"] == "fm"
    await e.stop()


async def test_the_topic_tells_a_radio_at_most_four_times_a_second(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    await page.quiet(0.4)
    before = len(page.ops("radios"))
    for _ in range(40):
        e.ctl.radio_changed.emit(FM_ID)
        await asyncio.sleep(0.025)
    await page.quiet(0.4)
    told = [op for op in page.ops("radios")[before:] if op.get("key") == "1"]
    assert 1 <= len(told) <= 6, f"a second of changes was told {len(told)} times"
    await e.stop()


async def test_the_frequencies_are_asked_for_by_the_station_level_command_too(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    asked: list[bool] = []
    e.ctl.frequencies.wanted = lambda: asked.append(True)           # type: ignore[method-assign]
    await page.send({"cmd": "frequencies"})
    await page.send({"cmd": "hf_frequencies"})
    await page.until(lambda: len(asked) == 2)
    await e.stop()


def test_a_radio_of_a_type_that_is_none_has_no_row_and_the_types_are_the_pages_list() -> None:
    from neoaprs.claims import Claims
    from neoaprs.radiotypes import TYPES
    from neoaprs.web.radioview import radio_row
    from tests.test_protocol import generator
    stranger = RadioSpec(5, "fm", "carrier-pigeon", "", True, 5)
    assert radio_row(stranger, (stranger,), None, Claims()) is None
    lists = generator().LISTS.read_text(encoding="utf-8")
    listed = json.loads(lists.split("export const RADIO_TYPES = ", 1)[1].split(" as const;", 1)[0].replace(",\n  ]", "\n  ]").replace(",\n    ]", "\n    ]").replace(",\n      }", "\n      }").replace(",\n  }", "\n  }").replace(",\n]", "\n]"))
    assert sorted(t["key"] for t in listed) == sorted(t.key for t in TYPES) and all(t["fields"] for t in listed)


async def test_a_message_on_its_way_says_the_radio_it_takes_next_as_the_choice_and_the_radios_change(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    await page.send({"cmd": "station_radio", "call": "OH2XYZ", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["radio_choice"] == id)
    await page.send({"cmd": "send_message", "to": "OH2XYZ", "text": "on the shack"})
    await page.until(lambda: [m["radio_now"] for m in page.topics["messages"].values() if m["to_call"] == "OH2XYZ"] == [id])
    [key] = [k for k, m in page.topics["messages"].items() if m["to_call"] == "OH2XYZ"]

    def told() -> tuple[object, object]:
        return page.topics["messages"][key]["radio_now"], page.topics["stations"]["OH2XYZ"]["radio_now"]

    steps: list[tuple[dict[str, Any], int]] = [
        ({"cmd": "station_radio", "call": "OH2XYZ", "radio": None}, FM_ID), ({"cmd": "station_radio", "call": "OH2XYZ", "radio": id}, id),
        ({"cmd": "radio_change", "radio": id, "enabled": False}, FM_ID), ({"cmd": "radio_change", "radio": id, "enabled": True}, id), ({"cmd": "radio_remove", "radio": id}, FM_ID),
    ]
    for command, now in steps:
        await page.send(command)
        await page.until(lambda now=now: told() == (now, now), timeout=3)          # (the clock of the test stands: no attempt is made meanwhile, the row is told by the change itself)
    assert page.topics["messages"][key]["state"] == "sending"
    await e.stop()


async def test_the_command_of_before_that_chooses_the_radio_tells_the_messages_on_their_way(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "dummy-hf"})
    await page.until(lambda: page.topics["radios"]["2"]["state"] == "connected")
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    await page.send({"cmd": "send_message", "to": "OH2XYZ", "text": "over FM"})
    await page.until(lambda: [m["radio_now"] for m in page.topics["messages"].values() if m["to_call"] == "OH2XYZ"] == [FM_ID])
    [key] = [k for k, m in page.topics["messages"].items() if m["to_call"] == "OH2XYZ"]
    for word, now in (("hf", HF_ID), ("fm", FM_ID)):
        await page.send({"cmd": "message_radio", "call": "OH2XYZ", "radio": word})
        await page.until(lambda now=now: page.topics["messages"][key]["radio_now"] == now, timeout=3)   # (the clock of the test stands: the choice itself tells the row)
    await e.stop()


async def test_a_call_the_book_does_not_hold_is_chosen_for_by_call_and_its_row_says_it_once_it_is_heard(tmp_path: Path) -> None:
    """Plan rule 3.2: the choice is kept by call, with or without a station in the book."""
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    await page.send({"cmd": "station_radio", "call": " oh2new ", "radio": id})
    await page.until(lambda: e.ctl.radios.choice("OH2NEW") == id)
    assert "OH2NEW" not in page.topics["stations"] and page.of("error") == [], "taken in the call's normal form, with no station to tell"
    error = await refused(page, {"cmd": "station_radio", "call": "not a call!", "radio": id})
    assert error["code"] == "call.shape" and json.loads(e.ctl.radios.choices_text()) == {"OH2NEW": id}, "a text that is no call is refused and nothing is kept for it"
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2NEW", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2NEW" in page.topics["stations"])
    row = page.topics["stations"]["OH2NEW"]
    assert (row["radio_choice"], row["radio_now"]) == (id, id), "the station heard later has the choice made for its call"
    await e.stop()


async def test_a_key_of_the_form_of_before_on_a_removed_radio_is_refused_with_its_code_and_sent_back_as_shown_it_saves(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "dummy-hf"})
    await page.until(lambda: "2" in page.topics["radios"])
    await page.send({"cmd": "radio_remove", "radio": 2})
    await page.until(lambda: page.topics["radios"]["2"]["removed"])
    for values in ({"hf/enabled": "true"}, {"mercury/tx_gain_db": "3"}, {"hf/profile": "dummy-hf"}):
        error = await refused(page, {"cmd": "set_config", "values": {**values, "station/comment": "not stored"}})
        assert (error["code"], error["key"], error["params"]) == ("radio.unknown", next(iter(values)), {"radio": 2}), values
    shown = page.topics["config"]["values"]
    await page.send({"cmd": "set_config", "values": {**shown, "station/comment": "the whole form"}})
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "the whole form")
    id = await added(page, "dummy")
    await page.send({"cmd": "radio_remove", "radio": FM_ID})
    await page.until(lambda: page.topics["radios"]["1"]["removed"])
    for values in ({"fm/enabled": "true"}, {"beacon/path": "WIDE1-1"}, {"digi/enabled": "true"}, {"serial/port": "/dev/ttyUSB1"}, {"tnc/profile": "kenwood-tnc2"}):
        error = await refused(page, {"cmd": "set_config", "values": values})
        assert (error["code"], error["key"], error["params"]) == ("radio.unknown", next(iter(values)), {"radio": FM_ID}), values
    shown = page.topics["config"]["values"]
    await page.send({"cmd": "set_config", "values": {**shown, "station/comment": "again"}})
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "again")
    assert [s.id for s in e.ctl.config.live_radios] == [id] and not page.of("error")[-1]["text"].startswith("set_config: the settings could not be stored")
    await e.stop()


async def test_a_main_radio_that_is_removed_is_shown_as_none_and_a_form_that_sends_back_what_it_was_given_saves(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    await page.send({"cmd": "set_config", "values": {"station/main_radio": str(id)}})
    await page.until(lambda: page.topics["config"]["radio_values"]["station/main_radio"] == str(id))
    await page.send({"cmd": "radio_remove", "radio": id})
    await page.until(lambda: page.topics["config"]["radio_values"]["station/main_radio"] == "")
    assert e.ctl.config.main_choice == id and e.ctl.config.main_radio == FM_ID, "the row is kept as it was; the first radio that is on is the main one"
    await page.send({"cmd": "set_config", "values": {"station/main_radio": str(id), "station/comment": "the stored one"}})
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "the stored one")
    stored = {s.id: dict(s.settings) for s in await e.ctl.store.radios()}
    await page.send({"cmd": "set_config", "values": {**page.topics["config"]["radio_values"], "station/comment": "what it was given"}})
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "what it was given")
    assert e.ctl.config.main_choice is None and not page.of("error")
    assert {s.id: dict(s.settings) for s in await e.ctl.store.radios()} == stored, "a radio's values sent back as shown write nothing: a default stays the default"
    assert (await refused(page, {"cmd": "set_config", "values": {"station/main_radio": str(id)}}))["code"] == "radio.unknown", "choosing the removed radio is refused"
    await e.stop()


async def test_the_stations_are_told_whole_only_when_what_their_rows_read_of_the_radios_changes(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    await page.quiet(0.6)

    def wholes() -> int:
        return sum(op["op"] == "replace" for op in page.ops("stations"))

    before = wholes()
    await page.send({"cmd": "radio_change", "radio": id, "name": "Shack"})
    await page.send({"cmd": "set_config", "values": {f"radio/{id}/path": "WIDE1-1", "beacon/path": "WIDE2-2"}})
    await page.until(lambda: page.topics["config"]["values"]["beacon/path"] == "WIDE2-2" and page.topics["radios"][str(id)]["name"] == "Shack")
    await page.quiet(0.6)
    assert wholes() == before, "a name, a path or a radio's own setting changes no station's row"
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: wholes() > before)
    await e.stop()


def test_a_device_named_by_another_radio_that_is_on_is_refused_and_two_radios_may_swap_theirs_in_one_save() -> None:
    from neoaprs.claims import Claims
    from neoaprs.config import Config, SettingError
    from neoaprs.web.confighandlers import refuse_held
    from neoaprs.web.radioview import claimed_value

    def kiss(id: int, port: str, on: bool = True) -> RadioSpec:
        return RadioSpec(id, "fm", "kiss", "", on, id, settings={"port": port})

    claims = Claims()
    before = Config(radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3"), kiss(6, "")))
    with pytest.raises(SettingError) as held:
        refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3"), kiss(6, "/dev/ttyUSB3"))), claims)
    assert (held.value.key, held.value.code, held.value.params) == ("radio/6/port", "radio.resource_held", {"resource": "serial", "holder": "FM 2"}), "set to it, though not holding it yet"
    refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3", on=False), kiss(6, "/dev/ttyUSB3"))), claims)
    claims.hold(Claim("serial", claimed_value("serial", "/dev/ttyUSB0"), 1))
    claims.hold(Claim("serial", claimed_value("serial", "/dev/ttyUSB3"), 5))
    refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyUSB3"), kiss(5, "/dev/ttyUSB0"), kiss(6, ""))), claims)
    claims.hold(Claim("gps", claimed_value("gps", "/dev/ttyACM0"), None))
    with pytest.raises(SettingError) as gps:
        refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyACM0"), kiss(5, "/dev/ttyUSB3"), kiss(6, ""))), claims, {"serial/port": "/dev/ttyACM0"})
    assert (gps.value.key, gps.value.params) == ("serial/port", {"resource": "serial", "holder": "GPS"}), "the key of the form of before that set it, and the receiver named"
    refuse_held(before, replace(before, radios=(*before.radios[:2], replace(kiss(6, ""), name="Six"))), claims)      # (a device not named again is not looked at)


async def test_an_object_on_a_radio_that_is_removed_is_told_without_it(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    base = {"cmd": "object_set", "kind": "object", "lat": 60, "lon": 25, "symbol_table": "/", "symbol_code": ">", "comment": "", "course_deg": None, "speed_kmh": None, "path": None, "qru_group": "", "on_request": True}
    await page.send({**base, "name": "BOTH", "radios": [FM_ID, id]})
    await page.send({**base, "name": "ALONE", "radios": [id]})
    await page.until(lambda: {"BOTH", "ALONE"} <= set(page.topics["own_objects"]))
    await page.send({"cmd": "radio_remove", "radio": id})
    await page.until(lambda: page.topics["own_objects"]["BOTH"]["radios"] == [FM_ID], timeout=3)
    assert page.topics["own_objects"]["ALONE"]["radios"] == [id], "an object on no other radio keeps it, as its row does (read as the main radio)"
    await e.stop()


async def test_a_modems_commands_reach_the_modem_of_the_radio_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    done: list[str] = []

    class Modem:
        async def tune(self) -> None:
            done.append("tune")

        async def tune_stop(self) -> None:
            done.append("stop")

        async def key_test(self) -> None:
            done.append("key")

    real = e.ctl.radios.get
    shack = real(id)
    assert shack is not None
    monkeypatch.setattr(e.ctl.radios, "get", lambda radio: SimpleNamespace(spec=shack.spec, name=shack.name, driver=SimpleNamespace(modem=Modem())) if radio == id else real(radio))
    for command in ({"cmd": "radio_tune", "radio": id, "on": True}, {"cmd": "radio_tune", "radio": id, "on": False}, {"cmd": "radio_key_test", "radio": id}):
        await page.send(command)
    await page.until(lambda: done == ["tune", "stop", "key"])
    assert not page.of("error")
    await e.stop()


async def test_a_modems_command_on_a_radio_whose_modem_is_not_running_is_refused_with_that_radios_name(tmp_path: Path) -> None:
    """The Dummy HF radio has a modem part that never runs, as a Mercury radio whose modem is down: the refusal names the radio, not the HF radio of before."""
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "dummy-hf"})
    await page.until(lambda: page.topics["radios"]["2"]["state"] == "connected")
    await page.send({"cmd": "radio_change", "radio": HF_ID, "name": "Attic"})
    await page.until(lambda: page.topics["radios"]["2"]["name"] == "Attic")
    for command in ({"cmd": "radio_tune", "radio": HF_ID, "on": True}, {"cmd": "radio_key_test", "radio": HF_ID}):
        error = await refused(page, command)
        assert (error["code"], error["params"], error["text"]) == ("radio.no_modem", {"name": "Attic"}, f"{command['cmd']}: the Attic radio has no modem running"), command
    assert (await refused(page, {"cmd": "hf_tune", "on": True}))["code"] == "hf.not_running", "the command of before answers as it did"
    await e.stop()


async def test_with_no_radio_on_a_command_that_sends_on_the_main_radio_is_refused_with_its_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neoaprs.radioregistry import RadioRegistry
    e, page = await started(tmp_path)
    monkeypatch.setattr(RadioRegistry, "main", property(lambda self: None))
    for command in ({"cmd": "qru_ask", "text": "INFO"}, {"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True}):
        error = await refused(page, command)
        assert (error["code"], error["params"]) == ("radio.none", {}), command
    await e.stop()


def test_a_radio_that_is_not_connected_says_why_by_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from neoaprs.claims import Claims
    from neoaprs.source import Source
    from neoaprs.web import radioview
    from neoaprs.web.radioview import radio_problem
    radio = RadioSpec(1, "fm", "kiss", "Mobile", True, 1, settings={"port": "/dev/ttyUSB0"})

    def line(state: Source.State, searching: bool = False) -> Any:
        return SimpleNamespace(state=state, searching=searching, silent_since=None, modem=None)

    claims = Claims()
    assert radio_problem(radio, (radio,), line(Source.State.CONNECTED), claims) is None
    assert radio_problem(replace(radio, enabled=False), (radio,), line(Source.State.STOPPED), claims) is None
    assert radio_problem(radio, (radio,), line(Source.State.WAITING), claims) == {"code": "radio.not_connected", "params": {"name": "Mobile"}}
    assert radio_problem(radio, (radio,), line(Source.State.WAITING, searching=True), claims) == {"code": "radio.searching", "params": {}}
    assert radio_problem(radio, (radio,), line(Source.State.SILENT), claims) == {"code": "radio.silent", "params": {"since": ""}}
    monkeypatch.setattr(radioview, "modem_state", lambda tnc: {"state": "waiting", "reason": "not_installed"})
    assert radio_problem(radio, (radio,), line(Source.State.WAITING), claims) == {"code": "modem.not_installed", "params": {}}
    claims.hold(Claim("gps", radioview.claimed_value("gps", "/dev/ttyUSB0"), None))
    assert radio_problem(radio, (radio,), line(Source.State.WAITING), claims) == {"code": "radio.resource_held", "params": {"resource": "serial", "holder": "GPS"}}, "the device first"
