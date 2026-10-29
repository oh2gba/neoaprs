"""`neoaprs doctor`: the checklist on a temporary data folder: each check ok, warn or fail with its fix, the exit code, and the pieces that tell about the computer (the group of the serial devices, brltty and
ModemManager, Firefox as a Flatpak, the ports, a daemon that holds the data folder). The ports are listed by a stand-in; nothing is opened, written or sent."""
import http.server
import sqlite3
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.cli import dbcmd, doctor, hostcheck
from neoaprs.cli.daemonstate import describe, is_running, page_answers, page_url, tail
from neoaprs.instancelock import InstanceLock
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.serialprobe import PortInfo


@pytest.fixture(autouse=True)
def this_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A computer with one TNC cable, in the group of its serial devices, with neither brltty nor ModemManager."""
    monkeypatch.setattr(doctor, "available_ports", lambda: [PortInfo("/dev/ttyUSB0", "FT232R USB UART", "USB VID:PID=0403:6001", 0x0403, 0x6001)])
    monkeypatch.setattr(doctor, "serial_group_check", lambda: hostcheck.GroupCheck("ok", "dialout", ""))
    monkeypatch.setattr(doctor, "brltty_installed", lambda: False)
    monkeypatch.setattr(doctor, "modemmanager_installed", lambda: False)
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: None)


def run(data: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = doctor.main(["--data", str(data)])
    return code, capsys.readouterr().out


def lines_of(text: str, status: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(status)]


def set_up(data: Path, **settings: str) -> None:
    for key, value in settings.items():
        assert dbcmd.main(["--data", str(data), "set", key.replace("_", "/", 1), value]) == 0


def test_a_fresh_computer_has_warnings_with_their_fixes_and_no_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    assert "the service is not set up" in text and "fix: neoaprs service install" in text
    assert "no daemon is running" in text
    assert out.rstrip().splitlines()[-1].endswith("to look at")


def test_a_data_folder_with_a_database_a_call_and_a_map_is_all_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")
    (data / "basemap.pmtiles").write_bytes(b"x" * 3_000_000)
    (data / "basemap-world.pmtiles").write_bytes(b"x" * 1_000_000)
    monkeypatch.setattr(doctor.servicecmd, "backend_for", lambda system: type("B", (), {"installed": staticmethod(lambda plan: (True, "the user unit /x/neoaprs.service"))}))
    code, out = run(data, capsys)
    assert code == 0, out
    assert f"database neoaprs.sqlite, version {SCHEMA_VERSION}" in out and "call OH2GBA" in out
    assert "data folder" in out and "(writable)" in out
    assert "base map: basemap.pmtiles 3 MB, basemap-world.pmtiles 1 MB" in out and "service set up: the user unit /x/neoaprs.service" in out
    assert not lines_of(out, "warn") and out.rstrip().splitlines()[-1] == "all is well"


def test_a_call_that_cannot_transmit_is_a_warning_with_the_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="N0CALL")                 # (a placeholder call is stored as it is and does not transmit)
    code, out = run(data, capsys)
    assert code == 0 and "the call N0CALL cannot transmit" in out


def test_a_folder_that_is_a_file_and_a_database_that_is_not_one_fail_and_the_exit_code_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file").write_text("x")
    code, out = run(tmp_path / "file", capsys)
    assert code == 1 and "is not a folder" in out and "fix: give another folder with --data" in out
    data = tmp_path / "data"
    data.mkdir()
    (data / "neoaprs.sqlite").write_bytes(b"this is not a database" * 100)
    code, out = run(data, capsys)
    assert code == 1 and "cannot be read" in out and "fix: if it is damaged" in out and out.rstrip().splitlines()[-1].startswith("1 to fix")


def test_a_database_of_a_newer_neoaprs_fails_and_one_of_an_older_version_is_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")
    conn = sqlite3.connect(data / "neoaprs.sqlite")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 4}")
    conn.close()
    code, out = run(data, capsys)
    assert code == 1 and f"database version {SCHEMA_VERSION + 4}: made by a newer NeoAPRS" in out and "update NeoAPRS" in out
    conn = sqlite3.connect(data / "neoaprs.sqlite")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
    conn.close()
    code, out = run(data, capsys)
    assert code == 0 and f"database version {SCHEMA_VERSION - 1}, this NeoAPRS uses {SCHEMA_VERSION}" in out and "migrates the file" in out


def test_the_doctor_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    set_up(data, station_call="OH2GBA")
    before = sorted((p.name, p.stat().st_size) for p in data.iterdir() if p.name != "neoaprs.lock")
    run(data, capsys)
    run(tmp_path / "nowhere", capsys)
    assert sorted((p.name, p.stat().st_size) for p in data.iterdir() if p.name != "neoaprs.lock") == before and not (tmp_path / "nowhere").exists()


def test_no_port_and_the_things_that_grab_one_are_said_with_the_way_out(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "available_ports", lambda: [])
    monkeypatch.setattr(doctor, "brltty_installed", lambda: True)
    monkeypatch.setattr(doctor, "modemmanager_installed", lambda: True)
    monkeypatch.setattr(doctor, "serial_group_check", lambda: hostcheck.GroupCheck("missing", "dialout", "sudo usermod -aG dialout jane   (then log out and in again)"))
    code, out = run(tmp_path / "data", capsys)
    assert code == 0
    assert "no serial port is listed by the system" in out and "socket://127.0.0.1:8001" in out
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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()
    thread.join(5)


def log_of(data: Path, *lines: str) -> None:
    data.mkdir(exist_ok=True)
    (data / "neoaprs.log").write_text("\n".join(lines) + "\n")


def test_a_daemon_that_holds_the_lock_is_found_with_its_page(tmp_path: Path, page: int, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    log_of(data, "2026-10-22 12:00:00Z  INFO  NeoAPRS 0.1.0 starting, data in /x", f"2026-10-22 12:00:01Z  INFO  web page at http://127.0.0.1:{page}/")
    assert not is_running(data)
    lock = InstanceLock(data)
    lock.acquire()
    try:
        assert is_running(data) and page_url(data) == f"http://127.0.0.1:{page}/" and page_answers(f"http://127.0.0.1:{page}/")
        assert describe(data) == (True, f"a daemon is running; its page http://127.0.0.1:{page}/ answers")
        code, out = run(data, capsys)
        assert code == 0 and f"its page http://127.0.0.1:{page}/ answers" in out
    finally:
        lock.release()
    assert not is_running(data), "the lock was taken for a moment to find out, and let go"


def test_a_page_that_does_not_answer_and_a_run_without_a_page_are_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    log_of(data, "x starting, data in /x", "y web page at http://127.0.0.1:9/")
    lock = InstanceLock(data)
    lock.acquire()
    try:
        code, out = run(data, capsys)
        assert code == 0 and "http://127.0.0.1:9/ does not answer" in out and "fix: open the log" in out
        log_of(data, "x starting, data in /x", "y web page at http://127.0.0.1:9/", "z starting, data in /x", "the web server cannot listen on 127.0.0.1:7303: in use; NeoAPRS goes on without the page")
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
    assert hostcheck.decide(["dialout"], {"dialout", "users"}, {"dialout"}, "jane") == hostcheck.GroupCheck("ok", "dialout", "")
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
    mine = grp.getgrgid(os.getgid()).gr_name
    if mine == "root":
        pytest.skip("root owns the files it makes: no group to be in")
    check = hostcheck.serial_group_check([str(device)], "someone")
    assert (check.status, check.group) == ("ok", mine), "the group of the file is the test user's own, which this session has"



def test_brltty_and_modemmanager_are_found_by_their_programs_or_their_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def fake_flatpak(installed: bool = True, user: str = NO_OVERRIDES, system: str = NO_OVERRIDES, permissions: str = "[Session Bus Policy]\norg.freedesktop.portal.Desktop=talk\n") -> tuple[list[list[str]], hostcheck.FlatpakRun]:
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
    assert check is not None and check.status == "missing" and "NOTIFY_IGNORE_PORTAL" not in check.fix and "--talk-name=org.freedesktop.Notifications" in check.fix
    check = hostcheck.firefox_flatpak(fake_flatpak(user="[Session Bus Policy]\norg.freedesktop.Notifications=talk\n")[1], "KDE", True)
    assert check is not None and "--env=NOTIFY_IGNORE_PORTAL=1" in check.fix and "--talk-name" not in check.fix


def test_the_overrides_are_found_wherever_they_are_set(on_linux: None) -> None:
    runs = (
        fake_flatpak(user=BOTH_OVERRIDES)[1],
        fake_flatpak(system=BOTH_OVERRIDES)[1],
        fake_flatpak(user="[Environment]\nNOTIFY_IGNORE_PORTAL=1\n", permissions="[Session Bus Policy]\norg.freedesktop.Notifications=talk\n")[1],
    )
    for run in runs:
        assert hostcheck.firefox_flatpak(run, "KDE", True) == hostcheck.FlatpakFirefox("ok", "")


def test_it_does_not_apply_without_kde_a_flatpak_command_or_a_flatpak_firefox(monkeypatch: pytest.MonkeyPatch, on_linux: None) -> None:
    run = fake_flatpak()[1]
    assert hostcheck.firefox_flatpak(run, "GNOME", True) is None
    assert hostcheck.firefox_flatpak(run, "", True) is None
    assert hostcheck.firefox_flatpak(run, "KDE", False) is None
    assert hostcheck.firefox_flatpak(fake_flatpak(installed=False)[1], "KDE", True) is None
    assert hostcheck.firefox_flatpak(run, "ubuntu:KDE", True) is not None
    monkeypatch.setattr(hostcheck.sys, "platform", "win32")
    assert hostcheck.firefox_flatpak(run, "KDE", True) is None


def test_the_desktop_comes_from_the_environment_and_flatpak_from_the_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, on_linux: None) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert hostcheck.firefox_flatpak(fake_flatpak()[1]) is None


def test_the_flatpak_runner_survives_a_missing_program(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert hostcheck.run_flatpak(["info", "org.mozilla.firefox"]) == (1, "")


def test_the_doctor_warns_with_the_commands_for_firefox_as_a_flatpak(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    fix = "flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox\n      then restart Firefox"
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: hostcheck.FlatpakFirefox("missing", fix))
    code, out = run(tmp_path / "data", capsys)
    assert code == 0
    assert "warn  Firefox is a Flatpak: on KDE its web pop-ups can go missing" in out
    assert "fix: flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox" in out
    monkeypatch.setattr(doctor, "firefox_flatpak", lambda: hostcheck.FlatpakFirefox("ok", ""))
    assert "ok    Firefox is a Flatpak: its web pop-ups go to the desktop's notification service" in run(tmp_path / "data", capsys)[1]
