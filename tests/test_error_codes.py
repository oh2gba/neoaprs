"""The `error` message says what it answers (`cmd`), which setting it is about (`key`) and what is wrong (`code` and `params`), besides the English sentence: a page goes by the first three and never reads the sentence.
The settings' own refusals are SettingErrors with the same; a wrapper that only passes on the text of another refusal has its code."""
from pathlib import Path
from typing import Any

import pytest

from neoaprs.callsign import CallsignError, parse_call
from neoaprs.coded import CodedError
from neoaprs.config import DEFAULTS, Config, SettingError
from neoaprs.message import MessagingError, check_text, normal_path
from neoaprs.ownbulletin import PostError, make_bulletin, slot_of
from neoaprs.ownobject import OwnError, make_object
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.session import error_message
from tests.support.clock import FixedClock
from tests.support.env import Env

NOW = FixedClock()()


def refused(key: str, text: str) -> SettingError:
    with pytest.raises(SettingError) as e:
        Config.check(key, text)
    return e.value


def test_a_setting_that_is_wrong_is_a_setting_error_with_its_key_a_code_and_the_values_the_sentence_is_made_of() -> None:
    e = refused("station/lat", "95")
    assert (e.key, e.code, e.params) == ("station/lat", "setting.range", {"value": 95.0, "min": -90.0, "max": 90.0}) and str(e) == "station/lat: 95 is not between -90 and 90"
    assert (refused("tcp/port", "70000").code, refused("tcp/port", "70000").params) == ("setting.range", {"value": 70000, "min": 1, "max": 65535})
    assert refused("tcp/port", "x").code == "setting.not_whole" and refused("beacon/interval_min", "14").code == "setting.off_or_range"
    assert refused("station/lat", "x").code == "setting.not_number" and refused("web/network", "maybe").code == "setting.not_boolean"
    assert (refused("station/comment", "x" * 44).code, refused("station/comment", "x" * 44).params) == ("setting.too_long", {"length": 44, "max": 43})
    assert refused("station/comment", "a|b").code == "setting.tnc_char" and refused("station/comment", "café").code == "setting.not_ascii"
    assert refused("station/call", "OH2GBA-16").code == "call.ssid" and refused("station/call", "OH 2").code == "call.shape"
    assert refused("beacon/path", ",".join(["WIDE1-1"] * 9)).code == "path.too_long" and refused("status/template", "{x}").code == "setting.template_field"
    assert refused("status/rigctld", "nope").code == "setting.not_hostport" and refused("web/key", "abc").code == "setting.not_access_key"
    assert refused("tnc/profile", "nope").code == "setting.not_profile" and refused("beacon/antenna_direction", "up").code == "setting.not_direction"
    nothing = refused("tnc/check_sec", "5")
    assert (nothing.key, nothing.code) == ("tnc/check_sec", "setting.unknown") and str(nothing).startswith("tnc/check_sec: no such setting")


def test_the_rules_between_settings_name_the_setting_that_is_held_up() -> None:
    with pytest.raises(SettingError) as e:
        Config.checked(DEFAULTS, {"station/comment": "x" * 40, "beacon/power_w": "5"})
    assert (e.value.key, e.value.code, e.value.params) == ("station/comment", "setting.comment_too_long", {"length": 40, "limit": 36})
    with pytest.raises(SettingError) as e:
        Config.checked(DEFAULTS, {"status/source": "rig"})
    assert (e.value.key, e.value.code) == ("status/source", "setting.status_needs_rigctld")
    with pytest.raises(SettingError) as e:
        Config.checked(DEFAULTS, {"tnc/profile": "kiss-tcp", "serial/port": "/dev/ttyUSB0"})
    assert (e.value.key, e.value.code) == ("tnc/profile", "setting.profile_port") and e.value.params["port"] == "/dev/ttyUSB0"
    with pytest.raises(SettingError) as e:
        Config.checked(Config(tnc_profile="kiss-tcp"), {"serial/port": "COM3"})
    assert e.value.key == "serial/port"


def test_every_refusal_of_the_domain_that_the_page_shows_has_a_code() -> None:
    cases: list[tuple[type[CodedError], str, Any]] = [
        (CallsignError, "call.characters", lambda: parse_call("OH2GÄ")),
        (CallsignError, "call.shape", lambda: parse_call("TOOLONGCALL")),
        (CallsignError, "call.ssid", lambda: parse_call("OH2GBA-16")),
        (CodedError, "path.too_long", lambda: normal_path(",".join(["A1"] * 9))),
        (CodedError, "message.empty", lambda: check_text(" ")),
        (CodedError, "message.too_long", lambda: check_text("x" * 68)),
        (CodedError, "message.forbidden", lambda: check_text("a|b")),
        (CodedError, "message.not_ascii", lambda: check_text("café")),
        (CodedError, "message.control", lambda: check_text("a\tb")),
        (OwnError, "object.name_chars", lambda: make_object(NOW, "A_B", "object", 60.0, 24.0, "/", ">")),
        (OwnError, "object.name_length", lambda: make_object(NOW, "AB", "item", 60.0, 24.0, "/", ">")),
        (OwnError, "object.position", lambda: make_object(NOW, "AAA", "object", 91.0, 24.0, "/", ">")),
        (OwnError, "object.symbol", lambda: make_object(NOW, "AAA", "object", 60.0, 24.0, "?", ">")),
        (OwnError, "object.course", lambda: make_object(NOW, "AAA", "object", 60.0, 24.0, "/", ">", course_deg=360)),
        (OwnError, "object.speed", lambda: make_object(NOW, "AAA", "object", 60.0, 24.0, "/", ">", speed_kmh=2000.0)),
        (OwnError, "object.comment_length", lambda: make_object(NOW, "AAA", "object", 60.0, 24.0, "/", ">", "x" * 37, 90)),
        (OwnError, "setting.tnc_char", lambda: make_object(NOW, "AAA", "object", 60.0, 24.0, "/", ">", "a~b")),
        (OwnError, "call.shape", lambda: make_object(NOW, "AAA", "object", 60.0, 24.0, "/", ">", path="A B")),
        (PostError, "bulletin.slot", lambda: slot_of("NWS-WARN")),
        (PostError, "bulletin.group", lambda: slot_of("BLNAHAMS")),
        (PostError, "message.too_long", lambda: make_bulletin(NOW, "BLN1", "x" * 68)),
    ]
    for kind, code, make in cases:
        with pytest.raises(kind) as e:
            make()
        assert e.value.code == code, (code, str(e.value))


def test_the_error_message_has_every_field_and_a_number_json_has_no_word_for_goes_as_text() -> None:
    assert error_message("x") == {"type": "error", "cmd": "", "key": None, "code": "other", "params": {}, "text": "x"}
    message = error_message("set_config: station/lat: nan is not between -90 and 90", "set_config", "setting.range", "station/lat", {"value": float("nan"), "min": -90.0})
    assert message["params"] == {"value": "nan", "min": -90.0} and message["key"] == "station/lat"


async def asked(tmp_path: Path, *commands: dict[str, Any]) -> list[dict[str, Any]]:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    answers = []
    for command in commands:
        await page.send(command)
        answers.append(await page.expect("error"))
    await e.stop()
    return answers


async def test_a_page_is_told_the_command_the_key_and_the_code_of_every_refusal(tmp_path: Path) -> None:
    answers = await asked(
        tmp_path,
        {"cmd": "set_config", "values": {"station/lat": "95"}},
        {"cmd": "set_config", "values": {"beacon/power_w": "5", "station/comment": "x" * 40}},
        {"cmd": "set_config", "values": {"tnc/check_sec": "5"}},
        {"cmd": "send_message", "to": "OH2RDG", "text": "x" * 68},
        {"cmd": "send_message", "to": "OH2GBA", "text": "hello"},
        {"cmd": "object_set", "name": "A_B", "kind": "object", "lat": 60.0, "lon": 24.0, "symbol_table": "/", "symbol_code": ">", "comment": "", "course_deg": None, "speed_kmh": None, "path": None},
        {"cmd": "bulletin_post", "slot": "NWS-WARN", "text": "x"},
        {"cmd": "bulletin_unpost", "slot": "BLN3HAMS"},
        {"cmd": "forget_station", "call": "NOBODY"},
        {"cmd": "map_cancel"},
        {"cmd": "subscribe", "topics": ["nope"]},
    )
    seen = [(a["cmd"], a["key"], a["code"]) for a in answers]
    assert seen == [
        ("set_config", "station/lat", "setting.range"),
        ("set_config", "station/comment", "setting.comment_too_long"),
        ("set_config", "tnc/check_sec", "setting.unknown"),
        ("send_message", None, "message.too_long"),
        ("send_message", None, "other"),
        ("object_set", None, "object.name_chars"),
        ("bulletin_post", None, "bulletin.slot"),
        ("bulletin_unpost", None, "bulletin.not_posted"),
        ("forget_station", None, "station.unknown"),
        ("map_cancel", None, "map.no_job"),
        ("subscribe", None, "topic.unknown"),
    ]
    assert answers[0]["params"] == {"value": 95.0, "min": -90.0, "max": 90.0} and answers[0]["text"] == "set_config: station/lat: 95 is not between -90 and 90"
    assert answers[3]["params"] == {"length": 68, "max": 67} and answers[3]["text"].startswith("send_message: the text is 68 characters")
    assert answers[4]["text"] == "send_message: OH2GBA is our own call", "a refusal that has no code yet keeps its text"


async def test_a_frame_that_is_no_command_is_answered_with_a_code_and_the_command_when_it_named_one(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    for text in ("not json", "[1]", '{"cmd": "nope"}', "{}", '{"cmd": "forget_station"}'):
        await page.send_text(text)
    await page.until(lambda: len(page.of("error")) == 5)
    assert [(m["cmd"], m["code"]) for m in page.of("error")] == [("", "not_json"), ("", "not_object"), ("", "unknown_command"), ("", "no_command"), ("forget_station", "invalid")]
    assert all(m["key"] is None for m in page.of("error"))
    await e.stop()


def test_a_messaging_error_that_only_passes_on_another_has_the_code_of_the_other() -> None:
    try:
        try:
            check_text("x" * 68)
        except CodedError as inner:
            raise MessagingError(str(inner)) from None
    except MessagingError as e:
        assert e.code == "other" and isinstance(e.__context__, CodedError) and e.__context__.code == "message.too_long"
