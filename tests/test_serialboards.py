"""The search leaves development boards alone (neoaprs/serialboards.py): their USB console resets the chip when the port is opened. The USB ids come from faked listings of the ports: no device is looked at."""
import asyncio
import logging
from pathlib import Path

import pytest
from serial.tools.list_ports_common import ListPortInfo  # type: ignore[import-untyped]

from neoaprs import serialprobe
from neoaprs.cli import doctor
from neoaprs.serialboards import BOARDS, board_kind
from neoaprs.serialport import SerialError
from neoaprs.serialprobe import PortInfo, searchable_ports
from neoaprs.tncsearch import PortSearch

ESP32 = (0x303A, 0x1001)
BOARD_IDS = [ESP32, (0x303A, 0x4001), (0x303A, 0x0002), (0x2341, 0x0043), (0x2341, 0x8036), (0x2A03, 0x0043), (0x2E8A, 0x000A), (0x2E8A, 0x0005), (0x239A, 0x8014), (0x16C0, 0x0483), (0x1366, 0x0105), (0x1366, 0x1015),
             (0x0483, 0x3748), (0x0483, 0x374B), (0x0483, 0x374E), (0x0483, 0x3744)]
TNC_IDS = [(0x0403, 0x6001), (0x0403, 0x6015), (0x0403, 0x6010), (0x10C4, 0xEA60), (0x1A86, 0x7523), (0x1A86, 0x55D4), (0x067B, 0x2303), (0x0483, 0x5740), (0x16C0, 0x27DD), (0x2166, 0x0001), (0x1D6B, 0x0002)]
Ids = dict[str, tuple[int, int] | None]


def listed(device: Path, ids: tuple[int, int] | None) -> ListPortInfo:
    info = ListPortInfo(str(device))
    info.description, info.hwid = "n/a", "n/a"
    info.vid, info.pid = ids if ids else (None, None)
    return info


@pytest.mark.parametrize("ids", BOARD_IDS)
def test_a_development_board_is_known_by_its_usb_ids(ids: tuple[int, int]) -> None:
    assert board_kind(*ids)


@pytest.mark.parametrize("ids", TNC_IDS)
def test_the_usb_serial_bridges_and_the_tncs_are_searched(ids: tuple[int, int]) -> None:
    assert board_kind(*ids) == ""


def test_a_device_without_ids_is_searched() -> None:
    assert board_kind(None, None) == "" and board_kind(0x303A, None) == "" and board_kind(None, 0x1001) == ""


def test_the_vendors_that_make_bridges_and_tncs_are_not_skipped_whole() -> None:
    whole = {vid for vid, pids, _ in BOARDS if pids is None}
    assert not whole & {0x0403, 0x10C4, 0x1A86, 0x067B, 0x0483, 0x16C0}


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Ids:
    """/dev of the test: ttyACM0 an ESP32, ttyACM1 a device with ids that are no board's, ttyUSB0 an FTDI, ttyUSB1 a port without ids, and the by-id links of the first and the third. The dict is the USB ids
    the system lists for each node; a node taken out of it is not listed."""
    ids: Ids = {"ttyACM0": ESP32, "ttyACM1": (0x2166, 0x0001), "ttyUSB0": (0x0403, 0x6001), "ttyUSB1": None}
    (tmp_path / "serial" / "by-id").mkdir(parents=True)
    for name in ids:
        (tmp_path / name).touch()
    (tmp_path / "serial" / "by-id" / "usb-Espressif_USB_JTAG-if00").symlink_to(tmp_path / "ttyACM0")
    (tmp_path / "serial" / "by-id" / "usb-FTDI_FT232R-if00-port0").symlink_to(tmp_path / "ttyUSB0")
    monkeypatch.setattr(serialprobe.serial.tools.list_ports, "comports", lambda: [listed(tmp_path / name, found) for name, found in ids.items()])
    return ids


def pattern_of(root: Path) -> str:
    return f"{root}/serial/by-id/* {root}/ttyUSB* {root}/ttyACM*"


def test_the_search_leaves_a_board_out_whatever_name_it_is_found_by(tmp_path: Path, machine: Ids) -> None:
    ports, boards = searchable_ports(pattern_of(tmp_path))
    assert ports == [str(tmp_path / "serial/by-id/usb-FTDI_FT232R-if00-port0"), str(tmp_path / "ttyACM1"), str(tmp_path / "ttyUSB1")]
    assert boards == {str(tmp_path / "serial/by-id/usb-Espressif_USB_JTAG-if00"): "an ESP32 development board (USB 303a:1001)"}
    assert searchable_ports(f"{tmp_path}/ttyACM0")[1] == {str(tmp_path / "ttyACM0"): "an ESP32 development board (USB 303a:1001)"}


def test_a_port_the_system_does_not_list_is_searched(tmp_path: Path, machine: Ids) -> None:
    del machine["ttyACM0"]
    assert searchable_ports(f"{tmp_path}/ttyACM0") == ([str(tmp_path / "ttyACM0")], {})


def test_the_system_is_not_asked_when_no_port_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serialprobe, "available_ports", lambda: pytest.fail("listed the ports"))
    assert searchable_ports(f"{tmp_path}/nothing_*") == ([], {})


def port_search() -> PortSearch:
    return PortSearch(lambda coro: asyncio.get_running_loop().create_task(coro), lambda text: None, b"\r")


async def find(search: PortSearch, pattern: str) -> str:
    return await search.find(pattern, 9600, 0.2, lambda heard: False, False, 1.0, (), lambda: True)


async def test_the_search_says_once_which_board_it_skipped_and_why(tmp_path: Path, machine: Ids, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "ttyACM1").unlink()
    (tmp_path / "ttyUSB0").unlink()
    (tmp_path / "ttyUSB1").unlink()
    search = port_search()
    caplog.set_level(logging.INFO, logger="neoaprs.tnc")
    for _ in range(2):
        with pytest.raises(SerialError):
            await find(search, pattern_of(tmp_path))
    told = [r.getMessage() for r in caplog.records if "skipping" in r.getMessage()]
    assert told == [f"tnc: skipping {tmp_path}/serial/by-id/usb-Espressif_USB_JTAG-if00: an ESP32 development board (USB 303a:1001)"]


async def test_with_nothing_but_boards_the_error_names_them_and_the_way_out(tmp_path: Path, machine: Ids) -> None:
    with pytest.raises(SerialError) as caught:
        await find(port_search(), f"{tmp_path}/ttyACM0")
    assert "ttyACM0 is an ESP32 development board (USB 303a:1001)" in str(caught.value) and "choose the port by its name" in str(caught.value)


def test_the_doctor_marks_a_board_in_its_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "available_ports", lambda: [PortInfo("/dev/ttyACM0", "USB JTAG/serial debug unit", "USB VID:PID=303A:1001", 0x303A, 0x1001), PortInfo("/dev/ttyUSB0", "FT232R", "USB VID:PID=0403:6001", 0x0403, 0x6001)])
    text = doctor.check_ports().text
    acm, usb = (line for line in text.splitlines() if line.startswith("    /dev/"))
    assert "an ESP32 development board" in acm and "name the port" in acm and "development board" not in usb
