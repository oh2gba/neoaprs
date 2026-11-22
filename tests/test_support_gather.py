"""The parts of the support bundle that read the computer and database
(neoaprs/cli/supportgather.py) beyond the whole-bundle tests: the system name per system, an
unreadable log, a start line with no time, unknown migrations.
"""
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from neoaprs.cli import supportgather, systemdescription
from neoaprs.config import DEFAULTS
from neoaprs.cli.logfile import START_LINE
from neoaprs.migrations import MIGRATIONS, source_hash
from neoaprs.packetcodec import PacketRow
from neoaprs.store import DB_NAME
from tests.support.migrated import opened
from tests.support.migrated31 import at_thirty


def row_of(raw: bytes, source: str = "OH2XYZ", destination: str = "APRS", path: str = "WIDE1-1,WIDE2-1") -> tuple[object, ...]:
    return tuple(PacketRow("2026-10-26T08:00:00.123456Z", "in", raw, source, destination, path, "undecoded", "", "{}", "no position", "rf", "fm"))


# ---- the system

@pytest.mark.parametrize(("system", "facts", "words"), [
    ("Linux", {"release": "6.12.0", "os_release": {"PRETTY_NAME": "Debian GNU/Linux 13"}}, "Debian GNU/Linux 13, kernel 6.12.0"),
    ("Linux", {"release": "6.12.0", "os_release": {}}, "Linux, kernel 6.12.0"),
    ("Linux", {"release": "6.12.0", "os_release": OSError("no os-release")}, "Linux, kernel 6.12.0"),
    ("Windows", {"release": "11", "version": "10.0.22631"}, "Windows 11 (10.0.22631)"),
    ("Darwin", {"release": "23.5.0", "mac_ver": ("14.5", ("", "", ""), "arm64")}, "macOS 14.5"),
    ("Darwin", {"release": "23.5.0", "mac_ver": ("", ("", "", ""), "arm64")}, "macOS 23.5.0"),
    ("FreeBSD", {"platform": "FreeBSD-14.0-RELEASE-amd64"}, "FreeBSD-14.0-RELEASE-amd64"),
])
def test_the_system_is_named_as_a_person_names_it(monkeypatch: pytest.MonkeyPatch, system: str, facts: dict[str, object], words: str) -> None:
    def os_release() -> dict[str, str]:
        found = facts["os_release"]
        if isinstance(found, OSError):
            raise found
        return found  # type: ignore[return-value]

    platform = systemdescription.platform
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "release", lambda: facts.get("release", ""))
    monkeypatch.setattr(platform, "version", lambda: facts.get("version", ""))
    monkeypatch.setattr(platform, "mac_ver", lambda: facts.get("mac_ver", ("", ("", "", ""), "")))
    monkeypatch.setattr(platform, "platform", lambda: facts.get("platform", ""))
    monkeypatch.setattr(platform, "freedesktop_os_release", os_release)
    assert systemdescription.system_description() == words


# ---- the logs

def test_a_log_that_cannot_be_read_is_left_out_and_the_others_are_joined_oldest_first(tmp_path: Path) -> None:
    newer, older = tmp_path / "neoaprs.log", tmp_path / "neoaprs.log.1"
    newer.write_text("c\nd\n")
    older.write_text("a\nb\n")
    unreadable = tmp_path / "neoaprs.log.2"
    unreadable.mkdir()                                                       # (a name that cannot be read as a file)
    assert supportgather.log_lines([newer, older, unreadable]) == ["a", "b", "c", "d"]


def test_the_start_of_the_daemon_is_the_latest_start_line_with_a_time_and_none_where_the_time_is_not_one() -> None:
    first = f"2026-10-26 08:00:00Z  INFO  NeoAPRS 0.10.1{START_LINE}/data"
    second = f"2026-10-26 09:30:15Z  INFO  NeoAPRS 0.10.1{START_LINE}/data"
    assert supportgather.started_at(["x", first, "y", second, "z"]) == datetime(2026, 10, 26, 9, 30, 15, tzinfo=UTC)
    assert supportgather.started_at(["x", "y"]) is None
    assert supportgather.started_at([first, f"not a time at all{START_LINE}/data"]) is None, "(the latest start line is the one that counts, and it has no time)"


# ---- the database

def test_a_migration_that_this_program_does_not_know_and_one_whose_source_cannot_be_compared_are_said_so(monkeypatch: pytest.MonkeyPatch) -> None:
    applied = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    known = source_hash(MIGRATIONS[0])
    lines = supportgather.migration_lines([
        (1, "a", known, applied, ""),
        (1, "a", "0" * 64, applied, "migrated by another build"),
        (1, "a", "unknown", applied, ""),
        (len(MIGRATIONS) + 5, "future", known, applied, ""),
        (0, "zero", known, applied, ""),
    ])
    assert "source hash matches" in lines[0]
    assert "SOURCE HASH DIFFERS" in lines[1] and "(migrated by another build)" in lines[1]
    assert "source hash not comparable" in lines[2]
    assert "does not know this step" in lines[3] and "does not know this step" in lines[4]
    monkeypatch.setattr(supportgather, "source_hash", lambda migration: "unknown")
    assert "source hash not comparable" in supportgather.migration_lines([(1, "a", known, applied, "")])[0]


def test_a_packet_that_is_no_ax25_frame_is_shown_with_what_the_columns_say() -> None:
    row = row_of(b"\x00\x01 not a frame")
    text = supportgather.packet_text(row)
    assert text.startswith("OH2XYZ>APRS,WIDE1-1,WIDE2-1: (not an AX.25 frame) b'") and text.isprintable()
    assert supportgather.packet_text(row_of(b"\x01", path="")).startswith("OH2XYZ>APRS: (not an AX.25 frame)")
    assert "NOT DECODED: no position" in supportgather.packet_line(row)


# ---- the settings whose value is free text that holds a secret

TOKEN = "123456:ABCdefGhIjKlMnOpQrStUvWxYz"


def test_the_alert_command_and_a_changed_update_address_are_only_said_to_be_set_while_the_default_is_shown() -> None:
    command = f"curl -s https://api.telegram.org/bot{TOKEN}/sendMessage -d chat_id=1"
    rows = {"messages/alert_command": command, "update/url": f"https://user:{TOKEN}@example.org/version", "web/key": "k7m2-x9pq-4hrt"}
    text = supportgather.settings_json(rows)
    assert TOKEN not in text and "k7m2" not in text
    values = json.loads(text)["values"]
    assert values["messages/alert_command"] == f"(set, {len(command)} characters)" and values["update/url"].startswith("(set, ") and values["web/key"] == "(set, 14 characters)"
    default = json.loads(supportgather.settings_json({}))["values"]
    assert default["messages/alert_command"] == DEFAULTS.messages_alert_command and default["update/url"] == DEFAULTS.update_url
    assert set(supportgather.secrets_of(rows)) == {command, rows["update/url"], rows["web/key"]}, "(the net under the redaction takes them out of every file)"
    assert supportgather.secrets_of({"messages/alert_command": DEFAULTS.messages_alert_command}) == [], "(the default holds nothing)"


# ---- the radios

FLAT = {"station/call": "OH2GBA", "tnc/profile": "kantronics", "serial/baud": "4800", "hf/enabled": "true", "mercury/keying": "vox"}


def at_version_thirty(tmp_path: Path, rows: dict[str, str]) -> Path:
    db = at_thirty(tmp_path / DB_NAME)
    db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", sorted(rows.items()))
    db.close()
    return tmp_path


def test_a_file_from_before_the_radios_were_rows_tells_its_rows_of_the_radios_as_they_are_stored(tmp_path: Path) -> None:
    """The keys of before are no settings of this NeoAPRS: the rows are told as the file keeps them,
    for the migration to make the radios of (tests/support/bundledb.py)."""
    data = at_version_thirty(tmp_path, FLAT)
    stored = supportgather.read_stored(data)
    assert stored.rows == FLAT and stored.radios is None
    told = json.loads(supportgather.settings_json(stored.rows, stored.radios))
    assert "radios" not in told and told["other_rows"] == {key: value for key, value in FLAT.items() if key != "station/call"} and told["values"]["station/call"] == "OH2GBA"
    assert not {"tnc/profile", "hf/enabled"} & (set(told["values"]) | set(told["defaults_are_used_for"])), "no key of before among the settings"
    assert told == json.loads(supportgather.settings_json(FLAT)), "the same as the settings alone say"


def test_a_radio_setting_that_is_wrong_is_told_as_stored_while_its_default_is_in_force(tmp_path: Path) -> None:
    data = at_version_thirty(tmp_path, FLAT)
    opened(data / DB_NAME).close()
    db = sqlite3.connect(data / DB_NAME, isolation_level=None)
    db.execute("UPDATE radio_setting SET value = 'fast' WHERE radio_id = 1 AND key = 'baud'")
    db.close()
    stored = supportgather.read_stored(data)
    assert stored.radios is not None and stored.radios.problem == ""
    told = json.loads(supportgather.settings_json(stored.rows, stored.radios))
    fm = told["radios"][0]
    assert (fm["id"], fm["log_name"], fm["type"], fm["values"]["baud"], fm["stored"]["baud"]) == (1, "FM", "kantronics", "", "fast"), "the value in force is the default, the text stored is told"
    assert told["radios"][1]["stored"] == {"keying": "vox"} and told["radios"][1]["values"]["keying"] == "vox" and told["stored_text_differs"] == {}
    spec = supportgather.config_of(stored.rows, stored.radios).radio(1)
    assert spec is not None and spec.type == "kantronics"


def test_radios_that_cannot_be_read_are_told_and_the_settings_still_are(tmp_path: Path) -> None:
    data = at_version_thirty(tmp_path, FLAT)
    opened(data / DB_NAME).close()
    db = sqlite3.connect(data / DB_NAME, isolation_level=None)
    db.execute("DROP TABLE radio_setting")
    db.close()
    stored = supportgather.read_stored(data)
    assert stored.rows["station/call"] == "OH2GBA" and stored.radios is not None and "radio_setting" in stored.radios.problem
    told = json.loads(supportgather.settings_json(stored.rows, stored.radios))
    assert told["radios"] == [] and "could not be read" in told["radios_problem"] and told["values"]["station/call"] == "OH2GBA"


# ---- the pairs of radios

def two_radios(first: str, second: str) -> supportgather.StoredRadios:
    return supportgather.StoredRadios(rows=[(1, "fm", first, "", 1, 1, None), (2, "hf", second, "", 1, 2, None)])


PAIR_ROWS = {"station/call": "OH2GBA", "pair/1/2/enabled": "true", "pair/1/2/ssid": "12"}


def test_a_pair_is_told_as_a_pair_with_its_call_and_whether_its_radios_may_pair_now() -> None:
    told = json.loads(supportgather.settings_json(PAIR_ROWS, two_radios("dummy", "dummy-hf")))
    assert told["pairs"] == [{"low": 1, "high": 2, "enabled": True, "ssid": 12, "call": "OH2GBA-12", "may_pair_now": True}]
    assert told["other_rows"]["pair/1/2/ssid"] == "12", "(the stored rows are told as before)"


def test_a_pair_of_a_dummy_radio_and_a_real_one_or_of_a_radio_that_is_not_there_may_not_pair_now() -> None:
    mixed = json.loads(supportgather.settings_json(PAIR_ROWS, two_radios("dummy", "mercury")))
    assert mixed["pairs"][0]["may_pair_now"] is False and mixed["pairs"][0]["call"] == "OH2GBA-12"
    gone = json.loads(supportgather.settings_json({**PAIR_ROWS, "pair/1/7/enabled": "true"}, two_radios("dummy", "dummy-hf")))
    assert [(p["high"], p["may_pair_now"], p["call"]) for p in gone["pairs"]] == [(2, True, "OH2GBA-12"), (7, False, "")]
