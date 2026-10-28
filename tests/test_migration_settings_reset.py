"""Migration 16 (neoaprs/migrationsteps12to21.py): the settings that are no longer on the page (`map/maxzoom`, `map/source`, `update/url`, `serial/pattern`, `serial/skip`) go back to their defaults once, the rows of the
settings that no longer exist are deleted, and everything else (the page's settings, `web/port`, `web/allowed_hosts`, the state of the daemon) is as it was."""
import logging
from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS, KEYS, Config
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw

RESET = {"map/maxzoom": "14", "map/source": "https://example.org/world.pmtiles", "update/url": "http://localhost:9/v.php",
         "serial/pattern": "/dev/ttyS*", "serial/skip": "/dev/brainbox_2,/dev/ttyUSB3"}
REMOVED = ["messages/attempts", "log/keep_days", "update/check", "tnc/check_sec", "tnc/watchdog_min", "map/hide_after_min", "beacon/destination", "beacon/compressed", "beacon/dao"]
KEPT = {"station/call": "OH2GBA", "station/transmit": "false", "station/lat": "60.17", "station/lon": "24.94", "station/symbol_table": "\\", "station/symbol_code": ">", "station/comment": "odd comment",
        "station/status": "hello", "tnc/profile": "kenwood-tnc2", "serial/port": "/dev/ttyUSB7", "serial/baud": "19200", "serial/last_port": "/dev/ttyUSB7", "tcp/host": "10.0.0.5", "tcp/port": "8100",
        "beacon/interval_min": "45", "beacon/path": "WIDE2-2", "beacon/power_w": "25", "beacon/antenna_height_m": "12", "beacon/antenna_gain_db": "3", "beacon/antenna_direction": "NE",
        "web/network": "true", "web/key": "k7m2-x9pq-4hrt", "web/https": "true", "web/port": "7777", "web/allowed_hosts": "radio.lan,shack",
        "messages/alert": "false", "messages/alert_command": "echo hi", "status/source": "rig", "status/rigctld": "127.0.0.1:4532", "status/interval_min": "60", "status/template": "{freq}",
        "map/radius_km": "300", "map/station_hours": "12", "digi/enabled": "true", "igate/enabled": "true", "igate/server": "euro.aprs2.net:14580", "igate/password": "19628",
        "gps/source": "gpsd", "gps/host": "10.0.0.7:2947", "gps/device": "/dev/ttyUSB1", "gps/baud": "9600", "beacon/travel": "boat",
        "tnc/enter_kiss": "true", "web/bind": "0.0.0.0", "beacon/last_sent_at": "2026-10-23T10:00:00Z", "status/last_sent_at": "2026-10-23T10:00:00Z", "status/last_text": "on 145.800"}


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


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, tuple[str, int]]:
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_fifteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 16
    assert [(r[0], r[1], r[2]) for r in migrated.history()][15:] == [(16, "_v16", GOLDEN[16]), (17, "_v17", GOLDEN[17]), (18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19]), (20, "_v20", GOLDEN[20]), (21, "_v21", GOLDEN[21]), (22, "_v22", GOLDEN[22])]
    found = {str(k): (str(v), int(rev)) for k, v, rev in migrated.db.execute("SELECT key, value, rev FROM settings")}
    migrated.close()
    return found


def test_the_settings_off_the_page_go_back_to_the_defaults_and_the_removed_rows_are_gone(tmp_path: Path) -> None:
    found = migrate(tmp_path, {**RESET, **KEPT, **{key: "7" for key in REMOVED}})
    assert not set(RESET) & found.keys() and not set(REMOVED) & found.keys(), "the rows are deleted, the default is in force"
    assert {key: found[key] for key in KEPT} == {key: (value, 1) for key, value in KEPT.items()}, "everything else is as it was, revision included"
    assert found.keys() == KEPT.keys()
    config = Config.from_data({key: value for key, (value, _) in found.items()})
    for attr in ("map_maxzoom", "map_source", "update_url", "serial_pattern", "serial_skip"):
        assert getattr(config, attr) == getattr(DEFAULTS, attr)
    assert config.web_port == 7777 and config.web_allowed_hosts == "radio.lan,shack" and config.map_radius_km == 300


def test_every_setting_that_is_not_reset_is_kept(tmp_path: Path) -> None:
    assert set(KEYS) - set(RESET) <= KEPT.keys(), "the test holds an odd value for every setting that stays"
    found = migrate(tmp_path, {key: KEPT[key] for key in KEYS if key in KEPT})
    assert {key: value for key, (value, _) in found.items()} == {key: KEPT[key] for key in KEYS if key in KEPT}


def test_a_value_that_is_already_the_default_is_deleted_without_a_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {"map/maxzoom": "12", "map/source": "", "update/url": "https://oh2gba.eu/neoaprs/version.php", "serial/pattern": "/dev/serial/by-id/*  /dev/ttyUSB* /dev/ttyACM*", "serial/skip": ""})
    assert found == {}
    assert not [r for r in caplog.records if "reset to the default" in r.getMessage()]


def test_one_info_line_for_each_key_reset_with_the_old_value(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        migrate(tmp_path, {**RESET, "station/call": "OH2GBA"})
    lines = [r.getMessage() for r in caplog.records if "reset to the default" in r.getMessage() and r.levelno == logging.INFO]
    assert lines == ["map/maxzoom reset to the default: 14 → 12",
                     "map/source reset to the default: https://example.org/world.pmtiles → (empty)",
                     "update/url reset to the default: http://localhost:9/v.php → https://oh2gba.eu/neoaprs/version.php",
                     "serial/pattern reset to the default: /dev/ttyS* → /dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*",
                     "serial/skip reset to the default: /dev/brainbox_2,/dev/ttyUSB3 → (empty)"]


def test_a_database_with_no_such_rows_is_as_it_was(tmp_path: Path) -> None:
    assert migrate(tmp_path, {"station/call": "OH2GBA"}) == {"station/call": ("OH2GBA", 1)}


def test_a_new_database_has_no_rows_to_reset(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    assert not set(RESET) & {str(r[0]) for r in s.db.execute("SELECT key FROM settings")}
    s.close()


def test_a_removed_setting_that_is_stored_is_ignored_and_cannot_be_set() -> None:
    assert Config.from_data({key: "7" for key in REMOVED}) == DEFAULTS
    for key in REMOVED:
        with pytest.raises(ValueError, match=f"{key}: no such setting"):
            Config.check(key, "7")
