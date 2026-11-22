"""A new installation has no radio until the operator adds the first: the daemon's start writes no
radio and no row names a radio without a row. Each added radio gets a new id; a start on a database
with radios keeps them.
"""
import json
import logging
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from neoaprs.config import DEFAULTS, MESSAGE_RADIOS
from neoaprs.controller import Controller
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioedits import start_notes
from neoaprs.mercurydriver import modem_settings
from neoaprs.radiospec import FM_ID, HF_ID, RadioError, RadioSpec, modem_radio
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.stationchoices import StationChoices
from neoaprs.store import DB_NAME, Store
from tests.support.air import on_air
from tests.support.env import Env, until

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
RADIO = "SELECT id, kind, type, name, enabled, position, removed_at FROM radio ORDER BY id"


def tables(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """The rows of the database (the daemon stopped) of the radios, every column of them."""
    db = sqlite3.connect(path / DB_NAME)
    try:
        return {"radio": db.execute(RADIO).fetchall(), "radio_setting": db.execute("SELECT radio_id, key, value, rev FROM radio_setting ORDER BY radio_id, key").fetchall(),
                "settings": db.execute("SELECT key, value, rev FROM settings ORDER BY key").fetchall(), "sequence": db.execute("SELECT seq FROM sqlite_sequence WHERE name = 'radio'").fetchall()}
    finally:
        db.close()


def foreign_key_check(path: Path) -> list[tuple[Any, ...]]:
    db = sqlite3.connect(path / DB_NAME)
    try:
        return db.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        db.close()


async def test_a_new_installation_starts_with_no_radio_and_the_first_one_added_is_radio_1_whose_packets_name_it(tmp_path: Path) -> None:
    # A new installation: no settings row, no radio
    e = Env(tmp_path, operator=False, first_radio=False)
    await e.start(connected=False)
    assert e.ctl.config.radios == () and e.ctl.radios.all() == [], "the start writes no radio"
    assert await e.ctl.add_radio("kiss") == FM_ID and [(s.id, s.kind, s.type, s.enabled, s.position) for s in e.ctl.config.radios] == [(FM_ID, "fm", "kiss", True, 1)]
    await until(lambda: e.tnc.state.name == "CONNECTED")
    e.feed(on_air("OH2RDG", b"!6010.00N/02456.00E>heard on the new installation"))
    await until(lambda: e.ctl.stationbook.get("OH2RDG") is not None)
    [packet] = await e.packets()
    assert packet.radio_id == FM_ID
    await e.stop()
    rows = tables(tmp_path)
    assert rows["radio"] == [(1, "fm", "kiss", "", 1, 1, None)] and rows["radio_setting"] == [] and rows["settings"] == [], "radio 1 with the defaults of its type"
    assert foreign_key_check(tmp_path) == [], "every row names a radio that has its row"


async def test_a_start_on_a_database_with_radios_writes_none_and_reads_the_ones_stored(tmp_path: Path) -> None:
    first = Env(tmp_path, settings={"serial/baud": "4800"})
    await first.start()
    await first.stop()
    written = tables(tmp_path)
    assert written["radio"] == [(1, "fm", "kenwood-tnc2", "", 1, 1, None)] and written["radio_setting"] == [(1, "baud", "4800", 1), (1, "path", "WIDE1-1,WIDE2-1", 1)]
    again = Env(tmp_path)
    await again.start()
    spec = again.ctl.config.radio(FM_ID)
    assert spec is not None and (spec.type, spec.value("baud"), spec.value("path"), again.tnc.baud) == ("kenwood-tnc2", 4800, "WIDE1-1,WIDE2-1", 4800), "the stored radio is read"
    await again.stop()
    assert tables(tmp_path) == written, "a database with radios is left as it is"


@pytest.mark.expects_errors
async def test_a_failed_read_of_the_radios_runs_none_and_the_stored_radios_and_the_stations_choices_of_them_stay_as_they_were(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                                                              caplog: pytest.LogCaptureFixture) -> None:
    first = Env(tmp_path, settings={"hf/enabled": "false", "serial/baud": "1200"})
    await first.start()
    assert first.ctl.radios.choose("OH2AAA", HF_ID) and first.ctl.radios.choose("OH2BBB", FM_ID)
    await first.ctl.radios.flush()
    await first.stop()
    stored = tables(tmp_path)
    assert [row[:3] for row in stored["radio"]] == [(1, "fm", "kenwood-tnc2"), (2, "hf", "mercury")]
    chosen = {key: value for key, value, _ in stored["settings"]}[MESSAGE_RADIOS]
    assert json.loads(chosen) == {"OH2AAA": HF_ID, "OH2BBB": FM_ID}

    async def unread(self: Store) -> None:
        # (what Store.read_radios() gives for a read that failed)
        return None

    monkeypatch.setattr(Store, "read_radios", unread)
    # The database has its radios: the Env adds none
    again = Env(tmp_path, first_radio=False)
    await again.start(connected=False)
    assert again.ctl.config.radios == () and again.ctl.radios.all() == [], "no radio runs"
    assert "the radios could not be read" in caplog.text
    with pytest.raises(RadioError, match="no such radio"):
        await again.ctl.change_radio(FM_ID, name="Base")
    assert await again.ctl.add_radio("kiss") is None, "nor is a radio added: the next good start would have one more"
    assert "the radio is not added" in caplog.text
    assert await again.ctl.save_config(replace(again.ctl.config, station_comment="the station's own")), "the station's settings are stored all the same"
    # A choice made in the run: the daemon's own, the only one there is with no radio
    assert again.ctl.radios.choose("OH2CCC", None)
    again.ctl.radios.forget("OH2BBB")
    await again.ctl.radios.flush()
    await again.stop()
    after = tables(tmp_path)
    assert (after["radio"], after["radio_setting"], after["sequence"]) == (stored["radio"], stored["radio_setting"], stored["sequence"]), "the stored radios are as they were"
    assert {key: value for key, value, _ in after["settings"]}[MESSAGE_RADIOS] == chosen, "the stations' choices of the radios that did not run are kept as they were"


def test_a_choice_of_a_radio_the_settings_do_not_have_is_no_choice() -> None:
    book = StationBook()
    book.seed([Station(call, first_heard=T0, last_heard=T0) for call in ("OH2A", "OH2B", "OH2C")])
    kept: list[str] = []
    choices = StationChoices(book, kept.append, known=lambda id: id == FM_ID)
    choices.restore(json.dumps({"OH2A": 2, "OH2B": 1, "OH2C": 7, "OH2GONE": 2}))
    assert (choices.choice("OH2A"), choices.choice("OH2B")) == (None, FM_ID) and json.loads(choices.choices_text()) == {"OH2B": 1}, "a radio the settings do not have is no choice"
    assert choices.choose("OH2A", FM_ID) and json.loads(kept[-1]) == {"OH2A": 1, "OH2B": 1}
    choices.forget("OH2B")
    assert json.loads(kept[-1]) == {"OH2A": 1}, "forgotten: its choice goes with it"
    choices.forget_all()
    assert kept[-1] == "{}"


async def test_the_port_of_the_run_is_radio_1s_for_the_run_and_never_stored(tmp_path: Path) -> None:
    # The Env gives the Controller --port: its fake radio's address
    e = Env(tmp_path, operator=False)
    await e.start()
    spec = e.ctl.config.radio(FM_ID)
    assert spec is not None and e.tnc.path == e.link and spec.value("port") == ""
    await e.stop()
    assert tables(tmp_path)["radio_setting"] == [] and tables(tmp_path)["radio"] == [(1, "fm", "kiss", "", 1, 1, None)]


async def test_the_database_gives_each_radio_added_the_next_id_which_no_radio_had_before(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    assert await e.ctl.add_radio("dummy", "Shack", enabled=False) == HF_ID, "the HF radio has no id of its own: the next id is the database's"
    assert await e.ctl.add_radio("mercury", enabled=False) == 3
    assert await e.ctl.remove_radio(3)
    assert await e.ctl.add_radio("kiss", enabled=False) == 4, "a removed radio's id is never given again"
    with pytest.raises(RadioError, match="at most 8"):
        await e.ctl.add_radio("kiss", "a name too long")
    await e.stop()
    assert [row[0] for row in tables(tmp_path)["radio"]] == [1, 2, 3, 4]


async def test_the_log_says_a_station_has_no_radio_yet_and_a_port_of_the_run_that_no_radio_takes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.controller")
    # The Env gives the Controller --port: its fake radio's address
    fresh = Env(tmp_path / "fresh", operator=False, first_radio=False)
    await fresh.start(connected=False)
    assert "this station has no radio yet" in caplog.text
    assert f"--port {fresh.link} is radio 1's, and this station has no radio 1" in caplog.text, "the port of the run is said, not dropped without a word"
    assert await fresh.ctl.add_radio("kiss") == FM_ID
    await until(lambda: fresh.tnc.state.name == "CONNECTED")               # (the radio added takes it)
    await fresh.stop()
    caplog.clear()
    store = Store()
    data = tmp_path / "dummy"
    data.mkdir()
    ctl = Controller(data, store=store, port="socket://127.0.0.1:9", hf_port="socket://127.0.0.1:8100", check_sec=0)
    await ctl.open_database()
    assert await store.add_radio("fm", "dummy", "", True, 1) == FM_ID
    await ctl.start()
    assert "has no radio yet" not in caplog.text
    assert "--port socket://127.0.0.1:9 is not used: it is radio 1's, and radio 1 is of the type dummy, which opens no such port" in caplog.text
    assert "--hf-port socket://127.0.0.1:8100 is a Mercury radio's, and this station has none: it is taken once one is added" in caplog.text
    await ctl.stop()


async def test_the_log_says_nothing_of_a_port_of_the_run_that_its_radio_takes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.controller")
    e = Env(tmp_path, operator=False)
    await e.start()
    assert e.tnc.path == e.link and "--port" not in caplog.text and "has no radio yet" not in caplog.text
    await e.stop()


def test_the_start_says_a_port_of_the_run_whose_radio_is_removed_or_opens_no_such_port_is_not_used() -> None:
    radios = (RadioSpec(FM_ID, "fm", "kiss", "", True, 1, T0), RadioSpec(HF_ID, "hf", "dummy-hf", "", True, 2), RadioSpec(3, "fm", "kiss", "", True, 3))
    config = replace(DEFAULTS, radios=radios)
    assert start_notes(config, RunOverrides(port="/dev/ttyUSB0", hf_port="socket://127.0.0.1:8100")) == [
        (logging.WARNING, "--port /dev/ttyUSB0 is not used: it is radio 1's, and radio 1 is removed"),
        (logging.WARNING, "--hf-port socket://127.0.0.1:8100 is not used: it is radio 2's, and radio 2 is of the type dummy-hf, which opens no such port")]
    assert start_notes(config, RunOverrides()) == [], "no port given: nothing to say of one"
    taken = replace(DEFAULTS, radios=(RadioSpec(FM_ID, "fm", "kiss-tcp", "", False, 1), RadioSpec(HF_ID, "hf", "mercury", "", False, 2)))
    assert start_notes(taken, RunOverrides(port="socket://127.0.0.1:8001", hf_port="socket://127.0.0.1:8100")) == [], "a radio that takes it, on or off"
    [(level, note)] = start_notes(replace(DEFAULTS, radios=()), RunOverrides(port="/dev/ttyUSB0"))[:1]
    assert level == logging.INFO and note.startswith("this station has no radio yet"), "a new installation is a clean run: nothing on stderr"
    assert start_notes(replace(DEFAULTS, radios=()), RunOverrides(port="/dev/ttyUSB0"))[1][0] == logging.INFO, "nor is a port the first radio added takes"
    gone = replace(DEFAULTS, radios=tuple(replace(spec, removed_at=T0) for spec in radios))
    assert start_notes(gone, RunOverrides()) == [(logging.INFO, "every radio of this station is removed: none runs until one is added (the setup guide, Settings, Radio, or neoaprs db radios add TYPE)")], \
        "a station whose radios are all removed had radios: it is not told it has none yet"


def test_the_mercury_given_for_the_run_is_the_first_mercury_radios_whatever_its_id() -> None:
    """--hf-port is the station's first Mercury radio's (the lowest id of one not removed): on a new
    installation the Mercury added first may be radio 1; a Dummy HF radio or a TNC never takes it.
    """
    radios = (RadioSpec(FM_ID, "hf", "mercury", "", True, 1), RadioSpec(HF_ID, "hf", "dummy-hf", "", True, 2), RadioSpec(3, "fm", "kiss", "", True, 3), RadioSpec(4, "hf", "mercury", "", False, 4))
    assert (modem_radio(radios), modem_radio(radios[1:]), modem_radio(radios[1:3])) == (FM_ID, 4, None)
    assert modem_radio((replace(radios[0], removed_at=T0), *radios[1:])) == 4, "a removed radio takes nothing"
    run = RunOverrides(hf_port="socket://127.0.0.1:18100", attach_to=modem_radio(radios))
    assert modem_settings(radios[0], run).port == "socket://127.0.0.1:18100" and modem_settings(radios[3], run).port != "socket://127.0.0.1:18100", "one radio takes it"
    assert start_notes(replace(DEFAULTS, radios=radios), run) == [], "the radio that takes it says nothing"
    none = replace(DEFAULTS, radios=radios[1:3])
    assert start_notes(none, RunOverrides(hf_port="socket://127.0.0.1:18100", attach_to=modem_radio(none.radios))) == [
        (logging.INFO, "--hf-port socket://127.0.0.1:18100 is a Mercury radio's, and this station has none: it is taken once one is added")]
