"""Migration 34 (neoaprs/migrationsteps34.py): no main radio. On a database as the older version
leaves it (tests/support/migrated34.py) the step adds `own_bulletin.radios`, writes the ticks the
main radio stood for and deletes `station/main_radio`. One test for each station shape; a doubting
step leaves the file as it was.
"""

import sqlite3
from pathlib import Path

import pytest

from neoaprs.dberror import StoreError
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationsteps34 import _v34
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened
from tests.support.migrated32 import columns, run
from tests.support.migrated34 import Old, connect, fm, hf, lora, monitor, places, sets, settings, ticks, version_33
from tests.test_migration_alert_markup import version_twenty_six
from tests.test_migrations import GOLDEN

KEYS = ("status", "ask", "local_info")
LAST = "2026-11-16T11:50:00Z"


def stepped(tmp_path: Path, old: Old) -> sqlite3.Connection:
    """The database of `old` with step 34 run on it as the runner runs it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = connect(version_33(tmp_path / DB_NAME, old, FixedClock()))
    run(db, _v34)
    return db


def each(db: sqlite3.Connection) -> dict[str, dict[int, str]]:
    return {key: ticks(db, key) for key in KEYS}


ON = dict.fromkeys(KEYS)


# ---- the stations of the design (section 4)


def test_a_one_fm_radio_needs_no_tick_and_its_setting_goes(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1),), chosen=1, bulletins={"BLN1": "net"}, objects={"CAMP": "1"}))
    assert each(db) == dict.fromkeys(KEYS, {}) and ticks(db, "beacon") == {}, (
        "one radio that sends carries everything whatever is stored, and one added later ticks it then"
    )
    assert (
        "station/main_radio" not in settings(db)
        and "email/radio" not in settings(db)
        and sets(db, "own_bulletin") == {"BLN1": "1"}
        and sets(db, "own_object") == {"CAMP": "1"}
    )
    assert "radios" in columns(db, "own_bulletin")


def test_b_fm_and_hf_never_chosen_tick_the_first_box(tmp_path: Path) -> None:
    db = stepped(
        tmp_path,
        Old((fm(1), hf(2)), settings={"status/last_sent_at": LAST}, bulletins={"BLN1": "net", "BLNA": "hamfest"}),
    )
    assert each(db) == dict.fromkeys(KEYS, {1: "true"}) and places(db) == {1: 1, 2: 2}
    assert sets(db, "own_bulletin") == {"BLN1": "1", "BLNA": "1"}
    found = settings(db)
    assert found["email/radio"] == "1", (
        "the mail went on FM, and stays there when FM is switched off and on again (with no row the radio left on would be written then)"
    )
    assert found["status/last_sent_at"] == LAST and not any(key.endswith("/status_last_sent_at") for key in found), (
        "no radio's own last status: one that carries it later counts from the station's"
    )
    assert (found["objects/send_on"], found["bulletins/send_on"]) == ("1", "1"), (
        "a new object and a new bulletin start where the bulletins went"
    )


def test_c_fm_and_hf_with_hf_chosen_puts_hfs_box_first_and_keeps_the_mail_on_fm(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1), hf(2)), chosen=2, bulletins={"BLN1": "net"}, objects={"ONFM": "1", "ONHF": "2"}))
    assert places(db) == {2: 1, 1: 2}, (
        "the main radio's box first: the first that is on is the radio the main radio was"
    )
    assert each(db) == dict.fromkeys(KEYS, {2: "true"}) and sets(db, "own_bulletin") == {"BLN1": "2"}
    assert settings(db)["email/radio"] == "1", "0.20.0 sent the mail on FM, which internet gateways hear"
    assert sets(db, "own_object") == {"ONFM": "1", "ONHF": "2"}, "each on a radio that is on: as it was"


def test_d_fm_chosen_and_off_with_hf_and_lora_on_goes_on_hf_and_the_mail_on_lora(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1, enabled=False), hf(2), lora(3)), chosen=1, objects={"ONFM": "1", "BOTH": "1,3"}))
    assert each(db) == dict.fromkeys(KEYS, {2: "true"}) and places(db) == {1: 1, 2: 2, 3: 3}, (
        "the main radio was HF, the first that is on: its box is the first that is on already"
    )
    assert settings(db)["email/radio"] == "3" and "station/main_radio" not in settings(db)
    assert sets(db, "own_object") == {"ONFM": "1,2", "BOTH": "1,3"}, (
        "an object none of whose radios is on gets the main radio; FM stays among its radios for the day it is on"
    )


def test_e_the_chosen_radio_removed_is_as_none_chosen(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1), hf(2), hf(3, removed=True)), chosen=3, objects={"LEFT": "3"}))
    assert (
        each(db) == dict.fromkeys(KEYS, {1: "true"})
        and sets(db, "own_object") == {"LEFT": "1,3"}
        and settings(db)["email/radio"] == "1"
    )


def test_f_lora_beside_a_monitor_that_only_receives_needs_no_tick_and_the_monitor_none(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((monitor(1), lora(2)), chosen=1, bulletins={"BLN1": "net"}))
    assert (
        each(db) == dict.fromkeys(KEYS, {})
        and sets(db, "own_bulletin") == {"BLN1": "2"}
        and places(db) == {1: 1, 2: 2}
        and "email/radio" not in settings(db)
    )


# ---- the shapes beside them


def test_no_radio_gets_the_column_and_nothing_else(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((), chosen=4, settings={"station/call": "OH2GBA"}))
    assert "radios" in columns(db, "own_bulletin") and settings(db) == {"station/call": "OH2GBA"}


def test_every_radio_off_ticks_the_chosen_one_for_when_one_is_on(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1, enabled=False), hf(2, enabled=False)), chosen=2, bulletins={"BLN1": "net"}))
    assert (
        each(db) == dict.fromkeys(KEYS, {2: "true"})
        and places(db) == {2: 1, 1: 2}
        and sets(db, "own_bulletin") == {"BLN1": "2"}
    ), "the chosen radio's box first: once both are on, it is the first that is on"
    found = settings(db)
    assert (found["objects/send_on"], found["bulletins/send_on"]) == ("2", "2"), (
        "a new object and a new bulletin start on the radio chosen, not on the first box"
    )
    assert found["email/radio"] == "1", (
        "0.20.0 sent the mail on FM once it was on: internet gateways hear it, not the chosen HF"
    )
    fm_chosen = stepped(
        tmp_path / "fm", Old((fm(1, enabled=False), lora(2, enabled=False), fm(3, enabled=False)), chosen=3)
    )
    assert settings(fm_chosen)["email/radio"] == "3" and places(fm_chosen) == {3: 1, 1: 2, 2: 3}, (
        "the radio chosen, of a kind they hear"
    )


def test_hf_on_alone_with_fm_off_stores_fm_for_the_mail_once_it_is_on(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1, enabled=False), hf(2))))
    found = settings(db)
    assert found["email/radio"] == "1" and places(db) == {1: 1, 2: 2}, (
        "the mail goes on HF while it is alone, and on FM once FM is on, as 0.20.0 sent it"
    )
    assert "email/radio" not in settings(stepped(tmp_path / "hf", Old((hf(1), hf(2, enabled=False))))), (
        "no radio of a kind internet gateways hear: no row"
    )


def test_three_on_with_every_beacon_tick_off_tick_the_main_radios_beacon(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1, beacon="false"), hf(2, beacon="false"), lora(3, beacon="false"))))
    assert ticks(db, "beacon") == {1: "true", 2: "false", 3: "false"}, "0.20.0 sent the beacon on the main radio then"
    alone = stepped(tmp_path / "other", Old((fm(1, beacon="false"), hf(2, enabled=False, beacon="false"))))
    assert ticks(alone, "beacon") == {1: "false", 2: "false"}, (
        "one radio on beacons whatever its tick: nothing to write"
    )


def test_two_fm_radios_with_the_second_chosen_put_its_box_first(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1), fm(2)), chosen=2))
    assert (
        places(db) == {2: 1, 1: 2}
        and each(db) == dict.fromkeys(KEYS, {2: "true"})
        and settings(db)["email/radio"] == "2"
    )


def test_a_monitor_and_radios_that_are_off_keep_their_order_behind_the_main_radio(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((monitor(1), fm(2, enabled=False), fm(3), hf(4), lora(5, position=9)), chosen=4))
    assert places(db) == {4: 1, 1: 2, 2: 3, 3: 4, 5: 5}, "the main radio first, every other in its order"


def test_two_live_radios_in_one_place_are_numbered_again_in_their_order(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1, position=3), hf(2, position=3), lora(3, position=1))))
    assert places(db) == {3: 1, 1: 2, 2: 3}


# ---- rows that earlier builds of the main radio rule already wrote


def test_rows_already_stored_are_left_and_the_main_radio_ticked_where_none_of_those_on_is(tmp_path: Path) -> None:
    db = stepped(
        tmp_path,
        Old(
            (fm(1), hf(2, status="true"), lora(3, ask="false")),
            settings={
                "email/radio": "2",
                "radio/2/status_last_sent_at": "2026-11-16T11:00:00Z",
                "status/last_sent_at": LAST,
            },
        ),
    )
    assert each(db) == {"status": {2: "true"}, "ask": {1: "true", 3: "false"}, "local_info": {1: "true"}}, (
        "a row stored by the status's Send on of 0.20.1 is the operator's; a key some radio has a row for is left"
    )
    found = settings(db)
    assert found["email/radio"] == "2", "the choice of the E-mail tab stays"
    assert (
        "radio/1/status_last_sent_at" in found,
        found["radio/2/status_last_sent_at"],
        "radio/3/status_last_sent_at" in found,
    ) == (False, "2026-11-16T11:00:00Z", False), "a radio's own last status stays, and none is made"
    gap = stepped(tmp_path / "gap", Old((fm(1), hf(2, enabled=False, status="true"), lora(3, status="false"))))
    assert ticks(gap, "status") == {1: "true", 2: "true", 3: "false"}, (
        "ticked for HF alone, HF off, FM and LoRa on: 0.20.1 sent it on the main radio, which is now ticked"
    )


def test_a_stored_main_radio_that_is_no_number_is_as_none(tmp_path: Path) -> None:
    db = connect(
        version_33(tmp_path / DB_NAME, Old((fm(1), hf(2)), settings={"station/main_radio": " 2x"}), FixedClock())
    )
    run(db, _v34)
    assert (
        each(db) == dict.fromkeys(KEYS, {1: "true"})
        and places(db) == {1: 1, 2: 2}
        and "station/main_radio" not in settings(db)
    )


# ---- the step itself


def test_a_step_that_doubts_raises_and_leaves_the_file_as_it_was(tmp_path: Path) -> None:
    db = connect(version_33(tmp_path / DB_NAME, Old((fm(1), hf(2)), chosen=2, bulletins={"BLN1": "net"}), FixedClock()))
    # An update that changes no row: the count says so
    db.execute("CREATE TRIGGER still BEFORE UPDATE ON own_bulletin BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(StoreError, match="not every one was given its radio; nothing was changed"):
        run(db, _v34)
    assert (
        "radios" not in columns(db, "own_bulletin")
        and settings(db)["station/main_radio"] == "2"
        and places(db) == {1: 1, 2: 2}
        and each(db) == dict.fromkeys(KEYS, {})
    )


def test_the_step_run_again_is_refused_and_changes_nothing(tmp_path: Path) -> None:
    db = stepped(tmp_path, Old((fm(1), hf(2)), chosen=2))
    before = (settings(db), each(db), places(db))
    with pytest.raises(sqlite3.OperationalError, match="duplicate column"):
        run(db, _v34)
    assert (settings(db), each(db), places(db)) == before


def test_the_runner_takes_a_file_of_version_33_to_34_with_a_copy_first(tmp_path: Path) -> None:
    clock = FixedClock()
    path = version_33(tmp_path / DB_NAME, Old((fm(1), hf(2)), chosen=2), clock)
    s = opened(path, clock)
    assert s.version() == SCHEMA_VERSION >= 34 and [(n, name, sha) for n, name, sha, *_ in s.history()][33] == (
        34,
        "_v34",
        GOLDEN[34],
    )
    assert places(s.db) == {2: 1, 1: 2}
    s.close()
    assert [p.name for p in (tmp_path / "backup").glob("premigrate-*.sqlite")] == [
        f"premigrate-v33-to-v{SCHEMA_VERSION}-20261021-120000.sqlite"
    ]


def test_a_file_of_0_18_2_comes_through_steps_27_to_34_in_one_start_with_one_copy(tmp_path: Path) -> None:
    """FM and HF at version 26: steps 31 to 33 make radio 1 and radio 2 and no `station/main_radio`;
    step 34 ticks radio 1."""
    clock = FixedClock()
    path = tmp_path / DB_NAME
    version_twenty_six(
        path,
        clock,
        {
            "station/call": "OH2GBA",
            "tnc/profile": "kiss",
            "hf/enabled": "true",
            "hf/profile": "dummy-hf",
            "status/last_sent_at": LAST,
        },
    )
    s = opened(path, clock)
    assert s.version() == SCHEMA_VERSION and [n for n, *_ in s.history()][26:34] == list(range(27, 35))
    assert each(s.db) == dict.fromkeys(KEYS, {1: "true"}) and places(s.db) == {1: 1, 2: 2}
    assert (
        settings(s.db)["status/last_sent_at"] == LAST
        and "radio/2/status_last_sent_at" not in settings(s.db)
        and settings(s.db)["email/radio"] == "1"
    )
    s.close()
    assert [p.name for p in (tmp_path / "backup").glob("premigrate-*.sqlite")] == [
        f"premigrate-v26-to-v{SCHEMA_VERSION}-20261021-120000.sqlite"
    ], "one copy, of the file as 0.18.2 left it"
