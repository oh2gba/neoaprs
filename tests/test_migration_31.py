"""Migration 31 (neoaprs/migrationsteps31.py): the radios of a station become rows. The step is run alone on a database as version 30 left it, with the rows of one shape of installation in it, and
what it made is read back: the radios (`radio`), their own settings (`radio_setting`, with the revision each row had), the rows of `settings` that stay, the rows of the daemon's state under their
radio's name, the stations' choices by id, and the one row of `_m31` that the migrations 32 and 33 read. For every shape the settings in force afterwards (through the stored radios) are what the
flat keys said before. One test for each shape of the work breakdown (work/par/round/breakdown.md, sections 2.3 and 3)."""
import ast
import inspect
import json
import logging
import sqlite3
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import migrationsteps31
from neoaprs.cli import supportgather
from neoaprs.config import DEFAULTS, KEYS, STATION_KEYS, Config
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import MIGRATIONS, source_hash
from neoaprs.migrationsteps31 import _v31
from neoaprs.radiospec import HF_ID
from neoaprs.radiotype import radio_id_of
from neoaprs.services.beacon import memory_key_of
from neoaprs.services.memory import stamp
from neoaprs.store import DB_NAME
from tests.support.bundledb import bundle_database
from tests.support.clock import FixedClock
from tests.support.env import OPERATOR, Env
from tests.support.migrated31 import at_thirty, has_table, run_31, state_row, station_rows, stored_config, undo_31
from tests.test_migrations import GOLDEN, GOLDEN_USED, used_by

STAMP = "2026-10-21T12:00:00.000000Z"
LATER = "2026-10-21T12:30:00.000000Z"
# The checksum of the step and of what it uses beside itself, as tests/test_migrations.py pins them once the step is among MIGRATIONS (GOLDEN[31], GOLDEN_USED["_v31"]): frozen from the day it was written.
V31 = "3f4253eb76b65cc049509915a7db44623c5a8da1b7401c6af1cbcd0e95d1d1b1"
V31_USED = {"_CHOICES": "8dff05af4898688bb573d41c40e6ea66cb01fec877ebf9d1103e4e60ad8afbd6", "_FALSE": "26d5af627562f4f506311ff6b1f373ce1d4406cfbd264b33a38ed9fc8f613802", "_FM_MOVES": "51c809510ed2916bd937bbbd481e61c2ced3975132253b646c4544fa0d1cce96", "_FM_TYPES": "7541c474b50bbecda547e23a7ca29d8783194a22d030e54ba2cce545bfe803b9", "_GONE": "899f89869d238a2e74ed59d38c738a293da367551f893b12830f5e082b1f1e88", "_HF_MOVES": "4e04d8edf6de4538b82213828691ce0b0e0ae70998b818ed2eb4b57d2d43c49c", "_HF_ROWS": "193801f61fca27cd9ded94bac5f1f7cded93f930f3684f22435e7d4d606fde11", "_HF_TYPES": "40d1c888a8e29895c78e13046d4715f7e5be0b622c14709ebc8cf84203988679", "_KEPT": "81d155c5e50be9f6ef91ea3241da710fabe991e4377a1412919ed7ec71371fa5", "_STATE": "d15998254a92fef6d3ac0265df36572c51567de7b573570f61cfda7028f39757", "_TRUE": "2903545dd56c033b3f0962fa48660f7136a4656b920d5ff309b7f5cb810ebbb4", "_choices31": "38cc46833e0239c9051396bffba6e612f3c01025a619295951ae68c2bd33ae36", "_hf_named31": "7afe8ecbd8e34526876dbb7fe17155d89f89153aef209920bc7f6cd043b0654d", "_move31": "b827728202d34d1f4e2a9d3b7d00babdf9281af5d41205a51992a6dc28e4bff5", "_on31": "e0f91aa73006f8063e626492ea643502ae23ed4c90839a929649cec7006c0d67", "_tables31": "412412734227c3e63e9563ceb7156e04fc4edb8a621b83fca07ffc540dffd835", "_type31": "2d14e908b6235225e003fda1b4b077b0f021e53c4ca9f541d13315aa5b563fea"}
STATION = {"station/call": "OH2GBA", "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30", "status/interval_min": "60", "status/source": "text", "station/status": "QRV",
           "serial/pattern": "/dev/ttyS*", "serial/skip": "/dev/ttyUSB3", "update/hf_dial": "7.0541 MHz USB", "update/install_id": "4711", "status/last_sent_at": "2026-10-23T10:00:00Z",
           "web/port": "7777", "igate/enabled": "true"}             # rows that are the station's, the computer's and the daemon's own: no radio's


def old(tmp_path: Path, settings: dict[str, str] | None = None, *statements: tuple[str, tuple[object, ...]]) -> sqlite3.Connection:
    """A database as version 30 left it with these settings rows (each at revision 1) and what these statements insert."""
    db = at_thirty(tmp_path / DB_NAME, FixedClock())
    for key, value in (settings or {}).items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    for statement, values in statements:
        db.execute(statement, values)
    return db


def packet(radio: str, via: str = "rf", source: str = "OH2RDG") -> tuple[str, tuple[object, ...]]:
    return ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via, radio) VALUES (?, 'in', x'00', ?, 'APRS', '', 'status', 's', '{}', ?, ?)", (STAMP, source, via, radio))


def message(radio: str, direction: str = "in") -> tuple[str, tuple[object, ...]]:
    return ("INSERT INTO message (at, direction, from_call, to_call, text, msg_id, state, attempts, route, radio) VALUES (?, ?, 'OH2RDG', 'OH2GBA', 'hello', '7', ?, 0, '', ?)",
            (STAMP, direction, "received" if direction == "in" else "sending", radio))


def attempt(radio: str) -> tuple[str, tuple[object, ...]]:
    return ("INSERT INTO message_attempt (message_id, attempt, sent_at, path, radio) VALUES (1, 1, ?, '', ?)", (STAMP, radio))


def own_object(radio: str) -> tuple[str, tuple[object, ...]]:
    return ("INSERT INTO own_object (name, kind, lat, lon, symbol_table, symbol_code, comment, alive, created_at, updated_at, radio) VALUES ('LEIRI', 'object', 60.2, 25.0, '/', '-', 'camp', 1, ?, ?, ?)", (STAMP, STAMP, radio))


def station(heard_fm: int, heard_hf: int, call: str = "OH2HF") -> tuple[str, tuple[object, ...]]:
    """A station of the cache, heard so many times on each radio (the cache outlives the daily prune of the packets that counted it)."""
    return ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path, heard_fm, heard_hf, last_fm_at, last_hf_at) "
            "VALUES (?, 'station', '', '/', '-', ?, ?, '', '', ?, '', ?, ?, ?, ?)", (call, STAMP, STAMP, heard_fm + heard_hf, heard_fm, heard_hf, STAMP if heard_fm else None, STAMP if heard_hf else None))


def station_pref() -> tuple[str, tuple[object, ...]]:
    return ("INSERT INTO station_pref (call, path, updated_at) VALUES ('OH2RDG', 'WIDE1-1', ?)", (STAMP,))


def radios(db: sqlite3.Connection) -> list[tuple[object, ...]]:
    """(id, kind, type, name, enabled, position, removed_at) of every radio."""
    return [tuple(r) for r in db.execute("SELECT id, kind, type, name, enabled, position, removed_at FROM radio ORDER BY id")]


def own(db: sqlite3.Connection) -> dict[tuple[int, str], tuple[str, int]]:
    """The radios' own settings: (radio, key) to (value, revision)."""
    return {(int(radio), str(key)): (str(value), int(rev)) for radio, key, value, rev in db.execute("SELECT radio_id, key, value, rev FROM radio_setting")}


def settings(db: sqlite3.Connection) -> dict[str, tuple[str, int]]:
    return {str(key): (str(value), int(rev)) for key, value, rev in db.execute("SELECT key, value, rev FROM settings")}


def decided(db: sqlite3.Connection) -> list[tuple[object, ...]]:
    """The row of `_m31`: (hf_exists, fm_on, hf_on)."""
    return [tuple(r) for r in db.execute("SELECT hf_exists, fm_on, hf_on FROM _m31")]


def migrated(tmp_path: Path, rows: dict[str, str] | None = None, *statements: tuple[str, tuple[object, ...]]) -> sqlite3.Connection:
    """The old database of these rows after migration 31, with the settings in force held to what the flat keys said before it."""
    db = old(tmp_path, rows, *statements)
    before = Config.from_data(rows or {})
    run_31(db)
    after = stored_config(db)
    assert after.to_data() == before.to_data(), "every setting says what it said"
    assert [(s.id, s.kind) for s in after.enabled_radios] == [(s.id, s.kind) for s in before.enabled_radios] and after.main_radio == before.main_radio, "the radios that are on, and the main one, are the ones that were"
    return db


FM, FM_OFF = (1, "fm", "kiss", "", 1, 1, None), (1, "fm", "kiss", "", 0, 1, None)
HF, HF_OFF = (2, "hf", "mercury", "", 1, 2, None), (2, "hf", "mercury", "", 0, 2, None)


# ---- the shapes of an installation

def test_a_database_with_no_rows_at_all_is_a_new_installation_and_gets_no_radio(tmp_path: Path) -> None:
    db = old(tmp_path)
    run_31(db)
    assert radios(db) == [] and own(db) == {} and settings(db) == {} and decided(db) == [(0, 0, 0)], "no radio, and the row that says so for the migrations 32 and 33"
    assert stored_config(db).radios == () and stored_config(db).main_radio is None
    assert db.execute("INSERT INTO radio (kind, type, enabled, position) VALUES ('fm', 'kiss', 1, 1)").lastrowid == 1, "the first radio it is given is radio 1"


@pytest.mark.parametrize("row", [message("fm", "out"), message("", "out"), attempt("fm"), own_object("fm"), station(3, 0), station(0, 0), station_pref()],
                         ids=["message", "message-no-radio", "attempt", "object", "station-fm", "station-internet", "station-pref"])
def test_a_row_of_an_installation_and_no_settings_row_is_no_new_installation_and_gets_the_fm_radio(tmp_path: Path, row: tuple[str, tuple[object, ...]]) -> None:
    db = migrated(tmp_path, None, row)
    assert radios(db) == [FM] and decided(db) == [(0, 1, 0)], "the packets are pruned and these rows are not: the migrations 32 and 33 give them radio 1, which is there"
    assert db.execute("INSERT INTO radio (kind, type, enabled, position) VALUES ('hf', 'mercury', 1, 2)").lastrowid == 2, "a radio added later is a new one, and inherits nothing of radio 1"


def test_settings_and_no_packet_make_the_fm_radio_alone_on_with_its_default_type_and_touch_no_other_row(tmp_path: Path) -> None:
    db = migrated(tmp_path, STATION)
    assert radios(db) == [FM] and own(db) == {} and decided(db) == [(0, 1, 0)]
    assert settings(db) == {key: (value, 1) for key, value in STATION.items()}, "the station's rows, the computer's (serial/pattern, serial/skip) and the daemon's are as they were, revision included"


def test_a_packet_and_no_settings_row_is_an_installation_that_ran_and_gets_the_fm_radio(tmp_path: Path) -> None:
    db = migrated(tmp_path, None, packet("fm"), packet("", "is", "OH2NET"))
    assert radios(db) == [FM] and decided(db) == [(0, 1, 0)] and settings(db) == {}


@pytest.mark.parametrize(("rows", "type"), [
    ({"tnc/enter_kiss": "true"}, "kenwood-tnc2"), ({"tnc/enter_kiss": " Yes "}, "kenwood-tnc2"), ({"tnc/enter_kiss": "false"}, "kiss"), ({"tnc/enter_kiss": "maybe"}, "kiss"),
    ({"tnc/enter_kiss": "true", "tnc/profile": "kantronics"}, "kantronics"), ({"tnc/enter_kiss": "true", "tnc/profile": "kiss"}, "kiss")])
def test_enter_kiss_of_the_build_before_the_profiles_is_the_kenwood_tnc2_type_unless_a_profile_was_chosen(tmp_path: Path, rows: dict[str, str], type: str) -> None:
    db = migrated(tmp_path, {**rows, "station/call": "OH2GBA"})
    assert radios(db) == [(1, "fm", type, "", 1, 1, None)] and decided(db) == [(0, 1, 0)]
    assert settings(db) == {"station/call": ("OH2GBA", 1)}, "the old row is gone: what it meant is the radio's type"


def test_the_type_mercury_alone_of_the_build_before_two_radios_is_the_hf_radio_on_and_the_fm_radio_off(tmp_path: Path) -> None:
    db = migrated(tmp_path, {"tnc/profile": "mercury", "station/call": "OH2GBA", "mercury/sound_card": "plughw:1,0"})
    assert radios(db) == [FM_OFF, HF] and decided(db) == [(1, 0, 1)]
    assert own(db) == {(2, "sound_card"): ("plughw:1,0", 1)} and settings(db) == {"station/call": ("OH2GBA", 1)}


def test_the_type_mercury_alone_with_enter_kiss_keeps_the_kenwood_type_for_the_fm_radio_that_is_off(tmp_path: Path) -> None:
    db = migrated(tmp_path, {"tnc/profile": " mercury ", "tnc/enter_kiss": "true"})
    assert radios(db) == [(1, "fm", "kenwood-tnc2", "", 0, 1, None), HF] and decided(db) == [(1, 0, 1)] and settings(db) == {}


@pytest.mark.parametrize("tick", [{"fm/enabled": "true"}, {"hf/enabled": "false"}, {"fm/enabled": "true", "hf/enabled": "true"}])
def test_the_type_mercury_with_a_tickbox_stored_is_no_type_of_the_fm_radio_and_the_tickboxes_decide(tmp_path: Path, tick: dict[str, str], caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        db = migrated(tmp_path, {"tnc/profile": "mercury", **tick})
    hf_on = int(tick.get("hf/enabled") == "true")
    assert radios(db) == [FM, (2, "hf", "mercury", "", hf_on, 2, None)] and decided(db) == [(1, 1, hf_on)], "the FM radio has the default type, as the settings read it; the HF radio is there, the type named it"
    assert any("tnc/profile was 'mercury'" in r.getMessage() and "kiss" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(("fm", "hf", "on"), [("false", "true", (0, 1)), ("true", "true", (1, 1)), ("false", "false", (0, 0)), ("true", "false", (1, 0)), (" No ", "1", (0, 1)), ("maybe", "perhaps", (1, 0))])
def test_both_tickboxes_stored_are_the_radios_tickboxes_and_a_word_that_is_none_is_the_default(tmp_path: Path, fm: str, hf: str, on: tuple[int, int]) -> None:
    db = migrated(tmp_path, {"fm/enabled": fm, "hf/enabled": hf, "tnc/profile": "kenwood-d710", "hf/profile": "dummy-hf"})
    assert radios(db) == [(1, "fm", "kenwood-d710", "", on[0], 1, None), (2, "hf", "dummy-hf", "", on[1], 2, None)] and decided(db) == [(1, on[0], on[1])]
    assert settings(db) == {} and own(db) == {}, "the type and the tickbox are the radio's columns, written plainly"


def test_an_hf_radio_that_was_never_enabled_is_not_made_and_nothing_names_it(tmp_path: Path) -> None:
    rows = {**STATION, "tnc/profile": "kenwood-tnc2", "fm/enabled": "true", "serial/port": "/dev/ttyUSB0", "beacon/path": "WIDE1-1,WIDE2-1", "digi/enabled": "true", "beacon/last_sent_at": "2026-10-23T10:00:00Z",
            "messages/radio_by_station": '{"OH2RDG": "fm"}'}
    db = migrated(tmp_path, rows, packet("fm"), packet("", "is", "OH2NET"), message("fm"), message("", "out"), attempt("fm"), own_object("fm"))
    assert radios(db) == [(1, "fm", "kenwood-tnc2", "", 1, 1, None)] and decided(db) == [(0, 1, 0)]
    assert own(db) == {(1, "port"): ("/dev/ttyUSB0", 1), (1, "path"): ("WIDE1-1,WIDE2-1", 1), (1, "digipeat"): ("true", 1)}, "the path is the FM radio's alone: there is no radio 2 to keep it for"
    assert not [key for key in settings(db) if key.startswith(("radio/2/", "hf/", "mercury/"))] and settings(db)["messages/radio_by_station"] == ('{"OH2RDG": 1}', 2)
    assert stored_config(db).radio(2) is None and [s.id for s in stored_config(db).live_radios] == [1]


@pytest.mark.parametrize("row", [packet("hf"), message("hf"), attempt("hf"), own_object("hf"), own_object("both"), station(0, 4), station(2, 1)],
                         ids=["packet", "message", "attempt", "object-hf", "object-both", "station-hf", "station-both"])
def test_an_hf_radio_never_enabled_but_named_by_a_row_is_made_and_is_off(tmp_path: Path, row: tuple[str, tuple[object, ...]]) -> None:
    db = migrated(tmp_path, {"station/call": "OH2GBA", "beacon/path": "WIDE2-1"}, packet("fm"), row)
    assert radios(db) == [FM, HF_OFF] and decided(db) == [(1, 1, 0)], "what came by the HF radio still has a radio to name"
    assert own(db) == {(1, "path"): ("WIDE2-1", 1), (2, "path"): ("WIDE2-1", 1)}


def test_a_station_heard_on_hf_alone_after_its_packets_were_pruned_is_an_installation_with_the_hf_radio(tmp_path: Path) -> None:
    db = migrated(tmp_path, None, station(0, 4))
    assert radios(db) == [FM, HF_OFF] and decided(db) == [(1, 1, 0)], "what the HF radio heard still has its radio: a radio added later does not inherit it"
    assert db.execute("SELECT heard_hf FROM station").fetchone() == (4,)


@pytest.mark.parametrize("key", ["hf/enabled", "hf/profile", "mercury/sound_card", "mercury/keying", "mercury/tx_gain_db", "hf/beacon_last_sent_at"])
def test_any_settings_row_of_the_hf_radio_means_it_was_set_up_and_the_radio_is_made(tmp_path: Path, key: str) -> None:
    db = old(tmp_path, {key: "false" if key == "hf/enabled" else "mercury" if key == "hf/profile" else "2026-10-23T10:00:00Z" if key.endswith("_at") else "0" if key.endswith("_db") else ""})
    run_31(db)
    assert radios(db) == [FM, HF_OFF] and decided(db) == [(1, 1, 0)], "the program writes only what was changed, so a row means the HF radio was set"


def test_the_last_port_the_search_found_becomes_the_fm_radios_own_state(tmp_path: Path) -> None:
    db = migrated(tmp_path, {"serial/last_port": "/dev/serial/by-id/usb-FTDI-if00", "serial/pattern": "/dev/ttyS*"})
    assert settings(db) == {"radio/1/last_port": ("/dev/serial/by-id/usb-FTDI-if00", 1), "serial/pattern": ("/dev/ttyS*", 1)}
    assert state_row(db, "serial/last_port") == ("/dev/serial/by-id/usb-FTDI-if00", 1) and stored_config(db).serial_last_port == "/dev/serial/by-id/usb-FTDI-if00", "the settings read it as radio 1's"


def test_the_beacons_last_sends_become_each_radios_own_state(tmp_path: Path) -> None:
    db = migrated(tmp_path, {"beacon/last_sent_at": "2026-10-23T10:00:00Z", "hf/beacon_last_sent_at": "2026-10-23T10:20:00Z", "status/last_sent_at": "2026-10-23T10:05:00Z", "status/last_text": "on 145.800"})
    assert settings(db) == {"radio/1/beacon_last_sent_at": ("2026-10-23T10:00:00Z", 1), "radio/2/beacon_last_sent_at": ("2026-10-23T10:20:00Z", 1),
                            "status/last_sent_at": ("2026-10-23T10:05:00Z", 1), "status/last_text": ("on 145.800", 1)}, "the status report's rows are the station's and stay"
    assert radios(db) == [FM, HF_OFF], "an HF beacon that went out once: the HF radio was there"
    assert state_row(db, "beacon/last_sent_at") == ("2026-10-23T10:00:00Z", 1) and state_row(db, "hf/beacon_last_sent_at") == ("2026-10-23T10:20:00Z", 1)


def test_the_stations_radios_are_kept_by_id_and_a_choice_of_hf_makes_the_hf_radio(tmp_path: Path) -> None:
    db = migrated(tmp_path, {"messages/radio_by_station": '{"OH2GAX-2": "hf", "OH2RDG": "fm", "OH6XYZ": "hf"}'})
    assert settings(db) == {"messages/radio_by_station": ('{"OH2GAX-2": 2, "OH2RDG": 1, "OH6XYZ": 2}', 2)}, "the same row, the same calls, the radios by id; the revision moves on"
    assert radios(db) == [FM, HF_OFF] and decided(db) == [(1, 1, 0)]


@pytest.mark.parametrize(("text", "kept"), [('{"OH2RDG": "fm", "OH2ABC": "lora", "OH2DEF": 7, "OH2GHI": ""}', {"OH2RDG": 1}), ("not json", {}), ('["OH2RDG", "hf"]', {}), ("{}", {}), ("", {})])
def test_a_choice_that_is_no_radio_of_today_and_a_row_that_is_no_choices_say_nothing(tmp_path: Path, text: str, kept: dict[str, int]) -> None:
    db = migrated(tmp_path, {"messages/radio_by_station": text})
    assert json.loads(settings(db)["messages/radio_by_station"][0]) == kept and radios(db) == [FM], "as the daemon read the row: a word that is neither radio was no choice, and names no HF radio"


def test_a_tcp_type_with_a_tcp_address_in_the_port_keeps_both(tmp_path: Path) -> None:
    db = migrated(tmp_path, {"tnc/profile": "kiss-tcp", "serial/port": "tcp://192.168.1.5:8100", "tcp/host": "::1", "tcp/port": "8100", "serial/baud": ""})
    assert radios(db) == [(1, "fm", "kiss-tcp", "", 1, 1, None)]
    assert own(db) == {(1, "port"): ("tcp://192.168.1.5:8100", 1), (1, "tcp_host"): ("::1", 1), (1, "tcp_port"): ("8100", 1), (1, "baud"): ("", 1)} and settings(db) == {}
    spec = stored_config(db).radio(1)
    assert spec is not None and (spec.rtype.transport, spec.value("port"), spec.value("tcp_host"), spec.value("tcp_port"), spec.value("baud")) == ("tcp", "tcp://192.168.1.5:8100", "::1", 8100, None)


# ---- every row of the table of section 3 that says 31

def test_every_settings_row_of_the_radios_becomes_the_radios_own_with_its_revision_and_is_deleted(tmp_path: Path) -> None:
    flat = {"tnc/profile": "kenwood-d710", "fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf", "serial/port": "/dev/ttyUSB7", "serial/baud": "19200", "tcp/host": "10.0.0.5", "tcp/port": "8100",
            "mercury/sound_card": "plughw:2,0", "mercury/keying": "rts:/dev/ttyUSB3", "mercury/tx_gain_db": "-3", "beacon/path": "WIDE2-2", "digi/enabled": "true"}
    gone = {"tnc/enter_kiss": "true", "tnc/check_sec": "90", "hf/anything": "x", "mercury/old": "y", "tcp/timeout": "5"}            # rows of the radios' families that are no setting any more
    db = old(tmp_path, {**STATION, **flat, **gone})
    db.execute("UPDATE settings SET rev = 4 WHERE key IN ('serial/port', 'beacon/path', 'mercury/keying', 'station/call')")       # (saved a few times)
    before = Config.from_data({**STATION, **flat, **gone})
    run_31(db)
    assert radios(db) == [(1, "fm", "kenwood-d710", "", 0, 1, None), (2, "hf", "dummy-hf", "", 1, 2, None)] and decided(db) == [(1, 0, 1)]
    assert own(db) == {(1, "port"): ("/dev/ttyUSB7", 4), (1, "baud"): ("19200", 1), (1, "tcp_host"): ("10.0.0.5", 1), (1, "tcp_port"): ("8100", 1), (1, "path"): ("WIDE2-2", 4), (1, "digipeat"): ("true", 1),
                       (2, "sound_card"): ("plughw:2,0", 1), (2, "keying"): ("rts:/dev/ttyUSB3", 4), (2, "tx_gain_db"): ("-3", 1), (2, "path"): ("WIDE2-2", 4)}, "only the rows that were there, each with its value and revision; the path on both"
    assert settings(db) == {key: (value, 4 if key == "station/call" else 1) for key, value in STATION.items()}, "the radios' rows and their families' leftovers are deleted, every other row is as it was"
    assert station_rows(db) == {key: (value, 4 if key == "station/call" else 1) for key, value in STATION.items() if key in STATION_KEYS}
    after = stored_config(db)
    assert after.to_data() == before.to_data() and {key: after.to_data()[key] for key in flat} == flat, "and the settings read every one of them back from the radios"
    hf = after.radio(2)
    assert hf is not None and "path" not in hf.settings, "the HF radio's kept path is no setting of its kind today: it waits in the table"


def test_a_stored_value_that_was_wrong_is_kept_as_it_was_stored_and_is_the_default_in_force_as_before(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rows = {"tnc/profile": "tnc2", "hf/profile": "ardop", "hf/enabled": "true", "serial/baud": "12", "tcp/port": "0", "mercury/tx_gain_db": "99", "serial/port": "  /dev/ttyUSB0 "}
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        db = migrated(tmp_path, rows)
    assert radios(db) == [FM, HF], "a type that is none was the default type in force, and is written so"
    assert [r.getMessage() for r in caplog.records if "is no type" in r.getMessage()] == ["tnc/profile was 'tnc2', which is no type of that radio: its type is kiss, as it was in force",
                                                                                          "hf/profile was 'ardop', which is no type of that radio: its type is mercury, as it was in force"]
    assert own(db) == {(1, "baud"): ("12", 1), (1, "tcp_port"): ("0", 1), (1, "port"): ("  /dev/ttyUSB0 ", 1), (2, "tx_gain_db"): ("99", 1)}, "a value is moved as it is, not judged"
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="neoaprs.config"):
        config = stored_config(db)
    assert (config.serial_baud, config.tcp_port, config.mercury_tx_gain_db, config.serial_port) == (None, 8001, 0, "/dev/ttyUSB0")
    assert sorted(r.getMessage().split(":")[0] for r in caplog.records if r.name == "neoaprs.config") == ["radio/1/baud", "radio/1/tcp_port", "radio/2/tx_gain_db"], "told once each, with the radio's key"


SHAPES: list[dict[str, str]] = [
    {"hf/enabled": "true"},
    {"fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf"},
    {"tnc/profile": "kiss-tcp", "tcp/host": "::1", "tcp/port": "8100", "beacon/path": "DIRECT"},
    {"tnc/profile": " kenwood-d710 ", "serial/port": "/dev/serial/by-id/usb-FTDI-if00", "serial/baud": "19200", "beacon/path": "WIDE1-1,WIDE2-1", "digi/enabled": "true", "serial/last_port": "/dev/ttyUSB1"},
    {"tnc/profile": "dummy", "hf/enabled": "true", "mercury/sound_card": "plughw:1,0", "mercury/keying": "rts:/dev/ttyUSB1", "mercury/tx_gain_db": "-6"},
    {"digi/enabled": "On", "beacon/path": " wide1-1 , wide2-1 ", "web/bind": "0.0.0.0", "station/call": "oh2gba-7"},
    {key: DEFAULTS.to_data()[key] for key in KEYS},                                     # what a save of every setting of the form stored
]


@pytest.mark.parametrize("rows", SHAPES, ids=lambda rows: ",".join(f"{k}={v}" for k, v in list(rows.items())[:4]))
def test_the_settings_in_force_after_the_migration_are_what_the_flat_keys_said_before(tmp_path: Path, rows: dict[str, str]) -> None:
    db = migrated(tmp_path, rows)
    assert not [key for key in settings(db) if key.startswith(("tnc/", "hf/", "mercury/", "tcp/")) or key in ("serial/port", "serial/baud", "beacon/path", "digi/enabled", "fm/enabled", "serial/last_port")]
    assert station_rows(db) == {key: (value, 1) for key, value in rows.items() if key in STATION_KEYS}


# ---- a database made from a support bundle (tests/support/bundledb.py), for the proof on a real installation's settings

def test_a_database_made_from_a_support_bundle_has_the_rows_the_bundle_tells_and_comes_through_the_migration(tmp_path: Path) -> None:
    rows = {"station/call": "OH2GAX-2", "station/lat": "60.5", "station/lon": "25.1", "tnc/profile": "kenwood-tnc2", "serial/port": " /dev/ttyUSB0 ", "serial/baud": "12", "hf/enabled": "true", "mercury/keying": "rts:COM7",
            "mercury/sound_card": "{0.0.0.00000000}.{ca03}", "web/key": "k7m2-x9pq-4hrt", "igate/password": "", "messages/alert_command": "curl https://example.org/bot123:ABC", "beacon/last_sent_at": "2026-11-07T19:20:00Z",
            "hf/beacon_last_sent_at": "2026-11-07T19:24:00Z", "messages/radio_by_station": '{"OH2GBA": "hf"}', "update/install_id": "4711", "tnc/enter_kiss": "true"}
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "settings.json").write_text(supportgather.settings_json(rows), encoding="utf-8")
    (bundle / "state.json").write_text(json.dumps({"tnc": {"state": "connected", "stats": {"packets": 3}}, "hf": {"enabled": True, "tnc": {"stats": {"packets": 250}}}}), encoding="utf-8")
    assert bundle_database(tmp_path / DB_NAME, bundle, FixedClock()) == ["messages/alert_command", "web/key"], "what the bundle only says is set is left out, and told"
    db = sqlite3.connect(tmp_path / DB_NAME, isolation_level=None)
    assert db.execute("PRAGMA user_version").fetchone() == (30,) and not has_table(db, "radio"), "as version 30 kept it: the migrations of the radios have it to run on"
    assert {key: value for key, (value, _) in settings(db).items()} == {key: value for key, value in rows.items() if key not in ("messages/alert_command", "web/key")}, "every other row as it was stored, the wrong and the unknown ones too"
    assert db.execute("SELECT radio, count(*) FROM packet GROUP BY radio ORDER BY radio").fetchall() == [("fm", 3), ("hf", 20)], "some packets for each radio that heard any"
    before = Config.from_data(rows)
    run_31(db)
    assert radios(db) == [(1, "fm", "kenwood-tnc2", "", 1, 1, None), HF] and decided(db) == [(1, 1, 1)]
    after = stored_config(db)
    assert {key: value for key, value in after.to_data().items() if key not in ("messages/alert_command", "web/key")} == {key: value for key, value in before.to_data().items() if key not in ("messages/alert_command", "web/key")}
    assert json.loads(settings(db)["messages/radio_by_station"][0]) == {"OH2GBA": 2} and state_row(db, "hf/beacon_last_sent_at") == ("2026-11-07T19:24:00Z", 1)
    db.close()
    with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as z:
        z.writestr("settings.json", supportgather.settings_json({"station/call": "OH2GBA"}))
    assert bundle_database(tmp_path / "second" / DB_NAME, tmp_path / "bundle.zip", FixedClock()) == [], "a bundle made without the daemon has no state: the settings alone"
    db = sqlite3.connect(tmp_path / "second" / DB_NAME, isolation_level=None)
    assert settings(db) == {"station/call": ("OH2GBA", 1)} and db.execute("SELECT count(*) FROM packet").fetchone() == (0,)


# ---- a daemon started on a database of today: what 31 rewrites is read again (I2's guard: the readers of the rows it renames follow it before it is among the steps)

async def test_a_daemon_started_on_an_old_database_keeps_the_choices_the_last_sends_and_the_radios_settings(tmp_path: Path) -> None:
    """Whatever the newest step: on version 30 the old readers read the old rows; with 31 among the steps the readers must read the radios, the ids and the radios' own state rows, or this fails
    (the choices would be read as none and overwritten at the next choice, the beacons would go out at the start, the radios' settings would be the defaults and saved so)."""
    clock = FixedClock()
    fm_sent, hf_sent = clock() - timedelta(minutes=10), clock() - timedelta(minutes=5)
    rows = {**OPERATOR, "beacon/interval_min": "30", "beacon/path": "WIDE2-1", "digi/enabled": "true", "beacon/last_sent_at": stamp(fm_sent), "hf/beacon_last_sent_at": stamp(hf_sent),
            "messages/radio_by_station": '{"OH2GAX-2": "hf", "OH2RDG": "fm"}'}
    db = old(tmp_path, rows, station(0, 6, "OH2GAX-2"), station(9, 0, "OH2RDG"), station(2, 0, "OH6XYZ"))
    db.close()
    e = Env(tmp_path, clock=clock)
    await e.start()
    assert (e.ctl.config.beacon_path, e.ctl.config.digi_enabled, e.ctl.config.tnc_profile) == ("WIDE2-1", True, "kenwood-tnc2"), "the radios' own settings are in force"
    assert (e.ctl.radios.choice("OH2GAX-2"), e.ctl.radios.choice("OH2RDG")) == (2, 1), "the operator's choices are restored"
    assert e.ctl.beacon.running and e.ctl.beacon.next_due == fm_sent + timedelta(minutes=30), "the FM beacon keeps its time: no beacon at the start"
    assert await e.ctl.store.setting(memory_key_of(HF_ID)) == stamp(hf_sent), "the HF beacon's row is where its beacon reads it"
    assert e.ctl.radios.choose("OH6XYZ", 1)
    await e.ctl.radios.flush()
    await e.stop()
    db = sqlite3.connect(tmp_path / DB_NAME)
    [(text,)] = db.execute("SELECT value FROM settings WHERE key = 'messages/radio_by_station'").fetchall()
    assert {call: radio_id_of(radio) if isinstance(radio, str) else radio for call, radio in json.loads(text).items()} == {"OH2GAX-2": 2, "OH2RDG": 1, "OH6XYZ": 1}, "a new choice keeps the others"
    db.close()


# ---- the tables

def test_the_radio_table_refuses_what_the_program_cannot_produce_and_never_gives_an_id_twice(tmp_path: Path) -> None:
    db = old(tmp_path, {"hf/enabled": "true"})
    run_31(db)
    insert = "INSERT INTO radio (kind, type, name, enabled, position, removed_at) VALUES (?, ?, ?, ?, ?, ?)"
    for row in [("am", "kiss", "", 1, 3, None), ("fm", "", "", 1, 3, None), ("fm", "kiss", "123456789", 1, 3, None), ("fm", "kiss", "", 2, 3, None), ("fm", "kiss", "", 1, 3, "yesterday"), ("fm", "kiss", "", 1, None, None)]:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert, row)
    assert db.execute(insert, ("lora", "dummy-lora", "Shack", 1, 3, None)).lastrowid == 3
    with pytest.raises(sqlite3.IntegrityError, match="radio_name|UNIQUE"):
        db.execute(insert, ("fm", "kiss", "SHACK", 1, 4, None))
    db.execute("UPDATE radio SET removed_at = ? WHERE id = 3", (LATER,))
    assert db.execute(insert, ("fm", "kiss", "shack", 1, 4, None)).lastrowid == 4, "the name of a removed radio is free"
    assert db.execute(insert, ("fm", "kiss", "", 1, 5, None)).lastrowid == 5 and db.execute(insert, ("fm", "kiss", "", 1, 6, None)).lastrowid == 6, "any number without a name"
    db.execute("DELETE FROM radio WHERE id = 6")
    assert db.execute(insert, ("fm", "kiss", "", 1, 6, None)).lastrowid == 7, "an id is never used again"
    for row in [(1, "", "x"), (1, "a/b", "x"), (1, "port", None)]:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (?, ?, ?)", row)
    db.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (1, 'port', '/dev/ttyUSB0')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (1, 'port', '/dev/ttyUSB1')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE radio_setting SET rev = 0")
    assert [tuple(r) for r in db.execute("SELECT name, type, \"notnull\" FROM pragma_table_info('_m31') ORDER BY cid")] == [("hf_exists", "INTEGER", 1), ("fm_on", "INTEGER", 1), ("hf_on", "INTEGER", 1)]


def test_a_step_that_fails_changes_nothing(tmp_path: Path) -> None:
    rows = {"tnc/profile": "kenwood-tnc2", "hf/enabled": "true", "serial/port": "/dev/ttyUSB0", "beacon/last_sent_at": "2026-10-23T10:00:00Z", "messages/radio_by_station": '{"OH2RDG": "hf"}'}
    db = old(tmp_path, rows)
    db.execute("CREATE TABLE radio_setting (x)")           # (the step's second table is in its way: it raises with the first made)
    with pytest.raises(sqlite3.OperationalError):
        run_31(db)
    assert settings(db) == {key: (value, 1) for key, value in rows.items()} and not has_table(db, "radio") and not has_table(db, "_m31"), "rolled back whole"
    db.execute("DROP TABLE radio_setting")
    run_31(db)
    assert radios(db) == [(1, "fm", "kenwood-tnc2", "", 1, 1, None), HF], "and the next start finishes it"


def test_undo_31_takes_the_tables_out_so_that_the_step_runs_again(tmp_path: Path) -> None:
    db = old(tmp_path, {"hf/enabled": "true"})
    run_31(db)
    undo_31(db)
    assert not has_table(db, "radio") and not has_table(db, "radio_setting") and not has_table(db, "_m31")
    undo_31(db)                                            # (and where migration 33 dropped _m31, or nothing is there, it does nothing)
    db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    run_31(db)
    assert radios(db) == [FM], "the rows of the radios it made were dropped with the tables: the settings it is run on now name no HF radio"


# ---- the step is frozen, and reads nothing of the program

def test_the_step_and_what_it_uses_beside_itself_are_frozen() -> None:
    assert source_hash(_v31) == V31 and used_by(_v31) == V31_USED, "migration 31 was edited: once it has run on a kept database a change is a new migration"
    assert GOLDEN.get(31, V31) == V31 and GOLDEN_USED.get("_v31", V31_USED) == V31_USED, "tests/test_migrations.py pins the same step"
    assert _v31 not in MIGRATIONS or MIGRATIONS.index(_v31) == 30


def test_the_step_imports_nothing_of_the_program_but_the_error_and_the_log_of_the_migrations() -> None:
    tree = ast.parse(inspect.getsource(migrationsteps31))
    imports = sorted(f"{node.module}.{alias.name}" if isinstance(node, ast.ImportFrom) else alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names)
    assert imports == ["dberror.StoreError", "json", "migrationlog.log", "sqlite3"], "a frozen step reads the database, never the program's settings, types or defaults: they are written into it"
