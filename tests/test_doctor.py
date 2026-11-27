"""Tests for `neoaprs doctor` on a temporary data folder: each check's status and fix, the exit
code, radio names, and the computer-related checks. Ports and autostart are stand-ins; nothing is
opened."""

import http.server
import os
import sqlite3
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.cli import dbcmd, doctor, hostcheck, servicecmd
from neoaprs.cli.daemonstate import describe, is_running, page_answers, page_url, tail
from neoaprs.instancelock import InstanceLock
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION
from neoaprs.migrationsteps31 import _v31
from neoaprs.radiosql import insert_radio, put_radio_settings
from neoaprs.serialprobe import PortInfo
from neoaprs.stopfile import MIGRATING_FRESH_SEC, MIGRATING_NAME
from tests.support.httpthread import serve
from tests.support.migrated import opened
from tests.support.migrated31 import at_thirty


class Service:
    """The start at sign-in as the doctor asks for it (servicecmd.backend_for(...).installed(plan)):
    what a test says it is, and the plans it was asked about."""

    def __init__(self, set_up: bool, what: str) -> None:
        self.answer: tuple[bool, str] = (set_up, what)
        self.asked: list[servicecmd.Plan] = []

    def installed(self, plan: servicecmd.Plan) -> tuple[bool, str]:
        self.asked.append(plan)
        return self.answer


@pytest.fixture(autouse=True)
def this_computer(monkeypatch: pytest.MonkeyPatch) -> Service:
    """A computer with one TNC cable, in the group of its serial devices, with neither brltty nor
    ModemManager, and no start at sign-in set up (whatever the computer of the test has)."""
    monkeypatch.setattr(
        doctor,
        "available_ports",
        lambda: [PortInfo("/dev/ttyUSB0", "FT232R USB UART", "USB VID:PID=0403:6001", 0x0403, 0x6001)],
    )
    monkeypatch.setattr(doctor, "serial_group_check", lambda: hostcheck.GroupCheck("ok", "dialout", ""))
    monkeypatch.setattr(doctor, "brltty_installed", lambda: False)
    monkeypatch.setattr(doctor, "modemmanager_installed", lambda: False)
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: None)
    service = Service(False, "no user unit")
    monkeypatch.setattr(doctor.servicecmd, "backend_for", lambda system: service)
    return service


def run(data: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = doctor.main(["--data", str(data)])
    return code, capsys.readouterr().out


def lines_of(text: str, status: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(status)]


def set_up(data: Path, *radios: str, **settings: str) -> None:
    """The data folder of a station set up on the command line: these radios added (`db radios
    add`), then these settings set."""
    for radio_type in radios:
        assert dbcmd.main(["--data", str(data), "radios", "add", radio_type]) == 0
    for key, value in settings.items():
        assert dbcmd.main(["--data", str(data), "set", key.replace("_", "/", 1), value]) == 0


def test_a_fresh_computer_has_warnings_with_their_fixes_and_no_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = run(tmp_path / "data", capsys)
    assert code == 0, out
    assert out.startswith(f"NeoAPRS {VERSION} on ")
    assert not lines_of(out, "FAIL")
    assert any("Python 3." in line for line in lines_of(out, "ok"))
    assert any("does not exist yet" in line for line in lines_of(out, "ok"))
    assert any("no database yet" in line for line in lines_of(out, "ok"))
    text = out
    assert "no call is set" in text and "fix: set your call on the page (My station tab, Call)" in text
    assert "/dev/ttyUSB0  FT232R USB UART  VID:PID 0403:6001" in text
    assert "no base map yet" in text and "fix: make it on the page" in text
    assert "the service is not set up (no user unit)" in text and "fix: neoaprs service install" in text
    assert "no daemon is running" in text
    assert "radio " not in text, "a computer with no database has no radio to name yet"
    assert out.rstrip().splitlines()[-1].endswith("to look at")


def test_a_data_folder_with_a_database_a_call_and_a_map_is_all_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], this_computer: Service
) -> None:
    data = tmp_path / "data"
    set_up(data, "kiss", station_call="OH2GBA")
    (data / "basemap.pmtiles").write_bytes(b"x" * 3_000_000)
    (data / "basemap-world.pmtiles").write_bytes(b"x" * 1_000_000)
    this_computer.answer = (True, "the user unit /x/neoaprs.service")
    code, out = run(data, capsys)
    assert code == 0, out
    assert f"database neoaprs.sqlite, version {SCHEMA_VERSION}" in out and "call OH2GBA" in out
    assert "data folder" in out and "(writable)" in out
    assert (
        "base map: basemap.pmtiles 3 MB, basemap-world.pmtiles 1 MB" in out
        and "service set up: the user unit /x/neoaprs.service" in out
    )
    assert not lines_of(out, "warn") and out.rstrip().splitlines()[-1] == "all is well"
    assert [plan.data for plan in this_computer.asked] == [data.resolve()], (
        "the service of this data folder was asked for, of the stand-in"
    )


def test_a_call_that_cannot_transmit_is_a_warning_with_the_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    # (a placeholder call is stored as it is and does not transmit)
    set_up(data, station_call="N0CALL")
    code, out = run(data, capsys)
    assert code == 0 and "the call N0CALL cannot transmit" in out


def test_a_folder_that_is_a_file_and_a_database_that_is_not_one_fail_and_the_exit_code_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "file").write_text("x")
    code, out = run(tmp_path / "file", capsys)
    assert code == 1 and "is not a folder" in out and "fix: give another folder with --data" in out
    data = tmp_path / "data"
    data.mkdir()
    (data / "neoaprs.sqlite").write_bytes(b"this is not a database" * 100)
    code, out = run(data, capsys)
    assert (
        code == 1
        and "cannot be read" in out
        and "fix: if it is damaged" in out
        and out.rstrip().splitlines()[-1].startswith("1 to fix")
    )


def test_a_database_of_a_newer_neoaprs_fails_and_one_of_an_older_version_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")
    conn = sqlite3.connect(data / "neoaprs.sqlite")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 4}")
    conn.close()
    code, out = run(data, capsys)
    assert (
        code == 1
        and f"database version {SCHEMA_VERSION + 4}: made by a newer NeoAPRS" in out
        and "update NeoAPRS" in out
    )
    assert "there is no copy in the backup folder" in out
    kept = data / "backup" / "premigrate-v1-to-v2-20261101-120000.sqlite"
    kept.parent.mkdir()
    conn = sqlite3.connect(kept)
    conn.execute("CREATE TABLE t (x)")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.close()
    code, out = run(data, capsys)
    assert kept.name in out and "2026-11-01 12:00 UTC" in out and "neoaprs db restore" in out
    conn = sqlite3.connect(data / "neoaprs.sqlite")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
    conn.close()
    code, out = run(data, capsys)
    assert (
        code == 0
        and f"database version {SCHEMA_VERSION - 1}, this NeoAPRS uses {SCHEMA_VERSION}" in out
        and "migrates the file" in out
    )


def test_a_database_of_an_older_version_while_the_daemon_brings_it_up_to_date_is_ok(tmp_path: Path) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")
    conn = sqlite3.connect(data / "neoaprs.sqlite")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
    conn.close()
    note = data / MIGRATING_NAME
    note.write_text("")
    finding = doctor.check_database(data)[0]
    assert (finding.status, finding.text) == (
        "ok",
        f"database version {SCHEMA_VERSION - 1}: the daemon is bringing it up to date to version {SCHEMA_VERSION}",
    )
    # The note of a migration that a kill ended: the warning as without one.
    old = time.time() - 10 * MIGRATING_FRESH_SEC
    os.utime(note, (old, old))
    finding = doctor.check_database(data)[0]
    assert (
        finding.status == "warn"
        and f"database version {SCHEMA_VERSION - 1}, this NeoAPRS uses {SCHEMA_VERSION}" in finding.text
    )
    note.unlink()
    assert doctor.check_database(data)[0].status == "warn"


def test_the_doctor_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")
    before = sorted((p.name, p.stat().st_size) for p in data.iterdir() if p.name != "neoaprs.lock")
    run(data, capsys)
    run(tmp_path / "nowhere", capsys)
    assert (
        sorted((p.name, p.stat().st_size) for p in data.iterdir() if p.name != "neoaprs.lock") == before
        and not (tmp_path / "nowhere").exists()
    )


def test_no_port_and_the_things_that_grab_one_are_said_with_the_way_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "available_ports", lambda: [])
    monkeypatch.setattr(doctor, "brltty_installed", lambda: True)
    monkeypatch.setattr(doctor, "modemmanager_installed", lambda: True)
    monkeypatch.setattr(
        doctor,
        "serial_group_check",
        lambda: hostcheck.GroupCheck(
            "missing", "dialout", "sudo usermod -aG dialout jane   (then log out and in again)"
        ),
    )
    code, out = run(tmp_path / "data", capsys)
    assert code == 0
    assert (
        "no serial port is listed by the system" in out
        and "a radio of the type Sound card, or your own Direwolf, needs no serial port" in out
    )
    assert "not in the group dialout" in out and "fix: sudo usermod -aG dialout jane" in out
    assert "brltty is installed" in out and "fix: remove it: sudo apt remove brltty" in out
    assert "ModemManager is installed" in out and "sudo systemctl disable --now ModemManager" in out


# ---- a daemon that holds the data folder ----


@pytest.fixture
def page() -> Iterator[int]:
    """A page that answers on a free port of the loopback (a thread: the doctor asks over HTTP)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<title>NeoAPRS</title>")

        def log_message(self, *args: object) -> None:
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = serve(server)
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()
    thread.join(5)


def log_of(data: Path, *lines: str) -> None:
    data.mkdir(exist_ok=True)
    (data / "neoaprs.log").write_text("\n".join(lines) + "\n")


def test_a_daemon_that_holds_the_lock_is_found_with_its_page(
    tmp_path: Path, page: int, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    log_of(
        data,
        "2026-10-22 12:00:00Z  INFO  NeoAPRS 0.1.0 starting, data in /x",
        f"2026-10-22 12:00:01Z  INFO  web page at http://127.0.0.1:{page}/",
    )
    assert not is_running(data)
    lock = InstanceLock(data)
    lock.acquire()
    try:
        assert (
            is_running(data)
            and page_url(data) == f"http://127.0.0.1:{page}/"
            and page_answers(f"http://127.0.0.1:{page}/")
        )
        assert describe(data) == (True, f"a daemon is running; its page http://127.0.0.1:{page}/ answers")
        code, out = run(data, capsys)
        assert code == 0 and f"its page http://127.0.0.1:{page}/ answers" in out
    finally:
        lock.release()
    assert not is_running(data), "the lock was taken for a moment to find out, and let go"


def test_a_page_that_does_not_answer_and_a_run_without_a_page_are_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    log_of(data, "x starting, data in /x", "y web page at http://127.0.0.1:9/")
    lock = InstanceLock(data)
    lock.acquire()
    try:
        code, out = run(data, capsys)
        assert code == 0 and "http://127.0.0.1:9/ does not answer" in out and "fix: open the log" in out
        log_of(
            data,
            "x starting, data in /x",
            "y web page at http://127.0.0.1:9/",
            "z starting, data in /x",
            "the web server cannot listen on 127.0.0.1:7303: in use; NeoAPRS goes on without the page",
        )
        assert page_url(data) is None, "the page of an earlier run is not this run's"
        assert "log does not say where its page is" in describe(data)[1]
    finally:
        lock.release()


def test_the_end_of_a_log_is_its_last_lines(tmp_path: Path) -> None:
    path = tmp_path / "log"
    path.write_text("\n".join(str(n) for n in range(3000)) + "\n")
    assert tail(path, 3) == ["2997", "2998", "2999"] and tail(tmp_path / "missing") == []
    big = tmp_path / "big"
    big.write_text("\n".join("x" * 100 for _ in range(10_000)) + "\nlast\n")
    assert tail(big, 2)[-1] == "last" and len(tail(big, 100_000)) < 10_001


# ---- the group of the serial devices, brltty and ModemManager ----


def test_the_group_decision_tells_a_missing_group_from_a_session_that_began_before_it() -> None:
    assert hostcheck.decide(["dialout"], {"dialout", "users"}, {"dialout"}, "jane") == hostcheck.GroupCheck(
        "ok", "dialout", ""
    )
    missing = hostcheck.decide(["dialout"], {"users"}, set(), "jane")
    assert missing.status == "missing" and missing.fix == "sudo usermod -aG dialout jane   (then log out and in again)"
    relogin = hostcheck.decide(["uucp"], {"users"}, {"uucp"}, "jane")
    assert relogin.status == "relogin" and "log out and in again" in relogin.fix and "usermod" not in relogin.fix
    assert hostcheck.decide([], {"users"}, set(), "jane").status == "unknown"
    assert hostcheck.decide(["uucp", "dialout"], {"dialout"}, set(), "jane").status == "ok"


@pytest.mark.skipif(sys.platform != "linux", reason="the groups of serial devices are a Linux matter")
def test_the_group_check_reads_the_owner_of_the_devices_it_is_given(tmp_path: Path) -> None:
    device = tmp_path / "ttyUSB0"
    device.write_text("")
    import grp
    import os

    mine = grp.getgrgid(os.getgid()).gr_name  # type: ignore[attr-defined, unused-ignore]
    if mine == "root":
        pytest.skip("root owns the files it makes: no group to be in")
    check = hostcheck.serial_group_check([str(device)], "someone")
    assert (check.status, check.group) == ("ok", mine), (
        "the group of the file is the test user's own, which this session has"
    )


def test_brltty_and_modemmanager_are_found_by_their_programs_or_their_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hostcheck.sys, "platform", "linux")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(hostcheck, "BRLTTY_FILES", (str(tmp_path / "85-brltty.rules"),))
    monkeypatch.setattr(hostcheck, "MODEMMANAGER_FILES", (str(tmp_path / "ModemManager.service"),))
    assert not hostcheck.brltty_installed() and not hostcheck.modemmanager_installed()
    (tmp_path / "85-brltty.rules").write_text("")
    assert hostcheck.brltty_installed() and not hostcheck.modemmanager_installed()
    program = tmp_path / "bin"
    program.mkdir()
    (program / "ModemManager").write_text("#!/bin/sh\n")
    (program / "ModemManager").chmod(0o755)
    monkeypatch.setenv("PATH", str(program))
    assert hostcheck.modemmanager_installed()
    monkeypatch.setattr(hostcheck.sys, "platform", "win32")
    assert not hostcheck.brltty_installed() and not hostcheck.modemmanager_installed()


# ---- Firefox as a Flatpak on KDE ----

NO_OVERRIDES = ""
BOTH_OVERRIDES = "[Session Bus Policy]\norg.freedesktop.Notifications=talk\n\n[Environment]\nNOTIFY_IGNORE_PORTAL=1\n"


def fake_flatpak(
    installed: bool = True,
    user: str = NO_OVERRIDES,
    system: str = NO_OVERRIDES,
    permissions: str = "[Session Bus Policy]\norg.freedesktop.portal.Desktop=talk\n",
) -> tuple[list[list[str]], hostcheck.FlatpakRun]:
    """A `flatpak` that answers from the text it is given and records what it was asked."""
    asked: list[list[str]] = []

    def run(args: list[str]) -> tuple[int, str]:
        asked.append(args)
        if args[0] == "info" and len(args) == 2:
            return (0, "Firefox") if installed else (1, "")
        if args[:3] == ["override", "--user", "--show"]:
            return 0, user
        if args[:3] == ["override", "--system", "--show"]:
            return 0, system
        if args[:2] == ["info", "--show-permissions"]:
            return 0, permissions
        raise AssertionError(f"a command that may change something: {args}")

    return asked, run


@pytest.fixture
def on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hostcheck.sys, "platform", "linux")


def test_firefox_as_a_flatpak_on_kde_without_the_overrides_is_missing_both_commands(on_linux: None) -> None:
    asked, run = fake_flatpak()
    check = hostcheck.firefox_flatpak(run, "KDE", True)
    assert check is not None and check.status == "missing"
    lines = check.fix.splitlines()
    assert lines[0] == "flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox"
    assert lines[1].strip() == "flatpak override --user --env=NOTIFY_IGNORE_PORTAL=1 org.mozilla.firefox"
    assert lines[2].strip() == "then restart Firefox"
    assert asked == [
        ["info", "org.mozilla.firefox"],
        ["override", "--user", "--show", "org.mozilla.firefox"],
        ["override", "--system", "--show", "org.mozilla.firefox"],
        ["info", "--show-permissions", "org.mozilla.firefox"],
    ]


def test_one_override_that_is_there_is_not_asked_for_again(on_linux: None) -> None:
    check = hostcheck.firefox_flatpak(fake_flatpak(user="[Environment]\nNOTIFY_IGNORE_PORTAL=1\n")[1], "KDE", True)
    assert (
        check is not None
        and check.status == "missing"
        and "NOTIFY_IGNORE_PORTAL" not in check.fix
        and "--talk-name=org.freedesktop.Notifications" in check.fix
    )
    check = hostcheck.firefox_flatpak(
        fake_flatpak(user="[Session Bus Policy]\norg.freedesktop.Notifications=talk\n")[1], "KDE", True
    )
    assert check is not None and "--env=NOTIFY_IGNORE_PORTAL=1" in check.fix and "--talk-name" not in check.fix


def test_the_overrides_are_found_wherever_they_are_set(on_linux: None) -> None:
    runs = (
        fake_flatpak(user=BOTH_OVERRIDES)[1],
        fake_flatpak(system=BOTH_OVERRIDES)[1],
        fake_flatpak(
            user="[Environment]\nNOTIFY_IGNORE_PORTAL=1\n",
            permissions="[Session Bus Policy]\norg.freedesktop.Notifications=talk\n",
        )[1],
    )
    for run in runs:
        assert hostcheck.firefox_flatpak(run, "KDE", True) == hostcheck.FlatpakFirefox("ok", "")


def test_it_does_not_apply_without_kde_a_flatpak_command_or_a_flatpak_firefox(
    monkeypatch: pytest.MonkeyPatch, on_linux: None
) -> None:
    run = fake_flatpak()[1]
    assert hostcheck.firefox_flatpak(run, "GNOME", True) is None
    assert hostcheck.firefox_flatpak(run, "", True) is None
    assert hostcheck.firefox_flatpak(run, "KDE", False) is None
    assert hostcheck.firefox_flatpak(fake_flatpak(installed=False)[1], "KDE", True) is None
    assert hostcheck.firefox_flatpak(run, "ubuntu:KDE", True) is not None
    monkeypatch.setattr(hostcheck.sys, "platform", "win32")
    assert hostcheck.firefox_flatpak(run, "KDE", True) is None


def test_the_desktop_comes_from_the_environment_and_flatpak_from_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, on_linux: None
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert hostcheck.firefox_flatpak(fake_flatpak()[1]) is None


def test_the_flatpak_runner_survives_a_missing_program(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert hostcheck.run_flatpak(["info", "org.mozilla.firefox"]) == (1, "")


def test_the_doctor_warns_with_the_commands_for_firefox_as_a_flatpak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fix = "flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox\n      then restart Firefox"
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: hostcheck.FlatpakFirefox("missing", fix))
    code, out = run(tmp_path / "data", capsys)
    assert code == 0
    assert "warn  Firefox is a Flatpak: on KDE its web notifications can go missing" in out
    assert "fix: flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox" in out
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: hostcheck.FlatpakFirefox("ok", ""))
    assert (
        "ok    Firefox is a Flatpak: its web notifications go to the desktop's notification service"
        in run(tmp_path / "data", capsys)[1]
    )


# ---- the radios, each by the name the log gives it


def radios_of(data: Path, **flat: str) -> Path:
    """A data folder whose database had these flat settings at version 30 and was migrated: its
    radios are rows (migration 31)."""
    data.mkdir(parents=True, exist_ok=True)
    old = at_thirty(data / "neoaprs.sqlite")
    old.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        [(key.replace("_", "/", 1), value) for key, value in flat.items()],
    )
    old.close()
    opened(data / "neoaprs.sqlite").close()
    return data


def test_each_radio_is_a_line_by_its_name_with_its_type_and_how_it_is_reached_or_that_it_is_off(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = radios_of(
        tmp_path / "data",
        station_call="OH2GBA",
        tnc_profile="kenwood-tnc2",
        serial_port="/dev/ttyUSB0",
        hf_enabled="true",
        mercury_sound_card="plughw:1,0",
        mercury_keying="rts:/dev/ttyUSB1",
    )
    conn = sqlite3.connect(data / "neoaprs.sqlite", isolation_level=None)
    base = insert_radio(conn, "fm", "kiss-tcp", "Base", True, 3)
    put_radio_settings(conn, base, {"tcp_host": "10.0.0.9", "tcp_port": "8100"})
    insert_radio(conn, "fm", "dummy", "", False, 4)
    conn.close()
    code, out = run(data, capsys)
    assert code == 0, out
    assert [line for line in lines_of(out, "ok") if line.startswith("ok    radio ")] == [
        "ok    radio FM (kenwood-tnc2): port /dev/ttyUSB0, speed 9600 baud",
        "ok    radio Mercury (mercury): sound card plughw:1,0, keying rts:/dev/ttyUSB1",
        "ok    radio Base (kiss-tcp): port 10.0.0.9:8100",
        "ok    radio FM 3 (dummy): off",
    ], "by position; the third of its kind is FM 3, the named one counted"
    assert "no radio is on" not in out


def test_a_station_with_no_radio_on_is_a_warning_with_the_way_to_tick_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = radios_of(tmp_path / "data", station_call="OH2GBA", fm_enabled="false", hf_enabled="true")
    conn = sqlite3.connect(data / "neoaprs.sqlite", isolation_level=None)
    conn.execute("UPDATE radio SET enabled = 0")
    conn.close()
    code, out = run(data, capsys)
    assert code == 0 and "radio FM (kiss): off" in out and "radio Mercury (mercury): off" in out
    assert (
        "warn  no radio is on: nothing is heard and nothing is sent" in out
        and "fix: tick a radio on the page (Settings tab, Radio)" in out
    )


def test_a_database_without_radios_is_told_it_has_none_yet_and_an_older_file_is_read_without_its_radios(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")  # (a new installation's file: no radio yet)
    code, out = run(data, capsys)
    assert (
        code == 0
        and "warn  this station has no radio yet: nothing is heard and nothing is sent" in out
        and "fix: add one: the setup guide, the page (Settings tab, Radio), or neoaprs db radios add TYPE" in out
    )
    assert "radio FM" not in out and "no radio is on" not in out
    set_up(data, "kiss")
    set_up(data, **{"radio/1/port": "COM3"})
    code, out = run(data, capsys)
    assert code == 0 and "radio FM (kiss): port COM3, speed 9600 baud" in out and "no radio yet" not in out
    conn = sqlite3.connect(data / "neoaprs.sqlite", isolation_level=None)
    conn.execute("UPDATE radio SET removed_at = '2026-11-14T10:00:00.000000Z', enabled = 0")
    conn.close()
    code, out = run(data, capsys)
    assert (
        code == 0
        and "warn  every radio of this station is removed: nothing is heard and nothing is sent" in out
        and "no radio yet" not in out
    ), "its radios are removed, not never added"
    conn = sqlite3.connect(data / "neoaprs.sqlite", isolation_level=None)
    conn.execute("UPDATE radio SET removed_at = NULL, enabled = 1")
    conn.close()
    older = radios_of(tmp_path / "older", station_call="OH2GBA", tnc_profile="kantronics")
    conn = sqlite3.connect(older / "neoaprs.sqlite")
    conn.execute(f"PRAGMA user_version = {doctor.RADIO_ROWS_FROM - 1}")
    conn.execute("DROP TABLE radio_setting")
    conn.execute("DROP TABLE radio")
    conn.close()
    code, out = run(older, capsys)
    err = capsys.readouterr().err
    assert (
        code == 0 and "migrates the file" in out and "radio FM" not in out and "no radio yet" not in out and err == ""
    ), (
        "the radios of a file older than their rows are not asked for: the migration makes them, and nothing is said of tables it lacks"
    )


def test_the_version_from_which_the_radios_are_rows_is_the_one_of_migration_31() -> None:
    assert doctor.RADIO_ROWS_FROM == MIGRATIONS.index(_v31) + 1


def test_radios_that_cannot_be_read_are_a_failure_with_the_way_back_and_no_made_up_radio_is_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = radios_of(
        tmp_path / "data",
        station_call="OH2GBA",
        tnc_profile="kenwood-tnc2",
        serial_port="/dev/ttyUSB0",
        hf_enabled="true",
    )
    conn = sqlite3.connect(data / "neoaprs.sqlite")
    conn.execute("ALTER TABLE radio_setting RENAME TO radio_setting_gone")
    conn.close()
    code, out = run(data, capsys)
    assert code == 1, out
    assert (
        f"FAIL  the radios in {data / 'neoaprs.sqlite'} cannot be read: no such table: radio_setting" in out
        and "fix: restore a copy from the backup folder next to it (neoaprs db restore)" in out
    )
    assert not [line for line in out.splitlines() if line.startswith(("ok    radio ", "warn  no radio"))], (
        "the defaults of the flat keys are not this station's radios"
    )
    assert "ok    call OH2GBA" in out and "ok    database " in out, "the settings and the file are read as they are"


def test_a_bluetooth_port_of_windows_says_whether_it_reaches_the_device_or_is_the_incoming_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from neoaprs.serialprobe import PortInfo

    ports = [
        PortInfo(
            "COM7",
            "Serie estándar sobre el vínculo Bluetooth (COM7)",
            "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&000B\\8&C3F3ED0&0&000CBF18376C_C00000000",
            None,
            None,
        ),
        PortInfo(
            "COM8",
            "Serie estándar sobre el vínculo Bluetooth (COM8)",
            "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\8&C3F3ED0&0&000000000000_00000000",
            None,
            None,
        ),
    ]
    monkeypatch.setattr(doctor, "available_ports", lambda: ports)
    monkeypatch.setattr(doctor, "held_by", lambda path: "held by putty (pid 42)" if path == "COM7" else "")
    lines = doctor.check_ports().text.splitlines()
    assert lines[1].endswith("(Bluetooth: the port that reaches the device 000CBF18376C)  held by putty (pid 42)")
    assert lines[2].endswith(
        "(the computer's incoming Bluetooth port: it reaches no device, and NeoAPRS does not offer it)"
    )


def test_an_installer_install_is_told_to_tick_start_at_sign_in_not_to_install_a_daemon_only_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`neoaprs service install` writes a daemon-only entry over the app's own one, with no tray."""
    finding = doctor.check_service(tmp_path, "windows-installer")
    assert finding.fix == doctor.APP_START_FIX and "Start at sign-in" in finding.fix
    assert doctor.check_service(tmp_path, "wheel").fix == "neoaprs service install"
    monkeypatch.setenv("NEOAPRS_INSTALL_KIND", "windows-installer")
    assert doctor.check_service(tmp_path).fix == doctor.APP_START_FIX, "found from the install itself"
