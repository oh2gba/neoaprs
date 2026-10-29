"""The parts of the support bundle that read the computer and the database (neoaprs/cli/supportgather.py) where the whole-bundle tests (tests/test_support_bundle.py) do not go: the name of the system on each system (the
platform module is faked), a log that cannot be read, a log whose start line has no time, the migrations of a database that this program does not know, and a packet that is no frame."""
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from neoaprs.cli import supportgather
from neoaprs.config import DEFAULTS
from neoaprs.cli.logfile import START_LINE
from neoaprs.migrations import MIGRATIONS, source_hash
from neoaprs.packetcodec import PacketRow


def row_of(raw: bytes, source: str = "OH2XYZ", destination: str = "APRS", path: str = "WIDE1-1,WIDE2-1") -> tuple[object, ...]:
    return tuple(PacketRow("2026-10-26T08:00:00.123456Z", "in", raw, source, destination, path, "undecoded", "", "{}", "no position", "rf"))


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

    platform = supportgather.platform
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "release", lambda: facts.get("release", ""))
    monkeypatch.setattr(platform, "version", lambda: facts.get("version", ""))
    monkeypatch.setattr(platform, "mac_ver", lambda: facts.get("mac_ver", ("", ("", "", ""), "")))
    monkeypatch.setattr(platform, "platform", lambda: facts.get("platform", ""))
    monkeypatch.setattr(platform, "freedesktop_os_release", os_release)
    assert supportgather.system_description() == words


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
