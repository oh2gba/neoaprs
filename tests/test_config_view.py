"""Tests for the `config` topic: `values` holds the station settings and `radio_values` each radio's
own; `set_config` refuses a flat radio key with `setting.unknown` and stores nothing.
"""

import sqlite3
from dataclasses import replace
from pathlib import Path

from neoaprs.configradios import FLAT_HOMES
from neoaprs.config import BY_KEY, DEFAULTS
from neoaprs.radiospec import FM_ID, RadioSpec
from neoaprs.web.confighandlers import flat_refusal
from neoaprs.store import DB_NAME
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.views import CONFIG_KEYS
from tests.support.env import Env
from tests.support.wsclient import WsClient

FLAT = tuple(key for key, setting in BY_KEY.items() if setting.attr in FLAT_HOMES)


async def started(tmp_path: Path, settings: dict[str, str]) -> tuple[Env, WsClient]:
    e = Env(tmp_path, radio=False, web=True, settings=settings)
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return e, page


def rows_of(path: Path) -> tuple[dict[str, str], dict[tuple[int, str], str]]:
    db = sqlite3.connect(path / DB_NAME)
    try:
        return dict(db.execute("SELECT key, value FROM settings")), {
            (id, key): value for id, key, value in db.execute("SELECT radio_id, key, value FROM radio_setting")
        }
    finally:
        db.close()


async def test_the_config_topic_tells_the_stations_settings_and_each_radios_own_apart(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"serial/baud": "1200", "digi/enabled": "true"})
    config = page.topics["config"]
    fm = e.ctl.config.radio(FM_ID)
    assert fm is not None and (fm.type, dict(fm.settings)) == (
        "kenwood-tnc2",
        {"baud": "1200", "digipeat": "true", "path": "WIDE1-1,WIDE2-1"},
    )
    assert (
        sorted(config["values"]) == sorted(CONFIG_KEYS)
        and not set(FLAT) & set(config["values"])
        and not set(FLAT) & set(config["defaults"])
    ), "no flat key of a radio"
    assert (
        config["radio_values"]["radio/1/baud"],
        config["radio_values"]["radio/1/digipeat"],
        config["radio_values"]["radio/1/path"],
    ) == ("1200", "true", "WIDE1-1,WIDE2-1")
    await e.stop()


async def test_a_flat_key_of_a_radio_is_refused_with_the_radios_own_key_and_nothing_is_stored(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {})
    before = rows_of(tmp_path)
    # (the station of the Env: radio 1 an FM radio and no HF radio, so the keying names no id; the
    # Enable and the type of a radio are radio_change's)
    for key, own in (
        ("serial/port", "radio/1/port"),
        ("mercury/keying", "radio/<id>/keying"),
        ("hf/enabled", "radio_change's enabled"),
        ("tnc/profile", "radio_change's type"),
    ):
        await page.send({"cmd": "set_config", "values": {key: "x", "station/comment": "not stored"}})
        error = await page.expect("error")
        assert (error["code"], error["key"], error["text"]) == (
            "setting.unknown",
            key,
            f"set_config: {key}: no such setting: it is {own} now",
        ), key
    assert rows_of(tmp_path) == before and e.ctl.config.station_comment != "not stored", (
        "nothing of the command is stored"
    )
    await page.send({"cmd": "set_config", "values": {"radio/1/baud": "4800", "station/comment": "both"}})
    await page.until(lambda: page.topics["config"]["radio_values"]["radio/1/baud"] == "4800")
    await e.stop()
    settings, own = rows_of(tmp_path)
    assert settings["station/comment"] == "both" and not set(FLAT) & set(settings) and own[(FM_ID, "baud")] == "4800", (
        "the station's row in the settings, the radio's in its own"
    )


def test_the_refusal_of_a_flat_key_names_the_live_radio_of_its_kind_with_the_lowest_id_and_no_radio_the_station_has_not() -> (
    None
):
    def said(key: str, *radios: RadioSpec) -> str:
        error = flat_refusal(key, replace(DEFAULTS, radios=radios))
        assert error is not None and error.code == "setting.unknown"
        return str(error)

    fm3, fm5, hf4 = (
        RadioSpec(3, "fm", "kiss", "", True, 2),
        RadioSpec(5, "fm", "kiss", "", True, 1),
        RadioSpec(4, "hf", "mercury", "", True, 3),
    )
    assert said("serial/port") == "serial/port: no such setting: it is radio/<id>/port now", (
        "a station with no FM radio: no id to name"
    )
    assert said("serial/port", fm3, fm5, hf4) == "serial/port: no such setting: it is radio/3/port now", (
        "the FM radio with the lowest id, the station having no radio 1, whatever the order of the boxes"
    )
    assert said("mercury/keying", fm3, hf4) == "mercury/keying: no such setting: it is radio/4/keying now"
    assert said("hf/enabled", fm3) == "hf/enabled: no such setting: it is radio_change's enabled now"
    assert flat_refusal("station/call", DEFAULTS) is None and flat_refusal("radio/1/port", DEFAULTS) is None
