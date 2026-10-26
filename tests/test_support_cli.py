"""`neoaprs support` and the other ways to the support bundle that are not the page's: the Windows Start menu entry, the tray item of the desktop app; and what the daemon writes to its log for a bundle to be read by: the second line of its start
and the exceptions that nothing caught."""
import argparse
import asyncio
import logging
import re
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from neoaprs import PROGRAM, daemon as entry
from neoaprs.cli import supportcmd, supportmake, uncaught
from neoaprs.cli import main as neoaprs
from neoaprs.cli.supportmake import Made
from neoaprs.cli.supportreadme import MAIL
from neoaprs.desktop import menu
from neoaprs.desktop.menu import SUPPORT, AppActions
from neoaprs.desktop.session import Session
from neoaprs.instancelock import InstanceLock
from tests.support.proc import stop
from tests.support.supportdata import fake_folder, zip_members
from tests.test_desktop_logic import PAGE, FakeAutoStart, FakeFrame
from tests.test_main import ended, signals_restored, start, wait_for  # noqa: F401  (a fixture, used by name)


@pytest.fixture(autouse=True)
def no_file_manager(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The file manager is not started by a test: the files it would have shown are kept here."""
    shown: list[Path] = []
    monkeypatch.setattr(supportcmd, "show_file", lambda path: shown.append(path) or True)
    monkeypatch.setattr(supportmake, "show_file", lambda path, *a, **k: shown.append(path) or True)
    monkeypatch.setattr(supportmake.gather, "journal_text", lambda *a, **k: None)
    return shown


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = supportcmd.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---- the command

def test_the_command_makes_the_file_in_the_folder_it_is_given_and_prints_where_and_what_to_do(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = fake_folder(tmp_path)
    code, out, err = run(capsys, "--data", str(data), "--out", str(tmp_path / "wherever" / "deeper"))
    files = list((tmp_path / "wherever" / "deeper").glob("neoaprs-support-OH2GBA-*.zip"))
    assert code == 0 and len(files) == 1
    assert out.strip() == str(files[0]), "the path alone on stdout, for a script"
    assert str(files[0]) in err and f"Send it to {MAIL} with a few words: what you did, what you expected, what happened instead, and roughly when" in err and "README.txt" in err
    assert re.fullmatch(r"neoaprs-support-OH2GBA-\d{8}-\d{6}Z\.zip", files[0].name)
    members = zip_members(files[0])
    assert "state.json" not in members and "not running" in members["summary.txt"] and "neoaprs support, without the daemon" in members["summary.txt"]


def test_the_default_folder_is_the_desktop_and_without_one_the_home_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    home = Path.home()
    data = fake_folder(tmp_path)
    code, out, _ = run(capsys, "--data", str(data))
    assert code == 0 and Path(out.strip()).parent == home, "the test's home has no Desktop"
    (home / "Desktop").mkdir()
    code, out, _ = run(capsys, "--data", str(data))
    assert code == 0 and Path(out.strip()).parent == home / "Desktop"


def test_the_data_folder_is_the_default_one_of_the_environment(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    data = fake_folder(tmp_path)
    monkeypatch.setenv("NEOAPRS_DATA_DIR", str(data))
    code, out, _ = run(capsys, "--out", str(tmp_path / "o"))
    assert code == 0 and "OH2GBA" in Path(out.strip()).name


def test_a_daemon_that_holds_the_folder_is_said_in_the_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = fake_folder(tmp_path)
    lock = InstanceLock(data)
    lock.acquire()
    try:
        code, out, _ = run(capsys, "--data", str(data), "--out", str(tmp_path / "o"))
    finally:
        lock.release()
    summary = zip_members(Path(out.strip()))["summary.txt"]
    assert code == 0 and "Daemon:" in summary and "running, up" in summary and "by its log" in summary


def test_a_folder_that_cannot_be_written_is_said_and_is_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = fake_folder(tmp_path)
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    code, out, err = run(capsys, "--data", str(data), "--out", str(blocker / "inside"))
    assert code == 1 and out == "" and "could not be written" in err and "--out" in err


def test_show_opens_the_file_manager_at_the_file_and_a_failure_of_it_is_only_a_note(tmp_path: Path, capsys: pytest.CaptureFixture[str], no_file_manager: list[Path], monkeypatch: pytest.MonkeyPatch) -> None:
    data = fake_folder(tmp_path)
    code, out, _ = run(capsys, "--data", str(data), "--out", str(tmp_path / "o"), "--show")
    assert code == 0 and no_file_manager == [Path(out.strip())]
    no_file_manager.clear()
    run(capsys, "--data", str(data), "--out", str(tmp_path / "o"))
    assert no_file_manager == [], "only with --show"
    monkeypatch.setattr(supportcmd, "show_file", lambda path: False)
    code, out, err = run(capsys, "--data", str(data), "--out", str(tmp_path / "o"), "--show")
    assert code == 0 and "file manager could not be started" in err and out.strip() in err


class Console:
    def __init__(self, tty: bool) -> None:
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def test_pause_waits_for_enter_only_at_a_console(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    data = fake_folder(tmp_path)
    asked: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or "")
    monkeypatch.setattr(sys, "stdin", Console(False))
    assert run(capsys, "--data", str(data), "--out", str(tmp_path / "o"), "--pause")[0] == 0 and asked == [], "a pipe or a scheduled task is not waited for"
    monkeypatch.setattr(sys, "stdin", Console(True))
    run(capsys, "--data", str(data), "--out", str(tmp_path / "o"))
    assert asked == [], "only with --pause"
    run(capsys, "--data", str(data), "--out", str(tmp_path / "o"), "--pause")
    assert asked == ["Press Enter to close "]
    monkeypatch.setattr(sys, "stdin", None)
    assert run(capsys, "--data", str(data), "--out", str(tmp_path / "o"), "--pause")[0] == 0, "a program without stdin does not wait"


def test_the_window_of_the_start_menu_stays_when_the_command_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or "")
    monkeypatch.setattr(sys, "stdin", Console(True))
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    assert run(capsys, "--data", str(fake_folder(tmp_path)), "--out", str(blocker / "x"), "--pause")[0] == 1 and asked, "so that the message can be read"


def test_the_command_is_in_the_table_and_the_help_and_has_its_own_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert neoaprs(["--help"]) == 0
    help_text = capsys.readouterr().out
    assert re.search(r"^  support +make one file with the logs", help_text, re.M)
    with pytest.raises(SystemExit) as stopped:
        neoaprs(["support", "--help"])
    assert stopped.value.code == 0
    text = capsys.readouterr().out
    assert all(flag in text for flag in ("--data", "--out", "--show", "--pause")) and "Desktop" in text


# ---- the tray

def tray(support: object, owned: bool = True) -> tuple[AppActions, FakeFrame]:
    frame = FakeFrame(True)
    return AppActions(Session(Path("somewhere"), PAGE, owned), frame, FakeAutoStart(), support=support), frame  # type: ignore[arg-type]


def test_the_tray_has_an_item_that_makes_the_bundle_in_a_thread_and_says_where_it_is() -> None:
    seen: list[tuple[Path, str]] = []

    def support(data: Path) -> Made:
        seen.append((data, threading.current_thread().name))
        return Made(Path("/home/ham/Desktop/neoaprs-support-OH2GBA-1.zip"), 123456)
    actions, frame = tray(support)
    assert any(i.key == SUPPORT and i.label == "Collect support logs" for i in actions.items())
    actions.run(SUPPORT)
    assert actions.support_thread is not None
    actions.support_thread.join(10)
    assert seen == [(Path("somewhere"), "neoaprs-app-support")], "in a thread of its own, for the folder of the session"
    assert frame.told == [f"Support file saved: {Path('/home/ham/Desktop/neoaprs-support-OH2GBA-1.zip')}"]                # (the path as the system writes it: backslashes on Windows)


@pytest.mark.expects_errors
def test_a_bundle_that_cannot_be_made_is_told_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    def support(data: Path) -> Made:
        raise OSError("no space left")
    actions, frame = tray(support)
    actions.collect_support()
    assert frame.told == ["The support file could not be made; see neoaprs-app.log"]
    assert any("the support bundle could not be made" in r.getMessage() and r.exc_info for r in caplog.records)


def test_the_tray_item_makes_the_bundle_on_the_desktop_shows_it_and_logs_it(tmp_path: Path, no_file_manager: list[Path], caplog: pytest.LogCaptureFixture) -> None:
    (Path.home() / "Desktop").mkdir()
    data = fake_folder(tmp_path)
    caplog.set_level(logging.INFO, logger="neoaprs.support")
    made = menu.make_for_the_user(data)
    assert made.path.parent == Path.home() / "Desktop" and made.path.is_file() and no_file_manager == [made.path]
    (line,) = [r.getMessage() for r in caplog.records if r.name == "neoaprs.support"]
    assert line.startswith(f"support bundle made: {made.path}, ") and (line.endswith(" KB") or line.endswith(" MB"))
    assert zipfile.is_zipfile(made.path)


def test_a_file_manager_that_does_not_start_is_a_warning_and_not_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(supportmake, "show_file", lambda path, *a, **k: False)
    made = menu.make_for_the_user(fake_folder(tmp_path))
    assert made.path.is_file() and any("file manager could not be started" in r.getMessage() for r in caplog.records)


# ---- the log a bundle is read by

def test_the_start_has_a_second_line_that_says_where_it_runs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = start(data)
    wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
    log = (data / "neoaprs.log").read_text(encoding="utf-8").splitlines()
    pid = proc.pid
    stop(proc)
    out, err = ended(proc, data)
    first = next(i for i, line in enumerate(log) if " starting, data in " in line)
    second = log[first + 1]
    found = re.fullmatch(r"\S+ \S+Z  INFO  running on .+, \S+, Python \d+\.\d+\.\d+, installed as (source|pip|uv-tool|deb|appimage|windows-installer), pid (\d+)", second)
    assert found, second
    if sys.platform != "win32":                                     # (on Windows the venv's python.exe is a launcher that starts the real interpreter: another process id)
        assert int(found.group(2)) == pid
    assert "running on " + entry.system_description() in second
    assert "running on" not in err, "the rest of the INFO lines stay in the log file"


async def test_a_daemon_that_ends_with_an_exception_says_so_in_its_log_and_has_the_hooks_for_the_rest(tmp_path: Path, signals_restored: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    seen: dict[str, object] = {}

    async def broken(controller: object, stop: object, log: object) -> int:
        seen["loop"] = asyncio.get_running_loop().get_exception_handler()
        seen["hook"] = sys.excepthook
        seen["thread"] = threading.excepthook
        raise RuntimeError("the end of the world")
    monkeypatch.setattr(entry, "_serve", broken)
    hooks = (sys.excepthook, threading.excepthook)
    args = argparse.Namespace(data=str(tmp_path), port="", web_port=0, debug=False)
    with pytest.raises(RuntimeError, match="end of the world"):
        await entry._run_locked(args, tmp_path, [])
    assert (sys.excepthook, threading.excepthook) == hooks, "the hooks are put back"
    assert seen["loop"] is not None and seen["hook"] is not hooks[0] and seen["thread"] is not hooks[1]
    log = (tmp_path / "neoaprs.log").read_text(encoding="utf-8")
    assert "CRITICAL  the daemon ends with an exception nothing caught" in log and "RuntimeError: the end of the world" in log and "Traceback" in log


# ---- what escapes

@pytest.mark.expects_errors
def test_an_exception_that_ends_a_thread_is_logged_with_its_traceback(caplog: pytest.LogCaptureFixture) -> None:
    restore = uncaught.install(logging.getLogger("neoaprs.test"))
    try:
        def fail() -> None:
            raise ValueError("a thread went wrong")
        thread = threading.Thread(target=fail, name="neoaprs-test-thread")
        thread.start()
        thread.join()
    finally:
        restore()
    (record,) = [r for r in caplog.records if r.name == "neoaprs.test"]
    assert record.getMessage() == "uncaught exception in the thread neoaprs-test-thread" and record.exc_info is not None and record.exc_info[0] is ValueError


@pytest.mark.expects_errors
def test_an_exception_that_ends_the_program_is_logged_and_ctrl_c_is_not(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[type] = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, trace: printed.append(kind))
    restore = uncaught.install(logging.getLogger("neoaprs.test"), chain=True)
    try:
        for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
            sys.excepthook(kind, kind("x"), None)
    finally:
        restore()
    records = [r for r in caplog.records if r.name == "neoaprs.test"]
    assert [r.levelno for r in records] == [logging.CRITICAL] and "the program ends" in records[0].getMessage()
    assert printed == [RuntimeError, KeyboardInterrupt, SystemExit], "chained: Python still prints, and Ctrl+C is left to it alone"
    assert sys.excepthook is not uncaught


@pytest.mark.expects_errors
async def test_a_failure_in_a_callback_of_the_loop_is_logged_with_its_traceback(caplog: pytest.LogCaptureFixture) -> None:
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(uncaught.loop_handler(logging.getLogger("neoaprs.test")))
    done = asyncio.Event()

    def boom() -> None:
        try:
            raise KeyError("callback failed")
        finally:
            loop.call_soon(done.set)
    loop.call_soon(boom)
    await asyncio.wait_for(done.wait(), 5)
    await asyncio.sleep(0)
    (record,) = [r for r in caplog.records if r.name == "neoaprs.test"]
    assert record.getMessage().startswith("event loop: Exception in callback") and "boom" in record.getMessage()
    assert record.exc_info is not None and record.exc_info[0] is KeyError


@pytest.mark.expects_errors
async def test_a_task_nobody_awaited_that_failed_is_logged_by_the_loop_handler(caplog: pytest.LogCaptureFixture) -> None:
    import gc
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(uncaught.loop_handler(logging.getLogger("neoaprs.test")))

    async def fail() -> None:
        raise ValueError("a forgotten task failed")
    asyncio.get_running_loop().create_task(fail(), name="forgotten")
    await asyncio.sleep(0.05)
    gc.collect()
    await asyncio.sleep(0.05)
    records = [r for r in caplog.records if r.name == "neoaprs.test"]
    assert records and "Task exception was never retrieved" in records[0].getMessage() and "forgotten" in records[0].getMessage()
    assert records[0].exc_info is not None and records[0].exc_info[0] is ValueError


def test_a_context_with_no_exception_is_logged_without_a_traceback(caplog: pytest.LogCaptureFixture) -> None:
    handler = uncaught.loop_handler(logging.getLogger("neoaprs.test"))
    with caplog.at_level(logging.ERROR, logger="neoaprs.test"):
        handler(asyncio.new_event_loop(), {"message": "Fatal error on transport", "transport": "x" * 1000})
    (record,) = caplog.records
    assert record.exc_info is None and record.getMessage().startswith("event loop: Fatal error on transport (transport: xxxx") and len(record.getMessage()) < 400
