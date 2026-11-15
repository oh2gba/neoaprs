"""Which serial ports are part of a sound card's interface (neoaprs/usbtie.py), on a made-up sysfs: two Digirigs (a sound chip and a CP2102 behind a hub of each one's own), a dongle and an FTDI cable plugged
straight into the computer, and an all-in-one chip that is one USB device with both. The made-up sysfs is POSIX only (its folders are named with colons, its links are symbolic links); what Windows, which has
no sysfs, does instead (nothing can be told, and the keying falls back to the computer's one interface port) is tested on both systems."""
import sys
from pathlib import Path

import pytest

from neoaprs import nodevices, usbtie
from neoaprs.direwolf import choose_keying
from neoaprs.mercury import Keying, SerialPort
from tests.support.ptyline import posix_only
from tests.test_no_devices import under_the_switch  # noqa: F401  (the fixture)

PCI = "devices/pci0000:00/0000:00:14.0/usb1"


def _card(root: Path, number: int, name: str, place: str) -> None:
    interface = root / PCI / place
    interface.mkdir(parents=True, exist_ok=True)
    card = root / "class" / "sound" / f"card{number}"
    card.mkdir(parents=True)
    (card / "id").write_text(f"{name}\n", encoding="utf-8")
    (card / "device").symlink_to(interface)


def _tty(root: Path, name: str, place: str, usb_serial: bool = True) -> None:
    device = root / PCI / place / name if usb_serial else root / PCI / place            # (a USB serial chip's port is a device under its interface; an ACM port is the interface)
    device.mkdir(parents=True, exist_ok=True)
    tty = root / "class" / "tty" / name
    tty.mkdir(parents=True)
    (tty / "device").symlink_to(device)


@pytest.fixture
def sys_root(tmp_path: Path) -> Path:
    root = tmp_path / "sys"
    _card(root, 1, "Device", "1-2/1-2.1/1-2.1:1.0")
    _tty(root, "ttyUSB0", "1-2/1-2.2/1-2.2:1.0")
    _card(root, 2, "Device_1", "1-3/1-3.1/1-3.1:1.0")
    _tty(root, "ttyUSB1", "1-3/1-3.2/1-3.2:1.0")
    _card(root, 3, "Dongle", "1-4/1-4:1.0")
    _tty(root, "ttyUSB2", "1-5/1-5:1.0")
    _card(root, 4, "AIOC", "1-6/1-6:1.0")
    _tty(root, "ttyACM0", "1-6/1-6:1.3", usb_serial=False)
    return root


PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyACM0"]


@posix_only
def test_a_cards_ports_are_those_on_its_own_hub_or_its_own_device(sys_root: Path) -> None:
    assert usbtie.tied("plughw:CARD=Device,DEV=0", PORTS, sys_root) == ["/dev/ttyUSB0"]
    assert usbtie.tied("plughw:2,0", PORTS, sys_root) == ["/dev/ttyUSB1"], "the second Digirig, by the card's number: its own port, not the first one's"
    assert usbtie.tied("plughw:CARD=AIOC,DEV=0", PORTS, sys_root) == ["/dev/ttyACM0"], "one USB device with both"
    assert usbtie.tied("plughw:CARD=Dongle,DEV=0", PORTS, sys_root) == [], "two devices on the computer's own hub are not one interface"


@posix_only
def test_a_by_id_link_is_the_port_it_points_at(sys_root: Path, tmp_path: Path) -> None:
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev" / "ttyUSB1").write_text("", encoding="utf-8")
    link = tmp_path / "usb-Silicon_Labs_CP2102N-if00-port0"
    link.symlink_to(tmp_path / "dev" / "ttyUSB1")
    assert usbtie.tied("plughw:CARD=Device_1,DEV=0", [str(link)], sys_root) == [str(link)]


@posix_only
def test_where_the_card_is_not_found_on_the_usb_nothing_can_be_told(sys_root: Path, tmp_path: Path) -> None:
    assert usbtie.tied("plughw:CARD=Nothing,DEV=0", PORTS, sys_root) is None and usbtie.tied("default", PORTS, sys_root) is None
    assert usbtie.tied("plughw:CARD=Device,DEV=0", PORTS, tmp_path / "none") is None


def test_under_the_no_devices_switch_nothing_is_read(under_the_switch: None) -> None:  # noqa: F811
    assert nodevices.on() and usbtie.beside("plughw:CARD=Device,DEV=0", PORTS) is None and usbtie.beside("", PORTS) is None


def test_where_there_is_no_sysfs_nothing_can_be_told_and_the_keying_is_the_computers_one_interface_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(nodevices, "on", lambda: False)
    monkeypatch.setenv("NEOAPRS_SYS_ROOT", str(tmp_path))                           # (were it read, nothing is there)
    for system in ("win32", "darwin"):
        monkeypatch.setattr(sys, "platform", system)
        assert usbtie.beside("{0.0.1.00000000}.{2301}|{0.0.0.00000000}.{ca03}", ["COM3"]) is None and usbtie.beside("plughw:1,0", ["/dev/ttyUSB0"]) is None
    digirig, second = SerialPort("COM3", 0x10C4, 0xEA60), SerialPort("COM4", 0x10C4, 0xEA60)
    assert choose_keying("USB Audio CODEC", [digirig], None) == Keying("rts", "COM3"), "the computer's one such port, for a card that names itself as an interface's"
    assert choose_keying("USB Audio CODEC", [digirig, second], None) == Keying("vox") and choose_keying("Realtek(R) Audio", [digirig], None) == Keying("vox"), "two such ports, or the computer's own sound: VOX"
