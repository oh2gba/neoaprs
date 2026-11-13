"""Migration 29 (neoaprs/migrationsteps22on.py): `web/allowed_hosts` is checked now, where any text was taken before and the server split it on blanks and commas. A stored value is written again in the form the
check takes, so that every name in it stays allowed: blanks separate as commas do, a port and a dot at the end are dropped, and only what is not a name or an address at all is left out, with a line in the log."""
import logging
from pathlib import Path

import pytest

from neoaprs.config import Config
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw

KEY = "web/allowed_hosts"


def version_twenty_eight(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 28 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 29")
    step_back(db, 28)
    db.execute("PRAGMA user_version = 28")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, str]:
    clock = FixedClock()
    old = folder / DB_NAME
    version_twenty_eight(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 29
    assert [(r[0], r[1], r[2]) for r in migrated.history()][28:] == [(29, "_v29", GOLDEN[29])]
    found = {str(k): str(v) for k, v in migrated.db.execute("SELECT key, value FROM settings")}
    migrated.close()
    return found


@pytest.mark.parametrize(("stored", "now"), [
    ("proxy.example.com nas.lan", "proxy.example.com, nas.lan"),
    ("proxy.example.com, nas.lan:7303", "proxy.example.com, nas.lan"),
    ("x, nas.", "x, nas"),
    ("[::1]:7303 10.0.0.1:80 fe80::1", "[::1], 10.0.0.1, fe80::1"),
    ("pi pi.local pi", "pi, pi.local"),
])
def test_a_value_the_server_took_is_written_in_the_checked_form_and_every_name_in_it_stays_allowed(tmp_path: Path, stored: str, now: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {KEY: stored, "station/call": "OH2GBA"})
    assert found == {KEY: now, "station/call": "OH2GBA"}
    assert Config.from_data(found).web_allowed_hosts == now, "the check takes it, so the daemon starts with it"
    assert f"web/allowed_hosts written in the form that is checked now: {stored!r} → {now!r}" in caplog.text


def test_what_is_not_a_name_or_an_address_is_left_out_and_the_log_names_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {KEY: "nas.lan http://x x/y"})
    assert found == {KEY: "nas.lan"}
    assert "left out, not a name or an address: http://x, x/y" in caplog.text


def test_a_value_of_nothing_but_what_is_not_a_name_is_deleted(tmp_path: Path) -> None:
    assert migrate(tmp_path, {KEY: "http://x", "station/call": "OH2GBA"}) == {"station/call": "OH2GBA"}


@pytest.mark.parametrize("stored", ["aprs.example, pi", "10.0.0.1, pi ,[::1]", "a,b", "my_box"])
def test_a_value_in_the_checked_form_is_not_touched(tmp_path: Path, stored: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        assert migrate(tmp_path, {KEY: stored}) == {KEY: stored}
    assert KEY not in caplog.text


def test_a_database_without_the_row_is_left_alone(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        assert migrate(tmp_path, {"station/call": "OH2GBA"}) == {"station/call": "OH2GBA"}
    assert KEY not in caplog.text
