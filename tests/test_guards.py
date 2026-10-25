"""The guards of tests/support/guards.py must be able to fail. Each one is shown on a small test file run by a child pytest with the same fixtures
(a guard that fails at teardown is an ERROR line of that child), and the pure parts are tried directly."""
import asyncio
import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests.conftest import ROOT
from tests.support import guards
from tests.support.ptyline import posix_only

CONFTEST = """
import pytest
from tests.support import guards
from tests.support.guards import isolated_machine, logging_restored, no_leaked_tasks, no_unexpected_errors  # noqa: F401

def pytest_collection_modifyitems(items):
    guards.add_leak_guard(items)
"""

INNER_TESTS = '''
import asyncio, logging, os, socket, sys
from pathlib import Path
import pytest

async def test_clean():
    await asyncio.sleep(0)

async def test_leaks_a_task():
    asyncio.get_running_loop().create_task(asyncio.sleep(60), name="the-leak")

async def test_a_task_that_is_finishing_is_not_a_leak():
    t = asyncio.get_running_loop().create_task(asyncio.sleep(0.02))
    t.add_done_callback(lambda _: None)

async def test_reaches_out_and_swallows_the_error():
    try:
        socket.socket().connect(("192.0.2.1", 80))
    except OSError:
        pass

def test_asks_the_rigctld_of_this_machine():
    try:
        socket.create_connection(("127.0.0.1", 4532), timeout=0.2)
    except OSError:
        pass

def test_asks_the_rotctld_of_this_machine_by_name():
    try:
        socket.create_connection(("localhost", 4533), timeout=0.2)
    except OSError:
        pass

async def test_forgets_to_stop_its_daemon_and_the_guard_stops_it(tmp_path):
    from tests.support.env import Env
    e = Env(tmp_path)
    await e.start()
    assert e.ctl.running

async def test_stops_its_daemon_itself_and_the_guard_does_not_mind(tmp_path):
    from tests.support.env import Env
    e = Env(tmp_path)
    await e.start()
    await e.ctl.stop()

@pytest.mark.skipif(not hasattr(socket, "AF_BLUETOOTH"), reason="this Python has no Bluetooth sockets")
def test_makes_a_bluetooth_socket_and_swallows_the_error():
    try:
        socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    except OSError:
        pass

def test_makes_a_pair_of_sockets_that_stand_in_for_a_radio():
    a, b = socket.socketpair()
    a.close()
    b.close()

def test_sends_a_datagram_out():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(b"x", ("192.0.2.1", 9))
    except OSError:
        pass

def test_looks_up_a_name():
    try:
        socket.getaddrinfo("example.com", 80)
    except OSError:
        pass

def test_talks_to_the_loopback():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        with socket.create_connection(server.getsockname()):
            pass
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.sendto(b"x", ("127.0.0.1", server.getsockname()[1]))
        u.close()

def test_logs_an_error():
    logging.getLogger("something").error("it went wrong")

@pytest.mark.expects_errors
def test_logs_an_error_on_purpose():
    logging.getLogger("something").error("it went wrong")

def test_reads_the_log_itself(caplog):
    logging.getLogger("something").error("it went wrong")
    assert caplog.records

def test_a_warning_and_the_asyncio_logger_are_not_errors():
    logging.getLogger("something").warning("careful")
    logging.getLogger("asyncio").error("Task exception was never retrieved")

class Mine(logging.StreamHandler):
    pass

def test_changes_the_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(Mine())
    logging.getLogger("tornado.access").setLevel(logging.WARNING)
    logging.getLogger("a.new.logger").setLevel(logging.DEBUG)

def test_the_logging_is_as_it_was_before_the_test_that_changed_it():
    root = logging.getLogger()
    assert root.level == logging.WARNING and not [h for h in root.handlers if isinstance(h, Mine)]
    assert logging.getLogger("tornado.access").level == logging.NOTSET and logging.getLogger("a.new.logger").level == logging.NOTSET

def test_the_home_is_empty_and_not_the_real_one():
    home = Path(os.environ["USERPROFILE" if sys.platform == "win32" else "HOME"])          # (Path.home() reads USERPROFILE on Windows)
    assert home == Path.home() and home.is_dir() and home != Path(os.environ["REAL_HOME"])
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        assert Path(os.environ[name]).is_dir() and not any(Path(os.environ[name]).iterdir()), name
    assert len({os.environ[n] for n in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA")}) == 4 and all(Path(os.environ[n]).parent != Path(os.environ["REAL_HOME"]) for n in ("USERPROFILE", "LOCALAPPDATA", "APPDATA"))
    assert not Path(os.environ["XDG_DATA_DIRS"]).exists()
'''


@pytest.fixture(scope="module")
def child_outcomes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """name of the inner test -> 'ok', or 'error' when its teardown failed, or 'failed'."""
    work = tmp_path_factory.mktemp("child")
    (work / "conftest.py").write_text(CONFTEST)
    (work / "test_inner.py").write_text(INNER_TESTS)
    (work / "pytest.ini").write_text(textwrap.dedent("""
        [pytest]
        asyncio_mode = auto
        asyncio_default_fixture_loop_scope = function
        markers = expects_errors: on purpose
    """))
    env = {**os.environ, "PYTHONPATH": str(ROOT), "REAL_HOME": os.environ.get("HOME", "")}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "--color=no", "-q", str(work)], cwd=work, env=env, capture_output=True, text=True, timeout=120)
    outcomes: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        word, _, rest = line.partition(" ")
        if word in ("PASSED", "FAILED", "ERROR") and "::" in rest:
            name = rest.split("::", 1)[1].split(" ")[0]
            outcomes[name] = "error" if word == "ERROR" else "failed" if word == "FAILED" else outcomes.get(name, "ok")
    assert outcomes, proc.stdout + proc.stderr
    return outcomes


@pytest.mark.parametrize("name", [
    "test_clean", "test_a_task_that_is_finishing_is_not_a_leak", "test_forgets_to_stop_its_daemon_and_the_guard_stops_it", "test_stops_its_daemon_itself_and_the_guard_does_not_mind", "test_talks_to_the_loopback", "test_logs_an_error_on_purpose", "test_reads_the_log_itself",
    "test_a_warning_and_the_asyncio_logger_are_not_errors", "test_makes_a_pair_of_sockets_that_stand_in_for_a_radio", "test_the_home_is_empty_and_not_the_real_one", "test_changes_the_logging", "test_the_logging_is_as_it_was_before_the_test_that_changed_it"])
def test_what_is_allowed_passes_the_guards(child_outcomes: dict[str, str], name: str) -> None:
    assert child_outcomes[name] == "ok"


@pytest.mark.parametrize("name", ["test_leaks_a_task", "test_reaches_out_and_swallows_the_error", "test_sends_a_datagram_out", "test_looks_up_a_name", "test_logs_an_error", "test_asks_the_rigctld_of_this_machine", "test_asks_the_rotctld_of_this_machine_by_name",
                                  *(["test_makes_a_bluetooth_socket_and_swallows_the_error"] if hasattr(socket, "AF_BLUETOOTH") else [])])
def test_what_is_forbidden_fails_the_test(child_outcomes: dict[str, str], name: str) -> None:
    assert child_outcomes[name] == "error"


async def test_a_leaked_task_is_found_and_a_finished_one_is_not() -> None:
    assert await guards.leaked_tasks(0.01) == []
    task = asyncio.get_running_loop().create_task(asyncio.sleep(60), name="leak")
    try:
        found = await guards.leaked_tasks(0.01)
        assert found == [task] and "leak" in guards.describe_task(task)
    finally:
        task.cancel()
    assert await guards.leaked_tasks() == []


@pytest.mark.parametrize("host,local", [
    ("127.0.0.1", True), ("127.1.2.3", True), ("::1", True), ("localhost", True), ("0.0.0.0", True), ("", True), (b"127.0.0.1", True), ("::ffff:127.0.0.1", True),
    ("192.0.2.1", False), ("8.8.8.8", False), ("example.com", False), ("2001:db8::1", False), ("::ffff:8.8.8.8", False)])
def test_only_this_machine_is_local(host: str | bytes, local: bool) -> None:
    assert guards.is_local_host(host) is local


def test_the_network_guard_refuses_and_remembers_even_when_the_error_is_swallowed() -> None:
    network = guards.NetworkGuard()
    with pytest.MonkeyPatch.context() as mp:
        network.install(mp.setattr)
        with pytest.raises(guards.NonLoopbackConnection), socket.socket() as s:
            s.connect(("192.0.2.1", 80))
        with pytest.raises(OSError), socket.socket(socket.AF_INET6) as s6:
            s6.connect(("2001:db8::1", 80, 0, 0))
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("example.com", 80)
    assert network.refused == ["192.0.2.1:80", "2001:db8::1:80", "example.com (name lookup)"]


@pytest.mark.parametrize("address", [("127.0.0.1", 4532), ("localhost", 4533), ("::1", 4532, 0, 0), ("0.0.0.0", 4533), ("192.168.1.20", 4532), ("127.0.0.1", 2947), ("localhost", 2947)])
def test_the_rigctld_rotctld_and_gpsd_of_this_machine_are_not_fakes(address: tuple[object, ...]) -> None:
    network = guards.NetworkGuard()
    family = socket.AF_INET6 if address[0] == "::1" else socket.AF_INET
    with pytest.raises(guards.NonLoopbackConnection):
        network.check(address, family)
    assert len(network.refused) == 1


@pytest.mark.parametrize("address", [("127.0.0.1", 7303), ("::1", 7303, 0, 0), ("localhost", 80), ("0.0.0.0", 8080), ("127.0.0.1", 0)])
def test_any_port_of_this_machine_may_be_reached(address: tuple[object, ...]) -> None:
    network = guards.NetworkGuard()
    network.check(address, socket.AF_INET6 if address[0] == "::1" else socket.AF_INET)
    assert network.refused == []


@posix_only
def test_a_unix_socket_is_on_this_machine(tmp_path: Path) -> None:
    network = guards.NetworkGuard()
    network.check(str(tmp_path / "s"), socket.AF_UNIX)
    assert network.refused == []


def test_restoring_the_logging_undoes_levels_handlers_switches_and_says_what_had_changed(caplog: pytest.LogCaptureFixture) -> None:
    import logging
    root, mine = logging.getLogger(), logging.getLogger("guards.restore.mine")
    state = guards.logging_state()
    before = (root.level, list(root.handlers), mine.level)
    handler = logging.NullHandler()
    try:
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)
        mine.setLevel(logging.ERROR)
        mine.disabled = True
        logging.disable(logging.CRITICAL)
        changed = guards.restore_logging(state)
    finally:
        logging.disable(logging.NOTSET)
        root.removeHandler(handler)
        mine.disabled = False
        mine.setLevel(logging.NOTSET)
    assert (root.level, list(root.handlers), mine.level) == before and not mine.disabled and logging.root.manager.disable == 0
    assert any(c.startswith("root:") for c in changed) and any(c.startswith("guards.restore.mine:") for c in changed) and "logging.disable(50)" in changed
    assert guards.restore_logging(guards.logging_state()) == []                   # nothing to undo when nothing changed


async def test_a_database_thread_that_is_left_running_is_found_and_a_closed_one_is_not(tmp_path: Path) -> None:
    """The thread of a Db (neoaprs/db.py) must end with its close(): the guard fails the test that forgets it (a Db that nobody closes keeps a thread and a file open for ever)."""
    from neoaprs.db import Db
    db = Db.at(tmp_path / "x.sqlite")
    await db.start()
    leaked = guards.leaked_db_threads(patience_sec=0.05)
    assert len(leaked) == 1 and leaked[0].is_alive()
    await db.close()
    assert guards.leaked_db_threads() == []


def test_the_bluetooth_guard_refuses_and_remembers_even_when_the_error_is_swallowed() -> None:
    bluetooth = guards.BluetoothGuard()
    with pytest.MonkeyPatch.context() as mp:
        bluetooth.install(mp.setattr)
        a, b = socket.socketpair()                      # a socket of another family is none of its business
        a.close()
        b.close()
        if hasattr(socket, "AF_BLUETOOTH"):
            with pytest.raises(guards.BluetoothTouched):
                socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            l2cap = getattr(socket, "BTPROTO_L2CAP", None)           # (Windows has AF_BLUETOOTH but no L2CAP)
            if l2cap is not None:
                with pytest.raises(guards.BluetoothTouched):
                    socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, l2cap)
            assert len(bluetooth.refused) == (2 if l2cap is not None else 1)
        else:
            assert bluetooth.refused == []


async def test_the_bluetooth_guard_stands_in_for_bleak_and_remembers_a_scan_and_a_connection() -> None:
    bluetooth = guards.BluetoothGuard()
    with pytest.MonkeyPatch.context() as mp:
        bluetooth.install_ble(mp.setitem)
        import bleak
        with pytest.raises(guards.BluetoothTouched):
            await bleak.BleakScanner.find_device_by_address("AA:BB:CC:DD:EE:FF")
        with pytest.raises(guards.BluetoothTouched):
            bleak.BleakClient("AA:BB:CC:DD:EE:FF")
    assert bluetooth.refused == ["a Bluetooth LE scan", "a Bluetooth LE connection"]
