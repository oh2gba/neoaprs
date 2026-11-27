"""Migration 37 (neoaprs/migrationsteps37.py): a station that gated keeps gating. Internet stations on
with a passcode set by hand gets Send what I hear; any other station gets no row, and a row already
there is left alone.
"""

import sqlite3
from pathlib import Path

import pytest

from neoaprs.config import Config
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationsteps37 import _v37
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw

KEYS = ("igate/enabled", "igate/password", "igate/gate")


def version_36(path: Path, rows: dict[str, str]) -> None:
    """A database at version 36 with these iGate rows stored and no others."""
    opened(path, FixedClock()).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 37")
    step_back(db, 36)
    db.execute("PRAGMA user_version = 36")
    db.executemany("DELETE FROM settings WHERE key = ?", [(key,) for key in KEYS])
    db.executemany("INSERT INTO settings (key, value, rev) VALUES (?, ?, 1)", rows.items())
    db.close()


def stored(path: Path) -> dict[str, str]:
    db = sqlite3.connect(path)
    try:
        return dict(db.execute("SELECT key, value FROM settings WHERE key LIKE 'igate/%'").fetchall())
    finally:
        db.close()


@pytest.mark.parametrize(
    ("was", "gate"),
    [
        ({"igate/enabled": "true", "igate/password": "19628"}, "true"),
        ({"igate/enabled": "1", "igate/password": " 12345 "}, "true"),
        ({"igate/enabled": "true"}, None),
        ({"igate/enabled": "true", "igate/password": ""}, None),
        ({"igate/enabled": "false", "igate/password": "19628"}, None),
        ({"igate/password": "19628"}, None),
        ({}, None),
        ({"igate/enabled": "true", "igate/password": "19628", "igate/gate": "false"}, "false"),
    ],
)
def test_internet_stations_on_with_a_passcode_set_by_hand_gets_send_what_i_hear_and_nothing_else_changes(
    tmp_path: Path, was: dict[str, str], gate: str | None
) -> None:
    path = tmp_path / DB_NAME
    version_36(path, was)
    s = opened(path, FixedClock())
    assert s.version() == SCHEMA_VERSION and (37, "_v37", GOLDEN[37]) in [(r[0], r[1], r[2]) for r in s.history()]
    s.close()
    now = stored(path)
    assert now.get("igate/gate") == gate
    assert {key: value for key, value in now.items() if key != "igate/gate"} == {
        key: value for key, value in was.items() if key != "igate/gate"
    }, "the other rows are as they were"


def test_a_station_that_gated_gates_as_before_and_one_that_only_showed_still_only_shows(tmp_path: Path) -> None:
    for rows, show, gate in (
        ({"igate/enabled": "true", "igate/password": "19628"}, True, True),
        ({"igate/enabled": "true"}, True, False),
    ):
        path = tmp_path / f"{gate}" / DB_NAME
        path.parent.mkdir()
        version_36(path, rows)
        opened(path, FixedClock()).close()
        config = Config.from_data(stored(path))
        assert (config.igate_enabled, config.igate_gate) == (show, gate)


def test_a_second_start_changes_nothing_and_the_step_says_what_it_did_in_one_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / DB_NAME
    version_36(path, {"igate/enabled": "true", "igate/password": "19628"})
    opened(path, FixedClock()).close()
    opened(path, FixedClock()).close()
    assert stored(path)["igate/gate"] == "true"
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, rev INTEGER NOT NULL)")
    db.executemany("INSERT INTO settings VALUES (?, ?, 1)", [("igate/enabled", "true"), ("igate/password", "1")])
    with caplog.at_level("INFO"):
        _v37(db)
    assert [r.getMessage() for r in caplog.records] == [
        "the iGate gated with a passcode set by hand: Send what I hear is on"
    ]
