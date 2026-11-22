"""Structural guards: what a test must not do, checked for every test.

No real machine (home folders point into an empty folder, no real socket, serial port, Bluetooth or
program start) and no test left running something behind it.
"""
import asyncio
import errno
import fnmatch
import importlib
import inspect
import ipaddress
import logging
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import types
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import serial.tools.list_ports  # type: ignore[import-untyped]

from neoaprs import btpaired, bundled, direwolfprogram, mercuryhelper, nodevices, soundmixer, winmixer
from neoaprs.alertcommand import DEFAULT_ALERT_COMMAND
from neoaprs.cli import supportgather
from neoaprs.dbthread import DbThread
from neoaprs.services import alerts
from tests.support import env as env_module

# Not errors of the code under test: "asyncio" reports a task that was never awaited from the
# garbage collector, in whatever test runs then (the task guard says it, with the right name);
# "tornado.access" is the access log of the fake services, which logs every 500 the fake was told to
# answer.
IGNORED_LOGGERS = ("asyncio", "tornado.access")


# ---- no real machine: the environment

FOLDER_VARIABLES = ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR")


def empty_home(root: Path, set_env: Callable[[str, str], None]) -> Path:
    """HOME and the XDG folders, and the profile folders of Windows (USERPROFILE, which is
    Path.home() there, LOCALAPPDATA and APPDATA) (and the search path of the data folders) inside
    `root`, which is empty."""
    for name in FOLDER_VARIABLES:
        folder = root / name.lower()
        folder.mkdir(mode=0o700)
        set_env(name, str(folder))
    set_env("XDG_DATA_DIRS", str(root / "xdg_data_dirs"))
    return root


# ---- no real machine: the network

# The rigctld, rotctld and gpsd of whoever runs the tests: on this machine, but not a fake. A test
# that wants a rig or a GPS starts a fake one on a free port.
OPERATOR_SERVICE_PORTS = frozenset({4532, 4533, 2947})
# APRS-IS: the servers an iGate logs in to (rotate.aprs2.net, port 14580) and the ports they listen
# on. A test that wants an iGate starts a fake APRS-IS (tests/support/fakeaprsis.py) on a free port;
# the real one gets nothing a test made up.
APRS_IS_PORTS = frozenset({14580, 10152, 10151})
APRS_IS_HOSTS = ("aprs2.net", "aprs.net", "aprs-is.net", "aprs.fi")


def modem_ports() -> frozenset[int]:
    """The ports of this machine a real modem may listen on, as the no-devices switch refuses them
    (nodevices.modem_port: Direwolf's and Mercury's own defaults, the ports NeoAPRS's Direwolf and
    Mercury try). The operator's own Direwolf or a running NeoAPRS's modems are there, keyed to the
    radios; a test's made-up modem runs from port 20000 up (tests/support/modemports.py) or on a
    free port the system gives."""
    return frozenset(port for port in range(1, 65536) if nodevices.modem_port(port))


MODEM_PORTS = modem_ports()


class NonLoopbackConnection(ConnectionRefusedError):
    """Raised, as a refused connection, where a test's code would have reached something that is not
    a fake on this machine."""


def is_local_host(host: str | bytes | None) -> bool:
    if host is None:
        return True
    name = host.decode() if isinstance(host, bytes) else host
    if name in ("", "localhost", "localhost.localdomain"):
        return True
    try:
        address = ipaddress.ip_address(name.split("%")[0])
    except ValueError:
        # A name that is not localhost: a DNS lookup first, and then the real thing
        return False
    return address.is_loopback or address.is_unspecified


class NetworkGuard:
    """Patches the socket calls that leave the machine; records each refused address so that the
    test fails even when the code under test swallowed the error."""

    def __init__(self) -> None:
        self.refused: list[str] = []

    def check(self, address: Any, family: int) -> None:
        if family not in (socket.AF_INET, socket.AF_INET6) or not isinstance(address, tuple) or not address:
            return                                     # a unix socket is on this machine
        port = address[1] if len(address) > 1 else ""
        if not is_local_host(address[0]):
            self.refused.append(f"{address[0]}:{port}" + (" (APRS-IS)" if port in APRS_IS_PORTS else ""))
            raise NonLoopbackConnection(errno.ECONNREFUSED, f"the tests may only talk to this machine, not to {address[0]}" + (" (the real APRS-IS)" if port in APRS_IS_PORTS else ""))
        if port in APRS_IS_PORTS:
            self.refused.append(f"{address[0]}:{port} (APRS-IS)")
            raise NonLoopbackConnection(errno.ECONNREFUSED, f"the tests may only talk to a fake APRS-IS on a free port, not to port {port} ({address[0]}:{port})")
        if port in OPERATOR_SERVICE_PORTS:
            self.refused.append(f"{address[0]}:{port} (the operator's rigctld or rotctld)")
            raise NonLoopbackConnection(errno.ECONNREFUSED, f"the tests may only talk to fakes, not to the rigctld or rotctld of this machine ({address[0]}:{port})")
        if port in MODEM_PORTS:
            self.refused.append(f"{address[0]}:{port} (a port of a real modem)")
            raise NonLoopbackConnection(errno.ECONNREFUSED, f"the tests may only talk to a made-up modem on a port of the test's own, not to port {port} of this machine, where a real Direwolf or Mercury may listen ({address[0]}:{port})")

    def install(self, patch: Callable[[Any, str, Any], None], proactor: Any = None) -> None:
        """`proactor`: the class of the loop whose connect does not go through `socket.connect`
        (Windows: IocpProactor, by ConnectEx); a test of the guard gives a stand-in."""
        original_connect, original_connect_ex, original_sendto, original_lookup = socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto, socket.getaddrinfo
        proactor = proactor if proactor is not None else _iocp_proactor()

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
                    aprs_is = str(host).lower().rstrip(".").endswith(APRS_IS_HOSTS)
                    self.refused.append(f"{host} (name lookup{' of an APRS-IS server' if aprs_is else ''})")
                    raise socket.gaierror(socket.EAI_NONAME, f"the tests do not look up {host}") from None
            return original_lookup(host, *args, **kwargs)

        patch(socket.socket, "connect", connect)
        patch(socket.socket, "connect_ex", connect_ex)
        patch(socket.socket, "sendto", sendto)
        patch(socket, "getaddrinfo", getaddrinfo)
        if proactor is not None:
            original_proactor_connect = proactor.connect

            def proactor_connect(loop_proactor: Any, conn: socket.socket, address: Any) -> Any:
                self.check(address, conn.family)
                return original_proactor_connect(loop_proactor, conn, address)

            patch(proactor, "connect", proactor_connect)


if sys.platform == "win32":
    def _iocp_proactor() -> Any:
        """The proactor of the Windows loop, whose connect (ConnectEx) never calls `socket.connect`.
        """
        from asyncio import windows_events
        return windows_events.IocpProactor
else:
    def _iocp_proactor() -> Any:
        return None                                    # (the other loops connect through `socket.connect`)


# ---- no radio

RADIO_PATTERNS = ("/dev/brainbox_*", "/dev/tty*", "/dev/serial/*", "/dev/rfcomm*", "/dev/cu.*")
# Linux character devices of ttyS*, ttyACM*, ttyUSB* and on-chip UARTs; a pseudo-terminal is
# /dev/pts/N, 136 and up.
SERIAL_MAJORS = frozenset({4, 166, 188, 204})
SEARCH_VARIABLE = "NEOAPRS_SERIAL_PATTERN"
UPDATE_VARIABLE = "NEOAPRS_UPDATE_CHECK"
DEVICES_VARIABLE = "NEOAPRS_NO_DEVICES"


class RadioTouched(PermissionError):
    """Raised, as a refused open, where a test's code would have opened the operator's serial port.
    """


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
    """Patches `os.open` (which is what `serial.Serial` opens a port with), refuses the radio's
    device files and remembers each, so that the test fails even when the code under test swallowed
    the error. A symbolic link is looked through: /dev/brainbox_1 is refused by its name, and so is
    whatever /dev/ttyS* or /dev/ttyUSB* it points to."""

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

    def install_com(self, patch: Callable[[Any, str, Any], None], win32: Any = None) -> None:
        """Windows has no device file to open: pyserial opens a COM port with its own
        `win32.CreateFile`, which is refused for a port's name, and remembered. `win32`: the module
        that holds it (a test of the guard gives a stand-in)."""
        win32 = win32 if win32 is not None else _windows_serial()
        if win32 is None:
            return
        original = win32.CreateFile

        def guarded_create_file(name: Any, *args: Any, **kwargs: Any) -> Any:
            text = os.fsdecode(name) if isinstance(name, (str, bytes, os.PathLike)) else ""
            if is_com_port(text):
                self.refused.append(text)
                raise RadioTouched(errno.EACCES, f"a test may not open the radio's serial port {text}")
            return original(name, *args, **kwargs)

        patch(win32, "CreateFile", guarded_create_file)


# Windows: the name of a serial port as pyserial gives it to CreateFile: COM3, or \\\\.\\COM12 (the
# form for the ports from COM9 up), and any other name of the device namespace (a virtual port pair
# has its own), but not a pipe.
_COM_NAME = re.compile(r"(?:\\\\[.?]\\)?COM\d+|\\\\[.?]\\(?!pipe\\).+", re.IGNORECASE)


def is_com_port(name: str) -> bool:
    return _COM_NAME.fullmatch(name.strip()) is not None


def _windows_serial() -> Any:
    """pyserial's module of the Windows calls (its CreateFile is what opens a COM port); None
    elsewhere, where importing it fails."""
    return importlib.import_module("serial.win32") if sys.platform == "win32" else None


class BluetoothTouched(PermissionError):
    """Raised, as a refused socket, where a test's code would have made a Bluetooth socket of this
    machine."""


class BluetoothGuard:
    """Patches the creation of a socket: one of the Bluetooth family is refused and remembered, so
    that the test fails even when the code under test swallowed the error. A socket that only stands
    in for one (a pair of connected sockets of another family, tests/support/fakebluetooth.py) is
    not touched."""

    def __init__(self) -> None:
        self.refused: list[str] = []

    def check(self, family: Any) -> None:
        bluetooth = getattr(socket, "AF_BLUETOOTH", None)
        if bluetooth is not None and family == bluetooth:
            self.refused.append("a Bluetooth socket")
            raise BluetoothTouched(errno.EACCES, "a test may not make a Bluetooth socket (use tests/support/fakebluetooth.py)")

    def install(self, patch: Callable[[Any, str, Any], None]) -> None:
        original_init = socket.socket.__init__

        def guarded_init(sock: socket.socket, family: Any = -1, *args: Any, **kwargs: Any) -> None:
            self.check(family)
            original_init(sock, family, *args, **kwargs)

        patch(socket.socket, "__init__", guarded_init)


    def install_ble(self, setitem: Callable[[Any, str, Any], None]) -> None:
        """Puts a stand-in for the bleak library in `sys.modules`: its scanner and its client
        refuse, and are remembered. (A test of the BLE port, or of the missing library, sets its
        own.)"""
        stand_in = types.ModuleType("bleak")

        class BleakError(Exception):
            pass

        guard = self

        class Scanner:
            @staticmethod
            async def find_device_by_address(*args: Any, **kwargs: Any) -> None:
                guard.check_ble("a Bluetooth LE scan")

        class Client:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                guard.check_ble("a Bluetooth LE connection")

        stand_in.BleakError = BleakError                # type: ignore[attr-defined]
        stand_in.BleakScanner = Scanner                 # type: ignore[attr-defined]
        stand_in.BleakClient = Client                   # type: ignore[attr-defined]
        setitem(sys.modules, "bleak", stand_in)

    def check_ble(self, what: str) -> None:
        self.refused.append(what)
        raise BluetoothTouched(errno.EACCES, f"a test may not make {what} (use tests/support/fakeble.py)")


class ProcessGuard:
    """Patches `subprocess.Popen`: the `neoaprs` command (or `python -m neoaprs`) started with an
    environment of its own, which does not carry NEOAPRS_SERIAL_PATTERN, would search the machine's
    serial ports, and without NEOAPRS_UPDATE_CHECK=0 would ask the version page on the internet, and
    without NEOAPRS_NO_DEVICES would open what its settings name: refused, and remembered. And a
    start that reaches a modem program of the installation (`tools`: a folder of them, or several),
    whichever way it names it: refused, and remembered; the real Direwolf a test may start
    (`allowed`) only on a configuration that opens no sound card and keys nothing
    (`direwolf_refusal`)."""

    def __init__(self, tools: Path | Sequence[Path] | None = None, allowed: tuple[str, ...] = ()) -> None:
        self.refused: list[str] = []
        # The modem programs of this installation the test started, and the real Direwolf on a
        # configuration that opens a door
        self.shipped: list[str] = []
        folders = TOOLS_FOLDERS if tools is None else (tools,) if isinstance(tools, (str, os.PathLike)) else tuple(tools)
        # As written and as it is on the disk
        self._tools = tuple(dict.fromkeys(form for folder in folders for form in (_norm(os.path.abspath(folder)), _norm(os.path.realpath(folder)))))
        # The folders of the shipped programs this test may start (`real_direwolf`: "direwolf")
        self._allowed = tuple(_norm(name) for name in allowed)
        # Set while a Popen runs: the os call it makes (posix_spawn) is the same start, already
        # checked
        self._popen = threading.local()

    def _names_tools(self, text: str) -> bool:
        """`text` names the folder of the shipped programs itself, or something in it that is not
        under an allowed folder."""
        text = _norm(text)
        for folder in self._tools:
            at = text.find(folder)
            while at >= 0:
                after = text[at + len(folder):]
                if not after or after[0] in _ENDS:
                    return True                                # the folder itself (a cwd, an entry of PATH)
                if after[0] in _SEPARATORS and re.match(_SEGMENT, after[1:]).group() not in self._allowed:     # type: ignore[union-attr]
                    return True
                at = text.find(folder, at + 1)                 # (a folder whose name only begins like it: tools-other)
        return False

    def starts_shipped(self, args: Any, executable: Any = None, cwd: Any = None, env: Any = None) -> bool:
        """The start reaches one of this installation's shipped programs that this test may not
        start: the folder is in the command (a word of it, or the whole line of a shell), in
        `executable`, in `cwd` or in an entry of the PATH it runs with, as written or as it is on
        the disk, so that a program found from its cwd or its PATH, given as `executable`, behind a
        symbolic link of another name or wrapped in a shell counts as well (a copy or a hard link
        elsewhere does not)."""
        return any(self._names_tools(text) for text in _texts(args, executable, cwd, env))

    def direwolf_refusal(self, args: Any, cwd: Any = None, executable: Any = None, env: Any = None) -> str:
        """Why this start of the real Direwolf of an allowed folder opens a door ("" when it is no
        such start, or opens none): the program (named, given as `executable`, found from `cwd` or
        on the PATH it runs with) is started by itself, never through another program, on the file
        named after its last `-c` (the one Direwolf reads), which has an ADEVICE whose devices are
        each `null`, `stdin` or `udp:PORT` and no line of DIREWOLF_DOORS."""
        words = _words(args)
        for i, word in enumerate(words):
            if self._is_direwolf(word) or i == 0 and any(self._is_direwolf(program) for program in _programs(word, executable, cwd, env)):
                return "it is started through another program" if i else conf_refusal(_conf_of(words[1:], cwd))
        return ""

    def _is_direwolf(self, text: str) -> bool:
        text = _norm(text)
        return _norm("direwolf") in self._allowed and any(re.search(re.escape(os.path.join(folder, "direwolf", "direwolf")) + r"(\.exe)?(?![\w.-])", text) for folder in self._tools)

    @staticmethod
    def starts_neoaprs(args: Any) -> bool:
        words = [os.fsdecode(a) for a in args] if isinstance(args, (list, tuple)) else os.fsdecode(args).split()
        program = os.path.basename(words[0].replace("\\", "/")).removesuffix(".exe") if words else ""
        return program in ("neoaprs", "neoaprs-app", "neoaprsw") or any(a == "-m" and b.split(".")[0] == "neoaprs" for a, b in zip(words, words[1:]))

    def check(self, args: Any, env: Any, executable: Any = None, cwd: Any = None) -> None:
        if self.starts_shipped(args, executable, cwd, env):
            self.shipped.append(str(args))
            raise RadioTouched(errno.EACCES, f"a test may not start a modem program of this installation, which opens the machine's sound cards: {args}")
        if why := self.direwolf_refusal(args, cwd, executable, env):
            self.shipped.append(f"{args} ({why})")
            raise RadioTouched(errno.EACCES, f"a test may start the real Direwolf only on a configuration that opens no sound card and keys nothing: {why}: {args}")
        if env is None or not self.starts_neoaprs(args):
            return
        # A test that took the variable out of its own environment: its process may go without
        doors_open = DEVICES_VARIABLE in os.environ and env.get(DEVICES_VARIABLE, "").strip() in ("", "0")
        if not env.get(SEARCH_VARIABLE) or env.get(UPDATE_VARIABLE) != "0" or doors_open:
            self.refused.append(str(args))
            raise RadioTouched(errno.EACCES, f"a test may not start neoaprs without {SEARCH_VARIABLE}, {UPDATE_VARIABLE}=0 and {DEVICES_VARIABLE} in its environment: {args}")

    def install(self, patch: Callable[[Any, str, Any], None]) -> None:
        original_init = subprocess.Popen.__init__

        def guarded_init(popen: Any, args: Any, *rest: Any, **kwargs: Any) -> None:
            given = {**dict(zip(_POPEN_PARAMETERS, rest)), **kwargs}
            self.check(args, given.get("env"), given.get("executable"), given.get("cwd"))
            self._popen.inside = True
            try:
                original_init(popen, args, *rest, **kwargs)
            finally:
                self._popen.inside = False

        patch(subprocess.Popen, "__init__", guarded_init)
        self.install_os(patch)

    def install_os(self, patch: Callable[[Any, str, Any], None]) -> None:
        """The starts that do not go through Popen (`OS_STARTS`: os.exec*, os.spawn*,
        os.posix_spawn*, os.system, os.startfile; the ones this system has) are checked as a Popen
        of the same program is."""
        for name in OS_STARTS:
            original = getattr(os, name, None)
            if original is None:
                continue

            def guarded(*args: Any, _name: str = name, _original: Any = original, **kwargs: Any) -> Any:
                if not getattr(self._popen, "inside", False) and (start := os_start(_name, args, kwargs)) is not None:
                    self.check(*start)
                return _original(*args, **kwargs)

            patch(os, name, guarded)


OS_STARTS = ("system", "startfile", "posix_spawn", "posix_spawnp",
             *(f"exec{form}" for form in ("l", "le", "lp", "lpe", "v", "ve", "vp", "vpe")), *(f"spawn{form}" for form in ("l", "le", "lp", "lpe", "v", "ve", "vp", "vpe")))


def os_start(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, Any, Any, Any] | None:
    """What a call of one of `OS_STARTS` starts, as `ProcessGuard.check` takes it: (args, env,
    executable, cwd); None when it names no program (a file descriptor, no arguments). The `p` forms
    look the program up on the PATH (the name is not a file: no `executable`), the `e` forms give
    the environment, the `l` forms list the arguments, and spawn* has its mode first."""
    if name == "system":
        command = args[0] if args else kwargs.get("command")
        return (command, None, None, None) if isinstance(command, (str, bytes, os.PathLike)) else None
    if name == "startfile":
        target = args[0] if args else kwargs.get("filepath")
        # The text handed to the program: a word of it may name a modem program too
        arguments = args[2] if len(args) > 2 else kwargs.get("arguments")
        cwd = kwargs.get("cwd", args[3] if len(args) > 3 else None)
        return ([target, *([arguments] if isinstance(arguments, (str, bytes, os.PathLike)) and arguments else [])], None, None, cwd) if isinstance(target, (str, bytes, os.PathLike)) else None
    rest = args[1:] if name.startswith("spawn") else args
    form = name.removeprefix("posix_spawn").removeprefix("exec").removeprefix("spawn") or "v"
    if name.startswith("posix_spawn"):
        form = "v" + ("p" if name == "posix_spawnp" else "") + "e"
    if not rest or not isinstance(rest[0], (str, bytes, os.PathLike)):
        return None
    program, env = rest[0], None
    if form.startswith("l"):
        listed = list(rest[1:])
        if form.endswith("e") and listed:
            env = listed.pop()
    else:
        listed = list(rest[1]) if len(rest) > 1 else []
        env = rest[2] if form.endswith("e") and len(rest) > 2 else None
    if env is not None and not isinstance(env, Mapping):
        env = None
    return [program, *listed[1:]], env, None if "p" in form else program, None


# Popen's parameters after `args`, in their order
_POPEN_PARAMETERS = ("bufsize", "executable", "stdin", "stdout", "stderr", "preexec_fn", "close_fds", "shell", "cwd", "env")
_SEPARATORS = "/" + os.sep
_ENDS = " \t\n\"';:&|)<>" + os.pathsep          # what may follow a path in a line of a shell or a PATH
_SEGMENT = r"[^/\\\s\"';:&|)<>]*"


def _norm(path: str) -> str:
    return os.path.normcase(path)


def _words(args: Any) -> list[str]:
    """The words of a command: a list as it is; one string as a shell would split it (as written
    when it cannot be split)."""
    if isinstance(args, (list, tuple)):
        return [os.fsdecode(a) for a in args]
    line = os.fsdecode(args)
    try:
        return shlex.split(line, posix=sys.platform != "win32")
    except ValueError:
        return line.split()


def _program(word: str, cwd: Any) -> str:
    """The file a program word is, as it is on the disk: a relative one is found from `cwd` (as
    Popen does on POSIX)."""
    return os.path.realpath(os.path.join(os.fsdecode(cwd), word) if cwd is not None and not os.path.isabs(word) else word)


def _programs(word: str, executable: Any, cwd: Any, env: Any) -> list[str]:
    """The files the first word of a command may start, as they are on the disk: `executable` when
    it is given, the word found from `cwd`, and a bare name found on the PATH the start runs with.
    """
    programs = [os.path.realpath(os.fsdecode(executable))] if executable is not None else []
    programs.append(_program(word, cwd))
    if not any(sep in word for sep in _SEPARATORS) and (found := shutil.which(word, path=_search_path(env) or None)):
        programs.append(os.path.realpath(found))
    return programs


def _search_path(env: Any) -> str:
    environment = os.environ if env is None else env
    return next((str(value) for key, value in environment.items() if str(key).upper() == "PATH"), "")


def _texts(args: Any, executable: Any, cwd: Any, env: Any) -> list[str]:
    """Every text of a start that may name a program's folder: the words (or the line), the program
    as it is on the disk (from `cwd`, or found on the PATH it runs with), `executable`, `cwd` and
    the entries of the PATH, each also as it is on the disk."""
    words = _words(args)
    whole = [os.fsdecode(a) for a in args] if isinstance(args, (list, tuple)) else [os.fsdecode(args)]
    texts = [*whole, *words]
    if words:
        texts += _programs(words[0], None, cwd, env)
    for path in (executable, cwd, *[entry for entry in _search_path(env).split(os.pathsep) if entry]):
        if path is not None:
            texts += [os.fsdecode(path), os.path.realpath(os.fsdecode(path))]
    return texts


def _conf_of(words: Sequence[str], cwd: Any) -> Path | None:
    """The configuration a Direwolf command line names (`-c FILE` or `-cFILE`; of several the last,
    which Direwolf reads), found from `cwd` when it is relative; None without one."""
    named = [words[i + 1] if word == "-c" and i + 1 < len(words) else word[2:] if word.startswith("-c") and len(word) > 2 else "" for i, word in enumerate(words)]
    name = next((n for n in reversed(named) if n), "")
    if not name:
        return None
    return Path(os.fsdecode(cwd), name) if cwd is not None and not os.path.isabs(name) else Path(name)


# The lines of Direwolf's configuration that key a radio
DIREWOLF_DOORS = frozenset({"PTT", "TXINH", "DCD", "CON", "GPSNMEA", "GPSD", "SERIALKISS", "SERIALKISSPOLL", "NULLMODEM", "WAYPOINT", "IGSERVER"})
# or open a device, a GPIO pin, a serial port (NULLMODEM is the old name of SERIALKISS; WAYPOINT may
# write to one) or the real APRS-IS (IGSERVER: the Direwolf is a program of its own, which
# NetworkGuard does not see)
# No sound card: ALSA's null device, the standard input, a UDP port
_SAFE_AUDIO = re.compile(r"null|stdin|udp:\d+", re.IGNORECASE)


def conf_refusal(conf: Path | None) -> str:
    """Why a Direwolf on this configuration would open a door ("" when it would not): none named
    (Direwolf would read one of its own folder or of the home, else take the default sound card),
    one that cannot be read, an audio device that is not one of `_SAFE_AUDIO` (each of its one or
    two words), no audio device at all (the default sound card) or a line of DIREWOLF_DOORS."""
    if conf is None:
        return "no configuration is named (-c)"
    try:
        text = conf.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"its configuration {conf} cannot be read ({e.strerror})"
    audio = 0
    for line in text.splitlines():
        words = line.split()
        if not words or words[0].startswith(("#", "*")):
            continue
        keyword = words[0].upper()
        if keyword in DIREWOLF_DOORS:
            return f"its configuration has the line {line.strip()!r}"
        if re.fullmatch(r"ADEVICE\d*", keyword):
            audio += 1
            if not 1 <= len(words) - 1 <= 2 or not all(_SAFE_AUDIO.fullmatch(word) for word in words[1:]):
                return f"its configuration has the audio device {line.strip()!r} (only null, stdin or udp:PORT)"
    return "" if audio else "its configuration names no audio device (ADEVICE): Direwolf would open the default sound card"


# ---- no modem program of this installation
# Where this installation's shipped programs are, read before any test looks elsewhere
REAL_TOOLS = bundled.tools_dir()
CHECKOUT = Path(__file__).resolve().parent.parent.parent


def tools_folders(checkout: Path, own: Path) -> tuple[Path, ...]:
    """The folders of shipped programs a test must not start: `own`, this interpreter's, and when
    the checkout is a git worktree of the main one (`<main>/.claude/worktrees/<name>`) the main
    checkout's `.venv/tools` as well, where the developer's real Mercury is, and those of the other
    worktrees there (worked out from the path of the checkout, not asked of git)."""
    worktree = checkout.parent.name == "worktrees" and checkout.parent.parent.name == ".claude"
    main = checkout.parent.parent.parent if worktree else checkout
    folders = [own, *([main / ".venv" / "tools"] if worktree else []), *sorted((main / ".claude" / "worktrees").glob("*/.venv/tools"))]
    return tuple(dict.fromkeys(folders))


TOOLS_FOLDERS = tools_folders(CHECKOUT, REAL_TOOLS)


# The sound of the default alert command of Linux, in this and every older default
# (neoaprs/migrationsteps22on.py)
_DEFAULT_SOUND = "paplay /usr/share/sounds"


def no_default_alert(patch: Callable[[Any, str, Any], None], kind: type[alerts.Alerts] = alerts.Alerts) -> None:
    """The alert runs no default command (notify-send, kdialog, a sound by paplay; on Windows a
    notification and a sound), which would reach the desktop and the sound cards of the machine: as
    under the no-devices switch, which the test's process lifts: nor a line that holds it or the
    sound of an older default. A command of the test's own still runs."""
    original = kind._command

    def command(self: alerts.Alerts) -> str:
        chosen = original(self)
        # The default inside a line of the test's own, or an older default, which plays the same
        # sound
        return "" if DEFAULT_ALERT_COMMAND in chosen or _DEFAULT_SOUND in chosen else chosen

    patch(kind, "_command", command)


def _no_journalctl(*args: Any, **kwargs: Any) -> Any:
    raise OSError(errno.EACCES, "a test does not read the journal of this machine")


def no_journal(patch: Callable[[Any, str, Any], None], gather: Any = supportgather) -> None:
    """The support bundle reads no journal of this machine (journalctl): the module's `journal_text`
    finds no journalctl and runs nothing, and so does the function itself wherever it was bound
    before (a default argument), because its own defaults are those stand-ins too. A test of the
    journal gives its own `run` and `which`."""
    original = gather.journal_text
    positional = [p for p in inspect.signature(original).parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    names = [p.name for p in positional if p.default is not p.empty]           # (in the order of __defaults__)
    assert {"run", "which"} <= set(names), "journal_text no longer takes `run` and `which`: tests/support/guards.py no_journal must shut its new way to journalctl"
    stand_ins: dict[str, Any] = {"run": _no_journalctl, "which": lambda name: None}

    def journal_text(*args: Any, **kwargs: Any) -> Any:
        given = {p.name for p in positional[:len(args)]} | set(kwargs)
        return original(*args, **{name: value for name, value in stand_ins.items() if name not in given}, **kwargs)

    patch(gather, "journal_text", journal_text)
    patch(original, "__defaults__", tuple(stand_ins.get(name, value) for name, value in zip(names, original.__defaults__ or ())))


def no_shipped_programs(patch: Callable[[Any, str, Any], None], nowhere: Path, direwolf: bool = False) -> None:
    """The modems look for their shipped program in a folder that is not there, so that none is
    found: as in an installation without them (a wheel, the CI). `direwolf`: the real Direwolf's
    tests keep its folder."""
    patch(mercuryhelper, "tools_dir", lambda: nowhere)
    if not direwolf:
        patch(direwolfprogram, "tools_dir", lambda: nowhere)


# ---- no leak

def of_the_loop(task: asyncio.Task[Any]) -> bool:
    """A task the Windows loop itself keeps for as long as a server listens (IocpProactor.accept):
    not the test's."""
    return str(getattr(task.get_coro(), "__qualname__", "")).startswith("IocpProactor.")


def pending_tasks() -> list[asyncio.Task[Any]]:
    me = asyncio.current_task()
    return [t for t in asyncio.all_tasks() if t is not me and not t.done() and not of_the_loop(t)]


async def leaked_tasks(patience_sec: float = 0.25) -> list[asyncio.Task[Any]]:
    """The tasks still running once the test is over. A task that was cancelled or whose connection
    was closed a moment ago needs a few turns of the loop to end: wait for those, not longer."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + patience_sec
    pending = pending_tasks()
    while pending and loop.time() < deadline:
        await asyncio.sleep(0.005)
        pending = pending_tasks()
    return pending


def leaked_db_threads(patience_sec: float = 0.25) -> list[DbThread]:
    """The threads of a Db still running once the test is over. close() ends its thread, but a
    moment after it returns the thread may not have gone: wait for those, not longer."""
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
    """A test says that it expects errors in the log with the marker, or by reading the log itself
    (caplog)."""
    return request.node.get_closest_marker("expects_errors") is not None or "caplog" in request.fixturenames


def add_leak_guard(items: list[pytest.Item]) -> None:
    """The task guard is an async fixture, and an async fixture makes an event loop: so it is asked
    for by the async tests only. (A usefixtures marker added now would be too late: the fixtures of
    an item are worked out when it is made. The name goes onto the list that is set up, last, and so
    torn down first.)"""
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "obj", None)) and isinstance(item, pytest.Function):
            item.fixturenames.append("no_leaked_tasks")


# ---- no leaked logging

LoggerState = tuple[int, tuple[logging.Handler, ...], bool, bool]


def all_loggers() -> list[logging.Logger]:
    return [logging.getLogger(), *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]


def logging_state() -> tuple[int, dict[logging.Logger, LoggerState]]:
    """The global switch of logging.disable and, for every logger, its level, handlers, propagate
    and disabled."""
    return logging.root.manager.disable, {lg: (lg.level, tuple(lg.handlers), lg.propagate, lg.disabled) for lg in all_loggers()}


def restore_logging(state: tuple[int, dict[logging.Logger, LoggerState]]) -> list[str]:
    """Put every logger back as `state` says (a logger made since is put back to the defaults); the
    handlers a test added are closed. Returns what had changed. The handlers of pytest's own log
    capture come and go with the phases of a test: they are not touched."""
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


class Doors:
    """Guards of the network, serial ports, Bluetooth and program starts for what runs before a
    test's own guards: the fixtures of a module and of the session. Installed for the whole session;
    while a test runs (`paused`) the test's own guards watch instead, so a refusal is not counted
    twice. `take` hands over what a fixture reached for."""

    def __init__(self) -> None:
        self.paused = False
        self.network, self.radio, self.bluetooth, self.processes = NetworkGuard(), SerialGuard(), BluetoothGuard(), ProcessGuard()
        for guard in (self.network, self.radio, self.bluetooth, self.processes):
            guard.check = self._unless_paused(guard.check)                                   # type: ignore[method-assign]
        self.bluetooth.check_ble = self._unless_paused(self.bluetooth.check_ble)             # type: ignore[method-assign]

    def _unless_paused(self, check: Callable[..., Any]) -> Callable[..., Any]:
        def checked(*args: Any, **kwargs: Any) -> Any:
            return None if self.paused else check(*args, **kwargs)
        return checked

    def install(self, patch: Callable[[Any, str, Any], None], setitem: Callable[[Any, str, Any], None]) -> None:
        self.network.install(patch)
        self.radio.install(patch)
        self.radio.install_com(patch)
        self.bluetooth.install(patch)
        self.bluetooth.install_ble(setitem)
        self.processes.install(patch)

    def take(self) -> list[str]:
        """Everything the fixtures reached for since the last call, and forgets it."""
        taken = [*self.network.refused, *self.radio.refused, *self.bluetooth.refused, *self.processes.refused, *self.processes.shipped]
        for refused in (self.network.refused, self.radio.refused, self.bluetooth.refused, self.processes.refused, self.processes.shipped):
            refused.clear()
        return taken


ACTIVE_DOORS: Doors | None = None


def fail_for(taken: list[str], where: str) -> None:
    assert not taken, f"a fixture of {where} reached for something that is not this machine's to take (a real network, serial port, Bluetooth device or modem program): " + ", ".join(taken)


@pytest.fixture(scope="session", autouse=True)
def doors_of_the_session() -> Iterator[Doors]:
    global ACTIVE_DOORS
    doors = ACTIVE_DOORS = Doors()
    try:
        with pytest.MonkeyPatch.context() as patches:
            doors.install(patches.setattr, patches.setitem)
            yield doors
    finally:
        ACTIVE_DOORS = None
    fail_for(doors.take(), "the session")


@pytest.fixture(scope="module", autouse=True)
def doors_of_the_module(doors_of_the_session: Doors) -> Iterator[None]:
    """Set up before the fixtures of the module and torn down after them: what they reached for
    fails the module, at its last test."""
    yield
    fail_for(doors_of_the_session.take(), "the module")


# ---- the fixtures (wired in by tests/conftest.py)

@pytest.fixture(autouse=True)
def logging_restored() -> Iterator[None]:
    """Whatever a test does to the loggers is undone when it ends (and the next test starts from the
    same logging as the first one did)."""
    state = logging_state()
    yield
    restore_logging(state)


@pytest.fixture(autouse=True)
def isolated_machine(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with tempfile.TemporaryDirectory(prefix="neoaprs-test-home-") as root:
        empty_home(Path(root), monkeypatch.setenv)
        network = NetworkGuard()
        network.install(monkeypatch.setattr)
        real_direwolf = request.node.get_closest_marker("real_direwolf") is not None
        radio, processes, bluetooth = SerialGuard(), ProcessGuard(allowed=("direwolf",) if real_direwolf else ()), BluetoothGuard()
        no_shipped_programs(monkeypatch.setattr, Path(root) / "no-tools", real_direwolf)
        radio.install(monkeypatch.setattr)
        radio.install_com(monkeypatch.setattr)
        bluetooth.install(monkeypatch.setattr)
        bluetooth.install_ble(monkeypatch.setitem)
        no_default_alert(monkeypatch.setattr)
        no_journal(monkeypatch.setattr)
        # BlueZ is not asked which devices this machine is paired with: a test that needs some gives
        # its own answer
        monkeypatch.setattr(btpaired, "_run", lambda command: "")
        # The machine's USB devices are not read (slow, and not the test's): a test that needs some
        # gives its own list
        monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [])
        # No sound card's own levels are read or set (the machine's radios hang on its cards): as on
        # a system without ALSA; a test that needs a mixer gives its own
        monkeypatch.setattr(soundmixer, "load_alsa", lambda: None)
        monkeypatch.setattr(winmixer.CoreAudio, "_with_volume", lambda self, device, use: False)
        processes.install(monkeypatch.setattr)
        doors = ACTIVE_DOORS
        if doors is not None:
            # The guards of this test stand in front of the doors of the session.
            doors.paused = True
        yield
        if doors is not None:
            doors.paused = False
        assert not network.refused, "the test tried to reach something that is not this machine: " + ", ".join(network.refused)
        assert not radio.refused, "the test tried to open the radio's serial port: " + ", ".join(radio.refused)
        assert not bluetooth.refused, "the test tried to make a Bluetooth socket: " + ", ".join(bluetooth.refused)
        assert not processes.refused, f"the test started neoaprs without {SEARCH_VARIABLE} in its environment: " + ", ".join(processes.refused)
        assert not processes.shipped, "the test started a modem program of this installation: " + ", ".join(processes.shipped)


@pytest.fixture(autouse=True)
# logging_restored: set up first, torn down last
def no_unexpected_errors(request: pytest.FixtureRequest, logging_restored: None) -> Iterator[None]:
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
def no_leaked_db_threads() -> Iterator[None]:
    """Torn down after no_leaked_tasks (which stops the daemons of Env, and with them their Db): a
    Db that is still running now was not closed. Its thread is told to end, so that one leak does
    not fail the tests after it."""
    yield
    leaked = leaked_db_threads()
    for thread in leaked:
        thread.finish()
    assert not leaked, "the test left database threads running (await db.close()):\n  " + "\n  ".join(t.name for t in leaked)


# How long stopping what a test started may take when the test is over. A stop that hangs (on
# Windows 11 a teardown sat 25 minutes in the loop's `_poll`) fails the test by its name after this,
# with what still runs: the stacks that faulthandler_timeout (pyproject.toml, 120 s) prints end
# nothing, and a hung worker costs the CI job its whole time limit.
TEARDOWN_LIMIT_SEC = 60.0


async def torn_down_within(limit_sec: float, test: str) -> list[asyncio.Task[Any]]:
    """env.stop_all and the leaked tasks of `test`, in at most `limit_sec` (a timer of the loop: it
    wakes a loop that waits for a word that never comes, and cancels what waits); pytest.fail,
    naming the test, after that."""
    deadline = asyncio.timeout(limit_sec)
    try:
        async with deadline:
            await env_module.stop_all()
            return await leaked_tasks()
    except TimeoutError:
        if not deadline.expired():
            raise                                      # (a TimeoutError of the code being stopped, not of the limit)
        stuck = pending_tasks()
        for task in stuck:
            task.cancel()
        pytest.fail(f"{test}: stopping what the test started did not end in {limit_sec:g} s" + "".join(f"\n  still running: {describe_task(t)}" for t in stuck), pytrace=False)


@pytest_asyncio.fixture
async def no_leaked_tasks(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Added by tests/conftest.py to every async test (a fixture that is async would otherwise make
    a loop for the sync tests too)."""
    yield
    leaked = await torn_down_within(TEARDOWN_LIMIT_SEC, request.node.nodeid)
    for task in leaked:
        task.cancel()
    assert not leaked, "the test left tasks running (stop what it started):\n  " + "\n  ".join(describe_task(t) for t in leaked)
