"""Where the daemon's radios (neoaprs/radioedits.py, the controller, the page's config view) meet the command line and the support bundle (neoaprs/cli/dbcmd.py, doctor.py, support*.py). Each side
has its own tests; here one data folder goes through both. A new installation has no radio until one is added, which `neoaprs db`, `neoaprs doctor` and the bundle say, and then show the one added;
a radio added and set with the command line on a stopped daemon's file is what the next start runs with, and a save of the page is what `db get` reads; the HF radio added on the page is a second
radio for the command line and the bundle, and a database made of that bundle (tests/support/bundledb.py) and migrated has the same radios and the stations' choices of them; a removed radio is no
setting of the station's on the page, on the command line or in the bundle. A Sound card radio (`direwolf`) is a new installation's radio 1 by `radios add` where the installation carries Direwolf, and the first
start runs it on its own Direwolf; where none is carried the command refuses it and stores no radio."""
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from neoaprs import direwolfmodem, radioregistry
from neoaprs.cli import dbcmd, doctor, hostcheck, servicecmd
from neoaprs.cli.supportmake import make_bundle
from neoaprs.clock import utc
from neoaprs.config import BY_KEY, KEYS, MESSAGE_RADIOS
from neoaprs.direwolf import CONF_FILE, adevice
from neoaprs.direwolfdriver import DirewolfDriver
from neoaprs.mercuryclaims import radio_folder
from neoaprs.configradios import FLAT_HOMES, radios_from_rows
from neoaprs.radiospec import FM_ID, HF_ID, RadioSpec
from neoaprs.radiosql import radio_rows, radio_settings
from neoaprs.serialprobe import PortInfo
from neoaprs.store import DB_NAME
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import on_air
from tests.support import fakedirewolf
from tests.support.bundledb import bundle_database
from tests.support.clock import FixedClock
from tests.support.env import Env, until
from tests.support.migrated import opened
from tests.support.modemports import base_of_this_test
from tests.support.supportdata import zip_members
from tests.support.wsclient import WsClient

NOW = utc(2026, 11, 14, 12, 0, 0)
FLAT_KEYS = [key for key in KEYS if BY_KEY[key].attr in FLAT_HOMES]               # the keys of before of radios 1 and 2, which are no settings of the command line or the bundle
DUMMY_HF = {"hf/enabled": "true", "hf/profile": "dummy-hf", "mercury/keying": "vox", "mercury/tx_gain_db": "-4"}      # (the Dummy HF radio: no Mercury program, no sound card)


@pytest.fixture(autouse=True)
def this_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The doctor (alone and inside the bundle) reads nothing of the computer the test runs on: one TNC cable, the group of the serial devices, no brltty, ModemManager or start at sign-in."""
    monkeypatch.setattr(doctor, "available_ports", lambda: [PortInfo("/dev/ttyUSB0", "FT232R USB UART", "USB VID:PID=0403:6001", 0x0403, 0x6001)])
    monkeypatch.setattr(doctor, "serial_group_check", lambda: hostcheck.GroupCheck("ok", "dialout", ""))
    monkeypatch.setattr(doctor, "brltty_installed", lambda: False)
    monkeypatch.setattr(doctor, "modemmanager_installed", lambda: False)
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: None)

    class NoService:
        def installed(self, plan: servicecmd.Plan) -> tuple[bool, str]:
            return False, "no user unit"
    monkeypatch.setattr(doctor.servicecmd, "backend_for", lambda system: NoService())


async def db(capsys: pytest.CaptureFixture[str], data: Path, *args: str) -> tuple[int, str, str]:
    """`neoaprs db ARGS` on the data folder (in a thread: the command runs a loop of its own), with what it printed and what it said on stderr."""
    capsys.readouterr()
    code = await asyncio.to_thread(dbcmd.main, ["--data", str(data), *args])
    out = capsys.readouterr()
    return code, out.out, out.err


async def got(capsys: pytest.CaptureFixture[str], data: Path, key: str) -> str:
    code, out, err = await db(capsys, data, "get", key)
    assert code == 0, err
    return out.strip()


def listed(text: str) -> dict[str, str]:
    """`db list` as key to value (an empty value is no word before stored or default)."""
    return {words[0]: words[1] if len(words) == 3 else "" for words in (line.split() for line in text.splitlines()) if words and len(words) <= 3}


async def doctor_radios(capsys: pytest.CaptureFixture[str], data: Path) -> list[str]:
    """The lines of `neoaprs doctor` about the radios."""
    capsys.readouterr()
    assert await asyncio.to_thread(doctor.main, ["--data", str(data)]) == 0
    return [line for line in capsys.readouterr().out.splitlines() if " radio " in line[:12] or "no radio is on" in line]


async def bundle(out: Path, data: Path) -> tuple[Path, dict[str, str]]:
    """A support bundle of the data folder of a stopped daemon, as `neoaprs support` makes it: its path and its members."""
    made = await asyncio.to_thread(lambda: make_bundle(data, out, now=FixedClock(NOW), journal=lambda: None))
    return made.path, zip_members(made.path)


def bundle_radios(members: dict[str, str]) -> list[tuple[Any, ...]]:
    return [(r["id"], r["kind"], r["type"], r["log_name"], r["enabled"], r["removed_at"] is not None) for r in json.loads(members["settings.json"])["radios"]]


def summary_titles(members: dict[str, str]) -> list[str]:
    return [line for line in members["summary.txt"].splitlines() if line.startswith("Radio ")]


def tables(path: Path) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], dict[str, str]]:
    """The radios (every column but the time of a removal), their own settings, and the rows of the settings table, of a stopped daemon's file."""
    connection = sqlite3.connect(path)
    try:
        return (connection.execute("SELECT id, kind, type, name, enabled, position, removed_at IS NOT NULL FROM radio ORDER BY id").fetchall(),
                connection.execute("SELECT radio_id, key, value FROM radio_setting ORDER BY radio_id, key").fetchall(),
                dict(connection.execute("SELECT key, value FROM settings").fetchall()))
    finally:
        connection.close()


def in_force(path: Path) -> tuple[RadioSpec, ...]:
    """The radios of the file as the daemon reads them."""
    s = opened(path)
    try:
        return radios_from_rows(radio_rows(s.db), radio_settings(s.db))
    finally:
        s.close()


async def page_of(e: Env) -> WsClient:
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return page


async def test_a_new_installation_has_no_radio_until_one_is_added_and_the_command_line_the_doctor_and_the_bundle_say_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    e = Env(data, operator=False, first_radio=False)                  # (no settings row and no radio: what an installation's first start finds)
    await e.start(connected=False)
    await e.stop()
    code, out, err = await db(capsys, data, "radios")
    assert code == 0 and out == "" and "this station has no radio yet" in err, "the start wrote none"
    code, out, _ = await db(capsys, data, "list")
    assert code == 0 and not set(FLAT_KEYS) & set(listed(out)), "no key of before of a radio among the settings"
    assert await doctor_radios(capsys, data) == [], "the doctor names no radio"
    _, members = await bundle(tmp_path / "out", data)
    assert bundle_radios(members) == [] and summary_titles(members) == []
    code, out, _ = await db(capsys, data, "radios", "add", "kiss")
    assert code == 0 and out.split() == ["radio", "1", "FM", "fm", "kiss", "on", "(position", "1)"]
    code, out, err = await db(capsys, data, "radios")
    assert code == 0 and err == "" and [line.split() for line in out.splitlines() if line.startswith("radio ")] == [["radio", "1", "FM", "fm", "kiss", "on", "(position", "1)"]]
    assert await doctor_radios(capsys, data) == ["ok    radio FM (kiss): port (found by searching), speed 9600 baud"], "radio 1 alone"
    _, members = await bundle(tmp_path / "out2", data)
    assert bundle_radios(members) == [(FM_ID, "fm", "kiss", "FM", True, False)] and summary_titles(members) == ["Radio 1: FM"]
    assert "radios_problem" not in json.loads(members["settings.json"]) or not json.loads(members["settings.json"])["radios_problem"]



async def test_a_sound_card_radio_is_a_new_installations_radio_1_by_the_command_line_where_direwolf_is_carried_and_refused_with_nothing_stored_where_it_is_not(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: None)
    none = tmp_path / "none"
    code, _, err = await db(capsys, none, "radios", "add", "direwolf")
    assert code == 2 and "'direwolf' is not a type of radio of this installation" in err and (not (none / DB_NAME).exists() or tables(none / DB_NAME)[0] == []), "a wheel installed with pip, a checkout: no Direwolf, so no radio that would only wait for it"
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)             # (an installation that carries Direwolf: the made-up one)
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: fakedirewolf.program())
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))           # (Windows: the made-up card is the second input and output of the made-up Direwolf's WinMM lists; the machine's own name none)
    data = tmp_path / "data"
    code, out, _ = await db(capsys, data, "radios", "add", "direwolf")
    assert code == 0 and out.split() == ["radio", "1", "FM", "fm", "direwolf", "on", "(position", "1)"], "a new installation's first radio is radio 1"
    assert (await db(capsys, data, "set", "radio/1/sound_card", "plughw:7,0"))[0] == 0 and (await db(capsys, data, "set", "radio/1/keying", "vox"))[0] == 0, "and its own settings by its number"
    e = Env(data, operator=False, first_radio=False)
    await e.start(connected=False)
    try:
        radio = e.ctl.radios.get(FM_ID)
        assert radio is not None and isinstance(radio.driver, DirewolfDriver) and e.ctl.config.main_radio == FM_ID, "the first start runs radio 1 as the type the command line gave it"
        await until(lambda: radio.usable, 20)
        assert (radio.driver.modem.sound_card, radio.driver.modem.keying.text) == ("plughw:7,0", "vox")
        assert f"ADEVICE {adevice('plughw:7,0', radio.driver.modem._numbers)}\n" in (radio_folder(data, FM_ID) / CONF_FILE).read_text(encoding="utf-8"), "the card as this system takes it"
    finally:
        await e.stop()


async def test_db_set_on_a_stopped_daemons_file_is_what_the_next_start_runs_with_and_a_save_of_the_page_is_what_db_get_reads(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    assert (await db(capsys, data, "radios", "add", "kenwood-tnc2"))[0] == 0 and (await db(capsys, data, "set", "radio/1/baud", "4800"))[0] == 0, "before any start: a new installation's file"
    first = Env(data)
    await first.start()
    fm = first.ctl.config.radio(FM_ID)
    assert fm is not None and fm.settings.get("baud") == "4800" and first.tnc.baud == 4800, "the first start's radio 1 has the speed set before it"
    await first.stop()
    assert (await db(capsys, data, "set", "radio/1/baud", "1200"))[0] == 0 and (await db(capsys, data, "set", "radio/1/path", "WIDE2-1"))[0] == 0
    again = Env(data, web=True)
    await again.start()
    fm = again.ctl.config.radio(FM_ID)
    assert fm is not None and (fm.value("baud"), again.tnc.baud, fm.value("path")) == (1200, 1200, "WIDE2-1"), "a radio's own keys, set with the daemon stopped"
    page = await page_of(again)
    assert (page.topics["config"]["radio_values"]["radio/1/baud"], page.topics["config"]["radio_values"]["radio/1/path"]) == ("1200", "WIDE2-1")
    await page.send({"cmd": "set_config", "values": {"radio/1/baud": "9600", "radio/1/digipeat": "true"}})
    await page.until(lambda: page.topics["config"]["radio_values"]["radio/1/baud"] == "9600")
    await again.stop()
    assert [await got(capsys, data, key) for key in ("radio/1/baud", "radio/1/digipeat", "radio/1/path")] == ["9600", "true", "WIDE2-1"]
    assert not {"serial/baud", "digi/enabled", "beacon/path"} & tables(data / DB_NAME)[2].keys(), "the page's save went to radio 1's own rows"
    assert (await db(capsys, data, "get", "serial/baud"))[:2] == (2, ""), "the key of before is no setting"


async def test_the_hf_radio_ticked_on_the_page_is_a_second_radio_for_the_command_line_and_the_bundle_and_a_database_made_of_the_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    e = Env(data, web=True)
    await e.start()
    page = await page_of(e)
    await page.send({"cmd": "radio_add", "type": "dummy-hf"})
    assert (await page.expect("radio_added"))["id"] == HF_ID, "an HF radio added is radio 2"
    e.mercury._finder = lambda: None                              # (no program: the Dummy HF radio works without its speaker)
    await page.send({"cmd": "set_config", "values": {"radio/2/keying": "vox", "radio/2/tx_gain_db": "-4"}})
    await page.until(lambda: page.topics["config"]["radio_values"].get("radio/2/tx_gain_db") == "-4")
    calls = ("OH2GAX-2", "OH2RDG")
    for call in calls:
        e.feed(on_air(call, b"!6010.00N/02456.00E>heard"))
    await until(lambda: all(e.ctl.stationbook.get(call) is not None for call in calls))
    assert e.ctl.radios.choose("OH2GAX-2", HF_ID) and e.ctl.radios.choose("OH2RDG", FM_ID)
    await e.ctl.radios.flush()
    await e.stop()
    code, out, _ = await db(capsys, data, "radios")
    assert code == 0 and [line.split()[:6] for line in out.splitlines() if line.startswith("radio ")] == [["radio", "1", "FM", "fm", "kenwood-tnc2", "on"], ["radio", "2", "HF", "hf", "dummy-hf", "on"]]
    assert "radio/2/keying" in out and "vox" in out
    assert [line.split(":")[0] for line in await doctor_radios(capsys, data)] == ["ok    radio FM (kenwood-tnc2)", "ok    radio HF (dummy-hf)"]
    path, members = await bundle(tmp_path / "out", data)
    assert bundle_radios(members) == [(FM_ID, "fm", "kenwood-tnc2", "FM", True, False), (HF_ID, "hf", "dummy-hf", "HF", True, False)] and summary_titles(members) == ["Radio 1: FM", "Radio 2: HF"]
    made = tmp_path / "again" / DB_NAME
    assert bundle_database(made, path) == []
    opened(made).close()                                              # (migrated to this version, as a start does)
    radios, own, rows = tables(made)
    radios_before, own_before, rows_before = tables(data / DB_NAME)
    assert radios == radios_before and in_force(made) == in_force(data / DB_NAME), "the same radios, with the same own settings in force"
    assert [row for row in own if row[:2] != (HF_ID, "path")] == own_before, "(migration 31 keeps the station's path on radio 2 too, which no type of HF radio reads)"
    assert json.loads(rows[MESSAGE_RADIOS]) == json.loads(rows_before[MESSAGE_RADIOS]) == {"OH2GAX-2": HF_ID, "OH2RDG": FM_ID}, "the stations' choices of them, by id"


async def test_a_removed_radio_is_no_setting_of_the_station_on_the_page_on_the_command_line_or_in_the_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    e = Env(data, web=True, settings={**DUMMY_HF, "mercury/sound_card": "plughw:1,0"})
    e.mercury._finder = lambda: None
    await e.start()
    assert await e.ctl.remove_radio(HF_ID)
    page = await page_of(e)
    on_page = page.topics["config"]
    await e.stop()
    code, out, _ = await db(capsys, data, "list")
    on_line = listed(out)
    _, members = await bundle(tmp_path / "out", data)
    in_bundle = json.loads(members["settings.json"])
    assert code == 0 and not set(FLAT_KEYS) & set(on_line) and not set(FLAT_KEYS) & (set(in_bundle["values"]) | set(in_bundle["other_rows"])), "no key of before, the removed radio's keying and sound card least"
    assert not [key for key in on_page["radio_values"] if key.startswith("radio/2/")] and not set(FLAT_KEYS) & set(on_page["values"]), "the page is told no setting of the removed radio"
    code, out, err = await db(capsys, data, "get", "mercury/keying")
    assert (code, out) == (2, "") and "mercury/keying: no such setting: it is radio/<id>/keying now" in err, "the station has no HF radio to name"
    assert [(r[0], r[-1]) for r in bundle_radios(members)] == [(FM_ID, False), (HF_ID, True)] and summary_titles(members) == ["Radio 1: FM"], "the removed radio told as removed, no section"
