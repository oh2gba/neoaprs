"""The command line and the desktop app on a data folder that cannot be read or written, a garbled
answer from a port, and the small edges of the commands."""

import os
import socket
import sys
import threading
from pathlib import Path

import pytest

from neoaprs.cli import daemonstate, doctor, logfile, replaycmd, servicesystemd, stopcmd
from neoaprs.cli.gpsreplaycmd import position
from neoaprs.cli.gpstrip import Trip
from neoaprs.desktop import autostart, cmd
from neoaprs.desktop.autostart import AutoStartError, RunKeyAutoStart
from neoaprs.desktop.session import DaemonWatch, Session
from neoaprs.instancelock import InstanceLock, is_file, is_held
from tests.test_desktop_logic import PAGE, FakeDaemon, actions_for
from tests.test_service import Linux, fake_winreg

not_root = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a folder's mode binds only a user who is not root",
)


@pytest.fixture
def folder(tmp_path: Path):  # type: ignore[no-untyped-def]
    data = tmp_path / "data"
    data.mkdir()
    yield data
    data.chmod(0o700)


@not_root
def test_a_stop_that_cannot_write_its_file_says_it_did_not_stop(folder: Path) -> None:
    lock = InstanceLock(folder)
    lock.acquire()
    folder.chmod(0o500)
    try:
        assert stopcmd.stop_daemon(folder, 0.5) is False
    finally:
        lock.release()


@pytest.mark.expects_errors
def test_quit_ends_the_app_even_when_the_daemon_cannot_be_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    actions, frame, daemon, _ = actions_for(owned=True)

    def refuse(data: Path, seconds: float) -> bool:
        raise PermissionError("neoaprs.stop")

    monkeypatch.setattr(daemon, "stop", refuse)
    actions.quit_now()
    assert frame.quits == 1


@not_root
def test_a_folder_that_cannot_be_looked_into_is_not_a_crash(folder: Path) -> None:
    (folder / "neoaprs.lock").write_text("")
    folder.chmod(0)
    assert not is_file(folder / "neoaprs.lock") and not is_held(folder) and not daemonstate.is_running(folder)
    assert not logfile.network_is_on(folder)
    assert doctor.check_database(folder)[0].status == "ok"
    assert doctor.check_map(folder).status == "warn"
    assert daemonstate.describe(folder)[0] is False


@pytest.mark.expects_errors
def test_the_watch_goes_on_after_a_look_that_failed() -> None:
    gone = threading.Event()
    daemon = FakeDaemon(up=True)
    answers = iter([OSError("denied")])

    def running(data: Path) -> bool:
        found = next(answers, None)
        if found is not None:
            raise found
        return False

    daemon.running = running  # type: ignore[method-assign]
    watch = DaemonWatch(Session(Path("somewhere"), PAGE, owned=True), gone.set, daemon, every=0.02)
    watch.start()
    assert gone.wait(5)


@not_root
def test_an_existing_folder_that_cannot_be_written_gets_a_message_and_exit_code_one(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    said: list[str] = []
    monkeypatch.setattr(cmd.opencmd, "tell_the_user", said.append)
    folder.chmod(0o500)
    try:
        assert cmd._main(["--data", str(folder)]) == 1
    finally:
        folder.chmod(0o700)
    assert said and "cannot be made or used" in said[0]


def test_a_port_file_that_cannot_be_written_lets_go_of_the_app_lock(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (folder / "neoaprs-app.port").mkdir()
    single = cmd.SingleApp(folder)
    with pytest.raises(OSError):
        single.acquire()
    assert not single.running()


@pytest.mark.parametrize("char", ['"', "`", "$", "\\", "%", " "])
def test_the_exec_line_reads_back_as_it_was_written(char: str) -> None:
    argument = f"/tmp/a{char}b"
    line = autostart.desktop_exec(["prog", argument])
    word = line[len("prog ") :]
    if word.startswith('"'):
        word = word[1:-1]
    # the file format's string escape, which the desktop file is read with first
    once = word.replace("\\\\", "\0").replace("\0", "\\")
    for special in ('"', "`", "$", "\\"):
        once = once.replace("\\" + special, special)  # then the quoting rule of the Exec key
    assert once.replace("%%", "%") == argument


def test_a_registry_that_refuses_is_an_autostart_error_and_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    module = fake_winreg({})

    def refuse(*args: object) -> None:
        raise PermissionError("locked by policy")

    module.CreateKeyEx = refuse  # type: ignore[attr-defined]
    module.OpenKey = refuse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "winreg", module)
    run = RunKeyAutoStart(["neoaprs-app", "--tray"])
    assert run.enabled() is False
    with pytest.raises(AutoStartError):
        run.enable()
    with pytest.raises(AutoStartError):
        run.disable()


def test_an_answer_that_is_not_http_is_no_page() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    def answer() -> None:
        conn, _ = server.accept()
        conn.recv(1024)
        conn.sendall(b"not http at all\r\n\r\n")
        conn.close()

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    try:
        assert daemonstate.page_answers(f"http://127.0.0.1:{server.getsockname()[1]}/") is False
    finally:
        thread.join(5)
        server.close()


def test_a_service_install_beside_another_daemon_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    linux = Linux(tmp_path, monkeypatch)
    monkeypatch.setattr(servicesystemd, "is_running", lambda data: True)
    monkeypatch.setattr(servicesystemd, "ask", lambda *command: "")
    assert linux.run("install") == 0
    assert "another NeoAPRS holds the data folder" in capsys.readouterr().out


def test_the_trip_never_leaves_the_earth() -> None:
    trip = Trip(0.0, 179.9995, 50.0)
    samples = [trip.step() for _ in range(700)]
    assert all(-180.0 <= s.lon < 180.0 and -90.0 <= s.lat <= 90.0 for s in samples)
    assert any(s.lon < 0 for s in samples)
    with pytest.raises(ValueError):
        position("90,0")
    assert position("89.8,10") == (89.8, 10.0)


def test_pty_replay_on_windows_is_one_plain_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(replaycmd.sys, "platform", "win32")
    assert replaycmd.main(["--pty"]) == 2
    assert (lambda c: c.out + c.err)(capsys.readouterr()).strip() == "replay: --pty is not available on Windows"


def test_no_lines_of_the_log_are_none(tmp_path: Path) -> None:
    path = tmp_path / "log"
    path.write_text("".join(f"{n}\n" for n in range(100)))
    assert daemonstate.tail(path, 0) == [] and daemonstate.tail(path, -90) == [] and len(daemonstate.tail(path, 5)) == 5
