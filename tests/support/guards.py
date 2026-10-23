"""Structural guards: what a test must not do, checked for every test instead of remembered by each.

* no real machine: HOME, the XDG folders and the profile folders of Windows (USERPROFILE, LOCALAPPDATA, APPDATA) point into an empty folder of the test (the data folder and the settings of whoever runs the tests are not
  there to be read), and a socket that connects, sends a datagram or looks up a name that is not on this machine fails the test (a test must never post a made-up packet to the real
  internet, and pass);
* no radio: a test that opens a serial device of the machine (/dev/brainbox_*, /dev/tty*, /dev/serial/*, /dev/rfcomm*, or any device node of the serial drivers, whatever it is called or linked as) through `serial.Serial` or `os.open` fails; the tests use a fake radio on the loopback (tests/support/fakeradio.py) or, for a device file, a pseudo-terminal pair (tests/support/ptyline.py), and the live port is the operator's. A process a test starts inherits NEOAPRS_SERIAL_PATTERN (tests/conftest.py), which makes its search find no port, and NEOAPRS_UPDATE_CHECK=0, which keeps its daily update check from asking the version page on the internet; one that is given an environment of its own must carry both (`ProcessGuard`);
* no leak: a test that ends with an asyncio task still running fails (the daemons of `Env` are stopped for it first, see env.stop_all), and so does one that ends with the thread of
  a Db (neoaprs/db.py) still running (`await db.close()`);
* no swallowed error: a test that makes the code log an ERROR it did not say it expects fails (`@pytest.mark.expects_errors`, or a test that reads the log
  through `caplog`, says so);
* no leaked logging: the levels, handlers and switches of the loggers are what they were when the test started (neoaprs.daemon.setup_logging sets the level of the
  root logger and adds handlers; a test that ran it would leave the level at INFO for every test after it, which `caplog` of those would then see).

The fixtures are wired in by tests/conftest.py. They do not apply to tests/e2e (a browser, a page, their own rule for console errors).
Each guard is a small function here, so that tests/test_guards.py can show that it fails when it should."""
import asyncio
import errno
import fnmatch
import inspect
import ipaddress
import logging
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import serial.tools.list_ports  # type: ignore[import-untyped]

from neoaprs.dbthread import DbThread
from tests.support import env as env_module
from tests.support.markers import E2E_DIRS

# Not errors of the code under test: "asyncio" reports a task that was never awaited from the garbage collector, in whatever test runs then (the task guard says it,
# with the right name); "tornado.access" is the access log of the fake services, which logs every 500 the fake was told to answer.
IGNORED_LOGGERS = ("asyncio", "tornado.access")


def guarded(item: pytest.Item) -> bool:
    """Not the browser tests (tests/e2e, tests/e2e_pw): their own harness, their own rule for console errors."""
    return not any(part in E2E_DIRS for part in item.path.parts)


# ---- no real machine: the environment

FOLDER_VARIABLES = ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR")


def empty_home(root: Path, set_env: Callable[[str, str], None]) -> Path:
    """HOME and the XDG folders, and the profile folders of Windows (USERPROFILE, which is Path.home() there, LOCALAPPDATA and APPDATA) (and the search path of the data folders) inside `root`, which is empty."""
    for name in FOLDER_VARIABLES:
        folder = root / name.lower()
        folder.mkdir(mode=0o700)
        set_env(name, str(folder))
    set_env("XDG_DATA_DIRS", str(root / "xdg_data_dirs"))
    return root


# ---- no real machine: the network

# The rigctld and rotctld of whoever runs the tests: on this machine, but not a fake. A test that wants a rig starts a fake one on a free port.
OPERATOR_SERVICE_PORTS = frozenset({4532, 4533})


class NonLoopbackConnection(ConnectionRefusedError):
    """Raised, as a refused connection, where a test's code would have reached something that is not a fake on this machine."""


def is_local_host(host: str | bytes | None) -> bool:
    if host is None:
        return True
    name = host.decode() if isinstance(host, bytes) else host
    if name in ("", "localhost", "localhost.localdomain"):
        return True
    try:
        address = ipaddress.ip_address(name.split("%")[0])
    except ValueError:
        return False                                   # a name that is not localhost: a DNS lookup first, and then the real thing
    return address.is_loopback or address.is_unspecified


class NetworkGuard:
    """Patches the socket calls that leave the machine; records each refused address so that the test fails even when the code under test swallowed the error."""

    def __init__(self) -> None:
        self.refused: list[str] = []

    def check(self, address: Any, family: int) -> None:
        if family not in (socket.AF_INET, socket.AF_INET6) or not isinstance(address, tuple) or not address:
            return                                     # a unix socket is on this machine
        port = address[1] if len(address) > 1 else ""
        if not is_local_host(address[0]):
            self.refused.append(f"{address[0]}:{port}")
            raise NonLoopbackConnection(errno.ECONNREFUSED, f"the tests may only talk to this machine, not to {address[0]}")
        if port in OPERATOR_SERVICE_PORTS:
            self.refused.append(f"{address[0]}:{port} (the operator's rigctld or rotctld)")
            raise NonLoopbackConnection(errno.ECONNREFUSED, f"the tests may only talk to fakes, not to the rigctld or rotctld of this machine ({address[0]}:{port})")

    def install(self, patch: Callable[[Any, str, Any], None]) -> None:
        original_connect, original_connect_ex, original_sendto, original_lookup = socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto, socket.getaddrinfo

        def connect(sock: socket.socket, address: Any) -> None:
            self.check(address, sock.family)
            original_connect(sock, address)

        def connect_ex(sock: socket.socket, address: Any) -> int:
            self.check(address, sock.family)
            return original_connect_ex(sock, address)

        def sendto(sock: socket.socket, data: Any, *rest: Any) -> int:
            self.check(rest[-1], sock.family)          # sendto(data, address) or sendto(data, flags, address)
            return original_sendto(sock, data, *rest)

        def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
            if not is_local_host(host):
                try:
                    ipaddress.ip_address(host)         # an address needs no lookup: the connect says no
                except ValueError:
                    self.refused.append(f"{host} (name lookup)")
                    raise socket.gaierror(socket.EAI_NONAME, f"the tests do not look up {host}") from None
            return original_lookup(host, *args, **kwargs)

        patch(socket.socket, "connect", connect)
        patch(socket.socket, "connect_ex", connect_ex)
        patch(socket.socket, "sendto", sendto)
        patch(socket, "getaddrinfo", getaddrinfo)


# ---- no radio

RADIO_PATTERNS = ("/dev/brainbox_*", "/dev/tty*", "/dev/serial/*", "/dev/rfcomm*", "/dev/cu.*")
SERIAL_MAJORS = frozenset({4, 166, 188, 204})        # Linux: the character devices of ttyS*, ttyACM*, ttyUSB* and the on-chip UARTs (a node of another name is found by its number); a pseudo-terminal is /dev/pts/N, 136 and up
SEARCH_VARIABLE = "NEOAPRS_SERIAL_PATTERN"
UPDATE_VARIABLE = "NEOAPRS_UPDATE_CHECK"


class RadioTouched(PermissionError):
    """Raised, as a refused open, where a test's code would have opened the operator's serial port."""


def is_serial_device(name: str) -> bool:
    real = os.path.realpath(name)
    if any(fnmatch.fnmatchcase(candidate, pattern) for candidate in (name, real) for pattern in RADIO_PATTERNS):
        return True
    return _serial_node(real)


if sys.platform == "win32":
    def _serial_node(real: str) -> bool:
        return False                                  # Windows has no device numbers (and no /dev)
else:
    def _serial_node(real: str) -> bool:
        """Is `real` a character device of a serial driver, whatever its name?"""
        try:
            node = os.stat(real) if real.startswith("/dev/") else None
        except OSError:
            return False
        return node is not None and stat.S_ISCHR(node.st_mode) and os.major(node.st_rdev) in SERIAL_MAJORS


class SerialGuard:
    """Patches `os.open` (which is what `serial.Serial` opens a port with), refuses the radio's device files and remembers each, so that the test fails even when the code under test swallowed the error.
    A symbolic link is looked through: /dev/brainbox_1 is refused by its name, and so is whatever /dev/ttyS* or /dev/ttyUSB* it points to."""

    def __init__(self) -> None:
        self.refused: list[str] = []

    def check(self, path: Any) -> None:
        if isinstance(path, int):
            return
        try:
            name = os.fsdecode(path)
        except TypeError:
            return
        if is_serial_device(name):
            self.refused.append(name)
            raise RadioTouched(errno.EACCES, f"a test may not open the radio's serial port {name}")

    def install(self, patch: Callable[[Any, str, Any], None]) -> None:
        original_open = os.open

        def guarded_open(path: Any, *args: Any, **kwargs: Any) -> int:
            self.check(path)
            return original_open(path, *args, **kwargs)

        patch(os, "open", guarded_open)


class ProcessGuard:
    """Patches `subprocess.Popen`: the `neoaprs` command (or `python -m neoaprs`) started with an environment of its own, which does not carry NEOAPRS_SERIAL_PATTERN, would search the machine's serial ports, and without NEOAPRS_UPDATE_CHECK=0 would ask the version page on the internet: refused, and remembered."""

    def __init__(self) -> None:
        self.refused: list[str] = []

    @staticmethod
    def starts_neoaprs(args: Any) -> bool:
        words = [os.fsdecode(a) for a in args] if isinstance(args, (list, tuple)) else os.fsdecode(args).split()
        program = os.path.basename(words[0].replace("\\", "/")).removesuffix(".exe") if words else ""
        return program in ("neoaprs", "neoaprs-app", "neoaprsw") or any(a == "-m" and b.split(".")[0] == "neoaprs" for a, b in zip(words, words[1:]))

    def check(self, args: Any, env: Any) -> None:
        if env is not None and (not env.get(SEARCH_VARIABLE) or env.get(UPDATE_VARIABLE) != "0") and self.starts_neoaprs(args):
            self.refused.append(str(args))
            raise RadioTouched(errno.EACCES, f"a test may not start neoaprs without {SEARCH_VARIABLE} and {UPDATE_VARIABLE}=0 in its environment: {args}")

    def install(self, patch: Callable[[Any, str, Any], None]) -> None:
        original_init = subprocess.Popen.__init__

        def guarded_init(popen: Any, args: Any, *rest: Any, **kwargs: Any) -> None:
            self.check(args, kwargs.get("env"))
            original_init(popen, args, *rest, **kwargs)

        patch(subprocess.Popen, "__init__", guarded_init)


# ---- no leak

def of_the_loop(task: asyncio.Task[Any]) -> bool:
    """A task the Windows loop itself keeps for as long as a server listens (IocpProactor.accept): not the test's."""
    return str(getattr(task.get_coro(), "__qualname__", "")).startswith("IocpProactor.")


def pending_tasks() -> list[asyncio.Task[Any]]:
    me = asyncio.current_task()
    return [t for t in asyncio.all_tasks() if t is not me and not t.done() and not of_the_loop(t)]


async def leaked_tasks(patience_sec: float = 0.25) -> list[asyncio.Task[Any]]:
    """The tasks still running once the test is over. A task that was cancelled or whose connection was closed a moment ago needs a few turns of the loop to end: wait for those, not longer."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + patience_sec
    pending = pending_tasks()
    while pending and loop.time() < deadline:
        await asyncio.sleep(0.005)
        pending = pending_tasks()
    return pending


def leaked_db_threads(patience_sec: float = 0.25) -> list[DbThread]:
    """The threads of a Db still running once the test is over. close() ends its thread, but a moment after it returns the thread may not have gone: wait for those, not longer."""
    deadline = time.monotonic() + patience_sec
    alive = [t for t in threading.enumerate() if isinstance(t, DbThread) and t.is_alive()]
    while alive and time.monotonic() < deadline:
        time.sleep(0.005)
        alive = [t for t in threading.enumerate() if isinstance(t, DbThread) and t.is_alive()]
    return alive


def describe_task(task: asyncio.Task[Any]) -> str:
    coro = task.get_coro()
    return f"{task.get_name()}: {getattr(coro, '__qualname__', coro)}"


# ---- no swallowed error

class ErrorRecorder(logging.Handler):
    """Keeps the records of level ERROR and above that the code under test logged."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records_seen: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith(IGNORED_LOGGERS):
            self.records_seen.append(record)

    def lines(self) -> list[str]:
        return [f"{r.name}: {r.getMessage()}" for r in self.records_seen]


def expects_errors(request: pytest.FixtureRequest) -> bool:
    """A test says that it expects errors in the log with the marker, or by reading the log itself (caplog)."""
    return request.node.get_closest_marker("expects_errors") is not None or "caplog" in request.fixturenames


def add_leak_guard(items: list[pytest.Item]) -> None:
    """The task guard is an async fixture, and an async fixture makes an event loop: so it is asked for by the async tests only. (A usefixtures marker added
    now would be too late: the fixtures of an item are worked out when it is made. The name goes onto the list that is set up, last, and so torn down first.)"""
    for item in items:
        if guarded(item) and inspect.iscoroutinefunction(getattr(item, "obj", None)) and isinstance(item, pytest.Function):
            item.fixturenames.append("no_leaked_tasks")


# ---- no leaked logging

LoggerState = tuple[int, tuple[logging.Handler, ...], bool, bool]


def all_loggers() -> list[logging.Logger]:
    return [logging.getLogger(), *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]


def logging_state() -> tuple[int, dict[logging.Logger, LoggerState]]:
    """The global switch of logging.disable and, for every logger, its level, handlers, propagate and disabled."""
    return logging.root.manager.disable, {lg: (lg.level, tuple(lg.handlers), lg.propagate, lg.disabled) for lg in all_loggers()}


def restore_logging(state: tuple[int, dict[logging.Logger, LoggerState]]) -> list[str]:
    """Put every logger back as `state` says (a logger made since is put back to the defaults); the handlers a test added are closed. Returns what had changed.
    The handlers of pytest's own log capture come and go with the phases of a test: they are not touched."""
    disable, loggers = state
    changed: list[str] = []
    if logging.root.manager.disable != disable:
        changed.append(f"logging.disable({logging.root.manager.disable})")
        logging.disable(disable)
    for lg in all_loggers():
        level, handlers, propagate, disabled = loggers.get(lg, (logging.NOTSET, (), True, False))
        added = [h for h in lg.handlers if h not in handlers and not type(h).__module__.startswith("_pytest")]
        if (lg.level, lg.propagate, lg.disabled) != (level, propagate, disabled) or added:
            changed.append(f"{lg.name or 'root'}: level {logging.getLevelName(lg.level)}, {len(added)} handler(s) added")
        lg.setLevel(level)
        lg.propagate, lg.disabled = propagate, disabled
        for handler in added:
            lg.removeHandler(handler)
            handler.close()
    return changed


# ---- the fixtures (wired in by tests/conftest.py)

@pytest.fixture(autouse=True)
def logging_restored(request: pytest.FixtureRequest) -> Iterator[None]:
    """Whatever a test does to the loggers is undone when it ends (and the next test starts from the same logging as the first one did)."""
    state = logging_state()
    yield
    if guarded(request.node):
        restore_logging(state)


@pytest.fixture(autouse=True)
def isolated_machine(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if not guarded(request.node):
        yield
        return
    with tempfile.TemporaryDirectory(prefix="neoaprs-test-home-") as root:
        empty_home(Path(root), monkeypatch.setenv)
        network = NetworkGuard()
        network.install(monkeypatch.setattr)
        radio, processes = SerialGuard(), ProcessGuard()
        radio.install(monkeypatch.setattr)
        monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [])    # the machine's USB devices are not read (slow, and not the test's): a test that needs some gives its own list
        processes.install(monkeypatch.setattr)
        yield
        assert not network.refused, "the test tried to reach something that is not this machine: " + ", ".join(network.refused)
        assert not radio.refused, "the test tried to open the radio's serial port: " + ", ".join(radio.refused)
        assert not processes.refused, f"the test started neoaprs without {SEARCH_VARIABLE} in its environment: " + ", ".join(processes.refused)


@pytest.fixture(autouse=True)
def no_unexpected_errors(request: pytest.FixtureRequest, logging_restored: None) -> Iterator[None]:   # logging_restored: set up first, torn down last
    if not guarded(request.node):
        yield
        return
    recorder = ErrorRecorder()
    root = logging.getLogger()
    root.addHandler(recorder)
    try:
        yield
    finally:
        root.removeHandler(recorder)
    if recorder.records_seen and not expects_errors(request):
        pytest.fail("the code logged an error the test did not expect (mark the test with @pytest.mark.expects_errors when it should):\n  " + "\n  ".join(recorder.lines()[:10]), pytrace=False)


@pytest.fixture(autouse=True)
def no_leaked_db_threads(request: pytest.FixtureRequest) -> Iterator[None]:
    """Torn down after no_leaked_tasks (which stops the daemons of Env, and with them their Db): a Db that is still running now was not closed. Its thread is told to end, so that one leak does not fail the tests after it."""
    yield
    if not guarded(request.node):
        return
    leaked = leaked_db_threads()
    for thread in leaked:
        thread.finish()
    assert not leaked, "the test left database threads running (await db.close()):\n  " + "\n  ".join(t.name for t in leaked)


@pytest_asyncio.fixture
async def no_leaked_tasks() -> AsyncIterator[None]:
    """Added by tests/conftest.py to every async test that is guarded (a fixture that is async would otherwise make a loop for the sync tests too)."""
    yield
    await env_module.stop_all()
    leaked = await leaked_tasks()
    for task in leaked:
        task.cancel()
    assert not leaked, "the test left tasks running (stop what it started):\n  " + "\n  ".join(describe_task(t) for t in leaked)
