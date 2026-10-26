"""Find my radio on Windows and macOS (neoaprs/serialprobe.py, neoaprs/services/radiofinder.py): the ports are the ones the system lists (COM ports, the paired Bluetooth serial ports among them, or /dev/cu.*), USB adapters
first, tried one after the other like on Linux, and a port that another program has is passed over. The system's list and the serial open are fakes: no port of the machine is listed or opened, and the platform is said."""
import logging
import sys
import threading
import time
from typing import Any

import pytest
from serial.tools.list_ports_common import ListPortInfo  # type: ignore[import-untyped]

from neoaprs import ax25, kiss, serialport, serialprobe
from neoaprs.radiosearch import Found, Trying
from neoaprs.serialprobe import PortInfo
from neoaprs.services import radiofinder
from neoaprs.services.radiofinder import SPEEDS, RadioFinder, speeds_for
from neoaprs.services.radioprobe import Timing
from tests.support.faketnc import TncBrain, ears

QUICK = Timing(listen_sec=0.3, answer_sec=0.3, pace=0.001)
ESP32 = (0x303A, 0x1001)


def listed(device: str, description: str, hwid: str, vid: int | None = None, pid: int | None = None) -> ListPortInfo:
    info = ListPortInfo(device)
    info.description, info.hwid, info.vid, info.pid = description, hwid, vid, pid
    return info


WINDOWS = [
    listed("COM1", "Communications Port (COM1)", "ACPI\\PNP0501\\0"),
    listed("COM3", "Prolific USB-to-Serial Comm Port (COM3)", "USB VID:PID=067B:2303 SER=5", 0x067B, 0x2303),
    listed("COM4", "Silicon Labs CP210x USB to UART Bridge (COM4)", "USB VID:PID=10C4:EA60 SER=0001", 0x10C4, 0xEA60),
    listed("COM5", "USB Serial Port (COM5)", "USB VID:PID=0403:6001 SER=A1", 0x0403, 0x6001),
    listed("COM7", "Mobilinkd TNC3 (COM7)", "USB VID:PID=0483:5740 SER=2", 0x0483, 0x5740),
    listed("COM8", "USB Serial Device (COM8)", "USB VID:PID=303A:1001 SER=3", *ESP32),
    listed("COM9", "Standard Serial over Bluetooth link (COM9)", "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\7&1&0&0"),
    listed("COM10", "USB Serial Port (COM10)", "USB VID:PID=0403:6015 SER=B2", 0x0403, 0x6015),
]


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The platform is Windows and the system lists the ports above."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(serialprobe.serial.tools.list_ports, "comports", lambda: list(WINDOWS))


# ---- which ports are listed

def test_find_my_radio_is_made_on_linux_windows_and_macos_and_the_search_that_runs_by_itself_on_linux_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for platform, find, search in (("linux", True, True), ("win32", True, False), ("darwin", True, False), ("freebsd14", False, False)):
        monkeypatch.setattr(sys, "platform", platform)
        assert (serialprobe.can_find(), serialprobe.can_search()) == (find, search)


def test_the_ports_of_windows_are_the_com_ports_with_the_usb_adapters_first_the_boards_left_out_and_the_bluetooth_ones_last(windows: None) -> None:
    ports = serialprobe.system_ports()
    assert [p.device for p in ports] == ["COM3", "COM4", "COM5", "COM7", "COM10", "COM1", "COM9"]          # (natural order inside each group; COM8 is an ESP32 board)
    assert ports[0] == PortInfo("COM3", "Prolific USB-to-Serial Comm Port (COM3)", "USB VID:PID=067B:2303 SER=5", 0x067B, 0x2303)
    assert [serialprobe.is_bluetooth_com(p) for p in ports] == [False] * 6 + [True]


def test_a_paired_bluetooth_serial_port_is_a_com_port_with_no_speed(windows: None) -> None:
    assert serialprobe.bluetooth_com_keys() == {"COM9"}
    assert speeds_for("COM9", {"COM9"}) == (9600,) and speeds_for("COM5", {"COM9"}) == SPEEDS


def test_the_candidates_on_windows_are_the_listed_ports_without_the_skipped_ones(windows: None) -> None:
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ("com4",)) == ["COM3", "COM5", "COM7", "COM10", "COM1", "COM9"]


def test_a_pattern_of_globs_does_not_stand_for_the_ports_of_windows(windows: None) -> None:
    assert radiofinder.candidates("/dev/neoaprs-test-*", ()) == []


def test_a_system_that_lists_nothing_has_no_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(serialprobe.serial.tools.list_ports, "comports", lambda: [])
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == []


def test_the_ports_of_macos_are_the_cu_devices_without_the_ones_that_are_no_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(serialprobe.serial.tools.list_ports, "comports", lambda: [listed("/dev/cu.usbserial-A1", "FT232R USB UART", "USB VID:PID=0403:6001", 0x0403, 0x6001)])
    monkeypatch.setattr(serialprobe.glob, "glob", lambda pattern: ["/dev/cu.Bluetooth-Incoming-Port", "/dev/cu.TNC-SPP", "/dev/cu.debug-console", "/dev/cu.usbserial-A1"] if pattern == "/dev/cu.*" else [])
    assert [p.device for p in serialprobe.system_ports()] == ["/dev/cu.usbserial-A1", "/dev/cu.TNC-SPP"]
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == ["/dev/cu.usbserial-A1", "/dev/cu.TNC-SPP"]


def test_where_find_my_radio_is_not_made_there_is_no_port_to_try(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd14")
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == []


# ---- the search itself

class Rig:
    def __init__(self, ports: list[str], **finder: Any) -> None:
        self.tried: list[Trying] = []

        async def listed_() -> list[str]:
            return ports

        async def hold() -> None:
            pass

        self.finder = RadioFinder(listed_, hold, lambda: None, QUICK, **finder)


async def test_a_bluetooth_com_port_is_tried_once_and_found_without_a_speed(windows: None) -> None:
    ear = ears({("COM9", 9600): TncBrain("kiss")})
    rig = Rig(["COM5", "COM9"], line=ear)
    found = await rig.finder.find(rig.tried.append)
    assert found == Found("COM9", None, "kiss")
    assert [(t.port, t.baud) for t in rig.tried][-1] == ("COM9", None)
    assert [(t.port, t.baud) for t in rig.tried if t.port == "COM5"] == [("COM5", s) for s in SPEEDS]
    assert rig.tried[-1].total == len(SPEEDS) + 1


async def test_the_com_ports_are_tried_in_order_each_at_the_usual_speeds_and_the_first_tnc_that_answers_is_found(windows: None) -> None:
    brains = {("COM5", 57600): TncBrain("tnc2")}
    ear = ears(brains)
    rig = Rig(serialprobe_devices(), line=ear)
    found = await rig.finder.find(rig.tried.append)
    assert found == Found("COM5", 57600, "kenwood-tnc2")
    assert list(dict.fromkeys(port for port, _ in ear.opened)) == ["COM3", "COM4", "COM5"]            # one at a time: COM7 and the rest are not touched once COM5 answers
    assert ear.closed == ear.opened


def serialprobe_devices() -> list[str]:
    return radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ())


class FakeSerial:
    """What `serial.serial_for_url` gives instead of a real port: `in_use` ports cannot be opened (Windows: Access is denied), the others say what `said` is once, after they are opened. Nothing of the machine is opened."""

    opens: list[str] = []
    in_use: set[str] = set()
    said: dict[str, bytes] = {}

    def __init__(self, url: str) -> None:
        self.url = url
        self.dtr = self.rts = False
        self._said = b""
        self._stop = threading.Event()

    def open(self) -> None:
        self.opens.append(self.url)
        if self.url in self.in_use:
            raise PermissionError(13, "Access is denied.", None, 5)
        self._said = self.said.get(self.url, b"")

    @property
    def in_waiting(self) -> int:
        return len(self._said)

    def read(self, count: int = 1) -> bytes:
        chunk, self._said = self._said[:count], self._said[count:]
        if not chunk:
            self._stop.wait(0.02)
        return chunk

    def write(self, data: bytes) -> int:
        return len(data)

    def cancel_read(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self._stop.set()


async def test_a_port_that_another_program_has_is_passed_over_with_the_words_of_the_open_and_the_next_one_is_found(windows: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    packet = ax25.encode(ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("Q1ABC"), (ax25.Address.parse("WIDE1-1"),), info=b"!6010.00N/02456.00E-"))
    fake = type("Fake", (FakeSerial,), {"opens": [], "in_use": {"COM3"}, "said": {"COM4": kiss.encode(packet)}})
    monkeypatch.setattr(serialport.serial, "serial_for_url", lambda url, **settings: fake(url))
    monkeypatch.setattr(serialport.os, "name", "nt")
    caplog.set_level(logging.INFO, logger="neoaprs.tnc")
    rig = Rig(["COM3", "COM4", "COM5"])
    started = time.monotonic()
    found = await rig.finder.find(rig.tried.append)
    assert found == Found("COM4", 9600, "kiss")
    assert fake.opens == ["COM3", "COM4"]                                                         # (COM3 is refused once, not at each of its seven speeds)
    assert "COM3: in use by another program" in caplog.text
    assert [(t.port, t.baud, t.number, t.total) for t in rig.tried] == [("COM3", 9600, 1, 21), ("COM4", 9600, 8, 21)]
    assert time.monotonic() - started < 10
