"""Tests for the radio pair settings (neoaprs/pairsetting.py): `pair/<low>/<high>/enabled` and
`ssid`, their validation on save, the `config` topic, and removal with either radio."""

import logging
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from neoaprs.config import DEFAULTS, Config, SettingError
from neoaprs.dbfile import transaction
from neoaprs.pairsetting import (
    PAIR_FIELDS,
    PairError,
    PairSpec,
    call_of,
    call_refusal,
    changed_rows,
    free_ssid,
    may_pair,
    offered,
    own_calls,
    pair_defaults,
    pair_key,
    pair_key_of,
    pair_of,
    pair_values,
    pairs_from_rows,
    rows_of,
    with_pair_values,
    without_radio,
)
from neoaprs.radioedits import removed
from neoaprs.radiospec import RadioSpec
from neoaprs.radiosql import insert_radio, remove_radio
from neoaprs.store import DB_NAME
from neoaprs.web.confighandlers import split_values, with_pairs
from tests.support.clock import FixedClock
from tests.support.migrated31 import radio_tables
from tests.support.settingsdoc import undescribed
from tests.support.storedb import store_at
from tests.test_radios_wire import added, refused, started

GONE = datetime(2026, 11, 19, tzinfo=UTC)
CALL = "OH2GBA"


def radio(id: int, type: str, removed: bool = False, enabled: bool = True) -> RadioSpec:
    kind = {"dummy-hf": "hf", "mercury": "hf", "dummy-lora": "lora", "lora-console": "lora"}.get(type, "fm")
    return RadioSpec(id, kind, type, "", enabled, id, GONE if removed else None)  # type: ignore[arg-type]


RADIOS = (
    radio(1, "kiss"),
    radio(2, "mercury"),
    radio(3, "dummy"),
    radio(4, "dummy-hf"),
    radio(5, "tnc-text"),
    radio(6, "kiss", removed=True),
    radio(7, "direwolf", enabled=False),
)


def put(values: Mapping[str, str], pairs: tuple[PairSpec, ...] = (), call: str = CALL) -> tuple[PairSpec, ...]:
    return with_pair_values(call, RADIOS, pairs, values)


def refusal(values: Mapping[str, str], pairs: tuple[PairSpec, ...] = (), call: str = CALL) -> PairError:
    with pytest.raises(PairError) as e:
        put(values, pairs, call)
    return e.value


# ---- the keys and the rows


def test_a_pair_key_names_two_radios_low_first_and_a_field_and_any_other_key_is_none() -> None:
    assert (
        pair_key(2, 1, "ssid") == pair_key(1, 2, "ssid") == "pair/1/2/ssid"
        and pair_key_of("pair/1/12/enabled") == (1, 12, "enabled")
        and PAIR_FIELDS == ("enabled", "ssid")
    )
    for key in (
        "pair/2/1/enabled",
        "pair/1/1/ssid",
        "pair/0/2/ssid",
        "pair/01/2/ssid",
        "pair/1/2/call",
        "pair/1/2",
        "pair/1/2/ssid/x",
        "radio/1/path",
        "station/call",
    ):
        assert pair_key_of(key) is None, key


def test_the_rows_are_read_into_pairs_and_a_wrong_value_is_logged_with_its_key_and_has_its_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = {
        "pair/1/2/enabled": "true",
        "pair/1/2/ssid": "12",
        "pair/3/4/enabled": "maybe",
        "pair/3/4/ssid": "16",
        "pair/2/1/ssid": "9",
        "station/call": CALL,
    }
    with caplog.at_level(logging.WARNING, "neoaprs.pairsetting"):
        assert pairs_from_rows(rows) == (PairSpec(1, 2, True, 12), PairSpec(3, 4))
    assert [r.getMessage().split(":")[0] for r in caplog.records] == ["pair/3/4/enabled", "pair/3/4/ssid"]
    assert rows_of(pairs_from_rows(rows)) == {
        "pair/1/2/enabled": "true",
        "pair/1/2/ssid": "12",
        "pair/3/4/enabled": "false",
        "pair/3/4/ssid": "",
    }
    assert changed_rows(
        (PairSpec(1, 2, True, 12),), (PairSpec(1, 2, False, 12), PairSpec(3, 4), PairSpec(5, 7, ssid=3))
    ) == {"pair/1/2/enabled": "false", "pair/5/7/ssid": "3"}, (
        "a pair switched off is written false and its SSID row stays; a new pair at its defaults writes nothing"
    )


def test_the_pair_call_is_the_station_base_call_with_the_pairs_ssid_and_the_own_calls_are_the_station_and_the_enabled_pairs() -> (
    None
):
    assert (call_of("OH2GBA-9", 12), call_of("OH2GBA", None), call_of("", 12), call_of("not a call!", 12)) == (
        "OH2GBA-12",
        "",
        "",
        "",
    )
    pairs = (PairSpec(1, 2, True, 12), PairSpec(1, 3, False, 11), PairSpec(2, 3, True, None))
    assert own_calls("OH2GBA-9", pairs) == ("OH2GBA-9", "OH2GBA-12") and own_calls("", pairs) == ()
    assert (
        pair_of(pairs, 3, 1) == PairSpec(1, 3, False, 11)
        and pair_of(pairs, 4, 1) == PairSpec(1, 4)
        and without_radio(pairs, 3) == (PairSpec(1, 2, True, 12),)
    )


def test_two_live_radios_that_both_send_and_are_both_dummy_or_both_real_may_pair() -> None:
    assert offered(RADIOS) == [(1, 2), (1, 7), (2, 7), (3, 4)], (
        "a removed radio and one that only receives pair with none; a disabled radio may"
    )
    assert (
        not may_pair(RADIOS[0], RADIOS[2])
        and not may_pair(RADIOS[0], RADIOS[0])
        and not may_pair(RADIOS[0], radio(9, "no-such-type"))
    )
    assert list(pair_values(RADIOS, (PairSpec(1, 2, True, 12), PairSpec(1, 6, True, 3)))) == [
        pair_key(*p, f) for p in offered(RADIOS) for f in PAIR_FIELDS
    ]
    assert pair_values(RADIOS, (PairSpec(1, 2, True, 12),))["pair/1/2/ssid"] == "12" and set(
        pair_defaults(RADIOS).values()
    ) == {"false", ""}


# ---- a save


def test_a_pair_switched_on_gets_the_highest_free_ssid_and_a_valid_ssid_sent_is_kept() -> None:
    assert put({"pair/1/2/enabled": "true"}) == (PairSpec(1, 2, True, 15),)
    assert put({"pair/1/2/enabled": "true"}, call="OH2GBA-15") == (PairSpec(1, 2, True, 14),), (
        "the station's SSID is skipped"
    )
    assert put({"pair/1/2/enabled": "true", "pair/1/2/ssid": "12"}) == (PairSpec(1, 2, True, 12),)
    assert (
        put({"pair/1/2/ssid": "12"}) == (PairSpec(1, 2, False, 12),)
        and put({"pair/1/2/ssid": "", "pair/1/2/enabled": "false"}) == ()
    )
    others = (PairSpec(1, 7, True, 15), PairSpec(2, 7, True, 14), PairSpec(3, 4, False, 13))
    assert put({"pair/1/2/enabled": "true"}, others)[0] == PairSpec(1, 2, True, 12), (
        "skipping the other enabled pairs' SSIDs, and by preference the one a pair that is off stores"
    )
    assert put({"pair/1/2/enabled": "true"}, (PairSpec(1, 2, False, 9),))[0].ssid == 9, (
        "a stored SSID that is free is kept"
    )
    assert put({"pair/1/2/enabled": "true"}, (PairSpec(1, 2, False, 9), PairSpec(3, 4, True, 9)))[0].ssid == 15, (
        "a stored SSID another enabled pair has is chosen again"
    )
    assert put({"pair/1/2/enabled": "true", "pair/3/4/enabled": "true"}) == (
        PairSpec(1, 2, True, 15),
        PairSpec(3, 4, True, 14),
    )


def test_a_pair_switched_on_passes_over_the_ssid_a_pair_that_is_off_stores_and_that_pair_keeps_it_when_it_is_switched_on_again() -> (
    None
):
    off = (PairSpec(1, 2, False, 15),)
    both = put({"pair/3/4/enabled": "true"}, off)
    assert both == (PairSpec(1, 2, False, 15), PairSpec(3, 4, True, 14))
    again = put({"pair/1/2/enabled": "true"}, both)
    assert again == (PairSpec(1, 2, True, 15), PairSpec(3, 4, True, 14)), "nothing moves"


def test_a_pair_switched_on_takes_the_ssid_a_pair_that_is_off_stores_when_no_other_is_free() -> None:
    held = tuple(PairSpec(1, 100 + n, True, n) for n in range(1, 15))
    assert put({"pair/1/2/enabled": "true"}, (*held, PairSpec(3, 4, False, 15)))[0].ssid == 15


def test_an_ssid_that_is_no_value_the_stations_own_or_another_pairs_is_refused_under_its_key() -> None:
    for text, code in (("0", "setting.range"), ("16", "setting.range"), ("x", "setting.not_whole")):
        e = refusal({"pair/1/2/ssid": text})
        assert (e.key, e.code) == ("pair/1/2/ssid", code), text
    assert refusal({"pair/1/2/ssid": "16"}).params == {"value": 16, "min": 1, "max": 15}
    e = refusal({"pair/1/2/enabled": "maybe"})
    assert (e.key, e.code, e.params) == ("pair/1/2/enabled", "setting.not_boolean", {"value": "maybe"})
    e = refusal({"pair/1/2/enabled": "true", "pair/1/2/ssid": "9"}, call="OH2GBA-9")
    assert (e.key, e.code, e.params, str(e)) == (
        "pair/1/2/ssid",
        "pair.call_is_station",
        {"call": "OH2GBA-9"},
        "pair/1/2/ssid: OH2GBA-9 is the station's own call",
    )
    e = refusal({"pair/1/2/ssid": "12"}, (PairSpec(1, 2, True, 15), PairSpec(3, 4, True, 12)))
    assert (e.key, e.code, e.params, str(e)) == (
        "pair/1/2/ssid",
        "pair.call_taken",
        {"call": "OH2GBA-12"},
        "pair/1/2/ssid: OH2GBA-12 is the call of another pair",
    )
    assert put({"pair/1/2/ssid": "12"}, (PairSpec(3, 4, True, 12),)) == (
        PairSpec(1, 2, False, 12),
        PairSpec(3, 4, True, 12),
    ), "a disabled pair's SSID is not checked"
    assert put({"pair/1/2/enabled": "true", "pair/1/2/ssid": "12"}, (PairSpec(3, 4, False, 12),))[0] == PairSpec(
        1, 2, True, 12
    ), "a disabled pair's SSID reserves nothing"


def test_a_pair_switched_on_with_no_free_ssid_is_refused_under_its_enable() -> None:
    full = tuple(PairSpec(10 + ssid, 40 + ssid, True, ssid) for ssid in range(1, 15))
    e = refusal({"pair/1/2/enabled": "true"}, full, call="OH2GBA-15")
    assert (e.key, e.code, e.params, str(e)) == (
        "pair/1/2/enabled",
        "pair.no_free_call",
        {},
        "pair/1/2/enabled: every SSID from 1 to 15 is taken",
    )
    assert (
        free_ssid("OH2GBA-15", full, (1, 2)) is None
        and free_ssid("OH2GBA", full, (1, 2)) == 15
        and free_ssid("OH2GBA", full, (11, 41)) == 15
    )


def test_a_pair_of_a_radio_that_only_receives_or_of_a_dummy_and_a_real_radio_is_refused() -> None:
    e = refusal({"pair/1/5/enabled": "true"})
    assert (e.key, e.code, e.params, str(e)) == (
        "pair/1/5/enabled",
        "pair.receive_only",
        {"name": "FM 3"},
        "pair/1/5/enabled: radio FM 3 only receives",
    )
    e = refusal({"pair/1/3/ssid": "4"})
    assert (e.key, e.code, e.params, str(e)) == (
        "pair/1/3/ssid",
        "pair.dummy_and_real",
        {},
        "pair/1/3/ssid: a Dummy radio and a real one make no pair",
    )


def test_a_save_never_changes_a_pair_it_does_not_name() -> None:
    clash = (PairSpec(1, 2, True, 12), PairSpec(3, 4, True, 12))
    assert put({"pair/1/7/enabled": "true"}, clash) == (
        PairSpec(1, 2, True, 12),
        PairSpec(1, 7, True, 15),
        PairSpec(3, 4, True, 12),
    ), "a stored clash from before stays until the operator chooses"
    assert put({}, clash) == clash


def test_a_pair_that_keeps_its_stored_ssid_is_not_moved_by_a_save_that_takes_that_ssid_and_a_save_that_takes_it_is_refused() -> (
    None
):
    held = (PairSpec(1, 2, True, 12),)
    e = refusal({"pair/1/2/enabled": "true", "pair/3/4/enabled": "true", "pair/3/4/ssid": "12"}, held)
    assert (e.key, e.code, e.params) == ("pair/3/4/ssid", "pair.call_taken", {"call": "OH2GBA-12"})
    assert put({"pair/1/2/enabled": "true", "pair/3/4/enabled": "true"}, held) == (
        PairSpec(1, 2, True, 12),
        PairSpec(3, 4, True, 15),
    )
    with pytest.raises(SettingError) as raised:
        checked_pairs(
            {"station/call": "OH2GBA-15", "pair/1/2/enabled": "true"}, config_with((PairSpec(1, 2, True, 15),))
        )
    assert (raised.value.key, raised.value.code, raised.value.params) == (
        "station/call",
        "setting.call_of_pair",
        {"call": "OH2GBA-15"},
    )
    assert put({"pair/1/2/enabled": "true"}, (PairSpec(1, 2, True, 15),), "OH2GBA-15") == (PairSpec(1, 2, True, 14),), (
        "a stored clash with the station's call from before is chosen again"
    )
    both = (PairSpec(1, 2, False, 12), PairSpec(3, 4, False, 12))
    assert put({"pair/1/2/enabled": "true", "pair/3/4/enabled": "true"}, both) == (
        PairSpec(1, 2, True, 12),
        PairSpec(3, 4, True, 15),
    ), "two pairs switched on with one stored SSID: the first keeps it"


def test_an_ssid_sent_empty_for_a_pair_that_stays_enabled_keeps_the_stored_one_and_clears_it_when_the_pair_is_switched_off() -> (
    None
):
    stored = (PairSpec(1, 2, False, 12),)
    assert (
        put({"pair/1/2/enabled": "true", "pair/1/2/ssid": ""}, stored)
        == put({"pair/1/2/enabled": "true"}, stored)
        == (PairSpec(1, 2, True, 12),)
    )
    assert put({"pair/1/2/enabled": "true", "pair/1/2/ssid": ""}) == (PairSpec(1, 2, True, 15),)
    assert put({"pair/1/2/enabled": "false", "pair/1/2/ssid": ""}, (PairSpec(1, 2, True, 12),)) == (
        PairSpec(1, 2, False, None),
    )


def test_a_key_that_is_no_pair_key_is_refused_and_the_refusals_come_in_the_order_of_the_table() -> None:
    e = refusal({"station/comment": "5"})
    assert (e.key, e.code, e.params) == ("station/comment", "setting.unknown", {})
    e = refusal({"pair/1/2/ssid": "16", "pair/1/5/enabled": "true"})
    assert (e.key, e.code) == ("pair/1/5/enabled", "pair.receive_only"), (
        "a radio's refusal comes before a value's, whatever order the keys were sent in"
    )
    e = refusal({"pair/1/2/ssid": "16", "pair/1/2/enabled": "maybe"})
    assert (e.key, e.code) == ("pair/1/2/ssid", "setting.range"), "values are judged in the order sent"


def test_a_station_call_that_takes_an_enabled_pairs_ssid_is_refused_under_station_call() -> None:
    pairs = (PairSpec(1, 2, True, 12), PairSpec(3, 4, False, 11))
    error = call_refusal("OH2GBA-12", pairs)
    assert error is not None and (error.key, error.code, error.params, str(error)) == (
        "station/call",
        "setting.call_of_pair",
        {"call": "OH2GBA-12"},
        "station/call: OH2GBA-12 is the call of a pair of your radios",
    )
    assert (
        call_refusal("OH2GBA-11", pairs) is None
        and call_refusal("OH2GBA", pairs) is None
        and call_refusal("", pairs) is None
    )


# ---- the settings: Config and set_config's helpers


def config_with(pairs: tuple[PairSpec, ...]) -> Config:
    return replace(DEFAULTS, radios=RADIOS, station_call=CALL, pairs=pairs)


def test_a_save_of_another_setting_keeps_the_pairs_and_writes_no_pair_row() -> None:
    base = config_with((PairSpec(1, 2, True, 12),))
    after = Config.checked(base, {"station/comment": "only this"})
    assert (
        after.pairs == base.pairs
        and after.station_comment == "only this"
        and changed_rows(base.pairs, after.pairs) == {}
    )
    assert (
        Config.from_data({**base.to_data(), **rows_of(base.pairs)}, radios=RADIOS).pairs == base.pairs
        and Config.from_data(rows_of(base.pairs)).pairs == ()
    ), "read only once the radios are stored"


def test_the_values_are_split_three_ways_and_a_key_that_is_no_pair_key_goes_to_the_settings_which_refuse_it() -> None:
    assert split_values({"station/call": CALL, "radio/1/path": "", "pair/1/2/ssid": "3", "pair/2/1/ssid": "3"}) == (
        {"station/call": CALL, "pair/2/1/ssid": "3"},
        {"radio/1/path": ""},
        {"pair/1/2/ssid": "3"},
    )
    for key in ("pair/2/1/enabled", "pair/1/1/enabled", "pair/1/2/call"):
        with pytest.raises(SettingError) as e:
            Config.checked(config_with(()), split_values({key: "true"})[0])
        assert (e.value.key, e.value.code, e.value.params) == (
            key,
            "setting.unknown",
            {},
        ) and f"{key}: no such setting (the settings are " in str(e.value), key


def checked_pairs(values: dict[str, str], base: Config | None = None) -> Config:
    base = base or config_with(())
    flat, own, pairs = split_values(values)
    return with_pairs(base, Config.checked(base, flat), pairs, flat)


def test_with_pairs_refuses_a_radio_that_is_none_or_removed_as_no_radio_and_makes_a_setting_error_of_a_pairs_refusal() -> (
    None
):
    with pytest.raises(SettingError) as e:
        checked_pairs({"pair/1/6/enabled": "true"})
    assert (e.value.key, e.value.code, e.value.params) == (
        "pair/1/6/enabled",
        "radio.unknown",
        {"radio": 6, "name": "FM 5", "removed": 1},
    )
    with pytest.raises(SettingError) as e:
        checked_pairs({"pair/1/9/ssid": "3"})
    assert (e.value.key, e.value.code, e.value.params, str(e.value)) == (
        "pair/1/9/ssid",
        "radio.unknown",
        {"radio": 9},
        "pair/1/9/ssid: there is no radio 9",
    )
    with pytest.raises(SettingError) as e:
        checked_pairs({"pair/1/3/ssid": "3"})
    assert (e.value.key, e.value.code) == ("pair/1/3/ssid", "pair.dummy_and_real")
    with pytest.raises(SettingError) as e:
        checked_pairs({"station/call": "OH2GBA-12"}, config_with((PairSpec(1, 2, True, 12),)))
    assert (e.value.key, e.value.code, e.value.params) == (
        "station/call",
        "setting.call_of_pair",
        {"call": "OH2GBA-12"},
    )
    assert checked_pairs({"station/call": "OH2GBA-15", "pair/1/2/enabled": "true"}).pairs == (
        PairSpec(1, 2, True, 14),
    ), "the call sent in the same save is the station's"
    assert checked_pairs({"pair/1/7/enabled": "true"}).pairs == (PairSpec(1, 7, True, 15),), (
        "a disabled radio's pair may be set"
    )


def test_a_removed_radio_takes_its_pairs_out_of_the_settings_in_force() -> None:
    config = config_with((PairSpec(1, 2, True, 12), PairSpec(2, 7, True, 11), PairSpec(3, 4, True, 10)))
    assert removed(config, RADIOS[1], GONE).pairs == (PairSpec(3, 4, True, 10),)


def test_every_field_of_a_pair_is_described_in_the_settings_document() -> None:
    assert not [key for key in undescribed() if key.startswith("pair/")]


# ---- the database


def test_remove_takes_away_the_rows_of_every_pair_of_the_radio_and_no_other(tmp_path: Path) -> None:
    radio_tables(tmp_path / DB_NAME, FixedClock())
    db = sqlite3.connect(tmp_path / DB_NAME, isolation_level=None)
    for type in ("kiss", "mercury", "dummy"):
        insert_radio(db, "fm", type, "", True, 1)
    rows = {
        "pair/1/2/enabled": "true",
        "pair/1/2/ssid": "12",
        "pair/2/3/ssid": "11",
        "pair/1/3/ssid": "10",
        "pair/1/12/ssid": "9",
        "pair/12/20/ssid": "8",
        "radio/12/path": "x",
    }
    db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", rows.items())
    assert transaction(db, lambda conn: remove_radio(conn, 2, "2026-11-19T00:00:00.000000Z")) == 1
    assert dict(db.execute("SELECT key, value FROM settings").fetchall()) == {
        "pair/1/3/ssid": "10",
        "pair/1/12/ssid": "9",
        "pair/12/20/ssid": "8",
        "radio/12/path": "x",
    }
    db.close()


async def test_a_late_write_of_a_removed_radios_pair_is_not_stored(tmp_path: Path) -> None:
    radio_tables(tmp_path / DB_NAME, FixedClock())
    store = await store_at(tmp_path / DB_NAME, FixedClock())
    assert (
        await store.add_radio("fm", "dummy", "", True, 1) == 1
        and await store.add_radio("hf", "dummy-hf", "", True, 2) == 2
    )
    assert await store.put_settings({"pair/1/2/enabled": "true"}) and await store.remove_radio(2)
    assert not await store.put_settings({"pair/1/2/ssid": "12"}) and not await store.put_setting(
        "pair/1/2/enabled", "true"
    )
    assert not [key for key in await store.settings() if key.startswith("pair/")] and await store.put_setting(
        "pair/1/3/ssid", "4"
    ), "a pair of a radio with no row is not a removed one's"


# ---- through the page


async def config_of(page: Any, values: dict[str, str], told: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """The topic `config` once the save is told in it."""
    await page.send({"cmd": "set_config", "values": values})
    await page.until(lambda: told(page.topics["config"]))
    return dict(page.topics["config"])


async def test_through_the_page_a_pair_is_offered_set_refused_kept_and_survives_a_restart(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"tnc/profile": "dummy"})
    hf = await added(page, "dummy-hf")
    real = await added(page, "kiss")
    monitor = await added(page, "tnc-text")
    config = page.topics["config"]
    assert [k for k in config["radio_values"] if k.startswith("pair/")] == [
        f"pair/1/{hf}/enabled",
        f"pair/1/{hf}/ssid",
    ], "only the radios that may pair: none of the real or receive-only radio"
    assert (config["radio_values"][f"pair/1/{hf}/enabled"], config["radio_defaults"][f"pair/1/{hf}/ssid"]) == (
        "false",
        "",
    )
    for values, key, code, params in (
        ({f"pair/1/{real}/enabled": "true"}, f"pair/1/{real}/enabled", "pair.dummy_and_real", {}),
        (
            {f"pair/{real}/{monitor}/enabled": "true"},
            f"pair/{real}/{monitor}/enabled",
            "pair.receive_only",
            {"name": "FM 3"},
        ),
        ({f"pair/1/{hf}/ssid": "16"}, f"pair/1/{hf}/ssid", "setting.range", {"value": 16, "min": 1, "max": 15}),
        ({f"pair/{hf}/1/ssid": "3"}, f"pair/{hf}/1/ssid", "setting.unknown", {}),
    ):
        error = await refused(page, {"cmd": "set_config", "values": {**values, "station/comment": "not stored"}})
        assert (error["code"], error["key"], error["params"]) == (code, key, params), key
    assert e.ctl.config.pairs == () and e.ctl.config.station_comment != "not stored"

    config = await config_of(
        page, {f"pair/1/{hf}/enabled": "true"}, lambda c: c["radio_values"][f"pair/1/{hf}/enabled"] == "true"
    )
    assert (config["radio_values"][f"pair/1/{hf}/enabled"], config["radio_values"][f"pair/1/{hf}/ssid"]) == (
        "true",
        "15",
    ) and e.ctl.config.pairs == (PairSpec(1, hf, True, 15),)
    error = await refused(page, {"cmd": "set_config", "values": {"station/call": "OH2GBA-15"}})
    assert (error["code"], error["key"], error["params"]) == (
        "setting.call_of_pair",
        "station/call",
        {"call": "OH2GBA-15"},
    )
    await config_of(page, {"station/comment": "kept"}, lambda c: c["values"]["station/comment"] == "kept")
    assert e.ctl.config.pairs == (PairSpec(1, hf, True, 15),), "a save of another setting keeps the pair"
    await e.stop()

    db = sqlite3.connect(tmp_path / DB_NAME)
    assert dict(db.execute("SELECT key, value FROM settings WHERE key GLOB 'pair/*'").fetchall()) == {
        f"pair/1/{hf}/enabled": "true",
        f"pair/1/{hf}/ssid": "15",
    }
    db.close()
    again, page = await started(tmp_path)
    assert (
        again.ctl.config.pairs == (PairSpec(1, hf, True, 15),)
        and page.topics["config"]["radio_values"][f"pair/1/{hf}/ssid"] == "15"
    ), "read back after a restart"
    await page.send({"cmd": "radio_remove", "radio": hf})
    await page.until(lambda: not [k for k in page.topics["config"]["radio_values"] if k.startswith("pair/")])
    assert again.ctl.config.pairs == ()
    error = await refused(page, {"cmd": "set_config", "values": {f"pair/1/{hf}/enabled": "true"}})
    assert (error["code"], error["key"], error["params"]["removed"]) == ("radio.unknown", f"pair/1/{hf}/enabled", 1)
    await again.stop()
    db = sqlite3.connect(tmp_path / DB_NAME)
    assert not db.execute("SELECT key FROM settings WHERE key GLOB 'pair/*'").fetchall(), "the rows went with the radio"
    db.close()
