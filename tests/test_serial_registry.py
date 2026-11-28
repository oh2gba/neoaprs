"""Windows ports known only by their name in the registry map HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM, such as
a virtual port another program shares (neoaprs/serialprobe.py): offered wherever the operator
chooses a port, never chosen, searched or tried by NeoAPRS itself. The registry and pyserial's list are fakes,
from a station's support file (two com0com ports with the Ports class, a CP2105, and two virtual ports
without it)."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
import serial  # type: ignore[import-untyped]
from serial.tools.list_ports_common import ListPortInfo  # type: ignore[import-untyped]

from neoaprs import serialport, serialprobe
from neoaprs.claims import Claims
from neoaprs.coded import code_of
from neoaprs.config import Config
from neoaprs.direwolfmodem import proposal as sound_card_proposal
from neoaprs.mercurycards import SoundCard
from neoaprs.mercurymodem import proposal as mercury_proposal
from neoaprs.mercurymodem import system_serial_ports
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID
from neoaprs.serialprobe import AdapterId, PortInfo
from neoaprs.services import radiofinder
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from neoaprs.web import handlers
from neoaprs.web.radioview import radio_row
from tests.support.env import until


def listed(device: str, description: str, hwid: str, vid: int | None = None, pid: int | None = None) -> ListPortInfo:
    info = ListPortInfo(device, skip_link_detection=True)
    info.description, info.hwid, info.vid, info.pid = description, hwid, vid, pid
    return info


CP2105 = (0x10C4, 0xEA70)
DEVICES = [
    listed("COM3", "com0com - serial port emulator (COM3)", "COM0COM\\PORT\\CNCA0"),
    listed("COM4", "com0com - serial port emulator (COM4)", "COM0COM\\PORT\\CNCB0"),
    listed(
        "COM11",
        "Silicon Labs Dual CP2105 USB to UART Bridge: Standard COM Port (COM11)",
        "USB VID:PID=10C4:EA70 SER=00000001 LOCATION=1-2.1:x.1",
        *CP2105,
    ),
    listed(
        "COM12",
        "Silicon Labs Dual CP2105 USB to UART Bridge: Enhanced COM Port (COM12)",
        "USB VID:PID=10C4:EA70 SER=00000001",
        *CP2105,
    ),
]
# value name -> data, as the drivers write them (REG_SZ = 1)
SERIALCOMM = {
    "\\Device\\com0com10": "COM3",
    "\\Device\\com0com20": "COM4",
    "\\Device\\Silabser0": "COM11",
    "\\Device\\Silabser1": "COM12",
    "\\Device\\com0com11": "COM6",
    "\\Device\\com0com21": "COM8",
}


class FakeRegistry:
    """winreg with one key: the serial map, as {value name: data}; None makes the key missing."""

    HKEY_LOCAL_MACHINE = 0x80000002

    def __init__(self, values: dict[str, Any] | None) -> None:
        self.values = values
        self.opened: list[tuple[int, str]] = []

    @contextmanager
    def OpenKey(self, root: int, path: str) -> Iterator[str]:
        self.opened.append((root, path))
        if self.values is None:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        yield path

    def EnumValue(self, key: str, index: int) -> tuple[str, Any, int]:
        assert self.values is not None
        items = list(self.values.items())
        if index >= len(items):
            raise OSError(259, "No more data is available")
        name, data = items[index]
        return name, data, 1 if isinstance(data, str) else 3


@pytest.fixture
def station(monkeypatch: pytest.MonkeyPatch) -> FakeRegistry:
    """Windows with the station's devices and registry map."""
    registry = FakeRegistry(dict(SERIALCOMM))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: list(DEVICES))
    monkeypatch.setattr(serialprobe, "_registry", lambda: registry)
    return registry


# ---- the list


def test_the_ports_only_in_the_registry_map_are_listed_by_name_in_natural_order(station: FakeRegistry) -> None:
    ports = serialprobe.available_ports()
    assert [p.device for p in ports] == ["COM3", "COM4", "COM6", "COM8", "COM11", "COM12"]
    assert [p.name_only for p in ports] == [False, False, True, True, False, False]
    assert ports[2] == PortInfo("COM6", "n/a", "n/a", None, None, name_only=True)
    assert ports[0] == PortInfo("COM3", "com0com - serial port emulator (COM3)", "COM0COM\\PORT\\CNCA0", None, None), (
        "a port of the device list keeps what the system says of it"
    )
    assert station.opened == [(FakeRegistry.HKEY_LOCAL_MACHINE, "HARDWARE\\DEVICEMAP\\SERIALCOMM")]


def test_a_name_in_the_map_in_another_case_is_the_listed_device(
    station: FakeRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serialprobe, "_registry", lambda: FakeRegistry({"a": "com3", "b": " COM6\0", "c": "Com6"}))
    assert [(p.device, p.name_only) for p in serialprobe.available_ports()] == [
        ("COM3", False),
        ("COM4", False),
        ("COM6", True),
        ("COM11", False),
        ("COM12", False),
    ]


@pytest.mark.parametrize("values", [{}, None], ids=["empty map", "no map"])
def test_an_empty_or_missing_map_lists_the_devices_alone(
    station: FakeRegistry, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any] | None
) -> None:
    monkeypatch.setattr(serialprobe, "_registry", lambda: FakeRegistry(values))
    assert [p.device for p in serialprobe.available_ports()] == ["COM3", "COM4", "COM11", "COM12"]


def test_a_value_that_is_not_text_is_passed_over(station: FakeRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        serialprobe, "_registry", lambda: FakeRegistry({"a": b"COM7\0", "b": 7, "c": "", "d": ["COM9"], "e": "COM6"})
    )
    assert serialprobe.serialcomm_names() == ["COM6"]


def test_a_registry_that_cannot_be_read_is_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> Any:
        raise ImportError("No module named 'winreg'")

    monkeypatch.setattr(serialprobe, "_registry", missing)
    assert serialprobe.serialcomm_names() == []
    denied = FakeRegistry({})
    denied.OpenKey = lambda root, path: (_ for _ in ()).throw(PermissionError(13, "Access is denied"))  # type: ignore[method-assign]
    assert serialprobe.serialcomm_names(denied) == []


def test_off_windows_the_registry_is_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def never() -> Any:
        raise AssertionError("the registry was read")

    really = sys.platform
    monkeypatch.setattr(serialprobe, "_registry", never)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [listed("/dev/ttyUSB0", "CP2102", "USB", 1, 2)])
    for platform in ("linux", "darwin"):
        monkeypatch.setattr(sys, "platform", platform)
        assert [p.device for p in serialprobe.available_ports()] == ["/dev/ttyUSB0"]
        assert [p.device for p in serialprobe.offered_ports()] == ["/dev/ttyUSB0"]
    if really != "win32":
        assert "winreg" not in sys.modules, "nothing of winreg is loaded off Windows"


# ---- offered where the operator chooses


def test_the_page_offers_the_name_only_ports_for_a_radio_its_keying_and_the_gps_receiver(station: FakeRegistry) -> None:
    offered = [p.device for p in handlers.listed_ports()]
    assert offered == ["COM3", "COM4", "COM6", "COM8", "COM11", "COM12"]
    assert [p.device for p in system_serial_ports()] == offered, "the modems' own list of keying ports"


def test_the_doctor_and_the_support_file_show_them_without_ids(
    station: FakeRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neoaprs.cli import doctor
    from neoaprs.web import supportstate

    monkeypatch.setattr(doctor, "held_by", lambda path: "")
    monkeypatch.setattr(supportstate, "held_by", lambda path: "")
    lines = doctor.check_ports().text.splitlines()
    assert lines[0] == "6 serial ports listed by the system:"
    assert lines[3] == "    COM6  n/a  VID:PID -"
    rows = supportstate.ports_with_holders()
    assert rows[3] == {"device": "COM8", "description": "n/a", "hwid": "n/a", "vid": None, "pid": None, "held_by": ""}


# ---- never chosen by NeoAPRS itself


def test_find_my_radio_never_tries_a_name_only_port(station: FakeRegistry) -> None:
    assert [p.device for p in serialprobe.system_ports()] == ["COM11", "COM12", "COM3", "COM4"]
    assert "COM6" not in radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ())
    assert not serialprobe.can_search(), "on Windows no search runs by itself"


def test_no_keying_is_chosen_on_a_name_only_port(station: FakeRegistry) -> None:
    usb_card = [SoundCard("in|out", "USB Audio CODEC", True, True)]
    lone = [serialprobe.name_only_port("COM6")]
    assert sound_card_proposal(usb_card, lone, holder=2, beside=lambda card, devices: None) == ("in|out", "vox")
    assert mercury_proposal(usb_card, lone, Config(), holder=2) == ("in|out", "vox")
    one_cp210x = [*lone, PortInfo("COM11", "CP2102", "USB VID:PID=10C4:EA60 SER=1", 0x10C4, 0xEA60)]
    assert sound_card_proposal(usb_card, one_cp210x, holder=2, beside=lambda card, devices: None)[1] == "rts:COM11"
    assert mercury_proposal(usb_card, one_cp210x, Config(), holder=2)[1] == "rts:COM11"


def test_a_name_only_port_is_no_remembered_adapter_and_no_adapter_moves_to_it(station: FakeRegistry) -> None:
    assert serialprobe.identity_of("COM6") is None
    cp2105 = AdapterId(*CP2105, "00000002")
    assert serialprobe.moved_to(cp2105, "COM9") is None
    assert serialprobe.moved_to(serialprobe.identity_of("COM11"), "COM9") is None, "two ports of one CP2105"


# ---- opened once chosen


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


class VirtualSer:
    """A virtual port's pyserial object: not there until the program that makes it runs, or held by another."""

    def __init__(self) -> None:
        self.refusal: str | None = (
            "could not open port 'COM6': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"
        )
        self.in_waiting = 0

    def open(self) -> None:
        if self.refusal is not None:
            raise serial.SerialException(self.refusal)

    def read(self, size: int = 1) -> bytes:
        import time

        time.sleep(0.01)
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        pass


async def test_a_chosen_name_only_port_that_is_not_there_yet_waits_and_opens_once_it_is(
    station: FakeRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    station.values = {k: v for k, v in SERIALCOMM.items() if v != "COM6"}
    ser = VirtualSer()
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    tnc = Tnc("COM6", profile=KISS, backoff=Backoff([0.05]))
    try:
        await tnc.start()
        await until(lambda: tnc.problem != "")
        assert tnc.state is not Source.State.CONNECTED
        assert row_of(tnc) == ("waiting", {"code": "radio.not_connected", "params": {"name": "Packet"}})
        station.values = dict(SERIALCOMM)
        ser.refusal = None
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert row_of(tnc) == ("connected", None)
    finally:
        await tnc.stop()


async def test_a_name_only_port_another_program_holds_is_in_use_by_another_program(
    station: FakeRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    ser = VirtualSer()
    ser.refusal = "could not open port 'COM6': PermissionError(13, 'Access is denied.', None, 5)"
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    with pytest.raises(serialport.SerialError) as caught:
        await serialport.SerialPort("COM6").open()
    assert code_of(caught.value.args[0]) == ("radio.port_in_use", {})


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' own registry")
def test_the_real_registry_map_reads_without_error_as_com_names() -> None:
    import importlib
    import re

    names = serialprobe.serialcomm_names(importlib.import_module("winreg"))
    assert all(re.fullmatch(r"COM\d+", name, re.IGNORECASE) for name in names), names
