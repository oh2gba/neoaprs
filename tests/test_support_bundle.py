"""The support bundle (neoaprs/cli/supportbundle.py, supportgather.py, supportmake.py, supportsummary.py, supportreadme.py): what is in the zip, how the logs are cut to their budget, that no secret is in any member, that a part that fails
becomes a file that says so, and that the data folder is not changed. Built on a fake data folder (tests/support/supportdata.py)."""
import json
import os
import re
import zipfile
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.clock import utc
from neoaprs.cli import supportbundle, supportgather
from neoaprs.cli.supportbundle import Member, bundle_name, log_members, rotated_logs, scrubbed, secret_pattern, write_zip
from neoaprs.cli.supportmake import desktop_dir, make_bundle, show_command, show_file
from neoaprs.cli.supportreadme import MAIL
from neoaprs.cli.supportsummary import last_problems
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.supportdata import KEY, fake_folder, zip_members

NOW = utc(2026, 10, 26, 12, 0, 0)


def made(tmp_path: Path, data: Path | None = None, **options: object) -> tuple[Path, dict[str, str]]:
    data = data or fake_folder(tmp_path)
    result = make_bundle(data, tmp_path / "out", now=FixedClock(NOW), journal=lambda: None, **options)  # type: ignore[arg-type]
    return result.path, zip_members(result.path)


# ---- what is in it

def test_a_bundle_of_a_data_folder_has_the_files_a_reader_opens_in_order_and_is_deflated(tmp_path: Path) -> None:
    path, members = made(tmp_path)
    assert path.name == "neoaprs-support-OH2GBA-20261026-120000Z.zip"
    assert list(members)[:2] == ["README.txt", "summary.txt"]
    assert set(members) == {"README.txt", "summary.txt", "settings.json", "doctor.txt", "database.txt", "packets.txt", "logs/neoaprs.log", "logs/neoaprs-app.log"}, "no state.json without the daemon, no journal without journalctl"
    with zipfile.ZipFile(path) as bundle:
        assert {i.compress_type for i in bundle.infolist()} == {zipfile.ZIP_DEFLATED}
        assert bundle.testzip() is None
    assert not list((tmp_path / "out").glob("*.part")), "no half-written file is left"


def test_the_readme_says_what_to_do_what_is_in_it_and_what_was_left_out(tmp_path: Path) -> None:
    readme = made(tmp_path)[1]["README.txt"]
    assert f"Send it to {MAIL} with a few words: what you did, what you expected, what happened instead, and roughly when (the time finds it in the log)." in readme
    for name in ("summary.txt", "settings.json", "doctor.txt", "database.txt", "packets.txt", "logs/neoaprs.log", "logs/neoaprs-app.log"):
        assert name in readme
    assert "state.json" not in readme.split("What was left out")[0], "only the files that are there are listed"
    for left_out in ("access key", "certificates", "messages", "database file itself", "base map"):
        assert left_out in readme.split("What was left out")[1].lower()
    assert "public" in readme and "texts of messages" in readme


def test_the_summary_answers_what_version_what_system_what_is_wrong_on_one_screen(tmp_path: Path) -> None:
    summary = made(tmp_path)[1]["summary.txt"]
    assert "NeoAPRS:" in summary and VERSION in summary
    for label in ("System:", "Python:", "Data folder:", "Made:", "Daemon:", "Call:", "Position:", "Beacon:", "TNC profile:", "Port:", "Speed:", "State:", "GPS state:", "Listens:", "File:"):
        assert label in summary, label
    assert "OH2GBA" in summary and "Fixed" in summary and "on, every 60 min" in summary and "kenwood-tnc2" in summary
    assert "2026-10-26 12:00:00Z (UTC)" in summary and "local " in summary
    assert "not running" in summary, "nothing holds the data folder"
    assert f"schema version {SCHEMA_VERSION}" in summary
    assert "the daemon was not asked" in summary, "a bundle made without the daemon says which facts it does not have"
    assert "WARNING  line 7 of the log" in summary and summary.count("WARNING") <= 30 + 2
    assert len(summary.splitlines()) < 90


def test_a_daemon_that_holds_the_folder_is_said_so_and_its_state_is_in_the_bundle(tmp_path: Path) -> None:
    live = {"daemon": {"uptime_sec": 3 * 3600 + 120, "started_at": "2026-10-26T09:00:00Z"}, "tnc": {"state": "waiting", "problem": "no radio found", "path": "", "baud": 9600},
            "gps": {"state": "no_fix", "problem": "the receiver has no position fix yet"}, "beacon": {"last_sent": None, "next_due": "2026-10-26T13:00:00Z", "problem": "TNC not connected"},
            "web": {"address": "127.0.0.1", "port": 7303}}
    _, members = made(tmp_path, running=True, live=live, by="the running daemon")
    summary = members["summary.txt"]
    assert "running, up 3 h 2 min (since 2026-10-26T09:00:00Z)" in summary
    assert "waiting" in summary and "no radio found" in summary and "no_fix" in summary and "TNC not connected" in summary and "127.0.0.1, port 7303" in summary
    assert json.loads(members["state.json"])["tnc"]["state"] == "waiting"
    assert "state.json" in members["README.txt"]


def test_the_page_and_its_errors_are_members_when_given(tmp_path: Path) -> None:
    _, members = made(tmp_path, page={"build": "index-abc.js", "browser": "Firefox"}, page_errors=[{"message": "boom"}])
    assert json.loads(members["page.json"]) == {"build": "index-abc.js", "browser": "Firefox"}
    assert json.loads(members["page-errors.json"]) == [{"message": "boom"}]
    assert members["README.txt"].count("page.json") >= 1


def test_the_packets_are_listed_with_what_the_parser_made_of_them_and_the_undecoded_apart(tmp_path: Path) -> None:
    text = made(tmp_path)[1]["packets.txt"]
    heard, undecoded = text.split("could not be decoded")
    assert "2026-10-21 12:00:00.000Z  in " in heard and "-> position:" in heard
    assert "NOT DECODED: too short 1" in undecoded and "NOT DECODED: too short 0" in undecoded
    assert undecoded.index("too short 0") < undecoded.index("too short 1"), "the newest last"


def test_the_database_report_has_the_version_the_migrations_the_rows_and_the_check(tmp_path: Path) -> None:
    text = made(tmp_path)[1]["database.txt"]
    assert f"Schema version: {SCHEMA_VERSION} (this NeoAPRS expects {SCHEMA_VERSION})" in text
    assert text.count("source hash matches") == SCHEMA_VERSION
    assert re.search(r"^\s+packet\s+6$", text, re.M) and re.search(r"^\s+settings\s+9$", text, re.M)
    assert "quick_check" in text and "\n  ok\n" in text
    assert "write-ahead log" in text and "journal mode wal" in text


def test_a_big_database_is_not_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supportgather, "QUICK_CHECK_MAX_BYTES", 1000)
    assert "skipped: the file is" in made(tmp_path)[1]["database.txt"]


def test_a_migration_whose_source_changed_is_said_so(tmp_path: Path) -> None:
    data = fake_folder(tmp_path)
    from tests.support.migrated import opened
    s = opened(data / DB_NAME)
    s.db.execute("UPDATE schema_history SET sha256 = 'ff' WHERE version = 3")
    s.close()
    text = made(tmp_path, data)[1]["database.txt"]
    assert "SOURCE HASH DIFFERS" in text and text.count("source hash matches") == SCHEMA_VERSION - 1


def test_the_doctor_is_in_the_bundle_and_its_findings_are_in_the_summary(tmp_path: Path) -> None:
    members = made(tmp_path)[1]
    assert "Python 3." in members["doctor.txt"] and members["doctor.txt"].rstrip().splitlines()[-1].endswith(("look at", "all is well"))
    assert "Checks (doctor.txt has the fixes)" in members["summary.txt"] and "Result:" in members["summary.txt"]


# ---- the settings and the secret

def test_the_settings_are_all_there_and_the_key_is_only_said_to_be_set(tmp_path: Path) -> None:
    settings = json.loads(made(tmp_path)[1]["settings.json"])
    assert settings["values"]["web/key"] == f"(set, {len(KEY)} characters)"
    assert settings["values"]["station/call"] == "OH2GBA" and settings["values"]["beacon/interval_min"] == "60"
    assert "tnc/profile" in settings["values"] and "web/key" not in settings["defaults_are_used_for"]
    assert settings["other_rows"]["ui/theme"] == "dark" and "beacon/last_sent_at" in settings["other_rows"]
    assert "station/comment" in settings["defaults_are_used_for"]


def test_a_setting_that_has_a_secret_word_in_its_name_is_redacted_and_an_empty_one_is_said_empty(tmp_path: Path) -> None:
    data = fake_folder(tmp_path, settings={"web/key": "", "x/api_token": "abcdef123456", "x/Password": "hunter22", "station/call": "OH2GBA"})
    settings = json.loads(made(tmp_path, data)[1]["settings.json"])
    assert settings["values"]["web/key"] == "(empty)"
    assert settings["other_rows"]["x/api_token"] == "(set, 12 characters)" and settings["other_rows"]["x/Password"] == "(set, 8 characters)"


def test_the_access_key_is_in_no_member_of_the_zip_whatever_put_it_there(tmp_path: Path) -> None:
    data = fake_folder(tmp_path)
    log = data / "neoaprs.log"
    log.write_text(log.read_text(encoding="utf-8") + f"2026-10-21 12:30:00Z  WARNING  somebody typed {KEY} and again {KEY.replace('-', '').upper()} and {KEY.upper()}\n", encoding="utf-8")
    path, members = made(tmp_path, data, page={"note": f"my key is {KEY}"}, page_errors=[{"message": f"key {KEY}"}], live={"x": KEY})
    assert "(secret removed)" in members["logs/neoaprs.log"]
    with zipfile.ZipFile(path) as bundle:
        raw = b"".join(bundle.read(name) for name in bundle.namelist())
    plain = KEY.replace("-", "")
    for text in list(members.values()) + [raw.decode("latin-1")]:
        assert KEY not in text and KEY.upper() not in text and plain not in text.lower()


def test_a_short_value_is_not_hunted_for_in_the_text() -> None:
    assert secret_pattern(["abc"]) is None
    pattern = secret_pattern(["k7m2-x9pq-4hrt"])
    assert scrubbed("a K7M2X9PQ4HRT b", pattern) == "a (secret removed) b" and scrubbed("nothing", None) == "nothing"


# ---- the logs

def test_the_name_of_the_file_has_the_call_or_nocall_and_the_time() -> None:
    assert bundle_name("oh2gba-9", NOW) == "neoaprs-support-OH2GBA-9-20261026-120000Z.zip"
    assert bundle_name("", NOW) == "neoaprs-support-nocall-20261026-120000Z.zip"
    assert bundle_name("../x y", NOW) == "neoaprs-support-XY-20261026-120000Z.zip"


def test_the_rotated_logs_are_found_newest_first_and_the_app_log_is_not_one_of_them(tmp_path: Path) -> None:
    for name in ("neoaprs.log", "neoaprs.log.1", "neoaprs.log.10", "neoaprs.log.2", "neoaprs-app.log", "neoaprs.log.bak"):
        (tmp_path / name).write_text(name)
    assert [p.name for p in rotated_logs(tmp_path, "neoaprs.log")] == ["neoaprs.log", "neoaprs.log.1", "neoaprs.log.2", "neoaprs.log.10"]
    assert [p.name for p in rotated_logs(tmp_path, "neoaprs-app.log")] == ["neoaprs-app.log"]


def test_a_log_over_the_budget_keeps_its_newest_lines_cut_at_a_line_start_with_a_first_line_that_says_so(tmp_path: Path) -> None:
    lines = [f"line {n:04d} of the log\n" for n in range(1000)]
    big = tmp_path / "neoaprs.log"
    big.write_text("".join(lines), encoding="utf-8")
    member = log_members([big], budget=2000)[0]
    first, *kept = member.text.splitlines()
    assert member.name == "logs/neoaprs.log" and "left out" in first and "the first" in first and "bytes of neoaprs.log" in first
    assert kept and kept[-1] == "line 0999 of the log" and all(line.startswith("line ") and line.endswith(" of the log") for line in kept), "cut at a line start"
    assert len("".join(kept)) <= 2000 and kept == [line.rstrip("\n") for line in lines[-len(kept):]]


def test_rotated_logs_share_one_budget_the_newest_first_and_an_older_one_that_does_not_fit_is_one_line(tmp_path: Path) -> None:
    files = []
    for name in ("neoaprs.log", "neoaprs.log.1", "neoaprs.log.2"):
        path = tmp_path / name
        path.write_text("".join(f"{name} line {i:03d}\n" for i in range(100)), encoding="utf-8")
        files.append(path)
    members = {m.name: m.text for m in log_members(files, budget=1500)}
    total = sum(len(t.encode()) for t in members.values() if not t.startswith("["))
    assert total <= 1500
    assert members["logs/neoaprs.log"].startswith("neoaprs.log line 000") or "left out" in members["logs/neoaprs.log"].splitlines()[0]
    assert "the whole file of neoaprs.log.2 left out" in members["logs/neoaprs.log.2"] and len(members["logs/neoaprs.log.2"].splitlines()) == 1


def test_the_budget_of_a_bundle_is_the_one_of_the_module_and_the_newest_log_comes_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supportbundle, "LOG_BUDGET_BYTES", 3000)
    data = fake_folder(tmp_path, log_lines=400)
    (data / "neoaprs.log.1").write_text("".join(f"2026-10-20 10:00:00Z  INFO  older {n}\n" for n in range(300)), encoding="utf-8")
    _, members = made(tmp_path, data)
    logs = [n for n in members if n.startswith("logs/")]
    assert logs == ["logs/neoaprs.log", "logs/neoaprs.log.1", "logs/neoaprs-app.log"]
    assert sum(len(members[n].encode()) for n in logs) < 3000 + 600, "the notes of what was left out are all that may go over"
    assert "left out" in members["logs/neoaprs.log"].splitlines()[0]


def test_a_log_that_cannot_be_read_is_a_member_that_says_so(tmp_path: Path) -> None:
    gone = tmp_path / "neoaprs.log"
    assert log_members([gone])[0].text.startswith("[neoaprs.log could not be read")


def test_the_last_warnings_and_errors_are_the_last_thirty_with_the_line_of_a_traceback_that_names_the_exception() -> None:
    lines = ["2026-10-21 12:00:00Z  INFO  fine"]
    for n in range(40):
        lines.append(f"2026-10-21 12:01:{n:02d}Z  WARNING  problem {n}")
    lines += ["2026-10-21 12:02:00Z  ERROR  it failed", "Traceback (most recent call last):", '  File "x.py", line 1, in f', "ValueError: bad value", "2026-10-21 12:02:01Z  INFO  fine again"]
    found = last_problems(lines)
    records = [line for line in found if not line.startswith("    ")]
    assert len(records) == 30 and records[-1].endswith("ERROR  it failed") and records[0].endswith("problem 11")
    assert found[-1] == "    ValueError: bad value"
    assert last_problems(["2026-10-21 12:00:00Z  INFO  fine"]) == []


# ---- a part that fails

def test_a_database_that_is_no_database_makes_error_files_and_the_bundle_still_comes(tmp_path: Path) -> None:
    data = fake_folder(tmp_path)
    (data / DB_NAME).write_bytes(b"this is not a database at all, but a text of a few hundred bytes. " * 20)
    path, members = made(tmp_path, data)
    for part in ("database.txt", "packets.txt", "settings.json"):
        assert part not in members and "Traceback" in members[part + ".error.txt"] and f"{part} could not be made" in members[part + ".error.txt"]
    summary = members["summary.txt"]
    assert "Could not be read" in summary and "could not be read" in summary and members["README.txt"].count(".error.txt") >= 3
    assert "FAIL" in members["doctor.txt"]
    assert "logs/neoaprs.log" in members
    assert zipfile.ZipFile(path).testzip() is None


def test_a_data_folder_that_is_not_there_still_gives_a_bundle_that_says_so(tmp_path: Path) -> None:
    path, members = made(tmp_path, tmp_path / "nowhere")
    assert "There is no database file" in members["database.txt"] and "no database file yet" in members["summary.txt"]
    assert "nocall" in path.name and "(none set: nothing is transmitted)" in members["summary.txt"]
    assert not any(name.startswith("logs/") for name in members)


def test_a_missing_app_log_is_just_not_there(tmp_path: Path) -> None:
    _, members = made(tmp_path, fake_folder(tmp_path, app_log=False))
    assert "logs/neoaprs-app.log" not in members and "neoaprs-app.log" not in members["README.txt"].split("What was left out")[0]


def test_a_gatherer_that_raises_is_an_error_file_and_the_rest_is_made(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_data: Path) -> str:
        raise RuntimeError("the doctor fell over")
    monkeypatch.setattr(supportgather, "doctor_text", broken)
    _, members = made(tmp_path)
    assert "doctor.txt" not in members and "RuntimeError: the doctor fell over" in members["doctor.txt.error.txt"]
    assert "summary.txt" in members and "packets.txt" in members


def test_the_journal_when_there_is_one_is_a_member_and_a_failure_of_it_is_text(tmp_path: Path) -> None:
    data = fake_folder(tmp_path)
    result = make_bundle(data, tmp_path / "out", now=FixedClock(NOW), journal=lambda: "2026-10-26T12:00:00+02:00 host python[1]: hello\n")
    assert zip_members(result.path)["logs/journal.txt"].endswith("hello\n")

    class Done:
        returncode, stdout, stderr = 1, "", "no journal files"
    note = supportgather.journal_text(run=lambda *a, **k: Done(), which=lambda name: "/bin/" + name)
    if os.name == "posix" and supportgather.platform.system() == "Linux":
        assert note is not None and "ended with 1: no journal files" in note
    assert supportgather.journal_text(run=lambda *a, **k: Done(), which=lambda name: None) is None


def test_journalctl_that_cannot_be_run_never_fails_the_bundle() -> None:
    def boom(*a: object, **k: object) -> object:
        raise supportgather.subprocess.TimeoutExpired("journalctl", 5)
    if supportgather.platform.system() == "Linux":
        text = supportgather.journal_text(run=boom, which=lambda name: "/bin/" + name)
        assert text is not None and "could not be run" in text and "TimeoutExpired" in text


# ---- read only

def test_the_data_folder_is_not_changed(tmp_path: Path) -> None:
    data = fake_folder(tmp_path)

    def snapshot() -> dict[str, tuple[int, int, bytes]]:
        return {p.name: (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes()) for p in sorted(data.iterdir()) if p.is_file()}
    before = snapshot()
    names = sorted(p.name for p in data.iterdir())
    made(tmp_path, data)
    assert sorted(p.name for p in data.iterdir()) == names, "no -wal or -shm made beside the database"
    assert {k: v for k, v in snapshot().items() if k != DB_NAME} == {k: v for k, v in before.items() if k != DB_NAME}
    assert snapshot()[DB_NAME][2] == before[DB_NAME][2], "the database file is byte for byte what it was"


def test_the_zip_is_written_whole_or_not_at_all(tmp_path: Path) -> None:
    target = tmp_path / "x.zip"
    with pytest.raises(AttributeError):
        write_zip(target, [Member("a.txt", "fine"), 5], NOW)  # type: ignore[list-item]
    assert not target.exists() and not list(tmp_path.glob("*.part"))


# ---- where the file goes

def test_the_desktop_folder_is_found_by_the_name_the_system_gave_it_else_the_home_folder(tmp_path: Path) -> None:
    assert desktop_dir(tmp_path, {}) == tmp_path
    (tmp_path / "Desktop").mkdir()
    assert desktop_dir(tmp_path, {}) == tmp_path / "Desktop"
    (tmp_path / "Työpöytä").mkdir()
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/Lataukset"\nXDG_DESKTOP_DIR="$HOME/Työpöytä"\n', encoding="utf-8")
    assert desktop_dir(tmp_path, {}) == tmp_path / "Työpöytä"


def test_a_desktop_inside_onedrive_is_found_on_windows(tmp_path: Path) -> None:
    (tmp_path / "OneDrive" / "Desktop").mkdir(parents=True)
    assert desktop_dir(tmp_path, {"OneDrive": str(tmp_path / "OneDrive")}) == tmp_path / "OneDrive" / "Desktop"


def test_the_file_manager_is_started_the_way_each_system_does(tmp_path: Path) -> None:
    file = tmp_path / "a.zip"
    assert show_command(file, "win32") == f'explorer /select,"{file}"'
    assert show_command(file, "darwin") == ["open", "-R", str(file)]
    assert show_command(file, "linux") == ["xdg-open", str(tmp_path)]


def test_the_file_manager_is_started_with_the_command_and_one_that_is_not_there_is_a_false(tmp_path: Path) -> None:
    started: list[object] = []
    file = tmp_path / "a.zip"
    assert show_file(file, "linux", lambda command, **options: started.append(command)) and started == [["xdg-open", str(tmp_path)]]

    def missing(command: object, **options: object) -> None:
        raise FileNotFoundError("xdg-open")
    assert not show_file(file, "linux", missing)


def test_the_name_of_the_file_has_the_call_the_caller_knows_when_the_settings_cannot_be_read(tmp_path: Path) -> None:
    data = fake_folder(tmp_path)
    (data / DB_NAME).write_bytes(b"not a database " * 100)
    path, _ = made(tmp_path, data, call="oh2xyz")
    assert path.name == "neoaprs-support-OH2XYZ-20261026-120000Z.zip"
