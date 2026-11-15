"""How the refusals name a radio on the wire: a removed radio is said to be removed, by its name, where its id would say nothing to the operator ("there is no radio 3"); a name typed that is what another radio with no
name of its own is called ("FM", "HF 2") is taken already, and one in that form ("FM 3", "LoRa") is refused, since an add, a clear or a remove may make it another radio's; the last radio that is on, switched off by its key, is named by its id. Over the page's socket of a real daemon."""
from pathlib import Path

from neoaprs.radiospec import FM_ID
from tests.test_radios_wire import added, refused, started


async def test_a_removed_radio_is_refused_as_removed_with_its_name_and_a_radio_that_never_was_by_its_number(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    gone = await added(page, "dummy")
    await page.send({"cmd": "radio_remove", "radio": gone})
    await page.until(lambda: page.topics["radios"][str(gone)]["removed"])
    for command in ({"cmd": "radio_change", "radio": gone, "name": "Back"}, {"cmd": "radio_remove", "radio": gone}, {"cmd": "radio_tune", "radio": gone, "on": True},
                    {"cmd": "station_radio", "call": "OH2XYZ", "radio": gone}, {"cmd": "qru_ask", "text": "INFO", "radio": gone}):
        error = await refused(page, command)
        assert (error["code"], error["params"], error["text"]) == ("radio.unknown", {"radio": gone, "name": "FM 2", "removed": 1}, f"{command['cmd']}: radio FM 2 is removed"), command
    error = await refused(page, {"cmd": "set_config", "values": {f"radio/{gone}/path": "WIDE1-1"}})
    assert (error["key"], error["params"], error["text"]) == (f"radio/{gone}/path", {"radio": gone, "name": "FM 2", "removed": 1}, f"set_config: radio/{gone}/path: radio FM 2 is removed")
    error = await refused(page, {"cmd": "set_config", "values": {"station/main_radio": str(gone)}})
    assert (error["key"], error["params"]) == ("station/main_radio", {"radio": gone, "name": "FM 2", "removed": 1})
    for command in ({"cmd": "radio_change", "radio": 9, "name": "Never"}, {"cmd": "radio_tune", "radio": 9, "on": True}):
        error = await refused(page, command)
        assert (error["params"], error["text"]) == ({"radio": 9}, f"{command['cmd']}: " + ("radio 9: there is no such radio" if command["cmd"] == "radio_change" else "there is no radio 9")), "as before"
    await e.stop()


async def test_a_name_that_is_what_another_radio_is_called_is_taken(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    for typed, kept in (("FM", "FM"), (" fm ", "fm")):
        error = await refused(page, {"cmd": "radio_add", "type": "dummy", "name": typed})
        assert (error["code"], error["params"], error["text"]) == ("radio.name_taken", {"name": kept, "radio": FM_ID}, f"radio_add: the name '{kept}' is another radio's already: give this one another"), typed
    two = await added(page, "dummy")
    assert page.topics["radios"][str(two)]["name"] == "" and page.topics["radios"][str(two)]["number"] == 2
    error = await refused(page, {"cmd": "radio_change", "radio": FM_ID, "name": "fm 2"})
    assert (error["code"], error["params"]) == ("radio.name_taken", {"name": "fm 2", "radio": two}), "the second FM radio is FM 2"
    await e.stop()


async def test_a_name_in_the_form_of_a_radio_with_no_name_of_its_own_is_refused_so_that_none_becomes_another_radios_by_an_add_a_clear_or_a_remove(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    for command in ({"cmd": "radio_add", "type": "dummy", "name": "FM 3"}, {"cmd": "radio_add", "type": "dummy", "name": "HF"}, {"cmd": "radio_add", "type": "dummy", "name": "lora 7"},
                    {"cmd": "radio_change", "radio": FM_ID, "name": " Fm 1 "}):
        error = await refused(page, command)
        typed = str(command["name"]).strip()
        assert (error["code"], error["params"], error["text"]) == ("radio.name_label", {"name": typed},
                                                                   f"{command['cmd']}: the name '{typed}' is how a radio without a name of its own is called: give this one another"), command
    two = await added(page, "dummy")
    three = await added(page, "dummy")
    assert [page.topics["radios"][str(id)]["number"] for id in (two, three)] == [2, 3], "the radios added unnamed are FM 2 and FM 3, and no radio is called so by a name typed"
    for name in ("FM 2X", "FM2", "FMS", "Home"):
        await page.send({"cmd": "radio_change", "radio": FM_ID, "name": name})
        await page.until(lambda name=name: page.topics["radios"]["1"]["name"] == name)       # type: ignore[misc]
    await page.send({"cmd": "radio_remove", "radio": two})
    await page.until(lambda: page.topics["radios"][str(three)]["number"] == 2)
    error = await refused(page, {"cmd": "radio_change", "radio": FM_ID, "name": "FM 3"})
    assert (error["code"], error["params"]) == ("radio.name_label", {"name": "FM 3"}), "FM 3 is no radio's now, and would be the next one added"
    assert await e.ctl.change_radio(three, name="FM 9"), "a name stored before the rule"
    await page.until(lambda: page.topics["radios"][str(three)]["name"] == "FM 9")
    await page.send({"cmd": "radio_change", "radio": three, "name": "FM 9", "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(three)]["enabled"])
    assert page.topics["radios"][str(three)]["name"] == "FM 9", "the radio's own name, sent again by a form, is taken"
    await e.stop()


async def test_the_last_radio_that_is_on_switched_off_is_named_by_its_id(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    error = await refused(page, {"cmd": "radio_change", "radio": FM_ID, "enabled": False})
    assert (error["code"], error["params"]["radio"]) == ("radio.last_enabled", FM_ID)
    assert "turn another radio on first" in error["text"], "R1's words"
    await e.stop()
