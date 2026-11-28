"""The radios on the wire over a real daemon's page socket: the topic `radios`, the commands that
name a radio, a radio's own settings through `set_config`, and every refusal with its code, key and
holder.
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from neoaprs import radioregistry
from neoaprs.claims import Claim
from neoaprs.radiospec import FM_ID, HF_ID, RadioSpec
from neoaprs.radiotypes import type_of
from neoaprs.web import handlers as web_handlers
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.tncwire import RadioRow
from neoaprs.serialprobe import PortInfo, claim_value
from neoaprs.tncwatchdog import PassCount
from neoaprs.mercurymodem import Mercury
from tests.support.env import START_SEC, Env, until
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


async def at_rest(modem: Mercury) -> None:
    """The start of a Mercury radio, which the daemon makes in a task of its own after the radio is
    added, is over, and its modem has come to rest: the made-up program runs with its control line
    up, or there is none to run. Until then the modem forgets the rows it kept and lets go of what
    the radio held (the stop a start begins with, the link to the program's UI, every try of the
    control line that fails), so what a test puts there by hand waits for this."""
    await until(lambda: modem.state in ("running", "waiting"), START_SEC)


async def test_the_topic_has_every_radio_and_a_radio_added_changed_and_removed_is_told_with_its_row(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)
    radios = page.topics["radios"]
    assert set(radios) == {str(s.id) for s in e.ctl.config.radios} and all(
        ROW.validate_python(row) for row in radios.values()
    )
    assert (
        radios["1"]["kind"] == "fm"
        and radios["1"]["type"] == "kenwood-tnc2"
        and radios["1"]["can"]["find"]
        and radios["1"]["allowed"]["paths"]
    )
    id = await added(page, "dummy", "Shack")
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    row = page.topics["radios"][str(id)]
    assert (
        row["name"],
        row["kind"],
        row["type"],
        row["number"],
        row["dummy"],
        row["enabled"],
        row["removed"],
        row["problem"],
    ) == ("Shack", "fm", "dummy", 2, True, True, False, None)
    assert (
        row["choices"]
        == {"beacon": True, "status": False, "ask": False, "local_info": False, "path": "", "digipeat": False}
        and row["beacon"]["interval_min"] == 0
        and row["limits"] == {"max_frame": None, "beacon_min_min": 20, "slow": False}
    )
    await page.send({"cmd": "radio_change", "radio": id, "name": "Mobile", "position": 1})
    await page.until(
        lambda: page.topics["radios"][str(id)]["name"] == "Mobile" and page.topics["radios"][str(id)]["position"] == 1
    )
    assert e.ctl.config.radio(id).name == "Mobile", "stored and in force"  # type: ignore[union-attr]
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(
        lambda: not page.topics["radios"][str(id)]["enabled"] and page.topics["radios"][str(id)]["state"] == "stopped"
    )
    await page.send({"cmd": "radio_remove", "radio": id})
    await page.until(lambda: page.topics["radios"][str(id)]["removed"])
    gone = page.topics["radios"][str(id)]
    assert (gone["enabled"], gone["state"], gone["lines"], gone["holds"], gone["name"]) == (
        False,
        "stopped",
        [],
        [],
        "Mobile",
    ), "a removed radio keeps its row and its name"
    await e.stop()


async def test_every_refusal_of_the_radio_commands_has_its_code(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    cases: list[tuple[dict[str, Any], str, dict[str, Any]]] = [
        ({"cmd": "radio_add", "type": "pigeon"}, "radio.unknown_type", {"type": "pigeon"}),
        ({"cmd": "radio_add", "type": "dummy", "name": "SHACK"}, "radio.name_taken", {"name": "SHACK", "radio": id}),
        (
            {"cmd": "radio_add", "type": "dummy", "name": "much too long"},
            "radio.name_form",
            {"max": 8, "name": "much too long"},
        ),
        ({"cmd": "radio_change", "radio": id, "name": "Mö"}, "radio.name_form", {"max": 8, "name": "Mö"}),
        (
            {"cmd": "radio_change", "radio": id, "type": "mercury"},
            "radio.type_kind",
            {"type": "mercury", "kind": "Packet", "name": "Shack", "radio": id},
        ),
        ({"cmd": "radio_change", "radio": 9, "name": "Gone"}, "radio.unknown", {"radio": 9}),
        ({"cmd": "radio_remove", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "radio_tune", "radio": 9, "on": True}, "radio.unknown", {"radio": 9}),
        ({"cmd": "radio_tune", "radio": id, "on": True}, "radio.no_modem", {"name": "Shack", "radio": id}),
        ({"cmd": "radio_key_test", "radio": id}, "radio.no_modem", {"name": "Shack", "radio": id}),
        ({"cmd": "list_ports", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "find_radio", "radio": id}, "radio.no_line", {"name": "Shack", "radio": id}),
        ({"cmd": "radio_scope", "radio": id, "on": True}, "radio.no_scope", {"name": "Shack", "radio": id}),
        ({"cmd": "radio_scope", "radio": 9, "on": True}, "radio.unknown", {"radio": 9}),
        ({"cmd": "station_radio", "call": "OH2XYZ", "radio": 9}, "radio.unknown", {"radio": 9}),
        ({"cmd": "set_station_path", "call": "OH2XYZ", "path": "WIDE1-1", "radio": 9}, "radio.unknown", {"radio": 9}),
        (
            {
                "cmd": "object_set",
                "name": "MARK",
                "kind": "object",
                "lat": 60,
                "lon": 25,
                "symbol_table": "/",
                "symbol_code": ">",
                "comment": "",
                "course_deg": None,
                "speed_kmh": None,
                "path": None,
                "qru_group": "",
                "on_request": False,
                "radios": [FM_ID, 9],
            },
            "radio.unknown",
            {"radio": 9},
        ),
    ]
    for command, code, params in cases:
        error = await refused(page, command)
        assert (error["cmd"], error["code"], error["params"]) == (command["cmd"], code, params), command
    taken = await refused(page, {"cmd": "radio_add", "type": "dummy", "name": "SHACK"})
    assert taken["text"] == "radio_add: the name 'SHACK' is another radio's already: give this one another", (
        "the page names a radio by its name, not by an id"
    )
    assert (await refused(page, {"cmd": "radio_change", "radio": id, "type": "mercury"}))[
        "text"
    ] == "radio_change: radio Shack takes only a type of its own kind (Packet)", "no key, no type's key"
    await page.send({"cmd": "radio_change", "radio": FM_ID, "enabled": False})
    await page.until(lambda: not page.topics["radios"]["1"]["enabled"])
    for command in ({"cmd": "radio_change", "radio": id, "enabled": False}, {"cmd": "radio_remove", "radio": id}):
        error = await refused(page, command)
        assert (error["code"], error["params"]) == ("radio.last_enabled", {"name": "Shack", "radio": id}), (
            "the last radio that is on stays on"
        )
    await e.stop()


async def test_a_place_past_what_the_database_holds_is_refused_and_a_radio_is_added_after_the_last_place(
    tmp_path: Path,
) -> None:
    """A radio's place is a whole number from 1 to 2**31 - 1: a larger one is refused as `invalid`
    and nothing is stored (not `failed` from the database), and after a radio is put at the last
    place a radio added still goes after it."""
    e, page = await started(tmp_path)
    for position in (2**31, 2**63, 2**64):
        error = await refused(page, {"cmd": "radio_change", "radio": FM_ID, "position": position})
        assert (error["cmd"], error["code"]) == ("radio_change", "invalid"), position
    assert e.ctl.config.radio(FM_ID).position == 1 and [
        s.position for s in await e.ctl.store.radios() if s.id == FM_ID
    ] == [1]  # type: ignore[union-attr]
    await page.send({"cmd": "radio_change", "radio": FM_ID, "position": 2**31 - 1})
    await page.until(lambda: page.topics["radios"]["1"]["position"] == 2**31 - 1)
    id = await added(page, "dummy")
    assert e.ctl.config.radio(id).position == 2**31 and len(page.of("error")) == 3, (
        "the three refusals above, and no other"
    )  # type: ignore[union-attr]
    await e.stop()


async def test_a_command_that_names_no_radio_is_refused_for_radio_1_once_it_is_removed(tmp_path: Path) -> None:
    """A station path and Find my radio left without a radio are radio 1's; once radio 1 is removed
    they are refused as `radio.unknown`, and no row is written for a radio that is gone."""
    e, page = await started(tmp_path)
    await added(page, "dummy", "Shack")
    assert await e.ctl.remove_radio(FM_ID)
    for command in (
        {"cmd": "set_station_path", "call": "OH2XYZ", "path": "WIDE1-1"},
        {"cmd": "clear_station_path", "call": "OH2XYZ"},
        {"cmd": "find_radio"},
    ):
        error = await refused(page, command)
        assert (error["cmd"], error["code"], error["params"]["radio"]) == (command["cmd"], "radio.unknown", FM_ID), (
            command
        )
    assert e.ctl.prefbook.path_on("OH2XYZ", FM_ID) is None
    await e.stop()


async def test_a_radios_own_settings_ride_set_config_and_each_refusal_names_its_key(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    # Off with the defaults (127.0.0.1:8001 and 8002 below): the ports of a real Direwolf on this
    # machine.
    id = await e.ctl.add_radio("kiss-tcp", enabled=False)
    assert id is not None
    await page.until(
        lambda: str(id) in page.topics["radios"] and f"radio/{id}/tcp_port" in page.topics["config"]["radio_values"]
    )
    values = page.topics["config"]["radio_values"]
    assert (
        values[f"radio/{id}/tcp_port"] == "8001"
        and "station/main_radio" not in values
        and page.topics["config"]["radio_defaults"][f"radio/{id}/tcp_port"] == "8001"
    )
    assert not [key for key in page.topics["config"]["values"] if key.startswith("radio/") or key == "email/radio"], (
        "the form of before is shown none of them"
    )
    await page.send(
        {"cmd": "set_config", "values": {f"radio/{id}/tcp_port": "8002", "station/comment": "both at once"}}
    )
    await page.until(lambda: page.topics["config"]["radio_values"][f"radio/{id}/tcp_port"] == "8002")
    assert (
        page.topics["config"]["values"]["station/comment"] == "both at once"
        and e.ctl.config.radio(id).settings["tcp_port"] == "8002"
    )  # type: ignore[union-attr]
    assert dict((await e.ctl.store.radios())[-1].settings) == {"tcp_port": "8002"}, "stored in the radio's own rows"
    cases = [
        ({f"radio/{id}/tcp_port": "70000"}, f"radio/{id}/tcp_port", "setting.range"),
        ({f"radio/{id}/tcp_port": "x"}, f"radio/{id}/tcp_port", "setting.not_whole"),
        ({"radio/9/port": "COM3"}, "radio/9/port", "radio.unknown"),
        ({f"radio/{id}/frequency": "x"}, f"radio/{id}/frequency", "radio.no_setting"),
        ({f"radio/{id}/last_port": "x"}, f"radio/{id}/last_port", "radio.no_setting"),
        ({"email/radio": "9"}, "email/radio", "radio.unknown"),
        ({"email/radio": "x"}, "email/radio", "setting.not_whole"),
        ({"station/main_radio": "2"}, "station/main_radio", "setting.unknown"),
    ]
    for values_, key, code in cases:
        error = await refused(page, {"cmd": "set_config", "values": {**values_, "station/comment": "not stored"}})
        assert (error["key"], error["code"]) == (key, code), values_
    assert e.ctl.config.station_comment == "both at once", "nothing of a refused save is stored"
    # Switched on, for email to go out on it, at a made-up radio of the test
    fake = await e.new_radio()
    await page.send({"cmd": "set_config", "values": {f"radio/{id}/tcp_port": str(fake.port)}})
    await page.until(lambda: page.topics["config"]["radio_values"][f"radio/{id}/tcp_port"] == str(fake.port))
    await page.send({"cmd": "radio_change", "radio": id, "enabled": True})
    await page.until(lambda: page.topics["radios"][str(id)]["enabled"])
    # A second radio that sends: email stays on radio 1 until the operator chooses
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == str(FM_ID))
    await page.send({"cmd": "set_config", "values": {"email/radio": str(id)}})
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == str(id))
    await page.send({"cmd": "status"})
    await page.until(lambda: page.of("status")[-1]["email_radio"] == id, timeout=30)
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"])
    assert e.ctl.config.email_choice == id and e.ctl.config.unheard_radio == FM_ID, (
        "a radio chosen while it is off is kept, and carries nothing"
    )
    await e.stop()


async def test_a_device_another_radio_holds_is_refused_with_the_holders_name_and_shown_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "kiss", "Mobile")
    # Held as the table holds a device: by the name its search resolved
    e.ctl.radios.claims.hold(Claim("serial", claim_value("COM7") or "", FM_ID))
    error = await refused(page, {"cmd": "set_config", "values": {f"radio/{id}/port": "COM7"}})
    assert (error["key"], error["code"], error["params"]) == (
        f"radio/{id}/port",
        "radio.resource_held",
        {"resource": "serial", "holder": "Packet", "held_by": FM_ID},
    )
    monkeypatch.setattr(
        web_handlers,
        "offered_ports",
        lambda: [
            PortInfo("COM7", "USB Serial Port (COM7)", "USB VID:PID=0403:6001", 0x0403, 0x6001),
            PortInfo("COM8", "Bluetooth", "BTHENUM", None, None),
        ],
    )
    monkeypatch.setattr(web_handlers, "paired_bluetooth_ports", lambda: [])
    await page.send({"cmd": "list_ports", "radio": id})
    ports = (await page.expect("ports"))["ports"]
    assert [(p["device"], p["held_by"]) for p in ports] == [("COM7", FM_ID), ("COM8", None)]
    from neoaprs.mercurycards import SoundCard

    hf = await added(page, "mercury")
    modem = e.ctl.radios.get(hf).driver.modem  # type: ignore[union-attr]
    # Its start lets go of what the radio held, the claim made by hand below too
    await at_rest(modem)
    monkeypatch.setattr(
        modem,
        "sound_cards",
        lambda: [SoundCard("plughw:CARD=A", "A"), SoundCard("plughw:CARD=B", "B"), SoundCard("plughw:CARD=C", "C")],
    )
    e.ctl.radios.claims.hold(Claim("sound_card", "plughw:CARD=A", id))
    e.ctl.radios.claims.hold(Claim("sound_card", "plughw:CARD=B", hf))
    await page.send({"cmd": "list_ports", "radio": hf})
    answer = await page.expect("ports")
    cards = answer["sound_cards"]
    assert answer["radio"] == hf, "the answer says which radio it is for: the cards and the proposals are that radio's"
    assert [(c["id"], c["held_by"], c["pick"]) for c in cards] == [
        ("plughw:CARD=A", id, False),
        ("plughw:CARD=B", hf, True),
        ("plughw:CARD=C", None, False),
    ], "each card with who holds it; the proposal (for the radio named) leaves out what another radio holds"
    await page.send({"cmd": "list_ports"})
    bare = await page.expect("ports")
    assert (bare["sound_cards"], bare["radio"]) == ([], None), "a list for no radio has no sound card and names none"
    await e.stop()


def test_every_type_whose_row_carries_its_lines_says_it_has_a_terminal() -> None:
    """Every driver keeps the lines of the row (`lines`), the Dummies' made-up traffic too: so every
    type says it has a Terminal, and a new type that has none must say so."""
    from neoaprs.radiotypes import TYPES

    assert [t.key for t in TYPES if not t.can.terminal] == [], (
        "the page draws the Terminal of a type that says it has one"
    )


async def test_every_page_is_told_the_new_radio_of_a_call_no_radio_heard_at_once_not_at_the_next_status_of_the_timer(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "kiss", "Mobile")
    other = await e.ws()
    await other.until(lambda: len(other.of("status")) > 0)
    await page.send({"cmd": "radio_change", "radio": FM_ID, "position": 9})
    # The timer tells the status every 10 s
    await other.until(lambda: other.of("status")[-1]["unheard_radio"] == id, timeout=30)
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await other.until(lambda: other.of("status")[-1]["unheard_radio"] == FM_ID, timeout=30)
    await e.stop()


async def test_a_station_is_given_a_radio_and_a_path_on_it_and_its_row_says_both(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    row = page.topics["stations"]["OH2XYZ"]
    assert (row["radio_choice"], row["radio_now"], row["paths"], row["heard"]) == (
        None,
        FM_ID,
        {},
        {"1": {"count": 1, "last_at": row["last_heard"]}},
    )
    await page.send({"cmd": "station_radio", "call": "OH2XYZ", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["radio_choice"] == id)
    assert page.topics["stations"]["OH2XYZ"]["radio_now"] == id
    await page.send({"cmd": "set_station_path", "call": "OH2XYZ", "path": "OH2RCH-2", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["paths"] == {str(id): "OH2RCH-2"})
    assert "OH2XYZ" not in page.topics["station_prefs"], "radio 1's entry is not touched"
    await page.send({"cmd": "clear_station_path", "call": "OH2XYZ", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["paths"] == {})
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["radio_choice"] is None, timeout=30)
    assert page.topics["stations"]["OH2XYZ"]["radio_now"] == FM_ID, "a radio that is off is no choice"
    await page.send({"cmd": "station_radio", "call": "OH2XYZ", "radio": None})
    await page.until(lambda: e.ctl.radios.choice("OH2XYZ") is None)
    await e.stop()


async def test_a_stations_row_says_the_reply_path_on_a_radio_without_paths_without_rfonly(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy-hf")
    await page.send({"cmd": "set_station_rf_only", "call": "OH2XYZ", "on": True})
    await page.until(lambda: "OH2XYZ" in page.topics["station_prefs"])
    e.ctl.stationbook.take(
        replace(heard(">here", "OH2XYZ", ("OH2RCH-2*", "OH2GBA-12*"), at=e.ctl.clock()), radio_id=id)
    )
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    assert page.topics["stations"]["OH2XYZ"]["replies"] == {str(id): "OH2GBA-12,WIDE2-1"}, (
        "RF only is its own box: the path the page shows is the gateway's"
    )
    assert e.ctl.prefbook.path_for("OH2XYZ", None, id) == ("OH2GBA-12", "WIDE2-1", "RFONLY"), "the frame carries it"
    e.ctl.stationbook.take(replace(heard(">here", "OH2XYZ", at=e.ctl.clock()), radio_id=id))
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["replies"] == {}, timeout=30)
    await e.stop()


async def test_a_pair_switched_on_makes_its_call_ours_and_the_stations_row_loses_the_reply_through_it(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)
    low = await added(page, "dummy")
    id = await added(page, "dummy-hf")
    await page.send(
        {"cmd": "set_config", "values": {f"pair/{low}/{id}/ssid": "12", f"pair/{low}/{id}/enabled": "false"}}
    )
    await page.until(lambda: e.ctl.config.pairs and e.ctl.config.pairs[0].ssid == 12)
    e.ctl.stationbook.take(replace(heard(">here", "OH2XYZ", ("OH2GBA-12*",), at=e.ctl.clock()), radio_id=id))
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    assert page.topics["stations"]["OH2XYZ"]["replies"] == {str(id): "OH2GBA-12"}, (
        "the pair is off: its call is a gateway's"
    )
    await page.send({"cmd": "set_config", "values": {f"pair/{low}/{id}/enabled": "true"}})
    # Nothing was heard: only the own calls changed
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["replies"] == {}, timeout=30)
    await e.stop()


async def test_ask_around_goes_on_its_ticked_radios_and_local_info_on_the_radio_named_and_a_radio_that_is_off_is_refused_with_its_name(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    assert page.topics["general"]["by_radio"] == []
    error = await refused(page, {"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True})
    assert (error["code"], error["params"]["radio"]) == ("radio.not_connected", FM_ID), (
        "the radio added took over none of the ticks: Ask around stays on the first box, which is not connected here"
    )
    # Two ticks: one taken away, one given
    await page.send({"cmd": "set_config", "values": {f"radio/{FM_ID}/ask": "false", f"radio/{id}/ask": "true"}})
    await page.until(lambda: page.topics["radios"][str(id)]["choices"]["ask"])
    assert {spec.id: spec.settings.get("ask") for spec in await e.ctl.store.read_radios()} == {
        FM_ID: "false",
        id: "true",
    }, "each tick sent is stored, the one taken away too"
    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True})
    await page.until(lambda: [a["radios"] for a in page.topics["general"]["asked"]] == [[id]])
    two = await added(page, "dummy", "Two")
    await page.until(lambda: page.topics["radios"][str(two)]["state"] == "connected")
    assert (
        page.topics["radios"][str(two)]["choices"]["ask"],
        page.topics["radios"][str(two)]["choices"]["local_info"],
    ) == (False, False), "a radio added later starts with its beacon only"
    error = await refused(page, {"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True, "radio": two})
    assert error["code"] == "invalid", "Ask around names no radio: its Send on says them"
    await page.send(
        {
            "cmd": "set_config",
            "values": {f"radio/{FM_ID}/ask": "false", f"radio/{id}/ask": "false", f"radio/{two}/ask": "true"},
        }
    )
    await page.until(
        lambda: (
            page.topics["radios"][str(two)]["choices"]["ask"] and not page.topics["radios"][str(id)]["choices"]["ask"]
        )
    )
    await page.send({"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True})
    await page.until(
        lambda: [(a["radio"], a["kind"]) for a in page.topics["general"]["by_radio"]] == [(id, "aprs"), (two, "aprs")]
    )
    assert [a["radios"] for a in page.topics["general"]["asked"]] == [[two]], (
        "the latest of each kind, with its radios; the wait of each radio is its own"
    )
    await page.send({"cmd": "qru_ask", "text": "INFO", "radio": id})
    await page.until(lambda: page.topics["qru"]["asked"] is not None and page.topics["qru"]["asked"]["radios"] == [id])
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"])
    error = await refused(page, {"cmd": "qru_ask", "text": "INFO 50", "radio": id})
    assert (error["code"], error["params"]) == ("radio.off", {"name": "Shack", "radio": id}), (
        "a radio switched off is said to be off, not to be unplugged"
    )
    assert (await refused(page, {"cmd": "qru_ask", "text": "INFO", "radio": 9}))["code"] == "radio.unknown"
    await e.stop()


async def test_an_object_goes_on_the_radios_named_and_its_row_says_them(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    base = {
        "cmd": "object_set",
        "kind": "object",
        "lat": 60,
        "lon": 25,
        "symbol_table": "/",
        "symbol_code": ">",
        "comment": "",
        "course_deg": None,
        "speed_kmh": None,
        "path": None,
        "qru_group": "",
        "on_request": True,
    }
    await page.send({**base, "name": "BOTH", "radios": [FM_ID, id]})
    await page.until(lambda: "BOTH" in page.topics["own_objects"])
    assert (
        page.topics["own_objects"]["BOTH"]["radios"] == [FM_ID, id]
        and "radio" not in page.topics["own_objects"]["BOTH"]
    )
    assert (await refused(page, {**base, "name": "OLD", "radio": "fm"}))["code"] == "invalid", (
        "an object names its radios by their ids"
    )
    await e.stop()


async def test_the_topic_tells_a_radio_at_most_four_times_a_second(tmp_path: Path) -> None:
    """A second of changes, one every 25 ms of the hub's clock, which the test keeps (forty sleeps
    of the machine's are not a second: on Windows a sleep of 25 ms lasts two steps of its clock, 31
    ms)."""
    e, page = await started(tmp_path)
    assert e.server is not None
    hub, now = e.server.api.hub, [0.0]
    now[0] = hub.clock() + 1.0  # (whatever was waiting is due at once)
    hub.clock = lambda: now[0]
    await page.quiet(0.4)
    before = len(page.ops("radios"))
    for _ in range(40):
        e.ctl.radio_changed.emit(FM_ID)
        now[0] += 0.025
        await asyncio.sleep(0.025)
    now[0] += 0.25  # (the last change is due)
    await page.quiet(0.4)
    told = [op for op in page.ops("radios")[before:] if op.get("key") == "1"]
    assert 1 <= len(told) <= 6, f"a second of changes was told {len(told)} times"
    await e.stop()


async def test_what_the_pairs_passed_rides_the_row_of_the_radio_it_went_out_on_and_a_held_frame_is_told(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)
    radio = e.ctl.radios.get(FM_ID)
    assert radio is not None and page.topics["radios"]["1"]["stats"]["passed"] == []
    radio.stats.passed[HF_ID] = PassCount(sent=1, sent_at=e.ctl.clock(), held=3)
    radio.stats.passed[3] = PassCount(too_long=1)
    # A held frame changes no counter of the line: the digipeater tells it
    e.ctl.digipeater.counted.emit(FM_ID)
    await page.until(lambda: len(page.topics["radios"]["1"]["stats"]["passed"]) == 2)
    row = page.topics["radios"]["1"]
    assert ROW.validate_python(row) and [
        (p["heard_on"], p["sent"], p["held"], p["too_long"]) for p in row["stats"]["passed"]
    ] == [(HF_ID, 1, 3, 0), (3, 0, 0, 1)], "by the radio heard on, in the order of its id"
    assert row["stats"]["passed"][0]["sent_at"] is not None and row["stats"]["passed"][1]["sent_at"] is None
    await e.stop()


async def test_the_frequencies_are_asked_for_by_the_station_level_command_too(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    asked: list[bool] = []
    e.ctl.frequencies.wanted = lambda: asked.append(True)  # type: ignore[method-assign]
    await page.send({"cmd": "frequencies"})
    await page.until(lambda: len(asked) == 1)
    await e.stop()


def test_a_radio_of_a_type_that_is_none_has_no_row_and_the_types_are_the_pages_list() -> None:
    from neoaprs.claims import Claims
    from neoaprs.radiotypes import TYPES
    from neoaprs.web.radioview import radio_row
    from tests.test_protocol import generator

    stranger = RadioSpec(5, "fm", "carrier-pigeon", "", True, 5)
    assert radio_row(stranger, (stranger,), None, Claims()) is None
    lists = generator().LISTS.read_text(encoding="utf-8")
    listed = json.loads(
        lists.split("export const RADIO_TYPES = ", 1)[1]
        .split(" as const;", 1)[0]
        .replace(",\n  ]", "\n  ]")
        .replace(",\n    ]", "\n    ]")
        .replace(",\n      }", "\n      }")
        .replace(",\n  }", "\n  }")
        .replace(",\n]", "\n]")
    )
    assert sorted(t["key"] for t in listed) == sorted(t.key for t in TYPES) and all(t["fields"] for t in listed)
    assert {t["key"]: t["dummy"] for t in listed} == {t.key: t.dummy for t in TYPES}, (
        "the page tells a Dummy from a real type by the type's own fact (Add radio's Without a radio)"
    )


async def test_a_message_on_its_way_says_the_radio_it_takes_next_as_the_choice_and_the_radios_change(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy", "Shack")
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2XYZ" in page.topics["stations"])
    await page.send({"cmd": "station_radio", "call": "OH2XYZ", "radio": id})
    await page.until(lambda: page.topics["stations"]["OH2XYZ"]["radio_choice"] == id)
    await page.send({"cmd": "send_message", "to": "OH2XYZ", "text": "on the shack"})
    await page.until(
        lambda: [m["radio_now"] for m in page.topics["messages"].values() if m["to_call"] == "OH2XYZ"] == [id]
    )
    [key] = [k for k, m in page.topics["messages"].items() if m["to_call"] == "OH2XYZ"]

    def told() -> tuple[object, object]:
        return page.topics["messages"][key]["radio_now"], page.topics["stations"]["OH2XYZ"]["radio_now"]

    steps: list[tuple[dict[str, Any], int]] = [
        ({"cmd": "station_radio", "call": "OH2XYZ", "radio": None}, FM_ID),
        ({"cmd": "station_radio", "call": "OH2XYZ", "radio": id}, id),
        ({"cmd": "radio_change", "radio": id, "enabled": False}, FM_ID),
        ({"cmd": "radio_change", "radio": id, "enabled": True}, id),
        ({"cmd": "radio_remove", "radio": id}, FM_ID),
    ]
    for command, now in steps:
        await page.send(command)
        # The clock of the test stands: no attempt is made meanwhile, the row is told by the change
        # itself
        await page.until(lambda now=now: told() == (now, now), timeout=30)
    assert page.topics["messages"][key]["state"] == "sending"
    await e.stop()


async def test_a_call_the_book_does_not_hold_is_chosen_for_by_call_and_its_row_says_it_once_it_is_heard(
    tmp_path: Path,
) -> None:
    """The choice is kept by call, with or without a station in the book."""
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    await page.send({"cmd": "station_radio", "call": " oh2new ", "radio": id})
    # The daemon's own state, looked at every step: no message to the page need follow the command
    await until(lambda: e.ctl.radios.choice("OH2NEW") == id)
    assert "OH2NEW" not in page.topics["stations"] and page.of("error") == [], (
        "taken in the call's normal form, with no station to tell"
    )
    error = await refused(page, {"cmd": "station_radio", "call": "not a call!", "radio": id})
    assert error["code"] == "call.shape" and json.loads(e.ctl.radios.choices_text()) == {"OH2NEW": id}, (
        "a text that is no call is refused and nothing is kept for it"
    )
    e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2NEW", at=e.ctl.clock()), radio_id=FM_ID))
    await page.until(lambda: "OH2NEW" in page.topics["stations"])
    row = page.topics["stations"]["OH2NEW"]
    assert (row["radio_choice"], row["radio_now"]) == (id, id), (
        "the station heard later has the choice made for its call"
    )
    await e.stop()


async def test_the_radio_chosen_for_email_is_told_in_force_by_the_status_and_one_that_is_removed_is_none_chosen(
    tmp_path: Path,
) -> None:
    e, page = await started(tmp_path)

    async def in_force() -> int | None:
        before = len(page.of("status"))
        await page.send({"cmd": "status"})
        await page.until(lambda: len(page.of("status")) > before)
        return page.of("status")[-1]["email_radio"]

    assert (
        page.topics["config"]["radio_values"]["email/radio"] == ""
        and "email/radio" not in page.topics["config"]["values"]
        and await in_force() == FM_ID
    )
    id = await added(page, "dummy-hf", "Far")
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == str(FM_ID))
    assert await in_force() == FM_ID, (
        "a radio that comes on moves no mail: the radio it went on is written as the choice (sendonrule)"
    )
    await page.send({"cmd": "set_config", "values": {"email/radio": str(id)}})
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == str(id))
    assert e.ctl.config.email_choice == id and await in_force() == id, "any radio that can send, a Mercury one too"
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"])
    assert page.topics["config"]["radio_values"]["email/radio"] == str(id) and await in_force() == FM_ID, (
        "off: the choice is kept, and the mail goes on the one radio that is on"
    )
    await page.send({"cmd": "radio_remove", "radio": id})
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == "")
    assert e.ctl.config.email_choice is None and await in_force() == FM_ID, "removed: the choice goes with it"
    await page.send(
        {
            "cmd": "set_config",
            "values": {**page.topics["config"]["radio_values"], "station/comment": "what it was given"},
        }
    )
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "what it was given")
    assert e.ctl.config.email_choice is None and not page.of("error"), "a form that sends back what it was given saves"
    assert (await refused(page, {"cmd": "set_config", "values": {"email/radio": str(id)}}))[
        "code"
    ] == "radio.unknown", "choosing the removed radio is refused"
    await e.stop()


async def test_the_stations_are_told_whole_only_when_what_their_rows_read_of_the_radios_changes(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    await page.quiet(0.6)

    def wholes() -> int:
        return sum(op["op"] == "replace" for op in page.ops("stations"))

    before = wholes()
    await page.send({"cmd": "radio_change", "radio": id, "name": "Shack"})
    await page.send({"cmd": "set_config", "values": {f"radio/{id}/path": "WIDE1-1", "radio/1/path": "WIDE2-2"}})
    await page.until(
        lambda: (
            page.topics["config"]["radio_values"]["radio/1/path"] == "WIDE2-2"
            and page.topics["radios"][str(id)]["name"] == "Shack"
        )
    )
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
        refuse_held(
            before,
            replace(before, radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3"), kiss(6, "/dev/ttyUSB3"))),
            claims,
        )
    assert (held.value.key, held.value.code, held.value.params) == (
        "radio/6/port",
        "radio.resource_held",
        {"resource": "serial", "holder": "Packet 2", "held_by": 5},
    ), "set to it, though not holding it yet"
    refuse_held(
        before,
        replace(before, radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3", on=False), kiss(6, "/dev/ttyUSB3"))),
        claims,
    )
    claims.hold(Claim("serial", claimed_value("serial", "/dev/ttyUSB0"), 1))
    claims.hold(Claim("serial", claimed_value("serial", "/dev/ttyUSB3"), 5))
    refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyUSB3"), kiss(5, "/dev/ttyUSB0"), kiss(6, ""))), claims)
    claims.hold(Claim("gps", claimed_value("gps", "/dev/ttyACM0"), None))
    with pytest.raises(SettingError) as gps:
        refuse_held(
            before, replace(before, radios=(kiss(1, "/dev/ttyACM0"), kiss(5, "/dev/ttyUSB3"), kiss(6, ""))), claims
        )
    assert (gps.value.key, gps.value.params) == (
        "radio/1/port",
        {"resource": "serial", "holder": "GPS", "held_by": 0},
    ), "the radio's own key, and the receiver named"
    # A device not named again is not looked at
    refuse_held(before, replace(before, radios=(*before.radios[:2], replace(kiss(6, ""), name="Six"))), claims)


async def test_an_object_on_a_radio_that_is_removed_is_told_without_it(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    id = await added(page, "dummy")
    base = {
        "cmd": "object_set",
        "kind": "object",
        "lat": 60,
        "lon": 25,
        "symbol_table": "/",
        "symbol_code": ">",
        "comment": "",
        "course_deg": None,
        "speed_kmh": None,
        "path": None,
        "qru_group": "",
        "on_request": True,
    }
    await page.send({**base, "name": "BOTH", "radios": [FM_ID, id]})
    await page.send({**base, "name": "ALONE", "radios": [id]})
    await page.until(lambda: {"BOTH", "ALONE"} <= set(page.topics["own_objects"]))
    await page.send({"cmd": "radio_remove", "radio": id})
    await page.until(lambda: page.topics["own_objects"]["BOTH"]["radios"] == [FM_ID], timeout=30)
    assert page.topics["own_objects"]["ALONE"]["radios"] == [id], (
        "an object on no other radio keeps it, as its row does (ticked nowhere: it waits)"
    )
    await e.stop()


async def test_a_modems_commands_reach_the_modem_of_the_radio_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.setattr(
        e.ctl.radios,
        "get",
        lambda radio: (
            SimpleNamespace(
                spec=shack.spec, rtype=type_of("mercury"), name=shack.name, driver=SimpleNamespace(modem=Modem())
            )
            if radio == id
            else real(radio)
        ),
    )
    for command in (
        {"cmd": "radio_tune", "radio": id, "on": True},
        {"cmd": "radio_tune", "radio": id, "on": False},
        {"cmd": "radio_key_test", "radio": id},
    ):
        await page.send(command)
    # Looked at every step: the commands answer the page nothing
    await until(lambda: done == ["tune", "stop", "key"])
    assert not page.of("error")
    await e.stop()


async def test_tune_and_the_keying_test_on_a_type_that_has_neither_are_refused_though_its_driver_has_a_running_modem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The type is the one word on what a radio may do: the Dummy HF radio's driver has a modem (its
    speaker), and its type says no Tune and no keying test; stopping a tone is never refused."""
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "dummy-hf"})
    hf = e.ctl.radios.get(HF_ID)
    assert hf is not None and hf.rtype.key == "dummy-hf" and not hf.rtype.can.tune and not hf.rtype.can.key_test
    modem, done = hf.driver.modem, []
    assert modem is not None

    async def did(what: str) -> None:
        done.append(what)

    for name in ("tune", "tune_stop", "key_test"):
        # A modem that would do what it is asked: the type's word alone refuses
        monkeypatch.setattr(modem, name, lambda name=name: did(name))
    for command in ({"cmd": "radio_tune", "radio": HF_ID, "on": True}, {"cmd": "radio_key_test", "radio": HF_ID}):
        error = await refused(page, command)
        assert (error["cmd"], error["code"], error["params"]) == (
            command["cmd"],
            "radio.no_modem",
            {"name": hf.name, "radio": HF_ID},
        )
    await page.send({"cmd": "radio_tune", "radio": HF_ID, "on": False})
    await page.until(lambda: done == ["tune_stop"])
    await e.stop()


def test_a_running_modem_that_is_the_dummy_hf_radios_speaker_tunes_nothing_and_writes_nothing() -> None:
    """The modem's own guard under the type's: a Mercury started as the speaker refuses Tune and the
    keying test as not running, and no TUNE line is written."""
    from neoaprs.coded import CodedError
    from neoaprs.mercury import keying_of
    from neoaprs.mercurytune import Tuning
    from neoaprs.signal import Signal
    from neoaprs.tasks import TaskSet

    written: list[str] = []

    class Speaker(Tuning):
        speaker, test, tx_gain_db, keying = True, "", 0, keying_of("vox")

        # The whole of the modem's state the tone uses, so that without the guard the tone starts
        # and its line is written
        def __init__(self) -> None:
            self.changed, self._tasks, self._generation, self._test_task = Signal(), TaskSet(lambda task: None), 0, None

        @property
        def running(self) -> bool:
            return True

        def hold(self) -> str:
            return ""

        def _write(self, line: str) -> bool:
            written.append(line)
            return True

    async def outcome(begin: str) -> str:
        try:
            await getattr(Speaker(), begin)()
        except CodedError as refusal:
            return refusal.code
        return "begun"

    codes = [asyncio.run(outcome(begin)) for begin in ("tune", "key_test")]
    assert written == []
    assert codes == ["hf.not_running", "hf.not_running"]


async def test_a_modems_command_on_a_radio_whose_modem_is_not_running_is_refused_with_that_radios_name(
    tmp_path: Path,
) -> None:
    """The Dummy HF radio has a modem part that never runs, as a Mercury radio whose modem is down:
    the refusal names the radio, not the HF radio of before."""
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "dummy-hf"})
    await page.until(lambda: page.topics["radios"]["2"]["state"] == "connected")
    await page.send({"cmd": "radio_change", "radio": HF_ID, "name": "Attic"})
    await page.until(lambda: page.topics["radios"]["2"]["name"] == "Attic")
    for command in ({"cmd": "radio_tune", "radio": HF_ID, "on": True}, {"cmd": "radio_key_test", "radio": HF_ID}):
        error = await refused(page, command)
        assert (error["code"], error["params"], error["text"]) == (
            "radio.no_modem",
            {"name": "Attic", "radio": HF_ID},
            f"{command['cmd']}: radio Attic has no modem running",
        ), command
    await e.stop()


async def test_with_no_radio_that_sends_a_command_that_names_none_is_refused_with_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neoaprs.radioregistry import RadioRegistry

    e, page = await started(tmp_path)
    monkeypatch.setattr(RadioRegistry, "senders", lambda self: [])
    for command in (
        {"cmd": "qru_ask", "text": "INFO"},
        {"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True},
    ):
        error = await refused(page, command)
        assert (error["code"], error["params"]) == ("radio.none", {}), command
    await e.stop()


def test_a_radio_that_is_not_connected_says_why_by_a_code() -> None:
    from types import SimpleNamespace
    from neoaprs.claims import Claims
    from neoaprs.radiohealth import claimed_value, radio_health
    from neoaprs.source import Source
    from neoaprs.web.radioview import problem_row

    radio = RadioSpec(1, "fm", "kiss", "Mobile", True, 1, settings={"port": "/dev/ttyUSB0"})

    def problem(spec: RadioSpec, state: Source.State, searching: bool = False, modem: Any = None) -> Any:
        # A line that takes frames when it is connected
        line = SimpleNamespace(
            state=state,
            searching=searching,
            silent_since=None,
            modem_in_use=modem,
            why_unusable=lambda: "",
            write_stuck=None,
            problem="",
            entering_kiss=False,
            usable=state is Source.State.CONNECTED,
        )
        return problem_row(radio_health(spec, (radio,), SimpleNamespace(line=line, driver_key="tnc"), claims))

    claims = Claims()
    assert problem(radio, Source.State.CONNECTED) is None
    assert problem(replace(radio, enabled=False), Source.State.STOPPED) is None
    assert problem(radio, Source.State.WAITING) == {"code": "radio.not_connected", "params": {"name": "Mobile"}}
    assert problem(radio, Source.State.WAITING, searching=True) == {"code": "radio.searching", "params": {}}
    assert problem(radio, Source.State.SILENT) == {"code": "radio.silent", "params": {"since": ""}}
    not_installed = SimpleNamespace(state="waiting", reason="not_installed", test="")
    assert problem(radio, Source.State.WAITING, modem=not_installed) == {"code": "modem.not_installed", "params": {}}
    claims.hold(Claim("gps", claimed_value("gps", "/dev/ttyUSB0"), None))
    assert problem(radio, Source.State.WAITING) == {
        "code": "radio.resource_held",
        "params": {"resource": "serial", "holder": "GPS", "held_by": 0},
    }, "the device first"


async def test_radio_1_can_be_made_a_sound_card_radio_and_the_daemon_starts_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Radio 1 is a box like any other (the page offers it Sound card (Direwolf) in its Radio type):
    the change is taken, stored, and a daemon started on the folder runs radio 1 as that type."""
    # An installation that carries Direwolf; this checkout has none, so its modem waits
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)
    e, page = await started(tmp_path)
    await page.send({"cmd": "radio_change", "radio": FM_ID, "type": "direwolf"})
    await page.until(lambda: page.topics["radios"]["1"]["type"] == "direwolf" or bool(page.of("error")))
    assert not page.of("error"), page.of("error")
    assert getattr(e.ctl.config.radio(FM_ID), "type", None) == "direwolf" and not page.of("error")
    await e.stop()
    again, page = await started(tmp_path)
    try:
        row = page.topics["radios"]["1"]
        assert (row["type"], row["kind"], row["enabled"]) == ("direwolf", "fm", True) and ROW.validate_python(row)
        assert getattr(again.ctl.radios.get(FM_ID), "rtype", None) is type_of("direwolf")
    finally:
        await again.stop()
