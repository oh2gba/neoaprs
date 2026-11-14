"""Today's flat keys of the radios (tnc/profile, fm/enabled, serial/*, tcp/*, beacon/path, digi/enabled of radio 1; hf/*, mercury/* of radio 2) stay on the wire until wave 4 as a view of the radios
as they are stored (configradios.FLAT_HOMES): the `config` topic says what radios 1 and 2 say, and `set_config` of such a key changes that radio's own rows, never a row of the settings. The wire is as
it was."""
import sqlite3
from pathlib import Path

from neoaprs.config import DEFAULTS
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.store import DB_NAME
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.env import Env
from tests.support.wsclient import WsClient

FLAT = ("tnc/profile", "fm/enabled", "serial/port", "serial/baud", "tcp/host", "tcp/port", "beacon/path", "digi/enabled", "hf/enabled", "hf/profile", "mercury/sound_card", "mercury/keying", "mercury/tx_gain_db")


async def started(tmp_path: Path, settings: dict[str, str]) -> tuple[Env, WsClient]:
    e = Env(tmp_path, radio=False, web=True, settings=settings)
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return e, page


def rows_of(path: Path) -> tuple[set[str], dict[tuple[int, str], str]]:
    db = sqlite3.connect(path / DB_NAME)
    try:
        return {key for (key,) in db.execute("SELECT key FROM settings")}, {(id, key): value for id, key, value in db.execute("SELECT radio_id, key, value FROM radio_setting")}
    finally:
        db.close()


async def test_the_config_topic_says_of_the_flat_keys_what_radios_1_and_2_say(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"serial/baud": "1200", "digi/enabled": "true", "hf/enabled": "false", "mercury/keying": "vox", "mercury/tx_gain_db": "-4"})
    values = page.topics["config"]["values"]
    fm, hf = e.ctl.config.radio(FM_ID), e.ctl.config.radio(HF_ID)
    assert fm is not None and hf is not None and (fm.type, dict(fm.settings)) == ("kenwood-tnc2", {"baud": "1200", "digipeat": "true", "path": "WIDE1-1,WIDE2-1"})
    assert {key: values[key] for key in FLAT} == {**{key: DEFAULTS.to_data()[key] for key in FLAT}, "tnc/profile": "kenwood-tnc2", "serial/baud": "1200", "beacon/path": "WIDE1-1,WIDE2-1",
                                                  "digi/enabled": "true", "mercury/keying": "vox", "mercury/tx_gain_db": "-4"}
    assert sorted(values) == sorted(DEFAULTS.to_data()), "the keys of the wire, as they were"
    await e.stop()


async def test_set_config_of_a_flat_key_changes_the_radios_own_rows_and_the_topic_says_it(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"hf/enabled": "false"})
    await page.send({"cmd": "set_config", "values": {"serial/baud": "4800", "digi/enabled": "true", "mercury/keying": "rts:/dev/ttyUSB0", "station/comment": "both"}})
    await page.until(lambda: page.topics["config"]["values"]["mercury/keying"] == "rts:/dev/ttyUSB0")
    values = page.topics["config"]["values"]
    assert (values["serial/baud"], values["digi/enabled"], values["station/comment"]) == ("4800", "true", "both")
    await e.stop()
    settings, own = rows_of(tmp_path)
    assert not set(FLAT) & settings and "station/comment" in settings, "the station's row in the settings, the radios' in their own"
    assert own == {(FM_ID, "baud"): "4800", (FM_ID, "digipeat"): "true", (FM_ID, "path"): "WIDE1-1,WIDE2-1", (HF_ID, "keying"): "rts:/dev/ttyUSB0",
                   (HF_ID, "path"): "WIDE1-1,WIDE2-1"}, "(beacon/path is radio 2's too, as migration 31 keeps it)"


async def test_set_config_of_a_flat_key_of_the_hf_radio_where_there_is_none_writes_radio_2(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {})
    assert e.ctl.config.radio(HF_ID) is None and page.topics["config"]["values"]["hf/profile"] == "mercury", "no radio 2: the defaults of an HF radio that is off"
    await page.send({"cmd": "set_config", "values": {"hf/profile": "dummy-hf"}})
    await page.until(lambda: page.topics["config"]["values"]["hf/profile"] == "dummy-hf")
    hf = e.ctl.config.radio(HF_ID)
    assert hf is not None and (hf.kind, hf.type, hf.enabled) == ("hf", "dummy-hf", False) and page.topics["config"]["values"]["hf/enabled"] == "false"
    assert [(s.id, s.type) for s in await e.ctl.store.radios()] == [(FM_ID, "kenwood-tnc2"), (HF_ID, "dummy-hf")]
    await e.stop()


async def test_set_config_that_would_leave_no_radio_on_is_refused_and_nothing_is_stored(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"hf/enabled": "false"})
    before = await e.ctl.store.radios()
    await page.send({"cmd": "set_config", "values": {"fm/enabled": "false"}})
    error = await page.expect("error")
    assert error["code"] == "setting.no_radio" and error["key"] == "hf/enabled"
    assert await e.ctl.store.radios() == before and e.ctl.config.fm_enabled
    await e.stop()
