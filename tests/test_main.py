"""The entry point as a process (`python -m neoaprs`): it starts, makes the database and the log, and stops cleanly on SIGTERM, SIGINT and SIGHUP; a database of a newer version is refused with exit 2
and the unit does not restart on that code; the program creates nothing for others."""
import asyncio
import logging
import os
import random
import re
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import PROGRAM, VERSION
from neoaprs import daemon as entry
from neoaprs.daemon import _LogFile, _poll_for_signals, _stop_on_signals, setup_logging
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.conftest import ROOT
from tests.support.env import idle_for
from tests.support.files import fixture_bytes
from tests.support.proc import NEW_GROUP, WINDOWS, send, stop
from tests.support.ptyline import posix_only

_radios: list[socket.socket] = []
# A program that is stopped by a signal is stopped the way its system does: on Windows only Ctrl+Break reaches a child, and only one in a process group of its own (SIGTERM there is a kill).
SIGNALS = [signal.SIGBREAK] if WINDOWS else [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]
LOCAL_SIGNALS = [getattr(signal, n) for n in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK") if hasattr(signal, n)]


@pytest.fixture(autouse=True)
def radios() -> Iterator[None]:
    """The daemons of these tests are given a TCP port on the loopback for a radio (--port): without one a daemon would listen to the operator's /dev/brainbox_* ports."""
    yield
    for server in _radios:
        server.close()
    _radios.clear()


def radio() -> tuple[socket.socket, str]:
    """A listening socket and the `socket://` port that reaches it; the daemon's connection waits in its backlog until a test accepts it."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    _radios.append(server)
    return server, f"socket://127.0.0.1:{server.getsockname()[1]}"


def environment() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}


def start(data: Path, *extra: str) -> "subprocess.Popen[str]":
    port = () if "--port" in extra else ("--port", radio()[1])
    return subprocess.Popen([sys.executable, "-m", "neoaprs", "--data", str(data), *port, "--web-port", "0", *extra], cwd=ROOT, env=environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)


PATIENCE_SEC = 120          # a daemon started or stopped on a machine that is busy with a whole test run takes its time: this is the longest a test waits for it, not how long it takes
# The daemon's first prune (the daily one, which runs at the start) can still be asking the database for its write when the signal comes: the stop cancels the task that asked, the write commits all the same (neoaprs/db.py) and the
# stop says so as a WARNING, on stderr too. That is what the stop is for, not a fault of the run.
CUT_OFF = "a write of the database whose asker was cancelled before the answer came is committed"


def log_of(data: Path) -> str:
    path = data / "neoaprs.log"
    return path.read_text(encoding="utf-8") if path.exists() else "(no log)"


def wait_for(path: Path, text: str, proc: "subprocess.Popen[str]", seconds: float = PATIENCE_SEC) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and text in path.read_text(encoding="utf-8"):
            return
        assert proc.poll() is None, f"the daemon ended early: {proc.communicate()}\nits log:\n{log_of(path.parent)}"
        time.sleep(0.02)
    proc.kill()
    raise AssertionError(f"{text!r} did not appear in {path} in {seconds} s; its log:\n{log_of(path.parent)}")


def ended(proc: "subprocess.Popen[str]", data: Path, seconds: float = PATIENCE_SEC) -> tuple[str, str]:
    """Waits for the daemon to end and gives what it wrote to stdout and stderr; one that is still there when the time is up is killed and the test fails with its log."""
    try:
        return proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise AssertionError(f"the daemon did not end in {seconds} s\nstdout: {out}\nstderr: {err}\nits log:\n{log_of(data)}") from None


def without_the_cut_off(err: str) -> str:
    return "".join(line for line in err.splitlines(keepends=True) if CUT_OFF not in line)


@pytest.mark.parametrize("sig", SIGNALS)
def test_the_daemon_starts_makes_its_database_and_stops_cleanly_on_a_signal(tmp_path: Path, sig: signal.Signals) -> None:
    data = tmp_path / "data"
    proc = start(data)
    wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
    assert (data / DB_NAME).is_file()
    send(proc, sig)
    out, err = ended(proc, data)
    assert proc.returncode == 0, (out, err)
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert f"{PROGRAM} {VERSION} starting, data in {data}" in log and f"{PROGRAM} is closing" in log and log.rstrip().endswith(f"{PROGRAM} ended")
    assert " ERROR " not in log and without_the_cut_off(err) == "", f"nothing but warnings and errors goes to stderr, and a clean run has none; the log:\n{log}"
    db = sqlite3.connect(data / DB_NAME)
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION and db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


@posix_only      # (modes)
def test_the_program_creates_nothing_for_others(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = start(data)
    wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
    stop(proc)
    ended(proc, data)
    assert stat.S_IMODE(data.stat().st_mode) == 0o700, "the folder is made private even when the program made it"
    assert stat.S_IMODE((data / "neoaprs.log").stat().st_mode) == 0o600      # the umask of the program: private from the start
    assert stat.S_IMODE((data / DB_NAME).stat().st_mode) == 0o600


@posix_only      # (modes)
def test_a_data_folder_that_is_there_already_is_made_private_too(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir(mode=0o755)
    proc = start(data)
    wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
    stop(proc)
    ended(proc, data)
    assert stat.S_IMODE(data.stat().st_mode) == 0o700


def test_the_data_folder_is_the_one_in_the_environment_when_none_is_given(tmp_path: Path) -> None:
    data = tmp_path / "from-the-environment"
    proc = subprocess.Popen([sys.executable, "-m", "neoaprs", "--port", radio()[1], "--web-port", "0"], cwd=ROOT, env={**environment(), "NEOAPRS_DATA_DIR": str(data)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
    stop(proc)
    ended(proc, data)
    assert (data / DB_NAME).is_file()


def test_debug_logs_more(tmp_path: Path) -> None:
    quiet, loud = tmp_path / "quiet", tmp_path / "loud"
    for data, flag in ((quiet, ()), (loud, ("--debug",))):
        proc = start(data, *flag)
        wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
        stop(proc)
        ended(proc, data)
    assert " DEBUG " not in (quiet / "neoaprs.log").read_text(encoding="utf-8") and " DEBUG " in (loud / "neoaprs.log").read_text(encoding="utf-8")


def test_a_database_of_a_newer_version_is_refused_without_a_restart_loop(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    db = sqlite3.connect(data / DB_NAME)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 3}")
    db.commit()
    db.close()
    before = (data / DB_NAME).read_bytes()
    proc = start(data)
    out, err = ended(proc, data)
    assert proc.returncode == 2, (out, err)                                           # 2: the unit does not restart on it
    assert "newer NeoAPRS" in (data / "neoaprs.log").read_text(encoding="utf-8") and "newer NeoAPRS" in err
    assert (data / DB_NAME).read_bytes() == before, "the file is not touched"


def test_a_file_that_is_not_a_database_ends_the_daemon_with_2(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / DB_NAME).write_bytes(b"not a database, a sentence of some length " * 30)
    proc = start(data)
    out, err = ended(proc, data)
    assert proc.returncode == 2, (out, err)
    assert "the database could not be used" in (data / "neoaprs.log").read_text(encoding="utf-8")


def test_the_unit_does_not_restart_on_the_exit_code_of_a_database_it_cannot_use() -> None:
    unit = (ROOT / "neoaprs" / "cli" / "neoaprs.service").read_text(encoding="utf-8")
    assert "RestartPreventExitStatus=2" in unit


def test_version_and_help_do_nothing_else(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, "-m", "neoaprs", "--version"], cwd=tmp_path, env={**environment(), "PYTHONPATH": str(ROOT), "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == f"{PROGRAM} {VERSION}"
    helped = subprocess.run([sys.executable, "-m", "neoaprs", "--help"], cwd=tmp_path, env={**environment(), "PYTHONPATH": str(ROOT), "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=60)
    assert helped.returncode == 0 and "--data" in helped.stdout and "--debug" in helped.stdout and "--port" in helped.stdout
    assert list(tmp_path.iterdir()) == [], "nothing was made"


def test_the_daemon_on_a_tcp_port_logs_and_keeps_the_capture_and_stops_on_sigterm_in_time(tmp_path: Path) -> None:
    server, path = radio()
    data = tmp_path / "data"
    proc = start(data, "--port", path)
    wait_for(data / "neoaprs.log", "tnc: opened", proc)
    server.settimeout(20)
    connection, _ = server.accept()
    connection.sendall(fixture_bytes("kiss/thd7-2026-10-21.bin"))
    wait_for(data / "neoaprs.log", "OH2PU-9>APOTC1,OH2RCH-2*:", proc)
    began = time.monotonic()
    stop(proc)
    out, err = ended(proc, data)
    connection.close()
    assert proc.returncode == 0 and time.monotonic() - began < 10, (out, err)
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert "OH2RDK-7>APRX29,OH2RCH-2*,TRACE2-1:!6009.90NT02456.80E&432.500 MHz -> position 60.1650 24.9467 T& 432.500 MHz" in log and log.count(" -> position ") == 4
    assert " ERROR " not in log and without_the_cut_off(err) == "", log
    db = sqlite3.connect(data / DB_NAME)
    assert db.execute("SELECT COUNT(*) FROM packet").fetchone()[0] == 4
    assert [r[0] for r in db.execute("SELECT call FROM station WHERE lat IS NOT NULL AND call <> 'OH2GBA' ORDER BY call")] == ["OH2PU-9", "OH2RDG", "OH2RDK-7", "OH2RDS"]
    assert db.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0, "--port is for this run only: nothing is stored"
    db.close()


def page_url(data: Path, proc: "subprocess.Popen[str]") -> str:
    """The address the daemon says its page is at, once it does."""
    wait_for(data / "neoaprs.log", "web page at http://127.0.0.1:", proc)
    found = re.search(r"web page at (http://127\.0\.0\.1:\d+/)", (data / "neoaprs.log").read_text(encoding="utf-8"))
    assert found, "the log has no 'web page at' line"
    return found.group(1)


def test_the_daemon_serves_the_page_on_a_free_port_it_tells_in_the_log(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = start(data)
    url = page_url(data, proc)
    with urllib.request.urlopen(url, timeout=10) as answer:
        body = answer.read().decode()
        assert answer.status == 200 and "Content-Security-Policy" in answer.headers and answer.headers["X-Frame-Options"] == "DENY"
    assert "NeoAPRS" in body and ("scripts/build-page" in body or 'id="app"' in body), "the placeholder, or the built page"
    stop(proc)
    out, err = ended(proc, data)
    assert proc.returncode == 0, (out, err)
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert " ERROR " not in log and " ERROR " not in err and log.rstrip().endswith(f"{PROGRAM} ended")
    with pytest.raises(OSError):
        urllib.request.urlopen(url, timeout=3)


@contextmanager
def taken_ports(count: int) -> Iterator[int]:
    """`count` neighbouring ports on the loopback, bound and listening; the first of them."""
    for _ in range(50):
        base = random.randrange(20000, 60000)
        held: list[socket.socket] = []
        try:
            for port in range(base, base + count):
                sock = socket.socket()
                held.append(sock)
                sock.bind(("127.0.0.1", port))
                sock.listen()
        except OSError:
            for sock in held:
                sock.close()
            continue
        try:
            yield base
        finally:
            for sock in held:
                sock.close()
        return
    pytest.skip("no run of free neighbouring ports")


def test_a_port_that_is_in_use_moves_the_page_to_the_next_free_one_and_the_log_says_which(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with taken_ports(1) as taken:
        proc = start(data, "--web-port", str(taken))
        url = page_url(data, proc)
        with urllib.request.urlopen(url, timeout=10) as answer:
            assert answer.status == 200
        stop(proc)
        out, err = ended(proc, data)
    assert proc.returncode == 0, (out, err)
    port = int(url.rstrip("/").rsplit(":", 1)[1])
    assert taken < port <= taken + 10, "one of the ten after the port it was asked for"
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert f"web/port {taken} is in use" in log and f"the page is on port {port}" in log and f"web page at {url}" in log and "without the page" not in log


def test_when_the_port_and_the_ten_after_it_are_in_use_the_daemon_runs_without_the_page(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with taken_ports(11) as taken:
        proc = start(data, "--web-port", str(taken))
        wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
        stop(proc)
        out, err = ended(proc, data)
    assert proc.returncode == 0, (out, err)
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert f"the web server cannot listen on 127.0.0.1:{taken}" in log and "goes on without the page" in log and "web page at" not in log
    assert "goes on without the page" in err, "an error is on stderr, where systemctl status shows it"


# ---- one daemon to a data folder

def test_a_second_daemon_on_the_same_data_folder_refuses_to_start_and_the_first_is_not_disturbed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = start(data)
    wait_for(data / "neoaprs.log", f"{PROGRAM} is running", first)
    log_before = (data / "neoaprs.log").read_text(encoding="utf-8")
    second = start(data)
    out, err = ended(second, data)
    assert second.returncode == 2, (out, err)
    assert "another NeoAPRS is already running with the data folder" in err and str(data) in err and "--data" in err
    assert (data / "neoaprs.log").read_text(encoding="utf-8").startswith(log_before) and " ERROR " not in (data / "neoaprs.log").read_text(encoding="utf-8"), "the log is the first one's"
    assert first.poll() is None
    stop(first)
    out, err = ended(first, data)
    assert first.returncode == 0, (out, err)
    third = start(data)                                              # the lock went with the first daemon
    deadline = time.monotonic() + 30
    while (data / "neoaprs.log").read_text(encoding="utf-8").count(f"{PROGRAM} is running") < 2 and time.monotonic() < deadline:        # (the first one's line is in the log already)
        assert third.poll() is None
        time.sleep(0.02)
    stop(third)
    out, err = ended(third, data)
    assert third.returncode == 0, (out, err)


def test_a_daemon_on_another_data_folder_starts_beside_the_first(tmp_path: Path) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    first, second = start(one), start(other)
    for data, proc in ((one, first), (other, second)):
        wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
    for proc in (first, second):
        stop(proc)
        out, err = ended(proc, data)
        assert proc.returncode == 0, (out, err)


# ---- the signals, the log

@pytest.fixture
def signals_restored() -> Iterator[None]:
    names = [n for n in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK") if hasattr(signal, n)]
    saved = {n: signal.getsignal(getattr(signal, n)) for n in names}
    yield
    for n, handler in saved.items():
        signal.signal(getattr(signal, n), handler)


@pytest.mark.parametrize("sig", LOCAL_SIGNALS)
async def test_a_signal_sets_the_stop_event_through_the_loop(signals_restored: None, sig: signal.Signals) -> None:
    stop = _stop_on_signals(asyncio.get_running_loop())
    assert not stop.is_set()
    signal.raise_signal(sig)
    await asyncio.wait_for(stop.wait(), 5)


async def test_a_signal_from_another_thread_of_the_process_is_handled_on_the_loop(signals_restored: None) -> None:
    stop = _stop_on_signals(asyncio.get_running_loop())
    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler)
    await asyncio.get_running_loop().run_in_executor(None, handler, signal.SIGTERM, None)
    await asyncio.wait_for(stop.wait(), 5)


async def test_a_system_without_sighup_but_with_sigbreak_gets_the_ones_it_has(monkeypatch: pytest.MonkeyPatch) -> None:
    set_up: list[int] = []
    windows = SimpleNamespace(SIGTERM=15, SIGINT=2, SIGBREAK=21, signal=lambda number, handler: set_up.append(number))
    monkeypatch.setattr(entry, "signal", windows)
    _stop_on_signals(asyncio.get_running_loop())
    assert sorted(set_up) == [2, 15, 21]


async def test_the_poll_that_wakes_a_windows_loop_ends_with_the_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entry, "SIGNAL_POLL_SEC", 0.01)
    stop = asyncio.Event()
    poll = asyncio.create_task(_poll_for_signals(stop))
    await idle_for(0.05)
    assert not poll.done()
    stop.set()
    await asyncio.wait_for(poll, 5)


def test_a_program_without_a_console_logs_to_the_file_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", None)
    setup_logging(tmp_path, False)
    kinds = [type(h) for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    assert not [k for k in kinds if k is logging.StreamHandler]
    logging.getLogger("neoaprs.test").warning("a line")
    assert "a line" in (tmp_path / "neoaprs.log").read_text(encoding="utf-8")


def rotating(tmp_path: Path) -> tuple[logging.Logger, _LogFile]:
    handler = _LogFile(tmp_path / "x.log", maxBytes=300, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("neoaprs.test.rotating")
    logger.propagate, logger.level = False, logging.INFO
    logger.addHandler(handler)
    return logger, handler


def test_a_rollover_that_another_program_prevents_does_not_lose_lines_nor_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger, handler = rotating(tmp_path)
    failed: list[logging.LogRecord] = []
    monkeypatch.setattr(handler, "handleError", failed.append)
    real_rename = os.rename

    def held(source: object, target: object) -> None:
        raise PermissionError(13, "the file is in use by another program")

    monkeypatch.setattr(os, "rename", held)
    for n in range(30):
        logger.info("line %02d %s", n, "x" * 20)
    assert failed == [], "no record was dropped as an error"
    assert (tmp_path / "x.log").read_text(encoding="utf-8").count("line ") == 30 and not (tmp_path / "x.log.1").exists()
    monkeypatch.setattr(os, "rename", real_rename)
    logger.info("while the retry is not due")
    assert not (tmp_path / "x.log.1").exists(), "not retried at every line"
    handler._not_before = 0.0
    logger.info("after it")
    assert (tmp_path / "x.log.1").exists() and (tmp_path / "x.log").read_text(encoding="utf-8").endswith("after it\n")
    handler.close()
    logger.removeHandler(handler)


def test_a_log_that_cannot_be_reopened_after_a_failed_rollover_is_reported_by_the_handler_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger, handler = rotating(tmp_path)
    failed: list[logging.LogRecord] = []
    monkeypatch.setattr(handler, "handleError", failed.append)
    monkeypatch.setattr(os, "rename", lambda a, b: (_ for _ in ()).throw(PermissionError(13, "in use")))
    monkeypatch.setattr(handler, "_open", lambda: (_ for _ in ()).throw(PermissionError(13, "in use")))
    for n in range(30):
        logger.info("line %02d %s", n, "x" * 20)
    assert failed, "the handler's own error path took it"
    handler.stream = None
    handler.close()
    logger.removeHandler(handler)
