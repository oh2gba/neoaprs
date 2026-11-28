"""Migration 16 (neoaprs/migrationsteps12to21.py): the settings that are no longer on the page go
back to their defaults once, rows of settings that no longer exist are deleted, and everything else
is as it was. The settings are stored as version 15 kept them and read back where the newest
migration leaves them.
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS, KEYS, STATION_KEYS, Config
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.support.migrated31 import OWN_31, STATE_31, flat_row, has_table, state_row, station_rows, stored_config
from tests.test_migrations import GOLDEN, raw

RESET = {
    "map/maxzoom": "14",
    "map/source": "https://example.org/world.pmtiles",
    "update/url": "http://localhost:9/v.php",
    "serial/pattern": "/dev/ttyS*",
    "serial/skip": "/dev/brainbox_2,/dev/ttyUSB3",
}
REMOVED = [
    "messages/attempts",
    "log/keep_days",
    "update/check",
    "tnc/check_sec",
    "tnc/watchdog_min",
    "map/hide_after_min",
    "beacon/destination",
    "beacon/compressed",
    "beacon/dao",
]
KEPT = {
    "station/call": "OH2GBA",
    "station/transmit": "false",
    "station/main_radio": "2",
    "email/radio": "2",
    "station/lat": "60.17",
    "station/lon": "24.94",
    "station/symbol_table": "\\",
    "station/symbol_code": ">",
    "station/comment": "odd comment",
    "station/status": "hello",
    "tnc/profile": "kenwood-tnc2",
    "serial/port": "/dev/ttyUSB7",
    "serial/baud": "19200",
    "serial/last_port": "/dev/ttyUSB7",
    "tcp/host": "10.0.0.5",
    "tcp/port": "8100",
    "fm/enabled": "false",
    "hf/enabled": "true",
    "hf/profile": "dummy-hf",
    "mercury/sound_card": "plughw:2,0",
    "mercury/keying": "rts:/dev/ttyUSB3",
    "mercury/tx_gain_db": "-3",
    "beacon/interval_min": "45",
    "beacon/path": "WIDE2-2",
    "beacon/power_w": "25",
    "beacon/antenna_height_m": "12",
    "beacon/antenna_gain_db": "3",
    "beacon/antenna_direction": "NE",
    "web/network": "true",
    "web/key": "k7m2-x9pq-4hrt",
    "web/https": "true",
    "web/port": "7777",
    "web/allowed_hosts": "radio.lan,shack",
    "web/proxy": "true",
    "messages/alert": "false",
    "messages/chat_alert": "false",
    "messages/alert_command": "echo hi",
    "status/source": "rig",
    "status/rigctld": "127.0.0.1:4532",
    "status/interval_min": "60",
    "status/template": "{freq}",
    "map/radius_km": "300",
    "map/station_hours": "12",
    "map/aircraft": "receiver",
    "map/aircraft_host": "pi.local:8080",
    "map/ships": "fintraffic",
    "map/ships_host": "ais.local:2000",
    "map/ships_key": "0123456789abcdef0123456789abcdef01234567",
    "units/non_metric": "true",
    "digi/enabled": "true",
    "igate/enabled": "true",
    "igate/gate": "true",
    "igate/show_gated": "false",
    "igate/server": "euro.aprs2.net:14580",
    "igate/password": "19628",
    "gps/source": "gpsd",
    "gps/host": "10.0.0.7:2947",
    "gps/device": "/dev/ttyUSB1",
    "gps/baud": "9600",
    "beacon/travel": "boat",
    "tnc/enter_kiss": "true",
    "web/bind": "0.0.0.0",
    "beacon/last_sent_at": "2026-10-23T10:00:00Z",
    "status/last_sent_at": "2026-10-23T10:00:00Z",
    "status/last_text": "on 145.800",
}


def version_fifteen(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 15 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 16")
    step_back(db, 15)
    db.execute("PRAGMA user_version = 15")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


@contextmanager
def migrate(folder: Path, stored: dict[str, str]) -> Iterator[sqlite3.Connection]:
    """The database of a version 15 with these settings, brought up to date: every step from 16 on
    ran, each the frozen one."""
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_fifteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 16
    assert [(r[0], r[1], r[2]) for r in migrated.history()][15:] == [
        (number, f"_v{number}", GOLDEN[number]) for number in range(16, SCHEMA_VERSION + 1)
    ]
    try:
        yield migrated.db
    finally:
        migrated.close()


def rows_of(db: sqlite3.Connection) -> dict[str, tuple[str, int]]:
    """Every row of the settings table: key to (value, revision)."""
    return {str(k): (str(v), int(rev)) for k, v, rev in db.execute("SELECT key, value, rev FROM settings")}


# today's flat keys of the radios (and the last port the search found): read back through the
# settings in force
RADIOS = [key for key in KEYS if key not in STATION_KEYS]
STATE = ["beacon/last_sent_at", "status/last_sent_at", "status/last_text"]


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_the_settings_off_the_page_go_back_to_the_defaults_and_the_removed_rows_are_gone(tmp_path: Path) -> None:
    with migrate(tmp_path, {**RESET, **KEPT, **{key: "7" for key in REMOVED}}) as db:
        found, config = rows_of(db), stored_config(db)
        assert not set(RESET) & found.keys() and not set(REMOVED) & found.keys(), (
            "the rows are deleted, the default is in force"
        )
        assert station_rows(db) == {key: (value, 1) for key, value in KEPT.items() if key in STATION_KEYS}, (
            "every row of the station is as it was, revision included"
        )
        assert {key: config.to_data()[key] for key in RADIOS} == {key: KEPT[key] for key in RADIOS}, (
            "and so is every setting of the radios, read through the radios"
        )
        assert {key: state_row(db, key) for key in STATE} == {key: (KEPT[key], 1) for key in STATE} and found[
            "web/bind"
        ] == ("0.0.0.0", 1), "the daemon's own rows and the row of an older version too"
        assert {key: flat_row(db, key) for key in OWN_31} == {key: (KEPT[key], 1) for key in OWN_31}, (
            "each radio's own setting with the revision it had, wherever it is kept"
        )
        radios = has_table(db, "radio")
        # Once the radios are rows: their rows, moved or written as the radios' columns; and the
        # main radio, which migration 34 deletes
        gone = ((set(RADIOS) | {"tnc/enter_kiss"}) - set(STATE_31) | {"station/main_radio"}) if radios else set()
        # What a new object and a new bulletin start with, which migration 34 writes where several
        # radios send
        step_34 = {key for key in found if key in ("objects/send_on", "bulletins/send_on")} if radios else set()
        assert found.keys() - step_34 == {
            STATE_31.get(key, key) if radios else key for key in KEPT if key not in gone
        }, "nothing else is in the table, and nothing of it is lost"
        assert config.tnc_profile == "kenwood-tnc2", "the type that was chosen stands, whatever tnc/enter_kiss said"
    for attr in ("map_maxzoom", "map_source", "update_url", "serial_pattern", "serial_skip"):
        assert getattr(config, attr) == getattr(DEFAULTS, attr)
    assert config.web_port == 7777 and config.web_allowed_hosts == "radio.lan,shack" and config.map_radius_km == 300


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_every_setting_that_is_not_reset_is_kept(tmp_path: Path) -> None:
    assert set(KEYS) - set(RESET) <= KEPT.keys(), "the test holds an odd value for every setting that stays"
    stored = {key: KEPT[key] for key in KEYS if key in KEPT}
    with migrate(tmp_path, stored) as db:
        assert {key: value for key, (value, _) in station_rows(db).items()} == {
            key: value for key, value in stored.items() if key in STATION_KEYS
        }
        assert {key: value for key, value in stored_config(db).to_data().items() if key in stored} == stored, (
            "the station's and the radios' alike are in force as they were stored"
        )


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_a_value_that_is_already_the_default_is_deleted_without_a_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        with migrate(
            tmp_path,
            {
                "map/maxzoom": "12",
                "map/source": "",
                "update/url": "https://oh2gba.eu/neoaprs/version.php",
                "serial/pattern": "/dev/serial/by-id/*  /dev/ttyUSB* /dev/ttyACM*",
                "serial/skip": "",
            },
        ) as db:
            assert rows_of(db) == {}
    assert not [r for r in caplog.records if "reset to the default" in r.getMessage()]


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_one_info_line_for_each_key_reset_with_the_old_value(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        with migrate(tmp_path, {**RESET, "station/call": "OH2GBA"}):
            pass
    lines = [
        r.getMessage() for r in caplog.records if "reset to the default" in r.getMessage() and r.levelno == logging.INFO
    ]
    assert lines == [
        "map/maxzoom reset to the default: 14 → 12",
        "map/source reset to the default: https://example.org/world.pmtiles → (empty)",
        "update/url reset to the default: http://localhost:9/v.php → https://oh2gba.eu/neoaprs/version.php",
        "serial/pattern reset to the default: /dev/ttyS* → /dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*",
        "serial/skip reset to the default: /dev/brainbox_2,/dev/ttyUSB3 → (empty)",
    ]


@pytest.mark.slow("runs the migrations on database files of old versions")
def test_a_database_with_no_such_rows_is_as_it_was(tmp_path: Path) -> None:
    with migrate(tmp_path, {"station/call": "OH2GBA"}) as db:
        assert rows_of(db) == {"station/call": ("OH2GBA", 1)}


def test_a_new_database_has_no_rows_to_reset(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    assert not set(RESET) & {str(r[0]) for r in s.db.execute("SELECT key FROM settings")}
    s.close()


def test_a_removed_setting_that_is_stored_is_ignored_and_cannot_be_set() -> None:
    assert Config.from_data({key: "7" for key in REMOVED}) == DEFAULTS
    for key in REMOVED:
        with pytest.raises(ValueError, match=f"{key}: no such setting"):
            Config.check(key, "7")
