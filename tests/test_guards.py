"""The guards of tests/support/guards.py must be able to fail. Each one is shown on a small test
file run by a child pytest with the same fixtures (a guard that fails at teardown is an ERROR line
of that child), and the pure parts are tried directly."""

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import types
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import ROOT
from tests.support import guards
from tests.support.ptyline import AF_UNIX, posix_only

CONFTEST = """
import pytest
from tests.support import guards
from tests.support.guards import doors_of_the_module, doors_of_the_session, isolated_machine, logging_restored, no_leaked_tasks, no_unexpected_errors  # noqa: F401

def pytest_collection_modifyitems(items):
    guards.add_leak_guard(items)
"""

INNER_TESTS = """
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

async def test_leaves_a_stop_that_never_ends(monkeypatch):
    from tests.support import env, guards
    monkeypatch.setattr(guards, "TEARDOWN_LIMIT_SEC", 0.3)
    env.remember_stop(lambda: asyncio.Event().wait())

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

def test_starts_a_file_in_the_folder_of_the_shipped_programs_and_swallows_the_error():
    import subprocess
    from neoaprs import bundled
    try:
        subprocess.Popen([str(bundled.tools_dir() / "mercury" / "no-such-program"), "-l"])        # (not the real Mercury: were the guard broken, nothing would start)
    except OSError:
        pass

@pytest.mark.real_direwolf
def test_marked_for_the_real_direwolf_keeps_its_folder_and_finds_no_mercury():
    import subprocess
    from neoaprs import bundled, direwolfprogram, mercuryhelper
    assert direwolfprogram.tools_dir() == bundled.tools_dir() and mercuryhelper.find() is None and not mercuryhelper.expected_program().parent.parent.exists()
    with pytest.raises(FileNotFoundError):
        subprocess.Popen([str(bundled.tools_dir() / "direwolf" / "no-such-program")])            # (Direwolf's folder is open to it: the file is simply not there)

@pytest.mark.real_direwolf
def test_marked_for_the_real_direwolf_starts_a_file_of_mercurys_folder_and_swallows_the_error():
    import subprocess
    from neoaprs import bundled
    try:
        subprocess.Popen([str(bundled.tools_dir() / "mercury" / "no-such-program")])
    except OSError:
        pass

def test_connects_to_the_port_of_a_real_mercury_and_swallows_the_error():
    from neoaprs.mercury import BROADCAST_PORT
    try:
        socket.create_connection(("127.0.0.1", BROADCAST_PORT), timeout=0.2)
    except OSError:
        pass

def test_connects_to_the_kiss_port_of_a_real_direwolf_and_swallows_the_error():
    from neoaprs.radiotypes.kisstcp import TCP_PORT
    try:
        socket.create_connection(("localhost", int(TCP_PORT.default)), timeout=0.2)
    except OSError:
        pass

def test_the_default_alert_command_is_not_run_and_a_command_of_the_tests_own_is(monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr("neoaprs.nodevices.on", lambda: False)                  # (the switch lifted, as tests/conftest.py devices_are_fakes has it)
    from neoaprs.config import DEFAULTS
    from neoaprs.services.alerts import Alerts
    assert Alerts(lambda: DEFAULTS)._command() == "" and Alerts(lambda: replace(DEFAULTS, messages_alert_command="true"))._command() == "true"

def test_the_journal_of_this_machine_is_not_read():
    import inspect
    from neoaprs.cli import supportgather, supportmake
    for journal in (supportgather.journal_text, inspect.signature(supportmake.make_bundle).parameters["journal"].default):
        if journal is None:
            continue
        which = inspect.signature(journal).parameters.get("which")
        assert which is None or which.default("journalctl") is None, "it would look for journalctl on this machine"       # (asked before it is called: a broken guard reads nothing)
        assert journal() is None

def test_finds_no_modem_program_where_the_installation_has_them(tmp_path):
    from neoaprs import direwolfprogram, mercuryhelper
    assert mercuryhelper.find() is None and direwolfprogram.find() is None
    assert not mercuryhelper.expected_program().parent.parent.exists() and not direwolfprogram.expected_program().parent.parent.exists()

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
"""


INNER_MODULE_REACHES_OUT = """
import socket, pytest

@pytest.fixture(scope="module")
def reaches_out():
    try:
        socket.socket().connect(("192.0.2.1", 80))
    except OSError:
        pass

def test_a_module_fixture_reaches_out_and_swallows_the_error(reaches_out):
    pass
"""

INNER_MODULE_LOOPBACK = """
import socket, pytest

@pytest.fixture(scope="module")
def talks_to_the_loopback():
    server = socket.create_server(("127.0.0.1", 0))
    socket.create_connection(server.getsockname()).close()
    yield
    server.close()

def test_a_module_fixture_that_talks_to_the_loopback_is_left_alone(talks_to_the_loopback):
    pass
"""


INNER_SESSION_REACHES_OUT = """
import socket, pytest

@pytest.fixture(scope="session")
def reaches_out_at_the_end():
    yield
    try:
        socket.socket().connect(("192.0.2.1", 80))
    except OSError:
        pass

def test_a_session_fixture_reaches_out_at_its_end_and_swallows_the_error(reaches_out_at_the_end):
    pass
"""


@pytest.fixture(scope="module")
def child_outcomes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """name of the inner test -> 'ok', or 'error' when its teardown failed, or 'failed'."""
    work = tmp_path_factory.mktemp("child")
    (work / "conftest.py").write_text(CONFTEST)
    (work / "test_inner.py").write_text(INNER_TESTS)
    (work / "test_inner_reaches_out.py").write_text(INNER_MODULE_REACHES_OUT)
    (work / "test_inner_loopback.py").write_text(INNER_MODULE_LOOPBACK)
    # (the last file: the end of the session is its teardown)
    (work / "test_zz_inner_session.py").write_text(INNER_SESSION_REACHES_OUT)
    (work / "pytest.ini").write_text(
        textwrap.dedent("""
        [pytest]
        asyncio_mode = auto
        asyncio_default_fixture_loop_scope = function
        markers =
            expects_errors: on purpose
            real_direwolf: keeps Direwolf's folder
    """)
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT), "REAL_HOME": os.environ.get("HOME", "")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "--color=no", "-q", str(work)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    outcomes: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        word, _, rest = line.partition(" ")
        if word in ("PASSED", "FAILED", "ERROR") and "::" in rest:
            name = rest.split("::", 1)[1].split(" ")[0]
            outcomes[name] = "error" if word == "ERROR" else "failed" if word == "FAILED" else outcomes.get(name, "ok")
    assert outcomes, proc.stdout + proc.stderr
    return outcomes


@pytest.mark.parametrize(
    "name",
    [
        "test_clean",
        "test_a_task_that_is_finishing_is_not_a_leak",
        "test_forgets_to_stop_its_daemon_and_the_guard_stops_it",
        "test_stops_its_daemon_itself_and_the_guard_does_not_mind",
        "test_talks_to_the_loopback",
        "test_logs_an_error_on_purpose",
        "test_reads_the_log_itself",
        "test_a_warning_and_the_asyncio_logger_are_not_errors",
        "test_makes_a_pair_of_sockets_that_stand_in_for_a_radio",
        "test_finds_no_modem_program_where_the_installation_has_them",
        "test_the_home_is_empty_and_not_the_real_one",
        "test_changes_the_logging",
        "test_the_logging_is_as_it_was_before_the_test_that_changed_it",
        "test_marked_for_the_real_direwolf_keeps_its_folder_and_finds_no_mercury",
        "test_the_default_alert_command_is_not_run_and_a_command_of_the_tests_own_is",
        "test_the_journal_of_this_machine_is_not_read",
        "test_a_module_fixture_that_talks_to_the_loopback_is_left_alone",
    ],
)
def test_what_is_allowed_passes_the_guards(child_outcomes: dict[str, str], name: str) -> None:
    assert child_outcomes[name] == "ok"


@pytest.mark.parametrize(
    "name",
    [
        "test_leaks_a_task",
        "test_leaves_a_stop_that_never_ends",
        "test_reaches_out_and_swallows_the_error",
        "test_sends_a_datagram_out",
        "test_looks_up_a_name",
        "test_logs_an_error",
        "test_asks_the_rigctld_of_this_machine",
        "test_asks_the_rotctld_of_this_machine_by_name",
        "test_starts_a_file_in_the_folder_of_the_shipped_programs_and_swallows_the_error",
        "test_marked_for_the_real_direwolf_starts_a_file_of_mercurys_folder_and_swallows_the_error",
        "test_connects_to_the_port_of_a_real_mercury_and_swallows_the_error",
        "test_connects_to_the_kiss_port_of_a_real_direwolf_and_swallows_the_error",
        "test_a_module_fixture_reaches_out_and_swallows_the_error",
        "test_a_session_fixture_reaches_out_at_its_end_and_swallows_the_error",
        *(["test_makes_a_bluetooth_socket_and_swallows_the_error"] if hasattr(socket, "AF_BLUETOOTH") else []),
    ],
)
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


async def test_a_stop_that_hangs_when_the_test_is_over_fails_the_test_by_its_name_and_ends() -> None:
    # (a word that never comes: the Db's close on Windows 11 waited 25 minutes for one)
    hung = asyncio.get_running_loop().create_future()

    async def never_ends() -> None:
        await hung

    # (taken off the list by the stop_all that runs it)
    guards.env_module.remember_stop(never_ends)
    with pytest.raises(
        pytest.fail.Exception, match=r"tests/test_x\.py::test_y: stopping what the test started did not end in 0\.2 s"
    ):
        await asyncio.wait_for(guards.torn_down_within(0.2, "tests/test_x.py::test_y"), 10.0)
    assert hung.cancelled()


@pytest.mark.parametrize(
    "host,local",
    [
        ("127.0.0.1", True),
        ("127.1.2.3", True),
        ("::1", True),
        ("localhost", True),
        ("0.0.0.0", True),
        ("", True),
        (b"127.0.0.1", True),
        ("::ffff:127.0.0.1", True),
        ("192.0.2.1", False),
        ("8.8.8.8", False),
        ("example.com", False),
        ("2001:db8::1", False),
        ("::ffff:8.8.8.8", False),
    ],
)
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


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 4532),
        ("localhost", 4533),
        ("::1", 4532, 0, 0),
        ("0.0.0.0", 4533),
        ("192.168.1.20", 4532),
        ("127.0.0.1", 2947),
        ("localhost", 2947),
    ],
)
def test_the_rigctld_rotctld_and_gpsd_of_this_machine_are_not_fakes(address: tuple[object, ...]) -> None:
    network = guards.NetworkGuard()
    family = socket.AF_INET6 if address[0] == "::1" else socket.AF_INET
    with pytest.raises(guards.NonLoopbackConnection):
        network.check(address, family)
    assert len(network.refused) == 1


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 14580),
        ("localhost", 10152),
        ("::1", 14580, 0, 0),
        ("rotate.aprs2.net", 14580),
        ("185.1.2.3", 14580),
    ],
)
def test_the_real_aprs_is_is_not_reached_by_a_test(address: tuple[object, ...]) -> None:
    network = guards.NetworkGuard()
    family = socket.AF_INET6 if address[0] == "::1" else socket.AF_INET
    with pytest.raises(guards.NonLoopbackConnection, match="APRS-IS"):
        network.check(address, family)
    assert len(network.refused) == 1 and "APRS-IS" in network.refused[0]


def test_the_names_of_the_aprs_is_servers_are_not_looked_up_and_say_so() -> None:
    network = guards.NetworkGuard()
    with pytest.MonkeyPatch.context() as mp:
        network.install(mp.setattr)
        for name in ("rotate.aprs2.net", "euro.aprs2.net", "first.aprs.net", "ROTATE.APRS2.NET."):
            with pytest.raises(socket.gaierror):
                socket.getaddrinfo(name, 14580)
    assert network.refused == [
        f"{name} (name lookup of an APRS-IS server)"
        for name in ("rotate.aprs2.net", "euro.aprs2.net", "first.aprs.net", "ROTATE.APRS2.NET.")
    ]


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 7303),
        ("::1", 7303, 0, 0),
        ("localhost", 80),
        ("0.0.0.0", 8080),
        ("127.0.0.1", 0),
        ("127.0.0.1", 20000),
    ],
)
def test_any_port_of_this_machine_may_be_reached(address: tuple[object, ...]) -> None:
    network = guards.NetworkGuard()
    network.check(address, socket.AF_INET6 if address[0] == "::1" else socket.AF_INET)
    assert network.refused == []


def _modem_ports() -> list[int]:
    from neoaprs import direwolf, mercury, mercuryhelper
    from neoaprs.mercury import BROADCAST_PORT, CONTROL_OFFSET, UI_OFFSET
    from neoaprs.radiotypes.kisstcp import TCP_PORT

    last = BROADCAST_PORT + mercuryhelper.PORT_TRIES - 1
    return [
        int(TCP_PORT.default),
        direwolf.OWN_AGW_PORT,
        mercury.OWN_UI_PORT,
        direwolf.FIRST_PORT,
        direwolf.FIRST_PORT + direwolf.PORT_TRIES - 1,
        BROADCAST_PORT,
        BROADCAST_PORT + CONTROL_OFFSET,
        BROADCAST_PORT + CONTROL_OFFSET + 1,
        BROADCAST_PORT + UI_OFFSET,
        last,
        last + CONTROL_OFFSET + 1,
        last + UI_OFFSET,
    ]


@pytest.mark.parametrize("port", _modem_ports())
def test_a_port_of_this_machine_a_real_modem_may_listen_on_is_not_reached(port: int) -> None:
    """Direwolf's own default and the ports NeoAPRS's Direwolf and Mercury try: the operator's
    modems on the radios may be there. The tests' made-up modems run from 20000 up
    (tests/support/modemports.py)."""
    network = guards.NetworkGuard()
    for address, family in (
        (("127.0.0.1", port), socket.AF_INET),
        (("localhost", port), socket.AF_INET),
        (("::1", port, 0, 0), socket.AF_INET6),
    ):
        with pytest.raises(guards.NonLoopbackConnection, match="real Direwolf or Mercury"):
            network.check(address, family)
    assert len(network.refused) == 3 and all("a port of a real modem" in line for line in network.refused)


def test_the_ports_of_the_tests_own_modems_are_none_of_a_real_modems() -> None:
    from neoaprs import nodevices
    from tests.support.modemports import WORKER_SPAN, WORKERS

    assert (
        guards.MODEM_PORTS == {port for port in range(1, 65536) if nodevices.modem_port(port)}
        and set(_modem_ports()) <= guards.MODEM_PORTS
    ), "the ports the no-devices switch refuses"
    assert guards.MODEM_PORTS.isdisjoint(range(20000, 20000 + WORKER_SPAN * WORKERS + 2000 + 1000)), (
        "a worker's ports, its UI ports 2000 above them too"
    )
    assert guards.MODEM_PORTS.isdisjoint(range(32768, 65536)), (
        "nor a port the system gives (Linux from 32768, Windows from 49152)"
    )


def test_a_connect_a_probe_and_a_datagram_to_a_real_modems_port_are_refused_when_installed() -> None:
    from neoaprs.mercury import BROADCAST_PORT

    network = guards.NetworkGuard()
    with pytest.MonkeyPatch.context() as mp:
        network.install(mp.setattr)
        with pytest.raises(guards.NonLoopbackConnection), socket.socket() as s:
            s.connect(("127.0.0.1", BROADCAST_PORT))
        with pytest.raises(guards.NonLoopbackConnection), socket.socket() as s:
            s.connect_ex(("127.0.0.1", BROADCAST_PORT))
        with pytest.raises(guards.NonLoopbackConnection), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.sendto(b"x", ("127.0.0.1", BROADCAST_PORT))
    assert len(network.refused) == 3


def test_a_connect_of_the_windows_loop_which_goes_past_socket_connect_is_refused_too() -> None:
    """IocpProactor.connect, the Windows loop's, calls ConnectEx and never `socket.connect`: the
    guard wraps it as well (here a stand-in of it)."""
    from neoaprs.mercury import BROADCAST_PORT

    class Proactor:
        def connect(self, conn: socket.socket, address: Any) -> str:
            return "connected"

    network = guards.NetworkGuard()
    with pytest.MonkeyPatch.context() as mp, socket.socket() as s:
        network.install(mp.setattr, Proactor)
        with pytest.raises(guards.NonLoopbackConnection):
            Proactor().connect(s, ("127.0.0.1", BROADCAST_PORT))
        assert Proactor().connect(s, ("127.0.0.1", 20000)) == "connected"
    assert len(network.refused) == 1 and Proactor().connect(s, ("127.0.0.1", BROADCAST_PORT)) == "connected", (
        "put back after the test"
    )
    if sys.platform == "win32":
        from asyncio import windows_events

        assert guards._iocp_proactor() is windows_events.IocpProactor
    else:
        assert guards._iocp_proactor() is None


@posix_only
def test_a_unix_socket_is_on_this_machine(tmp_path: Path) -> None:
    network = guards.NetworkGuard()
    network.check(str(tmp_path / "s"), AF_UNIX)
    assert network.refused == []


def test_restoring_the_logging_undoes_levels_handlers_switches_and_says_what_had_changed(
    caplog: pytest.LogCaptureFixture,
) -> None:
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
    assert (
        (root.level, list(root.handlers), mine.level) == before
        and not mine.disabled
        and logging.root.manager.disable == 0
    )
    assert (
        any(c.startswith("root:") for c in changed)
        and any(c.startswith("guards.restore.mine:") for c in changed)
        and "logging.disable(50)" in changed
    )
    assert guards.restore_logging(guards.logging_state()) == []  # nothing to undo when nothing changed


async def test_a_database_thread_that_is_left_running_is_found_and_a_closed_one_is_not(tmp_path: Path) -> None:
    """The thread of a Db (neoaprs/db.py) must end with its close(): the guard fails the test that
    forgets it (a Db that nobody closes keeps a thread and a file open for ever)."""
    from neoaprs.db import Db

    db = Db.at(tmp_path / "x.sqlite")
    await db.start()
    leaked = guards.leaked_db_threads(patience_sec=0.05)
    assert len(leaked) == 1 and leaked[0].is_alive()
    await db.close()
    assert guards.leaked_db_threads() == []


def test_a_modem_program_of_the_installation_is_refused_whatever_it_is_called_and_only_the_real_direwolfs_tests_start_theirs(
    tmp_path: Path,
) -> None:
    """The folder of the shipped programs as a checkout has it where the developer built them: a
    test's radio that started the Mercury or the Direwolf in it would open the machine's sound
    cards."""
    tools = tmp_path / "venv" / "tools"
    for name in ("mercury", "direwolf"):
        (tools / name / "dev").mkdir(parents=True)
        (tools / name / name).write_text("#!/bin/sh\n")
    (tools / "direwolf" / "dev" / "gen_packets").write_text("#!/bin/sh\n")
    elsewhere = tmp_path / "made-up-mercury"
    elsewhere.write_text("#!/bin/sh\n")
    linked = tmp_path / "another-name"
    if sys.platform != "win32":
        linked.symlink_to(tools / "mercury" / "mercury")
    processes = guards.ProcessGuard(tools)
    assert (
        processes.starts_shipped([str(tools / "mercury" / "mercury"), "-l"])
        and processes.starts_shipped(str(tools / "direwolf" / "direwolf") + " -c x")
        and processes.starts_shipped([tools / "direwolf" / "dev" / "gen_packets"])
    )
    assert (
        not processes.starts_shipped([str(elsewhere)])
        and not processes.starts_shipped([sys.executable, "-m", "tests.support.fakemercury"])
        and not processes.starts_shipped([])
        and not processes.starts_shipped([str(tools) + "-other/mercury"])
    )
    assert sys.platform == "win32" or processes.starts_shipped([str(linked)]), "by the file it is, not by its name"
    with pytest.MonkeyPatch.context() as mp:
        processes.install(mp.setattr)
        with pytest.raises(guards.RadioTouched, match="modem program"):
            subprocess.Popen([str(tools / "mercury" / "mercury"), "-l"])
        with pytest.raises(guards.RadioTouched):
            subprocess.run([str(tools / "direwolf" / "direwolf")], check=False)
        # any other program is none of its business
        subprocess.run([sys.executable, "-c", "pass"], check=True)
    assert len(processes.shipped) == 2 and processes.refused == []
    direwolfs = guards.ProcessGuard(tools, allowed=("direwolf",))
    assert (
        not direwolfs.starts_shipped([str(tools / "direwolf" / "direwolf")])
        and not direwolfs.starts_shipped([str(tools / "direwolf" / "dev" / "gen_packets")])
        and direwolfs.starts_shipped([str(tools / "mercury" / "mercury")])
    )


def test_no_modem_looks_for_its_program_in_the_installation_and_the_real_direwolfs_tests_keep_theirs(
    tmp_path: Path,
) -> None:
    from neoaprs import direwolfprogram, mercuryhelper

    tools = tmp_path / "tools"
    for module, name in ((mercuryhelper, "mercury"), (direwolfprogram, "direwolf")):
        program = tools / name / module.program_file()
        program.parent.mkdir(parents=True)
        program.write_text("#!/bin/sh\n")
        program.chmod(0o755)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mercuryhelper, "tools_dir", lambda: tools)
        mp.setattr(direwolfprogram, "tools_dir", lambda: tools)
        assert mercuryhelper.find() is not None and direwolfprogram.find() is not None, (
            "an installation with both programs"
        )
        guards.no_shipped_programs(mp.setattr, tmp_path / "nowhere")
        assert mercuryhelper.find() is None and direwolfprogram.find() is None
        mp.setattr(direwolfprogram, "tools_dir", lambda: tools)
        guards.no_shipped_programs(mp.setattr, tmp_path / "nowhere", direwolf=True)
        assert mercuryhelper.find() is None and direwolfprogram.find() is not None


def test_the_bluetooth_guard_refuses_and_remembers_even_when_the_error_is_swallowed() -> None:
    bluetooth = guards.BluetoothGuard()
    with pytest.MonkeyPatch.context() as mp:
        bluetooth.install(mp.setattr)
        a, b = socket.socketpair()  # a socket of another family is none of its business
        a.close()
        b.close()
        if hasattr(socket, "AF_BLUETOOTH"):
            with pytest.raises(guards.BluetoothTouched):
                socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            l2cap = getattr(socket, "BTPROTO_L2CAP", None)  # (Windows has AF_BLUETOOTH but no L2CAP)
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


def _tools(root: Path) -> Path:
    """A folder of shipped programs as a checkout has it: Mercury, Direwolf with its dev/ tools."""
    tools = root / "tools"
    for name in ("mercury", "direwolf"):
        (tools / name / "dev").mkdir(parents=True)
        (tools / name / name).write_text("#!/bin/sh\n")
    (tools / "direwolf" / "dev" / "gen_packets").write_text("#!/bin/sh\n")
    return tools


def test_a_shipped_program_is_found_by_its_cwd_its_executable_its_path_a_shell_or_one_string_with_a_space_in_it(
    tmp_path: Path,
) -> None:
    tools = _tools(tmp_path / "John Smith" / "venv")  # (a profile folder with a space, as on Windows)
    mercury = tools / "mercury" / "mercury"
    processes = guards.ProcessGuard(tools)
    assert processes.starts_shipped(["./mercury", "-z"], cwd=tools / "mercury") and processes.starts_shipped(
        ["x"], executable=str(mercury)
    )
    assert processes.starts_shipped(
        ["mercury"], env={"PATH": f"/usr/bin{os.pathsep}{tools / 'mercury'}"}
    ) and processes.starts_shipped(["sh", "-c", f"{mercury} -z"])
    assert (
        processes.starts_shipped(f'"{mercury}" -z')
        and processes.starts_shipped(f"exec {mercury} -z")
        and processes.starts_shipped(["mercury"], cwd=tools)
    ), "the folder itself"
    assert not processes.starts_shipped(
        ["sh", "-c", "echo hello"], cwd=tmp_path, env={"PATH": "/usr/bin"}
    ) and not processes.starts_shipped([sys.executable, "-c", "pass"], executable=sys.executable)
    assert not processes.starts_shipped(["ls"], cwd=str(tools) + "-other") and not processes.starts_shipped(
        f"ls {tools}-other/mercury"
    )
    if sys.platform != "win32":
        (tmp_path / "into").symlink_to(tools / "mercury")
        assert processes.starts_shipped(["./mercury"], cwd=tmp_path / "into") and processes.starts_shipped(
            ["mercury"], env={"PATH": str(tmp_path / "into")}
        ), "by the folder it is on the disk"
    direwolfs = guards.ProcessGuard(tools, allowed=("direwolf",))
    assert not direwolfs.starts_shipped(
        ["gen_packets"], cwd=tools / "direwolf" / "dev", env={"PATH": str(tools / "direwolf")}
    ) and direwolfs.starts_shipped(["x"], executable=str(mercury))


async def test_a_shell_line_that_starts_a_shipped_program_is_refused_before_it_runs(tmp_path: Path) -> None:
    tools = _tools(tmp_path / "venv")
    processes = guards.ProcessGuard(tools)
    with pytest.MonkeyPatch.context() as mp:
        processes.install(mp.setattr)
        with pytest.raises(guards.RadioTouched):
            await asyncio.create_subprocess_shell(f'"{tools / "mercury" / "mercury"}" -z')
        with pytest.raises(guards.RadioTouched):
            subprocess.Popen(["./mercury", "-z"], cwd=tools / "mercury")
        with pytest.raises(guards.RadioTouched):
            subprocess.Popen(["anything"], executable=str(tools / "mercury" / "mercury"))
    assert len(processes.shipped) == 3


@pytest.mark.parametrize(
    "conf,why",
    [
        ("ADEVICE udp:7355 null\nKISSPORT 17411\n", ""),
        ("# written by NeoAPRS\nADEVICE stdin null\nACHANNELS 1\n", ""),
        ("ADEVICE null\n", ""),
        ("adevice NULL UDP:1\n", ""),
        ("ADEVICE plughw:1,0 null\n", "audio device"),
        ("ADEVICE default\n", "audio device"),
        ("ADEVICE null\nADEVICE1 hw:1\n", "audio device"),
        ("ADEVICE\n", "audio device"),
        ("ADEVICE null null null\n", "audio device"),
        ("ACHANNELS 1\nMODEM 1200\n", "no audio device"),
        ("ADEVICE null\nPTT CM108\n", "PTT CM108"),
        ("ADEVICE null\nptt /dev/ttyUSB0 RTS\n", "ptt"),
        ("ADEVICE null\nGPSNMEA /dev/ttyUSB1\n", "GPSNMEA"),
        ("ADEVICE null\nSERIALKISS /dev/ttyS0 9600\n", "SERIALKISS"),
        ("ADEVICE null\nTXINH GPIO 17\n", "TXINH"),
        ("ADEVICE null\nNULLMODEM /dev/ttyUSB0\n", "NULLMODEM"),
        ("ADEVICE null\nWAYPOINT /dev/ttyUSB0\n", "WAYPOINT"),
        ("ADEVICE null\nIGSERVER noam.aprs2.net\n", "IGSERVER"),
    ],
)
def test_the_real_direwolf_starts_only_on_a_configuration_that_opens_no_sound_card_and_keys_nothing(
    tmp_path: Path, conf: str, why: str
) -> None:
    tools = _tools(tmp_path / "venv")
    (tmp_path / "direwolf.conf").write_text(conf)
    direwolfs = guards.ProcessGuard(tools, allowed=("direwolf",))
    program = str(tools / "direwolf" / "direwolf")
    for args, cwd in (
        ([program, "-c", str(tmp_path / "direwolf.conf"), "-t", "0"], None),
        ([program, "-t", "0", "-c", "direwolf.conf"], tmp_path),
        ([program, f"-c{tmp_path / 'direwolf.conf'}"], None),
    ):
        found = direwolfs.direwolf_refusal(args, cwd)
        assert (why in found and bool(found)) if why else found == "", (args, found)


def test_the_real_direwolf_without_a_readable_configuration_or_through_another_program_is_refused_and_remembered(
    tmp_path: Path,
) -> None:
    tools = _tools(tmp_path / "venv")
    direwolfs = guards.ProcessGuard(tools, allowed=("direwolf",))
    program = str(tools / "direwolf" / "direwolf")
    good = tmp_path / "good.conf"
    good.write_text("ADEVICE stdin null\n")
    assert "no configuration" in direwolfs.direwolf_refusal(
        [program, "-t", "0"]
    ) and "cannot be read" in direwolfs.direwolf_refusal([program, "-c", str(tmp_path / "missing.conf")])
    assert "cannot be read" in direwolfs.direwolf_refusal([program, "-c", str(tmp_path)]), (
        "a folder is no configuration"
    )
    assert (
        "another program" in direwolfs.direwolf_refusal(["sh", "-c", f"{program} -c {good}"])
        and direwolfs.direwolf_refusal(f"{program} -c {good}") == ""
    )
    assert (
        direwolfs.direwolf_refusal([str(tools / "direwolf" / "dev" / "gen_packets"), "-o", "x.wav"]) == ""
        and direwolfs.direwolf_refusal(["sh", "-c", "echo"]) == ""
    ), "gen_packets and atest take no configuration"
    assert guards.ProcessGuard(tools).direwolf_refusal([program]) == "", (
        "where Direwolf is not allowed, starts_shipped refuses it"
    )
    bad = tmp_path / "bad.conf"
    bad.write_text("ADEVICE plughw:1,0\n")
    (tools / "direwolf" / "direwolf").chmod(0o755)
    if sys.platform == "win32":
        # (Windows finds a bare name on the PATH by its extension)
        shutil.copy(tools / "direwolf" / "direwolf", tools / "direwolf" / "direwolf.exe")
    assert "audio device" in direwolfs.direwolf_refusal(
        ["direwolf", "-c", str(bad)], env={"PATH": str(tools / "direwolf")}
    ), "found on the PATH it runs with"
    assert "audio device" in direwolfs.direwolf_refusal(["x", "-c", str(bad)], executable=program), (
        "given as the executable"
    )
    assert (
        "audio device" in direwolfs.direwolf_refusal([program, "-c", str(good), "-c", str(bad)])
        and direwolfs.direwolf_refusal([program, "-c", str(bad), "-c", str(good)]) == ""
    ), "Direwolf reads the last -c"
    with pytest.MonkeyPatch.context() as mp:
        direwolfs.install(mp.setattr)
        with pytest.raises(guards.RadioTouched, match="no sound card"):
            subprocess.Popen([program, "-c", str(tmp_path / "missing.conf")])
    assert len(direwolfs.shipped) == 1 and "missing.conf" in direwolfs.shipped[0]


def test_the_main_checkouts_programs_are_refused_too_when_the_tests_run_in_a_worktree_of_it(tmp_path: Path) -> None:
    main, own = tmp_path / "NeoAPRS", tmp_path / "NeoAPRS" / ".claude" / "worktrees" / "round" / ".venv" / "tools"
    assert guards.tools_folders(main / ".claude" / "worktrees" / "round", own) == (own, main / ".venv" / "tools")
    assert guards.tools_folders(main, main / ".venv" / "tools") == (main / ".venv" / "tools",) and guards.tools_folders(
        tmp_path / "worktrees" / "x", own
    ) == (own,)
    sibling = main / ".claude" / "worktrees" / "other" / ".venv" / "tools"
    sibling.mkdir(parents=True)
    own.mkdir(parents=True)
    assert guards.tools_folders(main / ".claude" / "worktrees" / "round", own) == (
        own,
        main / ".venv" / "tools",
        sibling,
    ) and guards.tools_folders(main, main / ".venv" / "tools") == (main / ".venv" / "tools", sibling, own), (
        "every worktree's"
    )
    assert (
        guards.TOOLS_FOLDERS == guards.tools_folders(guards.CHECKOUT, guards.REAL_TOOLS)
        and guards.TOOLS_FOLDERS[0] == guards.REAL_TOOLS
    )
    for folder in guards.TOOLS_FOLDERS:
        assert guards.ProcessGuard().starts_shipped([str(folder / "mercury" / "no-such-program")]), folder
    two = guards.ProcessGuard([_tools(tmp_path / "a"), _tools(tmp_path / "b")])
    assert (
        two.starts_shipped([str(tmp_path / "a" / "tools" / "mercury" / "mercury")])
        and two.starts_shipped([str(tmp_path / "b" / "tools" / "mercury" / "mercury")])
        and not two.starts_shipped([str(tmp_path / "c")])
    )


def test_the_journal_is_not_read_by_the_module_nor_by_the_function_bound_before(tmp_path: Path) -> None:
    """A default argument keeps the function it was given
    (`make_bundle(journal=gather.journal_text)`): the guard shuts the function too, not only the
    name in its module."""
    ran: list[str] = []

    def journal_text(
        run: Any = lambda *a, **k: ran.append("journalctl"), which: Any = lambda name: "/bin/" + name
    ) -> str | None:
        if which("journalctl") is None:
            return None
        run(["journalctl"])
        return "the journal"

    gather = types.SimpleNamespace(journal_text=journal_text)
    bound = journal_text  # (as a default argument holds it)
    assert bound() == "the journal" and ran == ["journalctl"], "the stand-in reads its journal"
    with pytest.MonkeyPatch.context() as mp:
        guards.no_journal(mp.setattr, gather)
        assert gather.journal_text() is None and bound() is None and ran == ["journalctl"]
        assert (
            bound(run=lambda *a, **k: None, which=lambda name: "/bin/" + name)
            == "the journal"
            == gather.journal_text(lambda *a, **k: None, which=lambda name: "/bin/" + name)
        ), "a test of the journal gives its own"
        assert gather.journal_text(lambda *a, **k: ran.append("given")) is None and ran == ["journalctl"], (
            "what it does not give stays shut"
        )
    assert bound.__defaults__ is not None and bound() == "the journal", "put back after the test"

    def other(run: Any = None) -> None:
        return None

    with pytest.MonkeyPatch.context() as mp, pytest.raises(AssertionError, match="no_journal"):
        guards.no_journal(mp.setattr, types.SimpleNamespace(journal_text=other))


def test_the_default_alert_command_is_shut_and_a_command_of_the_tests_own_runs() -> None:
    from dataclasses import replace

    from neoaprs.alertcommand import DEFAULT_ALERT_COMMAND
    from neoaprs.config import DEFAULTS
    from neoaprs.services import alerts

    class Unswitched(alerts.Alerts):
        def _command(self) -> str:
            return self._config().messages_alert_command.strip()  # (as with the no-devices switch lifted)

    assert Unswitched(lambda: DEFAULTS)._command() == DEFAULT_ALERT_COMMAND
    with pytest.MonkeyPatch.context() as mp:
        guards.no_default_alert(mp.setattr, Unswitched)
        assert (
            Unswitched(lambda: DEFAULTS)._command() == ""
            and Unswitched(lambda: replace(DEFAULTS, messages_alert_command=" echo hi "))._command() == "echo hi"
        )
        for wrapped in (
            f"true; {DEFAULT_ALERT_COMMAND}",
            f"{DEFAULT_ALERT_COMMAND} # mine",
            "notify-send x; paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
        ):
            assert (
                Unswitched(lambda wrapped=wrapped: replace(DEFAULTS, messages_alert_command=wrapped))._command() == ""
            ), wrapped


# ---- the doors the guards did not watch: a COM port, the starts that are not a Popen, and the
# fixtures of a module or the session


@pytest.mark.parametrize(
    "name, refused",
    [
        ("COM3", True),
        ("com12", True),
        ("\\\\.\\COM12", True),
        ("\\\\?\\COM4", True),
        ("\\\\.\\CNCA0", True),
        ("\\\\.\\pipe\\neoaprs", False),
        ("COMMAND", False),
        ("C:\\data\\COM3.txt", False),
        ("loop://", False),
        ("/dev/null", False),
        ("", False),
    ],
)
def test_a_com_port_of_windows_is_found_by_its_name_and_a_pipe_or_a_file_is_not(name: str, refused: bool) -> None:
    assert guards.is_com_port(name) is refused


def test_pyserials_windows_open_of_a_com_port_is_refused_and_remembered_even_when_the_error_is_swallowed_and_other_names_pass() -> (
    None
):
    opened: list[str] = []
    stand_in = types.SimpleNamespace(CreateFile=lambda name, *args: opened.append(name) or 7)
    radio = guards.SerialGuard()
    with pytest.MonkeyPatch.context() as mp:
        radio.install_com(mp.setattr, stand_in)
        for port in ("COM3", "\\\\.\\COM12"):
            with pytest.raises(guards.RadioTouched, match="serial port"):
                stand_in.CreateFile(port, 0, 0, None, 3, 0, 0)
        assert stand_in.CreateFile("\\\\.\\pipe\\x", 0, 0, None, 3, 0, 0) == 7
    assert opened == ["\\\\.\\pipe\\x"] and radio.refused == ["COM3", "\\\\.\\COM12"]
    assert stand_in.CreateFile("COM3", 0, 0, None, 3, 0, 0) == 7, "undone with the test"


def test_the_doors_of_the_session_put_the_com_guard_in_front_of_pyserials_windows_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stand_in = types.SimpleNamespace(CreateFile=lambda name, *args: 7)
    monkeypatch.setattr(guards, "_windows_serial", lambda: stand_in)
    doors = guards.Doors()
    with pytest.MonkeyPatch.context() as mp:
        doors.install(mp.setattr, mp.setitem)
        with pytest.raises(guards.RadioTouched):
            stand_in.CreateFile("COM250", 0, 0, None, 3, 0, 0)
    assert doors.take() == ["COM250"]


@pytest.mark.skipif(sys.platform != "win32", reason="a COM port is a Windows thing")
def test_a_test_that_opens_a_com_port_with_pyserial_is_refused() -> None:
    """The guard is the one every test has (`isolated_machine`): found behind pyserial's own
    CreateFile, and its refusal, which is this test's doing, is taken from it so that it is not held
    against the test."""
    import serial  # type: ignore[import-untyped,unused-ignore]

    create = guards._windows_serial().CreateFile
    guard = next(
        cell.cell_contents for cell in create.__closure__ or () if isinstance(cell.cell_contents, guards.SerialGuard)
    )
    with pytest.raises(guards.RadioTouched):
        serial.Serial("COM250")
    assert [name.rsplit("\\", 1)[-1] for name in guard.refused] == ["COM250"]
    guard.refused.clear()


def os_starts_made_up(mp: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    """Every call of OS_STARTS this system has is a stand-in that records itself, so that the guard
    in front of it is shown without starting anything."""
    started: list[tuple[str, tuple[Any, ...]]] = []
    for name in guards.OS_STARTS:
        if hasattr(os, name):
            mp.setattr(os, name, lambda *args, _name=name, **kwargs: started.append((_name, args)) or 0, raising=False)
    return started


def shipped_tools(tmp_path: Path) -> Path:
    tools = tmp_path / "venv" / "tools"
    (tools / "mercury").mkdir(parents=True)
    (tools / "mercury" / "mercury").write_text("#!/bin/sh\n")
    return tools


def test_a_start_by_exec_spawn_system_or_startfile_of_a_modem_program_of_the_installation_is_refused_and_remembered(
    tmp_path: Path,
) -> None:
    tools = shipped_tools(tmp_path)
    program = str(tools / "mercury" / "mercury")
    processes = guards.ProcessGuard(tools)
    with pytest.MonkeyPatch.context() as mp:
        started = os_starts_made_up(mp)
        processes.install(mp.setattr)
        calls: list[Any] = [lambda: os.system(program + " -l")]
        for name in guards.OS_STARTS:
            if not hasattr(os, name) or name == "system":
                continue
            form = name.removeprefix("posix_spawn").removeprefix("exec").removeprefix("spawn")
            if name == "startfile":
                args: list[Any] = [program]
                calls.append(lambda: os.startfile("cmd.exe", "open", "/c " + program))  # type: ignore[attr-defined,unused-ignore]
                calls.append(lambda: os.startfile("cmd.exe", arguments="/c " + program))  # type: ignore[attr-defined,unused-ignore]
            elif name.startswith("posix_spawn"):
                args = [program, [program], {}]
            # the argument list given as a list (v) or as words (l), the environment last (e), the
            # mode first for spawn
            else:
                args = [
                    *([os.P_NOWAIT] if name.startswith("spawn") else []),
                    program,
                    *([[program]] if form.startswith("v") else [program]),
                    *([{}] if form.endswith("e") else []),
                ]
            calls.append(lambda name=name, args=args: getattr(os, name)(*args))
        for call in calls:
            with pytest.raises(guards.RadioTouched, match="modem program"):
                call()
    assert started == [] and len(processes.shipped) == len(calls) and processes.refused == []


def test_the_arguments_of_a_startfile_are_checked_as_the_words_of_a_command_are(tmp_path: Path) -> None:
    program = str(shipped_tools(tmp_path) / "mercury" / "mercury")
    processes = guards.ProcessGuard(tmp_path / "venv" / "tools")
    for args, kwargs in ((("cmd.exe", "open", "/c " + program), {}), (("cmd.exe",), {"arguments": "/c " + program})):
        with pytest.raises(guards.RadioTouched, match="modem program"):
            processes.check(*(guards.os_start("startfile", args, kwargs) or ()))
    assert guards.os_start("startfile", ("notepad.exe",), {}) == (["notepad.exe"], None, None, None)
    assert guards.os_start("startfile", ("notepad.exe", "open", "a.txt"), {}) == (
        ["notepad.exe", "a.txt"],
        None,
        None,
        None,
    )


def test_a_start_by_exec_spawn_system_or_startfile_of_any_other_program_goes_through_with_its_arguments(
    tmp_path: Path,
) -> None:
    other = str(tmp_path / "other")
    processes = guards.ProcessGuard(shipped_tools(tmp_path))
    with pytest.MonkeyPatch.context() as mp:
        started = os_starts_made_up(mp)
        processes.install(mp.setattr)
        os.system("echo hello")
        os.execv(other, [other, "x"])
        os.execl(other, other, "x")
        os.execvp("ls", ["ls"])
        os.spawnv(os.P_WAIT, other, [other])
        if hasattr(os, "posix_spawn"):
            os.posix_spawn(other, [other], {})
    assert (
        [name for name, _ in started][:5] == ["system", "execv", "execl", "execvp", "spawnv"]
        and dict(started)["execv"] == (other, [other, "x"])
        and processes.shipped == []
        and processes.refused == []
    )


def test_neoaprs_started_by_exec_with_an_environment_of_its_own_needs_the_same_variables_as_one_started_by_popen() -> (
    None
):
    processes = guards.ProcessGuard()
    with pytest.MonkeyPatch.context() as mp:
        started = os_starts_made_up(mp)
        processes.install(mp.setattr)
        with pytest.raises(guards.RadioTouched, match="NEOAPRS_SERIAL_PATTERN"):
            os.execve("neoaprs", ["neoaprs", "daemon"], {"PATH": "x"})
        with pytest.raises(guards.RadioTouched):
            os.spawnle(os.P_NOWAIT, "neoaprs", "neoaprs", {"PATH": "x"})
        os.execve(
            "neoaprs",
            ["neoaprs", "daemon"],
            {guards.SEARCH_VARIABLE: "x", guards.UPDATE_VARIABLE: "0", guards.DEVICES_VARIABLE: "1"},
        )
    assert [name for name, _ in started] == ["execve"] and len(processes.refused) == 2


def test_a_popen_of_another_program_still_runs_under_the_guard_and_is_checked_once(tmp_path: Path) -> None:
    processes = guards.ProcessGuard(shipped_tools(tmp_path))
    checked: list[Any] = []
    original = processes.check
    processes.check = lambda *args, **kwargs: (checked.append(args[0]), original(*args, **kwargs))[1]  # type: ignore[method-assign]
    with pytest.MonkeyPatch.context() as mp:
        processes.install(mp.setattr)
        done = subprocess.run([sys.executable, "-c", "pass"], check=False)
    assert done.returncode == 0 and len(checked) == 1


def test_the_doors_of_the_session_refuse_and_keep_what_a_fixture_reached_for_and_stand_aside_while_a_test_runs() -> (
    None
):
    doors = guards.Doors()
    with pytest.MonkeyPatch.context() as mp:
        doors.install(mp.setattr, mp.setitem)
        with pytest.raises(guards.NonLoopbackConnection):
            socket.socket().connect(("192.0.2.1", 80))
        with pytest.raises(guards.RadioTouched):
            os.open("/dev/ttyS0", os.O_RDONLY)
    assert doors.take() == ["192.0.2.1:80", "/dev/ttyS0"] and doors.take() == []
    # (a test runs: its own guards watch, and say it)
    doors.paused = True
    doors.network.check(("192.0.2.1", 80), socket.AF_INET)
    doors.radio.check("/dev/ttyS0")
    assert doors.take() == []
    doors.paused = False
    with pytest.raises(AssertionError, match="a fixture of the module reached for"):
        guards.fail_for(["192.0.2.1:80"], "the module")
    guards.fail_for([], "the module")
