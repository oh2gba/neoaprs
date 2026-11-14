"""The stand-in (neoaprs/radioedits.py, until a new installation starts with no radio and the setup guide adds the first: package W3 deletes it): no row may ever name a radio that has no row. So on a
database whose table `radio` is empty, the daemon's start writes the radios today's program runs before anything else: radio 1, the FM radio, from the flat values in force (their rows becoming its own,
as migration 31 made them), and radio 2, the HF radio, when the run is given its Mercury (--hf-port) or a row names it; a database with radios is left as it is, and one whose radios cannot be read runs
today's FM radio and writes no radio. A radio the flat keys first name later (the HF radio, ticked or set) is written by that save, with its id, and read back at the next start."""
import json
import logging
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from neoaprs.config import LAST_PORT, MESSAGE_RADIOS
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioedits import seed_rows
from neoaprs.radiospec import FM_ID, HF_ID, RadioError
from neoaprs.services.beacon import memory_key_of
from neoaprs.source import Source
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.stationchoices import StationChoices
from neoaprs.store import DB_NAME, Store
from tests.support.air import on_air
from tests.support.clock import FixedClock
from tests.support.env import Env, until
from tests.support.fakemercury import Air, FakeMercury
from tests.support.migrated import opened

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
RADIO = "SELECT id, kind, type, name, enabled, position, removed_at FROM radio ORDER BY id"


def tables(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """The rows of the database (the daemon stopped) that the stand-in writes, every column of them."""
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


async def test_a_fresh_database_after_one_start_holds_radio_1_and_a_packet_heard_names_a_radio_there_is(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.controller")
    e = Env(tmp_path, operator=False)                                   # (a new installation: no settings row, no radio)
    await e.start()
    assert [(s.id, s.kind, s.type, s.enabled, s.position) for s in e.ctl.config.radios] == [(FM_ID, "fm", "kiss", True, 1)] and not e.ctl._stand_in
    assert "the database had no radio: radio 1 the FM radio (kiss, on) is written from the settings" in caplog.text
    e.feed(on_air("OH2RDG", b"!6010.00N/02456.00E>heard on the new installation"))
    await until(lambda: e.ctl.stationbook.get("OH2RDG") is not None)
    [packet] = await e.packets()
    assert packet.radio_id == FM_ID
    await e.stop()
    rows = tables(tmp_path)
    assert rows["radio"] == [(1, "fm", "kiss", "", 1, 1, None)] and rows["radio_setting"] == [] and rows["settings"] == [], "radio 1, today's FM radio, with the defaults; no flat row"
    assert foreign_key_check(tmp_path) == [], "every row names a radio that has its row"


async def test_a_second_start_writes_nothing_and_reads_the_radios_it_wrote(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    first = Env(tmp_path, settings={"serial/baud": "4800"})
    await first.start()
    await first.stop()
    written = tables(tmp_path)
    assert written["radio"] == [(1, "fm", "kenwood-tnc2", "", 1, 1, None)] and written["radio_setting"] == [(1, "baud", "4800", 1), (1, "path", "WIDE1-1,WIDE2-1", 1)]
    caplog.set_level(logging.INFO, "neoaprs.controller")
    again = Env(tmp_path)
    await again.start()
    assert (again.ctl.config.tnc_profile, again.ctl.config.serial_baud, again.ctl.config.beacon_path, again.tnc.baud) == ("kenwood-tnc2", 4800, "WIDE1-1,WIDE2-1", 4800), "the stored radio is read"
    await again.stop()
    assert tables(tmp_path) == written and "the database had no radio" not in caplog.text, "a database with radios is left as it is"


async def test_the_flat_rows_of_a_database_without_radios_become_the_radios_own_as_migration_31_moves_them(tmp_path: Path) -> None:
    """A database that has no radio and has flat rows (written by `neoaprs db set` before the first start, say): radio 1 and radio 2 are written from them, each row moved with its value and revision,
    the rows of the daemon's state take their radio's name and the stations' choices name the radio by its id, and no flat row of a radio stays."""
    rows = {"tnc/profile": "kiss-tcp", "tcp/port": "8100", "fm/enabled": "true", "hf/enabled": "false", "mercury/keying": "vox", "beacon/path": "WIDE2-1", "digi/enabled": "true", "serial/pattern": "/x/*",
            "serial/last_port": "/dev/ttyUSB3", "beacon/last_sent_at": "2026-10-21T11:50:00Z", "hf/beacon_last_sent_at": "2026-10-21T11:40:00Z", MESSAGE_RADIOS: json.dumps({"OH2GAX-2": "hf", "OH2RDG": "fm"})}
    e = Env(tmp_path, radio=False, settings=rows)
    await e.start(connected=False)
    c = e.ctl.config
    assert (c.tnc_profile, c.tcp_port, c.hf_enabled, c.mercury_keying, c.beacon_path, c.digi_enabled, c.serial_last_port) == ("kiss-tcp", 8100, False, "vox", "WIDE2-1", True, "/dev/ttyUSB3")
    await e.stop()
    after = tables(tmp_path)
    assert after["radio"] == [(1, "fm", "kiss-tcp", "", 1, 1, None), (2, "hf", "mercury", "", 0, 2, None)], "radio 2: a row of the settings names it"
    assert after["radio_setting"] == [(1, "digipeat", "true", 1), (1, "path", "WIDE2-1", 1), (1, "tcp_port", "8100", 1), (2, "keying", "vox", 1), (2, "path", "WIDE2-1", 1)]
    settings = {key: value for key, value, _ in after["settings"]}
    assert not {"tnc/profile", "tcp/port", "fm/enabled", "hf/enabled", "mercury/keying", "beacon/path", "digi/enabled", "serial/last_port", "beacon/last_sent_at", "hf/beacon_last_sent_at"} & settings.keys()
    assert (settings[LAST_PORT], settings[memory_key_of(FM_ID)], settings[memory_key_of(HF_ID)], settings["serial/pattern"]) == ("/dev/ttyUSB3", "2026-10-21T11:50:00Z", "2026-10-21T11:40:00Z", "/x/*")
    assert json.loads(settings[MESSAGE_RADIOS]) == {"OH2GAX-2": 2, "OH2RDG": 1}
    assert foreign_key_check(tmp_path) == []


@pytest.mark.expects_errors
async def test_a_failed_read_of_the_radios_writes_nothing_and_the_stored_radios_stay_as_they_were(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = Env(tmp_path, settings={"hf/enabled": "false", "serial/baud": "1200"})
    await first.start()
    await first.stop()
    stored = tables(tmp_path)
    assert [row[:3] for row in stored["radio"]] == [(1, "fm", "kenwood-tnc2"), (2, "hf", "mercury")]

    async def none(self: Store) -> tuple[()]:
        return ()                                                       # (what Store.radios() gives for a read that failed)

    monkeypatch.setattr(Store, "radios", none)
    again = Env(tmp_path)
    await again.start()
    assert again.ctl._stand_in and [(s.id, s.kind) for s in again.ctl.config.radios] == [(FM_ID, "fm")] and again.tnc.state is Source.State.CONNECTED, "today's FM radio runs"
    assert not await again.ctl.save_config(replace(again.ctl.config, serial_baud=9600)), "a save that changes a radio is not stored"
    assert not await again.ctl.save_config(replace(again.ctl.config, hf_enabled=True)), "nor one that names a radio the settings in force do not have"
    assert await again.ctl.add_radio("kiss") is None, "nor a radio added"
    assert await again.ctl.save_config(replace(again.ctl.config, station_comment="the station's own")), "the station's settings are stored all the same"
    await again.stop()
    after = tables(tmp_path)
    assert (after["radio"], after["radio_setting"], after["sequence"]) == (stored["radio"], stored["radio_setting"], stored["sequence"]), "the stored radios are as they were"


@pytest.mark.expects_errors
async def test_a_run_whose_radios_could_not_be_read_keeps_the_stations_choices_of_the_radios_it_does_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The stand-in runs radio 1 alone: a station's choice of radio 2 is no choice for that run, and the row keeps it all the same, through the choices made, the stations forgotten and the stop of that
    run; the next start that reads the radios has it again."""
    first = Env(tmp_path, settings={"hf/enabled": "false"})
    await first.start()
    for call in ("OH2GAX-2", "OH2RDG", "OH6XYZ", "OH3GON"):
        first.feed(on_air(call, b"!6010.00N/02456.00E>heard"))
    await until(lambda: all(first.ctl.stationbook.get(call) is not None for call in ("OH2GAX-2", "OH2RDG", "OH6XYZ", "OH3GON")))
    assert first.ctl.radios.choose("OH2GAX-2", HF_ID) and first.ctl.radios.choose("OH2RDG", FM_ID) and first.ctl.radios.choose("OH3GON", HF_ID)
    await first.ctl.radios.flush()
    await first.stop()

    async def none(self: Store) -> tuple[()]:
        return ()

    monkeypatch.setattr(Store, "radios", none)
    stand_in = Env(tmp_path)
    await stand_in.start()
    assert stand_in.ctl._stand_in and (stand_in.ctl.radios.choice("OH2GAX-2"), stand_in.ctl.radios.choice("OH2RDG")) == (None, FM_ID), "radio 2 is not run: the daemon's own choice for the run"
    assert stand_in.ctl.radios.choose("OH6XYZ", FM_ID), "a choice made meanwhile"
    stand_in.ctl.radios.forget("OH3GON")                               # (the book let it go: its choice goes with it)
    await stand_in.ctl.radios.flush()
    await stand_in.stop()
    monkeypatch.undo()
    rows = {key: value for key, value, _ in tables(tmp_path)["settings"]}
    assert json.loads(rows[MESSAGE_RADIOS]) == {"OH2GAX-2": HF_ID, "OH2RDG": FM_ID, "OH6XYZ": FM_ID}, "the row keeps the choice of radio 2"
    again = Env(tmp_path)
    await again.start()
    assert [again.ctl.radios.choice(call) for call in ("OH2GAX-2", "OH2RDG", "OH6XYZ", "OH3GON")] == [HF_ID, FM_ID, FM_ID, None], "the next start that reads the radios has every choice"
    await again.stop()


@pytest.mark.expects_errors
async def test_a_database_without_radios_whose_rows_disagree_runs_the_stand_in_and_is_left_as_it_was(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A radio's own row left where there is no radio (deleted by hand): migration 31's own check refuses to move the flat rows beside it. The station comes up all the same, as today's FM radio, and
    nothing is written."""
    opened(tmp_path / DB_NAME, FixedClock()).close()
    db = sqlite3.connect(tmp_path / DB_NAME)
    db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", {"station/call": "OH2GBA", "serial/baud": "4800"}.items())
    db.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (5, 'port', '/dev/ttyUSB9')")
    db.commit()
    db.close()
    before = tables(tmp_path)
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    assert e.ctl._stand_in and (e.ctl.config.serial_baud, [s.id for s in e.ctl.config.radios]) == (4800, [FM_ID]), "today's FM radio, as the flat rows say"
    await e.stop()
    assert tables(tmp_path) == before and "the radios of the settings were not stored" in caplog.text


async def test_the_stand_ins_radios_are_decided_on_the_rows_the_write_itself_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A read of the settings that fails (it gives none) at the first start of a database without radios: the radios are decided and their rows moved in one transaction, from what it reads, so the
    type, the tickboxes and the HF radio the rows say are what is written."""
    async def none(self: Store) -> dict[str, str]:
        return {}

    e = Env(tmp_path, radio=False, settings={"tnc/profile": "kenwood-tnc2", "hf/enabled": "true", "hf/profile": "dummy-hf", "serial/baud": "4800"})
    monkeypatch.setattr(Store, "settings", none)
    await e.start(connected=False)
    await e.stop()
    after = tables(tmp_path)
    assert after["radio"] == [(1, "fm", "kenwood-tnc2", "", 1, 1, None), (2, "hf", "dummy-hf", "", 1, 2, None)] and (1, "baud", "4800", 1) in after["radio_setting"]
    assert not [key for key, _, _ in after["settings"] if key.startswith(("tnc/", "hf/", "serial/baud"))]


def test_the_choices_of_radios_not_in_force_are_kept_only_where_the_radios_could_not_be_read() -> None:
    book = StationBook()
    book.seed([Station(call, first_heard=T0, last_heard=T0) for call in ("OH2A", "OH2B", "OH2C")])
    kept: list[str] = []
    row = json.dumps({"OH2A": 2, "OH2B": 1, "OH2C": 7, "OH2GONE": 2})
    stand_in = StationChoices(book, kept.append, by_id=True, known=lambda id: id == FM_ID)
    stand_in.restore(row, keep_unknown=True)
    assert (stand_in.choice("OH2A"), stand_in.choice("OH2B")) == (None, FM_ID) and json.loads(stand_in.choices_text()) == {"OH2A": 2, "OH2B": 1, "OH2C": 7}, "a station the book has not is no choice"
    assert stand_in.choose("OH2A", FM_ID) and json.loads(kept[-1]) == {"OH2A": 1, "OH2B": 1, "OH2C": 7}, "chosen for since: the new choice"
    stand_in.forget("OH2C")
    assert json.loads(kept[-1]) == {"OH2A": 1, "OH2B": 1}, "forgotten: its choice goes with it"
    stand_in.restore(row, keep_unknown=True)
    stand_in.forget_all()
    assert kept[-1] == "{}"
    good = StationChoices(book, kept.append, by_id=True, known=lambda id: id == FM_ID)
    good.restore(row)
    assert json.loads(good.choices_text()) == {"OH2B": 1}, "where the radios were read, a radio the settings do not have is no choice, as before"


async def test_the_port_of_the_run_on_a_fresh_database_is_radio_1s_for_the_run_and_never_stored(tmp_path: Path) -> None:
    e = Env(tmp_path, operator=False)                                   # (the Env gives the Controller --port: its fake radio's address)
    await e.start()
    assert e.tnc.path == e.link and e.ctl.config.serial_port == ""
    await e.stop()
    assert tables(tmp_path)["radio_setting"] == [] and tables(tmp_path)["radio"] == [(1, "fm", "kiss", "", 1, 1, None)]


async def test_the_hf_port_of_the_run_on_a_fresh_database_makes_radio_2_off_as_the_settings_say(tmp_path: Path) -> None:
    hf = FakeMercury(Air())
    e = Env(tmp_path, operator=False, hf=hf)                            # (--hf-port: a Mercury something else runs; no settings row)
    await e.start(connected=False)
    assert [(s.id, s.kind, s.type, s.enabled) for s in e.ctl.config.radios] == [(FM_ID, "fm", "kiss", True), (HF_ID, "hf", "mercury", False)]
    assert e.ctl.radios.get(HF_ID) is not None and e.hf.state is Source.State.STOPPED, "radio 2 is there for the run's Mercury, off until it is ticked"
    await e.stop()
    assert tables(tmp_path)["radio"] == [(1, "fm", "kiss", "", 1, 1, None), (2, "hf", "mercury", "", 0, 2, None)]


async def test_the_first_save_that_names_the_hf_radio_writes_radio_2_and_the_next_start_reads_it(tmp_path: Path) -> None:
    """HF never set up: radio 1 alone. The first save of a flat key of the HF radio (on the page: its box's keying, or its tickbox) writes radio 2 with its id, off as the settings of today say until it is
    ticked; a later save changes its own rows; and the next start reads it from the database."""
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    assert e.ctl.radios.get(HF_ID) is None and [s.id for s in e.ctl.config.radios] == [FM_ID]
    assert await e.ctl.save_config(replace(e.ctl.config, mercury_keying="vox"))
    hf = e.ctl.config.radio(HF_ID)
    assert hf is not None and (hf.kind, hf.type, hf.enabled, dict(hf.settings)) == ("hf", "mercury", False, {"keying": "vox"}) and e.ctl.radios.get(HF_ID) is not None
    assert await e.ctl.save_config(replace(e.ctl.config, mercury_tx_gain_db=-3))
    await e.stop()
    assert tables(tmp_path)["radio"][1] == (2, "hf", "mercury", "", 0, 2, None) and tables(tmp_path)["radio_setting"][-2:] == [(2, "keying", "vox", 1), (2, "tx_gain_db", "-3", 1)]
    again = Env(tmp_path, radio=False)
    await again.start(connected=False)
    assert (again.ctl.config.mercury_keying, again.ctl.config.mercury_tx_gain_db, again.ctl.config.hf_enabled) == ("vox", -3, False) and again.ctl.config.radios == await again.ctl.store.radios()
    await again.stop()


async def test_a_radio_added_where_there_is_no_radio_2_leaves_id_2_to_the_hf_radio(tmp_path: Path) -> None:
    """Today's flat keys of the HF radio are a view of radio 2 until W3: an FM radio added on a database without radio 2 takes the id after it, an HF radio is radio 2."""
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    assert await e.ctl.add_radio("dummy", "Shack", enabled=False) == 3 and e.ctl.config.radio(HF_ID) is None
    assert await e.ctl.add_radio("mercury", enabled=False) == HF_ID and e.ctl.config.hf_profile == "mercury"
    assert await e.ctl.add_radio("kiss", enabled=False) == 4, "with radio 2 there, the database gives the id"
    with pytest.raises(RadioError, match="at most 8"):
        await e.ctl.add_radio("kiss", "a name too long")
    await e.stop()


@pytest.mark.parametrize(("rows", "run", "expected"), [
    ({}, RunOverrides(), [(1, "fm", "kiss", True, 1)]),
    ({"station/call": "OH2GBA", "serial/pattern": "/x/*"}, RunOverrides(port="/dev/pts/4"), [(1, "fm", "kiss", True, 1)]),
    ({"tnc/enter_kiss": "true"}, RunOverrides(), [(1, "fm", "kenwood-tnc2", True, 1)]),
    ({"tnc/profile": "mercury"}, RunOverrides(), [(1, "fm", "kiss", False, 1), (2, "hf", "mercury", True, 2)]),
    ({"tnc/profile": "dummy", "fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf"}, RunOverrides(), [(1, "fm", "dummy", False, 1), (2, "hf", "dummy-hf", True, 2)]),
    ({"mercury/sound_card": "plughw:1,0"}, RunOverrides(), [(1, "fm", "kiss", True, 1), (2, "hf", "mercury", False, 2)]),
    ({}, RunOverrides(hf_port="socket://127.0.0.1:18100"), [(1, "fm", "kiss", True, 1), (2, "hf", "mercury", False, 2)]),
    ({MESSAGE_RADIOS: json.dumps({"OH2GAX-2": "hf"})}, RunOverrides(), [(1, "fm", "kiss", True, 1), (2, "hf", "mercury", False, 2)]),
    ({MESSAGE_RADIOS: "not json", "tnc/profile": "kiss-tcp"}, RunOverrides(), [(1, "fm", "kiss-tcp", True, 1)]),
], ids=["nothing", "the station's rows and --port", "tnc/enter_kiss", "mercury alone", "both dummies", "a row of the modem", "--hf-port", "a choice of hf", "kiss-tcp"])
def test_the_stand_ins_radios_are_those_the_flat_values_in_force_run(rows: dict[str, str], run: RunOverrides, expected: list[tuple[object, ...]]) -> None:
    """Today's rules of the flat rows, as migration 31 applies them: radio 1 always (its type and tickbox as in force), radio 2 when anything names it."""
    assert seed_rows(rows, run) == expected
