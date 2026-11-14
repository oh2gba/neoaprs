"""The no-devices switch (neoaprs/nodevices.py): under NEOAPRS_NO_DEVICES=1 a daemon opens no real device and talks to no real service, whatever its settings say, and what is on this computer stays.

tests/conftest.py sets the variable for every process a test starts and lifts the switch in the test's own process (its fixture devices_are_fakes says why). The tests here are about the switch itself, so they
ask for `under_the_switch`, which keeps it on. Every way out of the process is watched while they run (`doors`): the record shows that a door was not even tried, where the guards of tests/support/guards.py
would only have refused it."""
import asyncio
import errno
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import serial.tools.list_ports  # type: ignore[import-untyped]

from neoaprs import btpaired, dummyline, mercurymodem, nodevices, pmtilesarchive, pmtilescut, serialprobe, updatedownload, updatefetch
from neoaprs.alertcommand import DEFAULT_ALERT_COMMAND
from neoaprs.gpsfeed import GpsFeed
from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryspeaker import player_command
from neoaprs.message import MessageRecord
from neoaprs.rigctld import RigError, read_rig
from neoaprs.serialport import SerialError, SerialPort
from neoaprs.services.alerts import Alerts
from neoaprs.source import Backoff, Source
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.wiring import hf_settings, hf_words
from tests.conftest import ROOT
from tests.support import realmercury
from tests.support.alertcmd import TIMEOUT_SEC, writing
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, idle_for, remember_stop, until
from tests.support.fakemercury import program as fake_mercury
from tests.support.fakeversionpage import version_page
from tests.support.madepmtiles import planet
from tests.support.proc import NEW_GROUP, stop
from tests.support.ptyline import Ptys, heard, held_by_a_program, posix_only
from tests.support.rangeserver import range_server
from tests.support.storedb import store_at

LOCAL = ("127.0.0.1", "::1", "localhost")
ELSEWHERE = "192.0.2.7"                           # a documentation address: no computer has it (so a door that this file found open would still have reached nobody)
REFUSED = os.strerror(errno.ECONNREFUSED)        # "Connection refused", in the system's words
PATIENCE_SEC = 60.0                              # the longest a test waits for a daemon it started as a process, on a machine busy with the whole suite
SAYS_THE_VALUE = "(the variable is {!r}: every value but an empty one and 0 sets it)"       # how the line at the start of the daemon ends
STARTS_A_DAEMON = {"scripts/smoke.py", "scripts/screenshots.py", "scripts/demoscene.py", "scripts/smoke-appimage", "scripts/smoke-macos-app", "scripts/check", "scripts/check-in-container"}
WITHOUT_THE_SWITCH: set[str] = set()                 # what starts daemons and does not set the switch for them


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The switch is on in this test's own process too (tests/conftest.py lifts it for every test that does not ask for this), and no door has been told in the log yet."""
    monkeypatch.setenv(nodevices.ENV, "1")
    monkeypatch.setattr(nodevices, "_told", set())


class Doors:
    """Every way out of the process, watched: each file opened by its path, each program started, each socket connected, each name looked up, each Bluetooth socket made and each time the machine is asked for its
    ports or its paired devices is written down, and then goes on as it would have. A socket pair is not a way out: where the system has none (Windows) the standard library makes one as a TCP connection to a
    listener of its own on 127.0.0.1, which every event loop does for its wake-up, so what is connected inside `socket.socketpair` is not written down."""

    def __init__(self, patch: Callable[[Any, str, Any], None]) -> None:
        self.opened: list[str] = []                 # what os.open was given (pyserial opens a device with it), with every link followed
        self.started: list[str] = []                # the programs started
        self.connected: list[str] = []              # the hosts sockets were connected to
        self.ports: list[int] = []                  # ... and the port of each
        self.looked_up: list[str] = []              # the names asked of the resolver
        self.bluetooth = 0                          # Bluetooth sockets made
        self.listed: list[str] = []                 # what the machine was asked to list
        self._pairing = threading.local()           # (whether this thread is inside socket.socketpair)
        real_pair = socket.socketpair
        real_open, real_popen, real_connect, real_connect_ex, real_lookup, real_socket, real_ports, real_paired = (
            os.open, subprocess.Popen.__init__, socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo, socket.socket.__init__, serial.tools.list_ports.comports, btpaired._run)

        def opening(path: Any, *args: Any, **kwargs: Any) -> int:
            if isinstance(path, (str, bytes, os.PathLike)):
                self.opened.append(os.path.realpath(os.fsdecode(path)))
            return real_open(path, *args, **kwargs)

        def starting(popen: Any, args: Any, *rest: Any, **kwargs: Any) -> None:
            self.started.append(str(args))
            real_popen(popen, args, *rest, **kwargs)

        def pairing(*args: Any, **kwargs: Any) -> Any:
            self._pairing.inside = True
            try:
                return real_pair(*args, **kwargs)
            finally:
                self._pairing.inside = False

        def connecting(sock: socket.socket, address: Any) -> None:
            self._note(address)
            real_connect(sock, address)

        def connecting_ex(sock: socket.socket, address: Any) -> int:
            self._note(address)
            return real_connect_ex(sock, address)

        def looking_up(host: Any, *args: Any, **kwargs: Any) -> Any:
            if host is not None:
                self.looked_up.append(os.fsdecode(host))
            return real_lookup(host, *args, **kwargs)

        def making(sock: socket.socket, family: Any = -1, *args: Any, **kwargs: Any) -> None:
            self.bluetooth += family == getattr(socket, "AF_BLUETOOTH", object())
            real_socket(sock, family, *args, **kwargs)

        def ports() -> Any:
            self.listed.append("the serial ports")
            return real_ports()

        def paired(command: list[str]) -> str:
            self.listed.append("the paired Bluetooth devices")
            return str(real_paired(command))

        for owner, name, watched in ((os, "open", opening), (subprocess.Popen, "__init__", starting), (socket.socket, "connect", connecting), (socket.socket, "connect_ex", connecting_ex),
                                     (socket, "getaddrinfo", looking_up), (socket, "socketpair", pairing), (socket.socket, "__init__", making), (serial.tools.list_ports, "comports", ports), (btpaired, "_run", paired)):
            patch(owner, name, watched)

    def _note(self, address: Any) -> None:
        if isinstance(address, tuple) and len(address) > 1 and isinstance(address[0], str) and not getattr(self._pairing, "inside", False):
            self.connected.append(address[0])
            self.ports.append(int(address[1]))

    @property
    def left_this_computer(self) -> list[str]:
        """Every host that was connected to or looked up and is not this computer (the page listens on the loopback address of this computer's name too, 127.0.1.1 on Debian)."""
        return [host for host in self.connected + self.looked_up if host not in LOCAL and not nodevices.this_computer(host)]

    def untouched(self) -> bool:
        """No program was started, nothing left this computer, no Bluetooth socket was made and the machine was asked for no list."""
        return not (self.started or self.left_this_computer or self.bluetooth or self.listed)


@pytest.fixture
def doors(monkeypatch: pytest.MonkeyPatch) -> Doors:
    return Doors(monkeypatch.setattr)


def said(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    """What the switch wrote to the log: the level and the line of each."""
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "neoaprs.nodevices"]


# ---- the switch

def test_the_suite_has_the_switch_in_the_environment_and_lifts_it_in_the_tests_own_process() -> None:
    assert os.environ[nodevices.ENV] == "1" and not nodevices.on(), "tests/conftest.py: set for the processes a test starts, lifted here"
    asks = [sys.executable, "-c", "from neoaprs import nodevices; print(nodevices.on())"]
    child = subprocess.run(asks, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert child.stdout.strip() == "True", child
    mistyped = subprocess.run(asks, cwd=ROOT, env={**os.environ, nodevices.ENV: "ture"}, capture_output=True, text=True, timeout=60)
    assert mistyped.stdout.strip() == "True", "a process whose switch was mistyped is under it all the same"
    assert nodevices.sets(realmercury.daemon_env().get(nodevices.ENV)), "the environment the harness builds for the daemon of a bench keeps the switch of the suite"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1", "01", "2", "ture", "false", "no", "off", "0.0"])
def test_the_switch_is_on_for_every_value_but_nothing_and_0_and_the_start_line_names_the_value(value: str, under_the_switch: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """It fails safe: `true`, a typo, and a word that was meant to switch it off all keep the doors shut, and the log shows which value did."""
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    monkeypatch.setenv(nodevices.ENV, value)
    assert nodevices.sets(value) and nodevices.on()
    nodevices.announce()
    with pytest.raises(FileNotFoundError):
        nodevices.check_port("/dev/ttyUSB0")
    with pytest.raises(ConnectionRefusedError):
        nodevices.check_host("rotate.aprs2.net", "APRS-IS")
    [(level, line)] = said(caplog)[:1]
    assert level == logging.INFO and line.startswith("NEOAPRS_NO_DEVICES is set: no serial port") and line.endswith(SAYS_THE_VALUE.format(value))


@pytest.mark.parametrize("value", ["", "0", " 0 ", "  ", None])
def test_the_switch_is_off_for_nothing_and_for_0(value: str | None, under_the_switch: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    if value is None:
        monkeypatch.delenv(nodevices.ENV)
    else:
        monkeypatch.setenv(nodevices.ENV, value)
    assert not nodevices.sets(value) and not nodevices.on()
    nodevices.announce()
    nodevices.check_port("/dev/ttyUSB0")
    nodevices.check_host("rotate.aprs2.net", "APRS-IS")
    assert nodevices.direct() == [] and said(caplog) == []


def gives(path: Path, variable: str, value: str) -> bool:
    """Whether the file gives the variable this value in its code (what follows a `#` on a line is a comment). In Python that is `env["X"] = "1"`, `"X": "1"` in a dict or `X="1"` in a call; in a shell script
    `export X=1` or `X=1 program`. The words of a docstring, which name the variable without quotes, are none of these."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    python = path.suffix == ".py" or "python" in "".join(lines[:1])           # (a script without an ending is known by its first line)
    form = rf'"{variable}"\]\s*=\s*"{value}"|"{variable}":\s*"{value}"|\b{variable}="{value}"' if python else rf"(?:^|\s){variable}={value}(?:\s|$)"
    return any(re.search(form, line.split("#", 1)[0]) for line in lines)


def test_a_line_of_code_sets_a_variable_and_a_comment_a_docstring_or_another_value_does_not(tmp_path: Path) -> None:
    def file(text: str, name: str = "script") -> Path:
        (tmp_path / name).write_text(text, encoding="utf-8")
        return tmp_path / name

    python, shell = "#!/usr/bin/env python3\n", "#!/usr/bin/env bash\n"
    for text in ('env["NEOAPRS_NO_DEVICES"] = "1"      # (why)\n', 'os.environ["NEOAPRS_NO_DEVICES"] = "1"\n', 'ENVIRONMENT = {"UV_FROZEN": "1", "NEOAPRS_NO_DEVICES": "1"}\n', 'env.update(NEOAPRS_UPDATE_CHECK="0", NEOAPRS_NO_DEVICES="1")\n'):
        assert gives(file(python + text), nodevices.ENV, "1") and gives(file(text, "script.py"), nodevices.ENV, "1"), text
    for text in ("export NEOAPRS_NO_DEVICES=1    # why\n", '    env -u PYTHONPATH NEOAPRS_NO_DEVICES=1 NEOAPRS_UPDATE_CHECK=0 "$python" scripts/smoke.py\n'):
        assert gives(file(shell + text), nodevices.ENV, "1"), text
    for text in ('# env["NEOAPRS_NO_DEVICES"] = "1"\n', '"""Inside, NEOAPRS_NO_DEVICES=1 is set."""\n', 'env["NEOAPRS_NO_DEVICES"] = "0"\n', 'DEVICES_VARIABLE = "NEOAPRS_NO_DEVICES"\n', 'env.pop("NEOAPRS_NO_DEVICES", None)\n'):
        assert not gives(file(python + text), nodevices.ENV, "1"), text
    for text in ("# export NEOAPRS_NO_DEVICES=1\n", "export NEOAPRS_NO_DEVICES=0\n", "export NEOAPRS_NO_DEVICES=10\n", 'echo "devices=${NEOAPRS_NO_DEVICES-unset}"\n', "unset NEOAPRS_NO_DEVICES\n"):
        assert not gives(file(shell + text), nodevices.ENV, "1"), text


def test_every_script_and_part_of_the_harness_that_starts_a_daemon_sets_the_switch_for_it() -> None:
    """Whatever starts a daemon tells it not to ask the version page (NEOAPRS_UPDATE_CHECK=0), so that is how the starters are found, a script written tomorrow among them. Under the suite the line of a script
    cannot be seen in what its daemon does (the daemon inherits the switch from tests/conftest.py anyway), so the files are read."""
    files = [p for p in sorted((ROOT / "scripts").iterdir()) if p.is_file()] + sorted((ROOT / "tests" / "support").glob("*.py"))
    starters = {p.relative_to(ROOT).as_posix() for p in files if gives(p, "NEOAPRS_UPDATE_CHECK", "0")}
    assert STARTS_A_DAEMON <= starters, "the rule finds the scripts that are known to start a daemon"
    without = {name for name in starters if not gives(ROOT / name, nodevices.ENV, "1")}
    assert without == WITHOUT_THE_SWITCH, "a script that starts a daemon without NEOAPRS_NO_DEVICES=1 (or one of WITHOUT_THE_SWITCH that sets it now and is to leave the list)"


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "localhost.", "127.0.0.1", "127.9.8.7", "::1", "[::1]", "::ffff:127.0.0.1", "::1%lo", "", " 127.0.0.1 "])
def test_this_computer_is_localhost_and_the_loopback(host: str) -> None:
    assert nodevices.this_computer(host)


@pytest.mark.parametrize("host", ["rotate.aprs2.net", "neo.oh2gba.eu", "192.168.1.20", "10.0.0.1", ELSEWHERE, "0.0.0.0", "::", "fe80::1%eth0", "127.0.0.1.example.org", "localhost.example.org", "2130706433", "127.1", "my-own-hostname"])
def test_any_other_name_or_address_is_somewhere_else_and_is_never_looked_up(host: str, doors: Doors) -> None:
    assert not nodevices.this_computer(host) and doors.looked_up == []


@pytest.mark.parametrize("path, error", [("/dev/ttyUSB0", FileNotFoundError), ("/dev/serial/by-id/usb-FTDI_FT232R-if00-port0", FileNotFoundError), ("COM3", FileNotFoundError), ("/dev/rfcomm0", FileNotFoundError),
                                         ("bt://AA:BB:CC:DD:EE:FF", ConnectionRefusedError), ("ble://AA:BB:CC:DD:EE:FF", ConnectionRefusedError), (f"socket://{ELSEWHERE}:8001", ConnectionRefusedError),
                                         ("tcp://radio.example.org:8001", ConnectionRefusedError), (f"socket://127.0.0.1:8001@{ELSEWHERE}:8001", ConnectionRefusedError), ("rfc2217://127.0.0.1:4000", ConnectionRefusedError),
                                         ("hwgrep://ttyUSB", ConnectionRefusedError)])
def test_a_port_is_refused_with_the_error_of_one_that_is_not_there(path: str, error: type[OSError], under_the_switch: None) -> None:
    with pytest.raises(error) as refusal:
        nodevices.check_port(path)
    assert type(refusal.value) is error and refusal.value.strerror == os.strerror(refusal.value.errno or 0)


@pytest.mark.parametrize("path", ["socket://127.0.0.1:8001", "tcp://localhost:8100", "socket://[::1]:8001", " TCP://127.0.0.1:8001 ", "socket://127.0.0.1:8001?logging=debug"])
def test_a_tcp_port_on_this_computer_is_let_through(path: str, under_the_switch: None, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    nodevices.check_port(path)
    assert said(caplog) == []


def test_an_address_is_refused_unless_it_names_this_computer_or_a_file(under_the_switch: None) -> None:
    for url in ("https://neo.oh2gba.eu/version.php", "http://build.protomaps.com/20261101.pmtiles", f"http://{ELSEWHERE}:8080/x", f"http://127.0.0.1:80@{ELSEWHERE}/x", "https://localhost.example.org/", "http://[::1"):
        assert nodevices.url_refused(url), url
        with pytest.raises(ConnectionRefusedError):
            nodevices.check_url(url)
    for url in ("http://127.0.0.1:8080/version.php", "https://localhost/x", "http://[::1]:9/", "/data/basemap.pmtiles", "basemap.pmtiles", "C:\\maps\\basemap.pmtiles", "file:///data/basemap.pmtiles"):
        assert not nodevices.url_refused(url), url
        nodevices.check_url(url)
    for host in ("rotate.aprs2.net", ELSEWHERE):
        assert nodevices.host_refused(host)
        with pytest.raises(ConnectionRefusedError):
            nodevices.check_host(host, "APRS-IS")
    nodevices.check_host("127.0.0.1", "gpsd")
    nodevices.check_host("localhost")


def test_the_start_is_one_line_and_each_door_is_told_once_at_its_level(under_the_switch: None, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    nodevices.announce()
    for _ in range(3):
        assert nodevices.refused("the Mercury modem program is not started")
        assert nodevices.refused("the ports are not listed", logging.INFO)
        with pytest.raises(FileNotFoundError):
            nodevices.check_port("/dev/ttyUSB0")
        with pytest.raises(ConnectionRefusedError):
            nodevices.check_host("rotate.aprs2.net", "APRS-IS")
        with pytest.raises(ConnectionRefusedError):
            nodevices.check_url("https://neo.oh2gba.eu/version.php", level=logging.DEBUG)
    lines = said(caplog)
    assert lines[0][0] == logging.INFO and lines[0][1].startswith("NEOAPRS_NO_DEVICES is set: no serial port, Bluetooth device or sound card is opened")
    assert lines[1:] == [(logging.WARNING, "NEOAPRS_NO_DEVICES is set: the Mercury modem program is not started"), (logging.INFO, "NEOAPRS_NO_DEVICES is set: the ports are not listed"),
                         (logging.WARNING, "NEOAPRS_NO_DEVICES is set: the serial port /dev/ttyUSB0 is not opened"), (logging.WARNING, "NEOAPRS_NO_DEVICES is set: no connection to rotate.aprs2.net (APRS-IS)"),
                         (logging.DEBUG, "NEOAPRS_NO_DEVICES is set: no connection to neo.oh2gba.eu")]


def test_with_the_switch_off_nothing_is_refused_and_nothing_is_said(under_the_switch: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    monkeypatch.delenv(nodevices.ENV)
    nodevices.announce()
    nodevices.check_port("/dev/ttyUSB0")
    nodevices.check_port("bt://AA:BB:CC:DD:EE:FF")
    nodevices.check_host("rotate.aprs2.net", "APRS-IS")
    nodevices.check_url("https://neo.oh2gba.eu/version.php")
    assert not nodevices.refused("anything") and not nodevices.host_refused(ELSEWHERE) and not nodevices.url_refused("https://neo.oh2gba.eu/")
    assert said(caplog) == []


def test_the_record_of_connections_leaves_out_a_socket_pair_and_not_a_connection_made_the_same_way(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows has no socket pair of its own: the standard library connects two sockets over the loopback, as the fallback here does (the system of the test has the real one, which does not connect at all)."""
    def over_the_loopback() -> tuple[socket.socket, socket.socket]:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        client = socket.socket()
        client.connect(listener.getsockname())
        server, _ = listener.accept()
        listener.close()
        return client, server

    monkeypatch.setattr(socket, "socketpair", over_the_loopback)
    doors = Doors(monkeypatch.setattr)
    for sock in socket.socketpair():
        sock.close()
    assert doors.connected == [] and doors.ports == [] and doors.untouched()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    client = socket.socket()
    try:
        client.connect(listener.getsockname())
        assert doors.connected == ["127.0.0.1"] and doors.ports == [listener.getsockname()[1]], "a connection of the code under test is still written down"
    finally:
        client.close()
        listener.close()


# ---- the doors, each where it is

@posix_only
async def test_the_serial_line_opens_no_device_no_bluetooth_port_and_no_tcp_port_elsewhere(under_the_switch: None, doors: Doors, ptys: Ptys) -> None:
    _, device = ptys()
    with pytest.raises(SerialError) as missing:
        await SerialPort(device).open()
    assert str(missing.value) == f"{device}: No such file or directory", "what the line says of a device that is not there"
    for port in ("bt://AA:BB:CC:DD:EE:FF", "ble://AA:BB:CC:DD:EE:FF", f"socket://{ELSEWHERE}:8001", f"tcp://{ELSEWHERE}:8001"):
        with pytest.raises(SerialError) as refused:
            await SerialPort(port).open()
        assert str(refused.value) == f"{port}: {REFUSED}"
    assert os.path.realpath(device) not in doors.opened and doors.untouched() and doors.connected == []


@posix_only
def test_the_lists_of_ports_are_empty_and_the_machine_is_not_asked(under_the_switch: None, doors: Doors, ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, device = ptys()
    (tmp_path / "probe_1").symlink_to(device)
    pattern = str(tmp_path / "probe_*")
    assert serialprobe.candidate_ports(pattern) == [] and serialprobe.searchable_ports(pattern) == ([], {})
    assert serialprobe.available_ports() == [] and serialprobe.paired_bluetooth_ports() == [] and serialprobe.system_ports() == []
    assert serialprobe.identity_of("/dev/ttyUSB0") is None and serialprobe.bluetooth_com_keys() == set()
    assert doors.listed == [] and doors.started == []
    monkeypatch.delenv(nodevices.ENV)
    assert serialprobe.candidate_ports(pattern) == [str(tmp_path / "probe_1")], "the same folder with the switch off"


async def test_nothing_is_fetched_from_or_sent_to_another_computer(under_the_switch: None, doors: Doors, tmp_path: Path) -> None:
    there = f"https://{ELSEWHERE}/version.php"
    assert updatefetch.get_url(there, "0.1.0", "linux") is None and updatefetch.get(there, "0.1.0", "linux", "0" * 32) is None
    assert await updatefetch.fetch_url(there, "0.1.0", "linux", 100) is None
    assert updatefetch.post_form(there, {"note": "x"}, {"bundle": ("b.zip", b"zip")}, "0.1.0", "linux") is None, "as a server that could not be reached"
    with pytest.raises(updatedownload.DownloadError, match="could not be fetched"):
        updatedownload.open_url(f"https://{ELSEWHERE}/releases/download/v0.1.0/SHA256SUMS", lambda url: True)
    assert pmtilesarchive.url_exists(f"https://{ELSEWHERE}/20261101.pmtiles") is False
    for dry_run in (True, False):
        with pytest.raises(pmtilescut.CutError) as unreachable:
            await pmtilescut.extract(f"https://{ELSEWHERE}/20261101.pmtiles", tmp_path / "map.pmtiles", None, 5, dry_run=dry_run)
        assert str(unreachable.value) == pmtilesarchive.UNREACHABLE and not list(tmp_path.glob("map.pmtiles*"))
    with pytest.raises(RigError, match="connection refused"):
        await read_rig(ELSEWHERE, 4532)
    assert doors.untouched() and doors.connected == []


async def test_a_gpsd_and_the_control_port_of_a_mercury_on_another_computer_are_not_connected_to(under_the_switch: None, doors: Doors, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    feed = GpsFeed(FixedClock(), Backoff([0.01]))
    remember_stop(feed.stop)
    feed.configure("gpsd", f"{ELSEWHERE}:2947", 4800)
    await feed.start()
    await until(lambda: feed.state is Source.State.WAITING)
    assert feed.problem == f"gpsd at {ELSEWHERE}:2947: {REFUSED}", "what the feed says of a gpsd that does not run"
    modem = Mercury(tmp_path, finder=lambda: None, control_backoff=Backoff([0.01]))
    remember_stop(modem.stop)
    await modem.start(replace(ON_AIR, hf_enabled=True), f"socket://{ELSEWHERE}:8100")       # (a Mercury that something else runs there, given for this run: its control port is the one line the modem part opens)
    await until(lambda: (logging.WARNING, f"NEOAPRS_NO_DEVICES is set: no connection to {ELSEWHERE} (the control port of a Mercury)") in said(caplog))
    await idle_for(0.1)                                     # (both try again after their back-off, several times in this)
    assert (logging.WARNING, f"NEOAPRS_NO_DEVICES is set: no connection to {ELSEWHERE} (gpsd)") in said(caplog) and len(said(caplog)) == 2
    assert modem.state == "starting" and feed.state is Source.State.WAITING, "the modem part waits for the control port as for a Mercury that is not up yet"
    assert doors.untouched() and doors.connected == []


async def test_a_server_on_this_computer_is_asked_itself_and_not_through_a_proxy_of_the_environment(under_the_switch: None, doors: Doors, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """urllib sends a request for the loopback to the proxy that http_proxy names unless no_proxy lists the loopback: under the switch that proxy, on another computer, is not asked."""
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, f"http://{ELSEWHERE}:3128")
    page = await version_page({"version": "9.9.9", "url": "https://example.org/", "message": ""})
    assert b"9.9.9" in (await updatefetch.fetch(page.url, "0.1.0", "linux") or b"")
    await asyncio.to_thread(updatefetch.post_form, page.url, {"note": "x"}, {}, "0.1.0", "linux")
    (await asyncio.to_thread(updatedownload.open_url, page.url, lambda url: True)).close()
    assert await asyncio.to_thread(pmtilesarchive.url_exists, page.url)
    with pytest.raises(pmtilescut.CutError, match="not 206"):
        await pmtilescut.extract(page.url, tmp_path / "map.pmtiles", None, 5)
    assert len(page.requests) == 5, "each of the five reached the server of this computer"
    assert doors.left_this_computer == [] and set(doors.connected) <= set(LOCAL) and set(doors.ports) == {page.port}


async def test_a_server_on_this_computer_is_still_asked(under_the_switch: None, doors: Doors) -> None:
    page = await version_page({"version": "9.9.9", "url": "https://example.org/", "message": ""})
    assert b"9.9.9" in (await updatefetch.fetch(page.url, "0.1.0", "linux") or b"") and len(page.requests) == 1
    assert doors.left_this_computer == [] and set(doors.connected) <= set(LOCAL) and page.port in doors.ports


def test_a_redirect_to_another_computer_is_not_followed(under_the_switch: None) -> None:
    request = urllib.request.Request("http://127.0.0.1:1/version.php")
    with pytest.raises(ConnectionRefusedError):
        updatefetch._NotDowngraded().redirect_request(request, None, 302, "Found", {}, f"http://{ELSEWHERE}/version.php")       # type: ignore[arg-type]
    assert updatefetch._NotDowngraded().redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1:2/version.php") is not None       # type: ignore[arg-type]


async def test_a_map_server_that_sends_the_cut_on_to_another_computer_is_not_followed(under_the_switch: None, doors: Doors, tmp_path: Path) -> None:
    server = await range_server(planet())
    server.mode, server.moved_to = "moved", f"http://{ELSEWHERE}/20261101.pmtiles"
    with pytest.raises(pmtilescut.CutError) as unreachable:
        await asyncio.to_thread(pmtilescut.Cutting(server.url, tmp_path / "map.pmtiles", None, 5, pauses=(0.0, 0.0, 0.0)).run)
    assert str(unreachable.value) == pmtilesarchive.UNREACHABLE and server.cuts == 4 and doors.left_this_computer == []
    request = urllib.request.Request("https://127.0.0.1:1/20261101.pmtiles")
    with pytest.raises(urllib.error.HTTPError, match="https to http"):
        pmtilesarchive.Redirected().redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1:1/20261101.pmtiles")       # type: ignore[arg-type]


async def test_the_default_alert_command_is_not_run_and_the_operators_own_is(under_the_switch: None, doors: Doors, tmp_path: Path) -> None:
    message = MessageRecord(0, FixedClock()(), "in", "OH2RDG-7", "OH2GBA", "Moi", "12", "received")
    config = replace(ON_AIR, messages_alert=True, messages_alert_command=f"  {DEFAULT_ALERT_COMMAND} ")
    alerts = Alerts(lambda: config, FixedClock(), TIMEOUT_SEC)
    remember_stop(alerts.stop)
    alerts.alert(message)
    assert len(alerts._tasks) == 0 and doors.started == []
    with pytest.raises(ValueError, match="no alert command"):
        await alerts.test()
    assert doors.started == [], "neither the alert nor its test button started the notifier or the player"
    out = tmp_path / "alert.txt"
    config = replace(config, messages_alert_command=writing(out))
    assert await alerts.test() == (True, "ran") and out.read_text(encoding="utf-8").splitlines()[0] == "NEOAPRS"


@posix_only
def test_no_player_of_the_dummy_hf_radios_audio_is_found(under_the_switch: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    player = tmp_path / "aplay"
    player.write_text("#!/bin/sh\n", encoding="utf-8")
    player.chmod(0o755)
    monkeypatch.setenv("NEOAPRS_PLAYER_PATH", str(tmp_path))
    assert player_command() is None
    monkeypatch.delenv(nodevices.ENV)
    assert (player_command() or [""])[0] == str(player), "the same folder with the switch off"


async def test_the_mercury_program_is_not_started_and_lists_no_sound_card(under_the_switch: None, doors: Doors, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    asked: list[str] = []
    monkeypatch.setattr(mercurymodem, "end_stale", lambda pid_file: asked.append(f"end the Mercury of {pid_file}"))
    (tmp_path / "mercury.pid").write_text("4242\n", encoding="utf-8")       # a copy of a data folder whose own daemon runs its modem: the file names a Mercury that is another daemon's
    modem = Mercury(tmp_path, finder=lambda: asked.append("where is Mercury") or fake_mercury())       # type: ignore[func-returns-value]
    remember_stop(modem.stop)
    await modem.start(replace(ON_AIR, hf_enabled=True, mercury_sound_card="plughw:1,0", mercury_keying="vox"))
    assert (modem.state, modem.reason) == ("waiting", "not_installed") and modem.sound_cards() == []
    await modem.start(ON_AIR, speaker=True)
    assert modem.state == "waiting" and not (tmp_path / "mercury.ini").exists() and (tmp_path / "mercury.pid").read_text(encoding="utf-8") == "4242\n"
    assert asked == [] and doors.started == [], "the program was not looked for, the Mercury the data folder names was left alone and nothing was started, as the modem or as the Dummy HF radio's speaker"
    logged = [r.getMessage() for r in caplog.records]
    assert logged[0] == "NEOAPRS_NO_DEVICES is set: the Mercury modem program is not started and its sound cards are not listed" and logged.count(logged[0]) == 1
    assert not [line for line in logged if line.startswith("no Mercury program at")], "the log names no place where the program is missing: nobody looked for it"


def test_the_hf_radio_has_no_port_unless_a_mercury_was_given_for_this_run(under_the_switch: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """The daemon starts no Mercury under the switch, so whatever listens where one of ours would have been (the operator's own modem, on this computer's port 8100) is not ours: the HF Tnc is given no port at all."""
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    off, on = replace(ON_AIR, hf_enabled=False), replace(ON_AIR, hf_enabled=True)
    assert (hf_settings(off).port, hf_settings(off).pattern, hf_settings(off).fallback_probe) == ("", "", False) and said(caplog) == [], "no port, and nothing said while there is no HF radio"
    assert (hf_settings(on).port, hf_settings(on, modem_port=18100).port, hf_settings(on).pattern) == ("", "", "")
    assert said(caplog) == [(logging.INFO, "NEOAPRS_NO_DEVICES is set: the HF radio has no line to a Mercury: none is started, and none was given for this run (--hf-port)")]
    assert hf_settings(on, "socket://127.0.0.1:18100").port == "socket://127.0.0.1:18100", "a Mercury given for this run (the benches') is the HF radio's"
    assert hf_settings(replace(on, hf_profile="dummy-hf")).port == dummyline.DUMMY_PATH
    assert hf_words(on, "") == "the Mercury modem, which is not started" and hf_words(replace(on, hf_profile="dummy-hf"), "") == "the Dummy HF radio, made-up stations", "the start line claims no modem and no speaker"
    assert hf_words(on, "socket://127.0.0.1:18100") == "the Mercury modem, one something else runs at socket://127.0.0.1:18100"
    monkeypatch.delenv(nodevices.ENV)
    assert hf_settings(on).port == "socket://127.0.0.1:8100" and hf_settings(on, modem_port=18100).port == "socket://127.0.0.1:18100", "the same with the switch off"
    assert hf_words(on, "") == "the Mercury modem, started by NeoAPRS" and hf_words(replace(on, hf_profile="dummy-hf"), "").endswith("and the modem played through the speakers")


# ---- what stays, and the whole daemon

async def test_a_kiss_tcp_radio_on_this_computer_is_still_opened_and_heard(under_the_switch: None, doors: Doors, tmp_path: Path) -> None:
    e = Env(tmp_path)                                       # (its radio is a TCP port of the loopback, and so is --port)
    await e.start()
    assert await e.play() == 4 and len(await e.packets()) == 4
    assert e.tnc.state is Source.State.CONNECTED and doors.left_this_computer == [] and doors.started == []


def lines_of(source: Source) -> str:
    return "\n".join(source.lines)


@posix_only
async def test_a_daemon_whose_settings_name_real_devices_comes_up_and_opens_none_and_its_dummy_radio_and_page_work(under_the_switch: None, doors: Doors, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                                                  caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="neoaprs")
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)
    monkeypatch.setenv(nodevices.ENV, "true")                # (not the 1 of the benches: any value but an empty one and 0 is the switch)
    e = Env(tmp_path, radio=False, web=True)
    port = {name: e.new_pty(name)[1] for name in ("radio", "probe_1", "gps", "ptt")}       # the FM radio's port, a port the search for the radio would find, the GPS receiver's and the HF radio's keying line: each a device that is there
    devices = {os.path.realpath(path) for path in port.values()}
    e.settings.update({"serial/port": port["radio"], "hf/enabled": "true", "hf/profile": "mercury", "mercury/sound_card": "plughw:1,0", "mercury/keying": f"rts:{port['ptt']}",
                       "igate/enabled": "true", "igate/server": "rotate.aprs2.net:14580", "igate/password": "12345", "gps/source": "serial", "gps/device": port["gps"],
                       "status/source": "rig", "status/rigctld": f"{ELSEWHERE}:4532", "messages/alert": "true"})
    looked_for: list[str] = []
    e.ctl.mercury._finder = lambda: looked_for.append("Mercury") or fake_mercury()       # type: ignore[func-returns-value]   # a Mercury that is there and would start
    e.ctl.rigstatus.poll_sec = 0.02
    await e.start()

    # every part waits as it does for a device that is not there
    await until(lambda: e.tnc.state is Source.State.WAITING and e.tnc.stats.opens == 0 and "trying again" in lines_of(e.tnc) and "no port" in lines_of(e.tnc))
    assert f"{port['radio']}: No such file or directory" in lines_of(e.tnc)
    await until(lambda: e.ctl.mercury.state == "waiting" and e.hf.state is Source.State.WAITING)
    assert e.ctl.mercury.reason == "not_installed" and looked_for == [] and e.hf.port == "" and e.hf.stats.opens == 0, "no Mercury was started, so the HF radio has no port to try"
    mercury_ports = {e.ctl.mercury.broadcast_port, e.ctl.mercury.control_port}                # where a Mercury of ours would have been: on the operator's computer his own modem may listen there
    await until(lambda: e.ctl.aprsis.state is Source.State.WAITING)
    assert (e.ctl.igate.state, e.ctl.igate.problem) == ("connecting", f"rotate.aprs2.net:14580: {REFUSED}")
    await until(lambda: e.ctl.gps_feed.state is Source.State.WAITING)
    assert e.ctl.gps_feed.problem == f"{port['gps']}: No such file or directory"
    await until(lambda: e.ctl.rigstatus.rig_state == "off")
    assert e.ctl.rigstatus._rig_problem == f"rigctld at {ELSEWHERE}:4532: connection refused"

    # the page is served and says the same; what it asks for lists nothing and reaches a server of this computer only
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert page.topics["tnc"]["state"] == "waiting" and page.topics["hf"]["state"] == "waiting" and page.topics["hf"]["modem"]["reason"] == "not_installed"
    assert page.topics["igate"]["state"] == "connecting" and page.topics["igate"]["problem"].endswith(REFUSED)
    await page.send({"cmd": "list_ports"})
    listed = await page.expect("ports")
    assert listed["ports"] == [] and listed["sound_cards"] == []
    versions = await version_page({"version": "99.0.0", "url": "https://example.org/", "message": ""})
    for address, outcome in ((f"https://{ELSEWHERE}/version.php", "no_answer"), (versions.url, "newer")):       # Check now, of a version page somewhere else and of one on this computer
        await page.send({"cmd": "set_config", "values": {"update/url": address}})
        await page.until(lambda address=address: page.topics["config"]["values"]["update/url"] == address)       # type: ignore[misc]
        await page.send({"cmd": "update_check"})
        assert (await page.expect("update_result"))["outcome"] == outcome
    assert len(versions.requests) == 1

    # the log: one line at the start, one for each door, however often it was tried
    lines = [line for _, line in said(caplog)]
    assert lines[0].startswith("NEOAPRS_NO_DEVICES is set: no serial port, Bluetooth device or sound card is opened") and lines[0].endswith(SAYS_THE_VALUE.format("true")) and len(lines) == len(set(lines))
    assert set(lines[1:]) == {f"NEOAPRS_NO_DEVICES is set: {door}" for door in (
        f"the serial port {port['radio']} is not opened", f"the serial port {port['gps']} is not opened", "the serial ports and the paired Bluetooth devices are not listed or searched",
        "the Mercury modem program is not started and its sound cards are not listed", "the HF radio has no line to a Mercury: none is started, and none was given for this run (--hf-port)",
        "no connection to rotate.aprs2.net (APRS-IS)", f"no connection to {ELSEWHERE} (rigctld)", f"no connection to {ELSEWHERE}")}
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], "nothing of this is an error"

    # the same daemon on the Dummy radios: made-up stations arrive and reach the page
    await page.send({"cmd": "set_config", "values": {"tnc/profile": "dummy", "hf/profile": "dummy-hf"}})
    await until(lambda: e.tnc.is_dummy and e.tnc.state is Source.State.CONNECTED and e.hf.is_dummy and e.hf.state is Source.State.CONNECTED)
    for _ in range(200):
        e.now.advance(10)                                                               # type: ignore[attr-defined]
        await idle_for(0.02)                                                            # (the Dummy radio's scene is asked what has come due at the new time)
        if sum(call.startswith("Q") for call in page.topics["stations"]) > 8:
            break
    assert {"Q1ABC", "Q4CAR-9", "Q2DIG-2"} <= set(page.topics["stations"])
    await page.until(lambda: page.topics["tnc"]["dummy"] and page.topics["tnc"]["state"] == "connected" and page.topics["hf"]["dummy"] and page.topics["hf"]["state"] == "connected")
    assert page.of("error") == []

    # and through all of it no device was opened, no program started and nothing left this computer
    assert not devices & set(doors.opened), "a pseudo-terminal named in the settings was opened"
    assert doors.started == [] and looked_for == [] and doors.bluetooth == 0 and doors.listed == []
    assert doors.left_this_computer == [] and set(doors.connected) <= set(LOCAL) and not mercury_ports & set(doors.ports)
    assert set(doors.ports) == {e.port, versions.port}, "the only connections were this test's own: its tab of the page, and the daemon's question to the version page of the test"


@posix_only
async def test_the_daemon_as_a_process_inherits_the_switch_says_so_in_its_log_and_opens_no_port_of_its_settings(tmp_path: Path, ptys: Ptys) -> None:
    """`python -m neoaprs` on a data folder whose settings name the radio's port and the GPS receiver's (pseudo-terminals that are there), an iGate and a rigctld on another address: started with nothing but the
    environment of the suite, it runs under the switch. (No Mercury here: a process cannot be given a made-up one, and a clone may hold the real one.)"""
    (radio, radio_port), (gps, gps_port) = ptys(), ptys()
    data = tmp_path / "data"
    data.mkdir()
    store = await store_at(data / "neoaprs.sqlite")
    await store.put_settings({"station/call": "OH2ZZZ", "station/lat": "60.17", "station/lon": "24.94", "tnc/profile": "kenwood-tnc2", "serial/port": radio_port, "gps/source": "serial", "gps/device": gps_port,
                              "igate/enabled": "true", "igate/server": f"{ELSEWHERE}:14580", "igate/password": "12345", "status/source": "rig", "status/rigctld": f"{ELSEWHERE}:4532"})
    assert store.db is not None
    await store.db.close()
    daemon = subprocess.Popen([sys.executable, "-m", "neoaprs", "--data", str(data), "--web-port", "0"], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    log = data / "neoaprs.log"

    def logged() -> str:
        return log.read_text(encoding="utf-8") if log.exists() else ""

    try:
        shut = (f"the serial port {radio_port} is not opened", f"the serial port {gps_port} is not opened", f"no connection to {ELSEWHERE} (APRS-IS)", f"no connection to {ELSEWHERE} (rigctld)")
        await until(lambda: daemon.poll() is not None or ("NeoAPRS is running" in logged() and all(f"NEOAPRS_NO_DEVICES is set: {door}" in logged() for door in shut)), PATIENCE_SEC)
        assert daemon.poll() is None, f"the daemon ended: {logged()}"
        assert "NEOAPRS_NO_DEVICES is set: no serial port, Bluetooth device or sound card is opened" in logged() and f"tnc: {radio_port}: No such file or directory; trying again" in logged()
        assert logged().index("NEOAPRS_NO_DEVICES is set: no serial port") < logged().index("is not opened"), "the line of the start comes before any door"
        written = await asyncio.gather(asyncio.to_thread(heard, radio, 1, 1.5), asyncio.to_thread(heard, gps, 1, 1.5))      # (a TNC line that is opened is asked at once whether the radio is there)
        assert written == [b"", b""], "nothing was written to a port: none was opened"
        if os.path.isdir(f"/proc/{daemon.pid}/fd"):
            held = {os.path.realpath(f"/proc/{daemon.pid}/fd/{name}") for name in os.listdir(f"/proc/{daemon.pid}/fd")}
            assert not held & {os.path.realpath(radio_port), os.path.realpath(gps_port)}, "the daemon holds a port open"
    finally:
        if daemon.poll() is None:
            stop(daemon)
        try:
            await asyncio.to_thread(daemon.communicate, None, PATIENCE_SEC)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.communicate()
            raise AssertionError(f"the daemon did not end: {logged()}") from None
    assert daemon.returncode == 0 and logged().rstrip().endswith("NeoAPRS ended"), logged()[-2000:]


@posix_only
async def test_a_port_that_another_program_holds_is_not_there_either_and_nobody_is_asked_who_holds_it(under_the_switch: None, doors: Doors, tmp_path: Path) -> None:
    """The bench daemon on a copy of the station's data folder while the station itself runs and holds the radio's port: the port is not there, as any other, and the log names no program and no pid."""
    e = Env(tmp_path, radio=False)
    _, device = e.new_pty("radio")
    e.settings["serial/port"] = device
    with held_by_a_program(device):
        await e.start()
        await until(lambda: e.tnc.state is Source.State.WAITING and "trying again" in lines_of(e.tnc))
        assert f"{device}: No such file or directory" in lines_of(e.tnc) and "held by" not in lines_of(e.tnc)
    assert os.path.realpath(device) not in doors.opened and e.tnc.stats.opens == 0
