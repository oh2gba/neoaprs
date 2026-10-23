"""The serial port (neoaprs/serialport.py, serialprobe.py, serialholders.py) on a fake radio (a TCP server on the loopback, tests/support/fakeradio.py), which runs the same on every system, and with stand-ins for the
pyserial object where a failure has to be made: reading and writing through the threads, the line settings, the open in a thread, a line that dies, the list of ports, the search (`probe`) and the guard that keeps a
test away from the radio's device files. What is about a real device file (the lock, a vanished device, the holders in /proc, the globs) is in tests/test_serialport_pty.py."""
import asyncio
import logging
import os
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
import serial  # type: ignore[import-untyped]
from serial.tools.list_ports_common import ListPortInfo  # type: ignore[import-untyped]

from neoaprs import serialport, serialprobe
from neoaprs.kiss import KissDecoder, encode
from neoaprs.serialholders import held_by, holders, port_key
from neoaprs.serialport import SerialError, SerialPort, is_socket, normalize
from neoaprs.serialprobe import PortInfo, available_ports, can_search, candidate_ports, probe
from tests.conftest import ROOT
from tests.support import guards
from tests.support.env import until
from tests.support.fakeradio import REFUSED, FakeRadio
from tests.support.ptyline import posix_only


@pytest_asyncio.fixture
async def radios() -> AsyncIterator[Callable[[int], Any]]:
    """Makes started fake radios for the test and closes every one of them when it ends."""
    made: list[FakeRadio] = []

    async def make(count: int = 1) -> list[FakeRadio]:
        for _ in range(count):
            radio = FakeRadio()
            await radio.start()
            made.append(radio)
        return made[-count:]

    yield make
    for radio in made:
        await radio.aclose()


Radios = Callable[[int], Any]


async def one(radios: Radios) -> FakeRadio:
    [radio] = await radios(1)
    return radio


async def opened(url: str, baud: int = 9600) -> SerialPort:
    port = SerialPort(url, baud)
    await port.open()
    return port


# ---- reading and writing

async def test_chunks_arrive_through_the_signal(radios: Radios) -> None:
    radio = await one(radios)
    chunks: list[bytes] = []
    port = SerialPort(radio.url, 9600)
    port.data.connect(chunks.append)
    await port.open()
    try:
        assert port.is_open and port.path == radio.url and port.baud == 9600
        await radio.connected()
        radio.feed(b"\xc0\x00hello\xc0")
        await until(lambda: b"".join(chunks) == b"\xc0\x00hello\xc0")
        radio.feed(b"\xdb\xdc")
        await until(lambda: b"".join(chunks).endswith(b"\xdb\xdc"))
        assert all(isinstance(c, bytes) and c for c in chunks)
    finally:
        port.close()


async def test_a_lot_of_bytes_arrive_whole_and_in_order(radios: Radios) -> None:
    radio = await one(radios)
    got = bytearray()
    port = SerialPort(radio.url, 9600)
    port.data.connect(got.extend)
    await port.open()
    try:
        sent = bytes(range(256)) * 64
        radio.feed(sent)
        await until(lambda: len(got) >= len(sent))
        assert bytes(got) == sent
    finally:
        port.close()


async def test_write_reaches_the_other_end_in_order_and_returns_the_count(radios: Radios) -> None:
    radio = await one(radios)
    port = await opened(radio.url)
    try:
        frame = encode(b"hello", port=0)
        assert port.write(frame) == len(frame)
        big = bytes(range(256)) * 12
        assert port.write(big) == len(big)
        assert await radio.said(len(frame) + len(big)) == frame + big
    finally:
        port.close()


async def test_what_is_written_just_before_the_close_still_goes_out(radios: Radios) -> None:
    radio = await one(radios)
    port = await opened(radio.url)
    port.write(b"last words")
    port.close()
    assert await radio.said(10) == b"last words"


async def test_writing_to_a_port_that_is_not_open_is_an_error(radios: Radios) -> None:
    radio = await one(radios)
    port = SerialPort(radio.url)
    with pytest.raises(SerialError, match="not open"):
        port.write(b"x")
    await port.open()
    port.close()
    with pytest.raises(SerialError, match="not open"):
        port.write(b"x")


# ---- nothing of one system in it

@pytest.mark.parametrize("module", ["serialport", "serialprobe", "serialholders", "tnc", "tncsearch"])
def test_the_serial_layer_has_no_descriptor_for_the_loop_and_no_terminal_calls(module: str) -> None:
    """Windows has no fcntl, termios or select on a handle, and its loop cannot wait for a serial handle: the layer reads and writes in threads, whatever the system."""
    text = (ROOT / "neoaprs" / f"{module}.py").read_text(encoding="utf-8")
    for name in ("import fcntl", "import termios", "import select", "add_reader", "remove_reader", "TIOCEXCL", "fileno"):
        assert name not in text, f"{module}.py uses {name}"


# ---- the settings of the line

async def test_the_line_is_8n1_without_flow_control_with_the_control_lines_low_before_the_open(radios: Radios, monkeypatch: pytest.MonkeyPatch) -> None:
    radio = await one(radios)
    seen: list[dict[str, Any]] = []
    real = serial.serial_for_url

    def spy(url: str, *args: Any, **kwargs: Any) -> Any:
        ser = real(url, *args, **kwargs)
        real_open = ser.open

        def open_() -> None:
            seen.append({"dtr": ser.dtr, "rts": ser.rts, "baud": ser.baudrate, "frame": (ser.bytesize, ser.parity, ser.stopbits), "flow": (ser.xonxoff, ser.rtscts, ser.dsrdtr),
                         "timeouts": (ser.timeout, ser.write_timeout), "url": url, "do_not_open": kwargs.get("do_not_open")})
            real_open()

        ser.open = open_
        return ser

    monkeypatch.setattr(serial, "serial_for_url", spy)
    port = await opened(radio.url, 4800)
    port.close()
    [state] = seen
    assert state == {"dtr": False, "rts": False, "baud": 4800, "frame": (8, "N", 1), "flow": (False, False, False), "timeouts": (0.1, 2.0), "url": radio.url, "do_not_open": True}


def test_a_device_is_opened_exclusively_on_posix_and_a_url_and_windows_are_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name == "posix":
        assert serialport._build("/dev/ttyUSB9", 9600).exclusive is True
    assert serialport._build("socket://127.0.0.1:1", 9600).exclusive is None
    monkeypatch.setattr(serialport, "os", SimpleNamespace(name="nt"))
    assert serialport._build("/dev/ttyUSB9", 9600).exclusive is None, "(Windows ports are always exclusive; pyserial refuses to be told otherwise)"
    ser = serialport._build("/dev/ttyUSB9", 9600)
    assert (ser.dtr, ser.rts, ser.is_open) == (False, False, False)


def test_tcp_is_another_name_for_socket_and_only_a_socket_is_a_socket() -> None:
    assert normalize("tcp://127.0.0.1:8001") == "socket://127.0.0.1:8001" == normalize(" TCP://127.0.0.1:8001 ")
    assert normalize("socket://localhost:8100") == "socket://localhost:8100" and normalize("COM3") == "COM3" and normalize("/dev/ttyUSB0") == "/dev/ttyUSB0"
    assert [is_socket(p) for p in ("socket://h:1", "tcp://h:1", "TCP://h:1", "COM3", "/dev/ttyUSB0", "rfc2217://h:1", "loop://")] == [True, True, True, False, False, False, False]


async def test_a_tcp_url_opens_like_a_socket_url(radios: Radios) -> None:
    radio = await one(radios)
    port = SerialPort(radio.url.replace("socket://", "tcp://"))
    await port.open()
    try:
        await radio.connected()
        assert port.is_socket
        port.write(b"x")
        assert await radio.said(1) == b"x"
    finally:
        port.close()


# ---- opening and closing

async def test_a_connection_that_is_refused_raises_serial_error_with_the_systems_words(radios: Radios) -> None:
    radio = await one(radios)
    radio.refuse()
    port = SerialPort(radio.url)
    with pytest.raises(SerialError) as caught:
        await port.open()
    assert str(caught.value) == f"{radio.url}: {REFUSED}" and not port.is_open


async def test_a_port_that_cannot_be_opened_raises_serial_error_with_the_systems_words(tmp_path: Path) -> None:
    port = SerialPort(str(tmp_path / "nothing-here"))
    with pytest.raises(SerialError, match="nothing-here: ."):
        await port.open()
    assert not port.is_open


async def test_a_url_pyserial_does_not_know_is_a_serial_error() -> None:
    with pytest.raises(SerialError, match="protocol 'nonsense' not known"):
        await SerialPort("nonsense://x").open()


async def test_a_port_is_open_once(radios: Radios) -> None:
    radio = await one(radios)
    port = await opened(radio.url)
    try:
        with pytest.raises(SerialError, match="already open"):
            await port.open()
    finally:
        port.close()


async def test_closing_ends_the_threads_and_the_connection_and_the_port_can_be_closed_again(radios: Radios) -> None:
    radio = await one(radios)
    chunks: list[bytes] = []
    port = SerialPort(radio.url)
    port.data.connect(chunks.append)
    await port.open()
    await radio.connected()
    before = {t.name for t in threading.enumerate() if t.name.startswith("serial-")}
    assert len(before) >= 2
    port.close()
    assert not port.is_open
    port.close()
    await until(lambda: radio.clients == 0)
    assert not {t for t in threading.enumerate() if t.name.startswith("serial-read") and radio.url in t.name and t.is_alive()}
    await asyncio.sleep(0.1)
    assert chunks == []


async def test_a_closed_port_can_be_opened_again(radios: Radios) -> None:
    radio = await one(radios)
    chunks: list[bytes] = []
    port = SerialPort(radio.url)
    port.data.connect(chunks.append)
    await port.open()
    port.close()
    await port.open()
    try:
        await until(lambda: radio.clients == 1)
        radio.feed(b"again")
        await until(lambda: b"".join(chunks) == b"again")
    finally:
        port.close()


class SlowSer:
    """A pyserial object whose open takes a while, to look at what the loop does meanwhile."""

    def __init__(self, seconds: float, fail: bool = False) -> None:
        self.seconds, self.fail = seconds, fail
        self.closed = threading.Event()
        self.in_waiting = 0

    def open(self) -> None:
        time.sleep(self.seconds)
        if self.fail:
            raise serial.SerialException("could not open port 'COM9': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)")

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.01)
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        self.closed.set()


async def test_the_open_is_made_in_a_thread_so_the_loop_goes_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serialport, "_build", lambda path, baud: SlowSer(0.4))
    port = SerialPort("COM9")
    ticks = 0
    task = asyncio.get_running_loop().create_task(port.open())
    while not task.done():
        await asyncio.sleep(0.01)
        ticks += 1
    await task
    port.close()
    assert ticks >= 20, "the loop ran during the open"


async def test_an_open_that_is_cancelled_leaves_no_port_open(monkeypatch: pytest.MonkeyPatch) -> None:
    ser = SlowSer(0.3)
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    port = SerialPort("COM9")
    task = asyncio.get_running_loop().create_task(port.open())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not port.is_open
    assert await asyncio.to_thread(ser.closed.wait, 2.0), "the thread closed what it opened when it found nobody waiting"


def test_windows_words_for_a_port_that_is_not_there_and_one_that_another_program_has(monkeypatch: pytest.MonkeyPatch) -> None:
    gone = serial.SerialException("could not open port 'COM9': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)")
    assert serialport._words("COM9", gone) == "COM9: The system cannot find the file specified"
    taken = serial.SerialException("could not open port 'COM3': PermissionError(13, 'Access is denied.', None, 5)")
    assert serialport._words("COM3", taken) == "COM3: Access is denied"
    monkeypatch.setattr(serialport, "_on_windows", lambda: True)
    assert serialport._in_use(taken) and serialport._in_use(PermissionError(13, "Permission denied")) and not serialport._in_use(gone)
    monkeypatch.setattr(serialport, "_on_windows", lambda: False)
    assert not serialport._in_use(taken) and not serialport._in_use(PermissionError(13, "Permission denied")), "(on Linux a permission error is the user's group, not another program)"
    assert serialport._in_use(serial.SerialException(11, "Could not exclusively lock port /dev/ttyUSB0"))


async def test_a_com_port_refused_with_access_denied_is_in_use_by_another_program(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(path: str, baud: int) -> Any:
        raise serial.SerialException("could not open port 'COM3': PermissionError(13, 'Access is denied.', None, 5)")

    monkeypatch.setattr(serialport, "_on_windows", lambda: True)
    monkeypatch.setattr(serialport, "_build", refuse)
    with pytest.raises(SerialError) as caught:
        await SerialPort("COM3").open()
    assert str(caught.value).startswith("COM3: in use by another program") and not isinstance(caught.value.__cause__, type(None))


# ---- a line that dies

async def test_a_connection_that_closes_emits_dropped_once_and_closes_the_port(radios: Radios) -> None:
    radio = await one(radios)
    reasons: list[str] = []
    port = SerialPort(radio.url)
    port.dropped.connect(reasons.append)
    await port.open()
    await radio.connected()
    radio.drop()
    await until(lambda: reasons)
    await asyncio.sleep(0.1)
    assert len(reasons) == 1 and "disconnected" in reasons[0]
    assert not port.is_open
    with pytest.raises(SerialError):
        port.write(b"x")


class FailingSer(SlowSer):
    def __init__(self, fail_read: bool = False, fail_write: bool = False) -> None:
        super().__init__(0.0)
        self.fail_read, self.fail_write = fail_read, fail_write

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.01)
        if self.fail_read:
            raise serial.SerialException("device reports readiness to read but returned no data")
        return b""

    def write(self, data: bytes) -> int:
        raise serial.SerialTimeoutException("Write timeout")


@pytest.mark.parametrize("which", ["read", "write"])
async def test_a_read_or_a_write_that_fails_reports_the_line_lost_once(which: str, monkeypatch: pytest.MonkeyPatch) -> None:
    ser = FailingSer(fail_read=which == "read")
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    reasons: list[str] = []
    port = SerialPort("COM9")
    port.dropped.connect(reasons.append)
    await port.open()
    if which == "write":
        port.write(b"x")
        port.write(b"y")
    await until(lambda: reasons)
    await asyncio.sleep(0.1)
    assert len(reasons) == 1 and not port.is_open and ser.closed.is_set()
    assert ("write failed" in reasons[0]) == (which == "write")


class StuckSer(SlowSer):
    """A line whose write does not come back until it is cancelled."""

    def __init__(self) -> None:
        super().__init__(0.0)
        self.release = threading.Event()
        self.cancelled = False

    def write(self, data: bytes) -> int:
        self.release.wait(10)
        raise serial.SerialException("write aborted")

    def cancel_write(self) -> None:
        self.cancelled = True
        self.release.set()


async def test_a_line_that_takes_no_more_writes_refuses_them_and_a_stuck_write_is_cut_short_by_the_close(monkeypatch: pytest.MonkeyPatch) -> None:
    ser = StuckSer()
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    lost: list[str] = []
    port = SerialPort("COM9")
    port.dropped.connect(lost.append)
    await port.open()
    with pytest.raises(SerialError, match="does not take"):
        for _ in range(serialport.MAX_QUEUED_WRITES + 5):
            port.write(b"x")
    began = time.monotonic()
    port.close()
    assert time.monotonic() - began < 2.0 and ser.cancelled and ser.closed.is_set()
    await asyncio.sleep(0.1)
    assert lost == [], "a write cut short by our own close is not a lost line"


# ---- the list of ports

def listed(device: str, description: str = "n/a", hwid: str = "n/a", vid: int | None = None, pid: int | None = None) -> ListPortInfo:
    info = ListPortInfo(device)
    info.description, info.hwid, info.vid, info.pid = description, hwid, vid, pid
    return info


def test_available_ports_lists_what_the_system_knows_in_natural_order(monkeypatch: pytest.MonkeyPatch) -> None:
    ports = [listed("COM10", "USB Serial Port (COM10)", "USB VID:PID=0403:6001 SER=A1", 0x0403, 0x6001), listed("COM2", "Communications Port (COM2)"), listed("COM3", "Standard Serial over Bluetooth link (COM3)", "BTHENUM\\{00001101}")]
    monkeypatch.setattr(serialprobe.serial.tools.list_ports, "comports", lambda: ports)
    assert available_ports() == [
        PortInfo("COM2", "Communications Port (COM2)", "n/a", None, None),
        PortInfo("COM3", "Standard Serial over Bluetooth link (COM3)", "BTHENUM\\{00001101}", None, None),
        PortInfo("COM10", "USB Serial Port (COM10)", "USB VID:PID=0403:6001 SER=A1", 0x0403, 0x6001),
    ]


def test_a_listing_that_fails_is_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> list[ListPortInfo]:
        raise OSError("sysfs is not there")

    monkeypatch.setattr(serialprobe.serial.tools.list_ports, "comports", fail)
    assert available_ports() == []


def test_the_list_never_opens_a_port(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_: list[object] = []
    monkeypatch.setattr(serial.Serial, "open", lambda self: opened_.append(self))
    available_ports()
    assert opened_ == []


def test_the_search_is_made_on_linux_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for platform, expected in (("linux", True), ("win32", False), ("darwin", False)):
        monkeypatch.setattr(serialprobe, "sys", SimpleNamespace(platform=platform))
        assert can_search() is expected


def test_candidate_ports_defaults_to_the_usb_serial_names() -> None:
    import inspect
    assert inspect.signature(candidate_ports).parameters["pattern"].default == "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*"


def test_candidate_ports_is_the_sorted_glob(tmp_path: Path) -> None:
    for name in ("brainbox_3", "brainbox_1", "brainbox_2", "other_1"):
        (tmp_path / name).touch()
    assert candidate_ports(str(tmp_path / "brainbox_*")) == [str(tmp_path / f"brainbox_{n}") for n in (1, 2, 3)]
    assert candidate_ports(str(tmp_path / "nothing_*")) == []
    assert candidate_ports("") == []


def test_the_name_of_a_port_is_compared_by_what_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    assert port_key("socket://127.0.0.1:8001") == port_key("SOCKET://127.0.0.1:8001 ")
    monkeypatch.setattr("neoaprs.serialholders._on_windows", lambda: True)
    assert port_key("com3") == port_key("COM3") == port_key("\\\\.\\COM3") == "COM3"


def test_a_socket_has_no_holders_and_without_linux_nobody_is_known_to_hold_a_port(monkeypatch: pytest.MonkeyPatch) -> None:
    assert holders("socket://127.0.0.1:8001") == [] and held_by("tcp://127.0.0.1:8001") == ""
    monkeypatch.setattr("neoaprs.serialholders._on_linux", lambda: False)
    assert holders(sys.executable) == [] and held_by("COM3") == ""


# ---- probing

def is_kiss(data: bytes) -> bool:
    return bool(KissDecoder().feed(data))


async def keep_feeding(radio: FakeRadio, data: bytes) -> None:
    """The radio talking on a line: a port that opens late still hears it."""
    while True:
        if radio.clients:
            radio.feed(data)
        await asyncio.sleep(0.02)


async def stop_feeding(*feeders: "asyncio.Task[None]") -> None:
    for feeder in feeders:
        feeder.cancel()
    await asyncio.gather(*feeders, return_exceptions=True)


async def test_probe_picks_the_port_that_sends_valid_bytes(radios: Radios) -> None:
    silent, talking = await radios(2)
    feeder = asyncio.get_running_loop().create_task(keep_feeding(talking, encode(b"a frame")))
    try:
        assert await probe([silent.url, talking.url], 9600, 2.0, is_kiss) == talking.url
    finally:
        await stop_feeding(feeder)


async def test_probe_does_not_take_a_port_that_sends_noise(radios: Radios) -> None:
    noisy = await one(radios)
    feeder = asyncio.get_running_loop().create_task(keep_feeding(noisy, b"just noise, no frame"))
    try:
        assert await probe([noisy.url], 9600, 0.15, is_kiss) is None
    finally:
        await stop_feeding(feeder)


async def test_probe_returns_none_when_nothing_is_valid_and_closes_every_port_it_opened(radios: Radios) -> None:
    pair = await radios(2)
    assert await probe([r.url for r in pair], 9600, 0.05, lambda data: False) is None
    await until(lambda: all(r.clients == 0 for r in pair))


async def test_probe_closes_the_port_it_chose_too(radios: Radios) -> None:
    radio = await one(radios)
    feeder = asyncio.get_running_loop().create_task(keep_feeding(radio, b"x"))
    try:
        assert await probe([radio.url], 9600, 2.0, lambda data: bool(data)) == radio.url
    finally:
        await stop_feeding(feeder)
    await until(lambda: radio.clients == 0)


async def test_probe_skips_a_path_that_cannot_be_opened_and_says_so_at_info(radios: Radios, caplog: pytest.LogCaptureFixture) -> None:
    gone, talking = await radios(2)
    gone.refuse()
    feeder = asyncio.get_running_loop().create_task(keep_feeding(talking, b"x"))
    try:
        with caplog.at_level(logging.INFO, logger="neoaprs.serialport"):
            assert await probe([gone.url, talking.url], 9600, 2.0, lambda data: bool(data)) == talking.url
    finally:
        await stop_feeding(feeder)
    assert [r.levelno for r in caplog.records if gone.url in r.getMessage()] == [logging.INFO]


async def test_probe_gives_up_on_a_port_that_dies_while_listening_and_goes_on(radios: Radios) -> None:
    dying, talking = await radios(2)
    feeder = asyncio.get_running_loop().create_task(keep_feeding(talking, b"x"))
    asyncio.get_running_loop().call_later(0.05, dying.drop)
    try:
        assert await probe([dying.url, talking.url], 9600, 5.0, lambda data: bool(data)) == talking.url
    finally:
        await stop_feeding(feeder)


async def test_probe_with_no_paths_finds_nothing() -> None:
    assert await probe([], 9600, 0.01, lambda data: True) is None


async def test_probe_listens_to_every_port_at_once_and_finds_the_one_that_talks_late(radios: Radios) -> None:
    three = await radios(3)
    loop = asyncio.get_running_loop()

    async def late() -> None:
        await asyncio.sleep(0.3)
        await three[2].connected()
        three[2].feed(encode(b"a frame"))

    talker = loop.create_task(late())
    began = loop.time()
    try:
        assert await probe([r.url for r in three], 9600, 5.0, is_kiss) == three[2].url
    finally:
        await stop_feeding(talker)
    assert 0.25 < loop.time() - began < 0.9, "the third port was heard as soon as it talked, not after a turn on each of the others"


async def test_probe_without_a_limit_waits_for_a_port_to_talk(radios: Radios) -> None:
    radio = await one(radios)
    loop = asyncio.get_running_loop()
    for limit in (None, 0):
        feeder = loop.create_task(keep_feeding(radio, b"x"))
        try:
            assert await asyncio.wait_for(probe([radio.url], 9600, limit, lambda data: bool(data)), 3.0) == radio.url
        finally:
            await stop_feeding(feeder)
        await until(lambda: radio.clients == 0)


async def test_probe_tells_which_ports_it_opened(radios: Radios) -> None:
    radio, gone = await radios(2)
    gone.refuse()
    told: list[list[str]] = []
    assert await probe([gone.url, radio.url], 9600, 0.05, lambda data: False, on_open=told.append) is None
    assert told == [[radio.url]]


async def test_probe_sends_the_nudge_to_every_port_once_after_the_wait(radios: Radios) -> None:
    three = await radios(3)
    task = asyncio.get_running_loop().create_task(probe([r.url for r in three], 9600, 0.5, lambda data: False, nudge=b"\r", nudge_after_sec=0.2))
    await asyncio.sleep(0.1)
    for radio in three:
        assert await radio.said(1, 0.0) == b"", "nothing is sent before the wait is over"
    assert await task is None
    for radio in three:
        assert await radio.said(1, 1.0) == b"\r"
        assert await radio.said(1, 0.05) == b"", "once"


async def test_a_nudge_is_not_needed_when_a_port_has_already_talked(radios: Radios) -> None:
    radio = await one(radios)
    talker = asyncio.get_running_loop().create_task(keep_feeding(radio, b"x"))          # (a line that talks: what is waiting at the moment a port is opened is thrown away, so one byte at the connect can be lost)
    try:
        assert await probe([radio.url], 9600, 20.0, lambda data: bool(data), nudge=b"\r", nudge_after_sec=10.0) == radio.url          # (it ends at the first byte: the long times are for a runner that is slow to open the port)
    finally:
        await stop_feeding(talker)
    assert await radio.said(1, 0.3) == b""


async def test_a_port_whose_nudge_fails_is_dropped_and_the_search_goes_on(radios: Radios, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    bad, good = await radios(2)
    real_write = SerialPort.write

    def write(self: SerialPort, data: bytes) -> int:
        if self.path == bad.url:
            raise SerialError(f"{bad.url}: write timed out")
        return real_write(self, data)

    monkeypatch.setattr(SerialPort, "write", write)
    loop = asyncio.get_running_loop()
    loop.call_later(0.3, bad.feed, b"ok")                                       # a dropped port is not listened to any more
    loop.call_later(0.4, good.feed, b"ok")
    with caplog.at_level(logging.INFO, logger="neoaprs.serialport"):
        assert await probe([bad.url, good.url], 9600, 2.0, lambda data: data == b"ok", nudge=b"\r", nudge_after_sec=0.1) == good.url
    assert any("dropping" in r.getMessage() and bad.url in r.getMessage() for r in caplog.records)
    assert await good.said(1, 1.0) == b"\r"


async def test_probe_returns_none_at_once_when_every_port_is_gone(radios: Radios) -> None:
    pair = await radios(2)
    loop = asyncio.get_running_loop()
    for radio in pair:
        loop.call_later(0.1, radio.drop)
    began = loop.time()
    assert await asyncio.wait_for(probe([r.url for r in pair], 9600, None, lambda data: True), 2.0) is None
    assert loop.time() - began < 0.9


async def test_cancelling_the_probe_closes_every_port(radios: Radios) -> None:
    three = await radios(3)
    task = asyncio.get_running_loop().create_task(probe([r.url for r in three], 9600, None, lambda data: False, nudge=b"\r"))
    await until(lambda: all(r.clients == 1 for r in three))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until(lambda: all(r.clients == 0 for r in three))


async def test_cancelling_the_probe_during_the_opens_leaves_no_port_open(radios: Radios, monkeypatch: pytest.MonkeyPatch) -> None:
    pair = await radios(2)
    real_build = serialport._build

    def slow(path: str, baud: int) -> Any:
        ser = real_build(path, baud)
        real_open = ser.open

        def open_() -> None:
            time.sleep(0.3)
            real_open()

        ser.open = open_
        return ser

    monkeypatch.setattr(serialport, "_build", slow)
    task = asyncio.get_running_loop().create_task(probe([r.url for r in pair], 9600, None, lambda data: False))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.8)
    assert all(r.clients == 0 for r in pair)


@pytest.mark.parametrize("listed_as, skipped", [("socket://{}", "SOCKET://{}"), ("tcp://{}", "socket://{}"), ("socket://{}", "tcp://{}")])
async def test_probe_never_touches_a_path_in_skip_however_it_is_written(listed_as: str, skipped: str, radios: Radios, caplog: pytest.LogCaptureFixture) -> None:
    excluded, radio = await radios(2)
    host = excluded.url.removeprefix("socket://")
    feeder = asyncio.get_running_loop().create_task(keep_feeding(radio, b"x"))
    told: list[list[str]] = []
    try:
        with caplog.at_level(logging.INFO, logger="neoaprs.serialport"):
            found = await probe([listed_as.format(host), radio.url], 9600, 2.0, lambda data: bool(data), nudge=b"\r", nudge_after_sec=0.05, on_open=told.append, skip=[skipped.format(host)])
    finally:
        await stop_feeding(feeder)
    assert found == radio.url and told == [[radio.url]] and excluded.connections == 0, "nothing was opened on a port on the skip list"
    assert [r.levelno for r in caplog.records if "on the skip list" in r.getMessage()] == [logging.INFO]


async def test_probe_with_every_path_skipped_finds_nothing_at_once(radios: Radios) -> None:
    radio = await one(radios)
    assert await asyncio.wait_for(probe([radio.url], 9600, None, lambda data: True, skip=[radio.url]), 1.0) is None
    assert radio.connections == 0


# ---- the guard: a test never touches the operator's radio

@posix_only      # (the radio's device files are /dev paths)
def test_the_guard_refuses_and_remembers_the_radios_device_files_even_when_the_error_is_swallowed() -> None:
    radio = guards.SerialGuard()
    with pytest.MonkeyPatch.context() as mp:
        radio.install(mp.setattr)
        for path in ("/dev/brainbox_1", "/dev/brainbox_4", "/dev/ttyS0", "/dev/ttyUSB3", "/dev/tty", b"/dev/ttyACM0"):
            with pytest.raises(guards.RadioTouched):
                os.open(path, os.O_RDWR)
        with pytest.raises(serial.SerialException):              # pyserial words the refusal as its own error; the guard has remembered it all the same
            serial.Serial("/dev/brainbox_2")
    assert radio.refused == ["/dev/brainbox_1", "/dev/brainbox_4", "/dev/ttyS0", "/dev/ttyUSB3", "/dev/tty", "/dev/ttyACM0", "/dev/brainbox_2"]


@posix_only
def test_the_guard_looks_through_a_link_to_the_device(tmp_path: Path) -> None:
    link = tmp_path / "radio"
    link.symlink_to("/dev/ttyS0")
    radio = guards.SerialGuard()
    with pytest.raises(guards.RadioTouched):
        radio.check(str(link))
    assert radio.refused == [str(link)]


def test_the_guard_lets_ordinary_files_and_a_socket_port_through(tmp_path: Path) -> None:
    radio = guards.SerialGuard()
    for path in (tmp_path / "file", Path("/dev/null"), Path("/dev/pts/ptmx"), "socket://127.0.0.1:8001", "COM3"):
        radio.check(path)
    radio.check(3)
    assert radio.refused == []


CHILD_TESTS = '''
import os
import serial

def test_clean(tmp_path):
    fd = os.open(tmp_path / "f", os.O_CREAT | os.O_WRONLY)
    os.close(fd)

def test_opens_the_radio_and_swallows_the_error():
    try:
        os.open("/dev/brainbox_1", os.O_RDWR)
    except OSError:
        pass

def test_opens_a_tty_through_pyserial_and_swallows_the_error():
    try:
        serial.Serial("/dev/ttyUSB0")
    except Exception:
        pass
'''


@posix_only
def test_the_guard_is_wired_in_and_fails_a_test_that_touches_the_radio(tmp_path: Path) -> None:
    work = tmp_path / "child"
    work.mkdir()
    (work / "conftest.py").write_text("from tests.support.guards import isolated_machine  # noqa: F401\n")
    (work / "test_inner.py").write_text(textwrap.dedent(CHILD_TESTS))
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "--color=no", "-q", str(work)], cwd=work, env=env, capture_output=True, text=True, timeout=120)
    outcome = {line.split("::")[1].split(" ")[0]: line.split(" ")[0] for line in proc.stdout.splitlines() if line.startswith(("PASSED", "ERROR", "FAILED"))}
    assert outcome == {
        "test_clean": "PASSED",
        "test_opens_the_radio_and_swallows_the_error": "ERROR",
        "test_opens_a_tty_through_pyserial_and_swallows_the_error": "ERROR",
    }, proc.stdout + proc.stderr
