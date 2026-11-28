"""Bluetooth serial radios on Windows, from what a Windows machine answered: the words for a port that
will not open, the lines of a Bluetooth COM port, and the paired devices offered by name and reached
by a direct RFCOMM socket (neoaprs/openfailure.py, serialport.py, winbluetooth.py, btpaired.py,
serialprobe.py). Windows' libraries are fakes; no real port, socket or library is touched."""

import asyncio
import ctypes
import logging
import socket
import sys
import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
import serial  # type: ignore[import-untyped]

from neoaprs import btpaired, btserial, openfailure, serialport, serialprobe, winbluetooth
from neoaprs.claims import Claims
from neoaprs.cli import doctor
from neoaprs.cli.radiosettings import reached
from neoaprs.coded import code_of
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID
from neoaprs.serialport import SerialError, SerialPort
from neoaprs.serialprobe import PortInfo
from neoaprs.services import radiofinder
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from neoaprs.web.radioview import radio_row
from tests.support.env import until
from tests.support.fakebluetooth import FakeBluetooth

# what Windows listed on the machine of the measurements, for the headphones "GBA"
ADDRESS = "E4:58:BC:C0:B5:3D"
OUTGOING = PortInfo(
    "COM3",
    "Standard Serial over Bluetooth link (COM3)",
    "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_VID&0001009E_PID&4082\\7&2A1B3C4D&0&E458BCC0B53D_C00000000",
    None,
    None,
)
INCOMING = PortInfo(
    "COM4",
    "Standard Serial over Bluetooth link (COM4)",
    "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\7&2A1B3C4D&0&000000000000_00000000",
    None,
    None,
)
USB = PortInfo("COM5", "USB-SERIAL CH340 (COM5)", "USB VID:PID=1A86:7523 SER= LOCATION=1-1", 0x1A86, 0x7523)
# pyserial's words for what Windows answered
DENIED = "could not open port 'COM3': PermissionError(13, 'Access is denied.', None, 5)"
SILENT = "could not open port 'COM3': OSError(22, 'The semaphore timeout period has expired.', None, 121)"
GONE = "could not open port 'COM3': OSError(22, 'The device does not recognize the command.', None, 22)"


def win_error(number: int, text: str) -> OSError:
    """A socket error as Windows raises it, with its own number (POSIX's OSError keeps none)."""
    error = OSError(number, text, None, number)
    if getattr(error, "winerror", None) != number:
        error.winerror = number  # type: ignore[attr-defined]
    return error


def row_of(tnc: Tnc) -> tuple[str, object]:
    spec = RadioSpec(FM_ID, "fm", "kiss", "", True, 1)
    at_work = SimpleNamespace(
        line=tnc,
        beacon=SimpleNamespace(last_sent=None, next_due=None, interval_min=0, problem=""),
        driver=SimpleNamespace(card=None),
        driver_key="tnc",
    )
    row = radio_row(spec, [spec], at_work, Claims())
    return row["state"], row["problem"]


class LinesSer:
    """A pyserial object of a COM port: its open fails with `refusal`, its lines are as set."""

    def __init__(self, refusal: str = "", lines: bool = True) -> None:
        self.refusal, self.cts, self.dsr, self.cd = refusal, lines, lines, lines
        self.closed = False
        self.in_waiting = 0

    def open(self) -> None:
        if self.refusal:
            raise serial.SerialException(self.refusal)

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.01)
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        self.closed = True


def com_port(monkeypatch: pytest.MonkeyPatch, ser: LinesSer, bluetooth: bool = True) -> None:
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    monkeypatch.setattr(serialport, "_bluetooth_com", lambda path: bluetooth)
    monkeypatch.setattr(serialport, "_on_windows", lambda: True)


async def refusal(path: str) -> SerialError:
    with pytest.raises(SerialError) as caught:
        await SerialPort(path).open()
    return caught.value


# ---- the words for a port that will not open


async def test_access_denied_is_another_program_on_any_port_with_windows_number_in_the_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for bluetooth in (True, False):
        com_port(monkeypatch, LinesSer(DENIED), bluetooth)
        why = (await refusal("COM3")).args[0]
        assert code_of(why) == ("radio.port_in_use", {})
        assert (
            why == "COM3: in use by another program (close it: a terminal, Direwolf, a rig program) (Windows error 5)"
        )


async def test_a_semaphore_timeout_on_a_bluetooth_port_is_a_device_that_does_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com_port(monkeypatch, LinesSer(SILENT))
    why = (await refusal("COM3")).args[0]
    assert code_of(why) == ("radio.no_answer", {})
    assert why == "COM3: the device does not answer (switched off, asleep or out of range) (Windows error 121)"


async def test_the_same_number_on_a_usb_port_proves_nothing_and_keeps_windows_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com_port(monkeypatch, LinesSer(SILENT), bluetooth=False)
    why = (await refusal("COM3")).args[0]
    assert code_of(why) == ("other", {})
    assert why == "COM3: The semaphore timeout period has expired (Windows error 121)"


async def test_any_other_number_on_a_bluetooth_port_is_a_port_that_could_not_be_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com_port(monkeypatch, LinesSer(GONE))
    why = (await refusal("COM3")).args[0]
    assert code_of(why) == ("radio.open_failed", {})
    assert why == "COM3: the port could not be opened: The device does not recognize the command (Windows error 22)"


@pytest.mark.parametrize(
    "error,code",
    [
        (win_error(10060, "A connection attempt failed"), "radio.no_answer"),
        (TimeoutError("timed out"), "radio.no_answer"),
        (win_error(10051, "A socket operation was attempted to an unreachable network"), "radio.not_paired"),
        (win_error(10064, "A socket operation failed because the destination host was down"), "radio.refused"),
        (win_error(10013, "An attempt was made to access a socket"), "radio.open_failed"),
    ],
)
def test_a_direct_connection_says_what_each_measured_number_proves(error: OSError, code: str) -> None:
    wrapped = serial.SerialException(f"Could not open port bt://{ADDRESS}: {error}")
    wrapped.__cause__ = error
    why = openfailure.failure(f"bt://{ADDRESS}", wrapped, "words", in_use=False, bluetooth=True)
    assert code_of(why) == (code, {})
    number = getattr(error, "winerror", None)
    assert (f"(Windows error {number})" in why) is (number is not None)


def test_no_number_is_made_up_where_the_system_gave_none() -> None:
    error = OSError(16, "Device or resource busy")
    assert openfailure.windows_error(serial.SerialException("could not open port /dev/ttyUSB0: [Errno 16]")) is None
    assert openfailure.failure("/dev/ttyUSB0", error, "/dev/ttyUSB0: busy", in_use=True, bluetooth=False) == (
        "/dev/ttyUSB0: in use by another program (close it: a terminal, Direwolf, a rig program)"
    )


async def test_a_radio_whose_device_does_not_answer_waits_with_that_problem_and_the_number_stays_in_its_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com_port(monkeypatch, LinesSer(SILENT))
    tnc = Tnc("COM3", profile=KISS, backoff=Backoff([0.05]), check_sec=0)
    try:
        await tnc.start()
        await until(lambda: tnc.state is Source.State.WAITING)
        assert row_of(tnc) == ("waiting", {"code": "radio.no_answer", "params": {}})
        assert "Windows error 121" in tnc.last_error, "the support file keeps Windows' number"
    finally:
        await tnc.stop()


# ---- the lines of a Bluetooth COM port


async def test_a_bluetooth_com_port_with_its_lines_off_is_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    ser = LinesSer(lines=False)
    com_port(monkeypatch, ser)
    why = (await refusal("COM3")).args[0]
    assert code_of(why) == ("radio.no_answer", {}) and ser.closed
    assert "CTS, DSR and CD are off" in why


async def test_a_bluetooth_com_port_with_dsr_and_cd_on_opens_and_a_usb_port_is_never_judged_by_its_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ser = LinesSer()
    ser.cts = False  # the measured device: DSR and CD on are enough
    com_port(monkeypatch, ser)
    port = SerialPort("COM3")
    await port.open()
    assert port.is_open
    port.close()
    com_port(monkeypatch, LinesSer(lines=False), bluetooth=False)
    usb = SerialPort("COM5")
    await usb.open()
    assert usb.is_open
    usb.close()


async def test_lines_that_cannot_be_read_decide_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    class Unreadable(LinesSer):
        @property
        def dsr(self) -> bool:
            raise serial.SerialException("GetCommModemStatus failed")

        @dsr.setter
        def dsr(self, value: bool) -> None:
            pass

    com_port(monkeypatch, Unreadable(lines=False))
    port = SerialPort("COM3")
    await port.open()
    assert port.is_open
    port.close()


async def test_an_open_bluetooth_com_port_whose_lines_go_off_is_lost_and_the_radio_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ser = LinesSer()
    com_port(monkeypatch, ser)
    monkeypatch.setattr(serialport, "LINES_EVERY_SEC", 0.02)
    tnc = Tnc("COM3", profile=KISS, backoff=Backoff([30.0]), check_sec=0)
    try:
        await tnc.start()
        assert row_of(tnc) == ("connected", None)
        ser.cts = ser.dsr = ser.cd = False
        await until(lambda: tnc.state is Source.State.WAITING)
        assert row_of(tnc) == ("waiting", {"code": "radio.no_answer", "params": {}})
    finally:
        await tnc.stop()


def test_a_bluetooth_com_port_is_known_by_its_hardware_id_on_windows_only(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = [SimpleNamespace(device=p.device, hwid=p.hwid) for p in (OUTGOING, INCOMING, USB)]
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: listed)
    monkeypatch.setattr(serialport, "_on_windows", lambda: True)
    assert [serialport._bluetooth_com(name) for name in ("COM3", "com3", "\\\\.\\COM3", "COM4", "COM5")] == [
        True,
        True,
        True,
        False,
        False,
    ]
    assert serialport._bluetooth_com(f"bt://{ADDRESS}") is False
    monkeypatch.setattr(serialport, "_on_windows", lambda: False)
    assert serialport._bluetooth_com("COM3") is False


# ---- Windows' libraries, faked


class FakeBthprops:
    """bthprops.cpl: the devices Windows remembers, (address, name, paired)."""

    HANDLE = 0x5150

    def __init__(self, devices: list[tuple[int, str, bool]]) -> None:
        self.devices, self.closed, self.at = devices, [], 0
        self.params: winbluetooth.SearchParams | None = None

    def BluetoothFindFirstDevice(self, params: Any, info: Any) -> int | None:
        self.params = params._obj
        if not self.devices:
            return None
        self.at = 0
        self._fill(info._obj)
        return self.HANDLE

    def BluetoothFindNextDevice(self, handle: int, info: Any) -> int:
        assert handle == self.HANDLE
        self.at += 1
        if self.at >= len(self.devices):
            return 0
        self._fill(info._obj)
        return 1

    def BluetoothFindDeviceClose(self, handle: int) -> int:
        self.closed.append(handle)
        return 1

    def _fill(self, info: winbluetooth.DeviceInfo) -> None:
        assert info.size == ctypes.sizeof(winbluetooth.DeviceInfo)
        address, name, paired = self.devices[self.at]
        info.address, info.authenticated = address, paired
        units = name.encode("utf-16-le")
        ctypes.memmove(ctypes.addressof(info.name), units, len(units))


class FakeWinsock:
    """ws2_32's lookup of a device's service directory: one answer of channels per call."""

    def __init__(self, answers: list[list[int]], begins: int = 0) -> None:
        self.answers, self.begins, self.ended = answers, begins, []
        self.context = b""
        self._kept: list[Any] = []

    def WSALookupServiceBeginW(self, query: Any, flags: int, handle: Any) -> int:
        asked = query._obj
        assert asked.size == ctypes.sizeof(winbluetooth.QuerySet) and asked.name_space == winbluetooth.NS_BTH
        assert bytes(asked.service_class.contents) == bytes(winbluetooth.SERIAL_PORT)
        self.context = ctypes.string_at(asked.context, 40)
        handle._obj.value = 77
        return self.begins

    def WSALookupServiceNextW(self, handle: Any, flags: int, size: Any, buffer: Any) -> int:
        if not self.answers:
            return -1
        channels = self.answers.pop(0)
        addresses = (winbluetooth.CsAddrInfo * len(channels))()
        for i, channel in enumerate(channels):
            there = winbluetooth.SockaddrBth(family=32, port=channel)
            self._kept.append(there)
            addresses[i].remote.sockaddr = ctypes.addressof(there)
            addresses[i].remote.length = ctypes.sizeof(there)
        self._kept.append(addresses)
        result = winbluetooth.QuerySet(size=ctypes.sizeof(winbluetooth.QuerySet), addresses=len(channels))
        result.address_list = ctypes.cast(addresses, ctypes.POINTER(winbluetooth.CsAddrInfo))
        ctypes.memmove(buffer, ctypes.addressof(result), ctypes.sizeof(result))
        return 0

    def WSALookupServiceEnd(self, handle: Any) -> int:
        self.ended.append(handle.value)
        return 0


ADDRESS_VALUE = 0xE458BCC0B53D


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="the sizes of a 64-bit Windows")
def test_the_structures_have_windows_own_sizes() -> None:
    sizes = {
        winbluetooth.SystemTime: 16,
        winbluetooth.DeviceInfo: 560,
        winbluetooth.SearchParams: 40,
        winbluetooth.Guid: 16,
        winbluetooth.SockaddrBth: 30,
        winbluetooth.SocketAddress: 16,
        winbluetooth.CsAddrInfo: 40,
        winbluetooth.QuerySet: 120,
    }
    assert {kind.__name__: ctypes.sizeof(kind) for kind in sizes} == {k.__name__: v for k, v in sizes.items()}
    assert winbluetooth.DeviceInfo.name.offset == 64 and winbluetooth.SockaddrBth.port.offset == 26


def test_the_paired_devices_come_by_name_and_the_search_is_closed() -> None:
    api = FakeBthprops(
        [(ADDRESS_VALUE, "GBA", True), (0x0011223344AA, "Seen once", False), (0x000CBF18376C, "X1C5Plus", True)]
    )
    assert winbluetooth.paired_devices(api) == [
        winbluetooth.Device(ADDRESS, "GBA"),
        winbluetooth.Device("00:0C:BF:18:37:6C", "X1C5Plus"),
    ]
    assert api.closed == [FakeBthprops.HANDLE]
    assert api.params is not None and not api.params.issue_inquiry, "no device is asked"
    assert api.params.size == ctypes.sizeof(winbluetooth.SearchParams)


def test_no_paired_device_is_an_empty_list_and_a_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, "neoaprs"):
        assert winbluetooth.paired_devices(FakeBthprops([]), lambda: winbluetooth.ERROR_NO_MORE_ITEMS) == []
        assert not caplog.records
        assert winbluetooth.paired_devices(FakeBthprops([]), lambda: 1168) == []
    assert "Windows error 1168" in caplog.text


def test_the_serial_channels_are_asked_of_the_device_by_its_address() -> None:
    ws = FakeWinsock([[1], [2, 1]])
    assert winbluetooth.serial_channels(ADDRESS, ws, lambda: winbluetooth.WSA_E_NO_MORE) == [1, 2]
    assert ws.context.startswith(f"({ADDRESS})\0".encode("utf-16-le")) and ws.ended == [77]


def test_a_directory_that_cannot_be_read_gives_no_channel(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, "neoaprs"):
        assert winbluetooth.serial_channels(ADDRESS, FakeWinsock([], begins=-1), lambda: 10108) == []
        assert winbluetooth.serial_channels(ADDRESS, FakeWinsock([[0, 31]]), lambda: 10110) == []
    assert "Windows error 10108" in caplog.text


# ---- the list of ports on Windows


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBthprops]:
    """A Windows machine with Bluetooth: the headphones and a tracker paired, with their COM ports."""
    api = FakeBthprops([(ADDRESS_VALUE, "GBA", True), (0x000CBF18376C, "X1C5Plus", True)])
    monkeypatch.setattr(socket, "AF_BLUETOOTH", 32, raising=False)
    monkeypatch.setattr(socket, "BTPROTO_RFCOMM", 3, raising=False)
    monkeypatch.setattr(winbluetooth, "_library", lambda name, calls: api)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(serialprobe, "available_ports", lambda: [USB, OUTGOING, INCOMING])
    yield api


def test_a_paired_device_is_offered_by_its_name_and_its_two_com_ports_are_not(windows: FakeBthprops) -> None:
    assert [p.device for p in serialprobe.offered_ports()] == ["COM5"]
    assert [(p.device, p.description) for p in serialprobe.paired_bluetooth_ports()] == [
        (f"bt://{ADDRESS}", "Bluetooth: GBA")
    ], "the tracker has no COM port: no serial port service"


def test_the_devices_windows_paired_come_sorted_by_name(windows: FakeBthprops) -> None:
    windows.devices.insert(0, (0x001122334455, "Alpha", True))
    assert [d.name for d in btpaired.paired_devices()] == ["Alpha", "GBA", "X1C5Plus"]


def test_where_the_direct_route_is_missing_the_com_ports_stay(
    windows: FakeBthprops, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(socket, "BTPROTO_RFCOMM")
    assert [p.device for p in serialprobe.offered_ports()] == ["COM5", "COM3"]
    assert serialprobe.paired_bluetooth_ports() == []


def test_under_the_no_devices_switch_no_device_is_listed(
    windows: FakeBthprops, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("neoaprs.nodevices.on", lambda: True)
    assert serialprobe.paired_bluetooth_ports() == [] and windows.closed == []


def test_find_my_radio_tries_the_device_by_name_after_the_usb_port(windows: FakeBthprops) -> None:
    serialprobe_can_search = serialprobe.can_search()
    assert not serialprobe_can_search
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == ["COM5", f"bt://{ADDRESS}"]


def test_the_device_channels_on_windows_come_from_its_directory(
    windows: FakeBthprops, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = FakeWinsock([[2]])
    monkeypatch.setattr(winbluetooth, "_library", lambda name, calls: ws if name == "ws2_32" else windows)
    monkeypatch.setattr(winbluetooth, "last_error", lambda: winbluetooth.WSA_E_NO_MORE)
    assert btserial.channels_for(ADDRESS) == [2, 1, 3]


# ---- the direct connection


@pytest.fixture
def device(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBluetooth]:
    fake = FakeBluetooth(monkeypatch, address=ADDRESS)
    yield fake
    fake.close()


async def test_a_refused_channel_is_followed_by_the_next_listed_one(
    device: FakeBluetooth, monkeypatch: pytest.MonkeyPatch
) -> None:
    device.listed, device.channel = [1, 2], 2
    monkeypatch.setattr(btserial, "listed_channels", lambda address: [1, 2])
    answer = device.connect_rfcomm

    def busy_on_one(address: tuple[str, int]) -> None:
        if address[1] == 1:
            device.connects.append(address)
            device._pending.pop(0).close()
            raise win_error(10064, "the destination host was down")
        answer(address)

    monkeypatch.setattr(device, "connect_rfcomm", busy_on_one)
    port = SerialPort(f"bt://{ADDRESS}")
    await port.open()
    assert device.connects == [(ADDRESS, 1), (ADDRESS, 2)] and port.is_open
    port.close()


async def test_a_device_that_refuses_every_channel_is_said_to_refuse(
    device: FakeBluetooth, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(btserial, "listed_channels", lambda address: [1, 2])
    device.fail(win_error(10064, "the destination host was down"))
    why = (await refusal(f"bt://{ADDRESS}")).args[0]
    assert code_of(why) == ("radio.refused", {}) and "(Windows error 10064)" in why
    assert [c for _, c in device.connects] == [1, 2, 3]


@pytest.mark.parametrize("number,code", [(10060, "radio.no_answer"), (10051, "radio.not_paired")])
async def test_a_device_off_or_not_paired_is_not_tried_on_every_channel(
    device: FakeBluetooth, monkeypatch: pytest.MonkeyPatch, number: int, code: str
) -> None:
    monkeypatch.setattr(btserial, "listed_channels", lambda address: [1, 2])
    device.fail(win_error(number, "Windows' words"))
    why = (await refusal(f"bt://{ADDRESS}")).args[0]
    assert code_of(why) == (code, {}) and len(device.connects) == 1


async def test_a_slow_connect_never_holds_the_event_loop(
    device: FakeBluetooth, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(btserial, "listed_channels", lambda address: [2])
    release = threading.Event()
    answer = device.connect_rfcomm

    def slow(address: tuple[str, int]) -> None:
        assert release.wait(10), "the test never let the connect go on"
        answer(address)

    monkeypatch.setattr(device, "connect_rfcomm", slow)
    port = SerialPort(f"bt://{ADDRESS}")
    opening = asyncio.create_task(port.open())
    ticks = 0
    while ticks < 20:  # the loop goes on while the device takes its time
        await asyncio.sleep(0.005)
        ticks += 1
    assert not opening.done()
    release.set()
    await opening
    assert port.is_open
    port.close()


# ---- what the doctor and the support summary say


def test_the_doctor_says_the_device_is_offered_by_name_beside_its_com_port(
    windows: FakeBthprops, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "available_ports", lambda: [OUTGOING, INCOMING])
    monkeypatch.setattr(doctor, "held_by", lambda path: "")
    lines = doctor.check_ports().text.splitlines()
    assert lines[1].endswith(
        "(Bluetooth: the port that reaches the device E458BCC0B53D; NeoAPRS offers the device itself,"
        " Bluetooth: GBA, and connects to it directly)"
    )
    assert lines[2].endswith(
        "(the computer's incoming Bluetooth port: it reaches no device, and NeoAPRS does not offer it)"
    )


def test_a_radio_on_a_device_by_name_is_reached_with_no_com_port_and_no_speed() -> None:
    spec = RadioSpec(FM_ID, "fm", "kiss", "", True, 1, settings={"port": f"bt://{ADDRESS}", "baud": "9600"})
    assert reached(spec) == [
        ("Port", f"bt://{ADDRESS} (a Bluetooth device, connected to directly: no COM port, no speed)")
    ]
