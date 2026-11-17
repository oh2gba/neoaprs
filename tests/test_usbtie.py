"""Which serial ports and sound cards are one radio's (neoaprs/usbtie.py), on a made-up sysfs: two Digirigs (a sound chip and a CP2102 behind a hub of each one's own), a dongle and an FTDI cable plugged
straight into the computer, an all-in-one chip that is one USB device with both, and the owner's station (two radios with USB, a desktop hub, a big hub, the mainboard's sound). The made-up sysfs is POSIX
only (its folders are named with colons, its links are symbolic links); what Windows, which has no sysfs, does instead (nothing can be told, and the keying falls back to the computer's one interface port) is tested on both systems."""
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


@pytest.fixture
def station(tmp_path: Path) -> Path:
    """The owner's two radios on one computer: the FTX-1's hub with a C-Media card, a CP2105 (two ports) and one more serial chip; the other radio's hub with its card and a CP2105. Beside them a lone FTDI
    cable and a lone dongle on a small desktop hub, a big hub with a keyboard, a dongle and a cable on it, and the mainboard's own sound."""
    root = tmp_path / "sys"
    _card(root, 1, "FTX1", "1-2/1-2.1/1-2.1:1.0")
    _tty(root, "ttyUSB0", "1-2/1-2.2/1-2.2:1.0")
    _tty(root, "ttyUSB1", "1-2/1-2.2/1-2.2:1.1")
    _tty(root, "ttyUSB2", "1-2/1-2.3/1-2.3:1.0")
    _card(root, 2, "CODEC", "1-3/1-3.1/1-3.1:1.0")
    _tty(root, "ttyUSB3", "1-3/1-3.2/1-3.2:1.0")
    _tty(root, "ttyUSB4", "1-3/1-3.2/1-3.2:1.1")
    _card(root, 3, "Dongle", "1-4/1-4.1/1-4.1:1.0")
    _tty(root, "ttyUSB5", "1-4/1-4.2/1-4.2:1.0")
    _card(root, 4, "Dongle_1", "1-5/1-5.1/1-5.1:1.0")
    _tty(root, "ttyUSB6", "1-5/1-5.2/1-5.2:1.0")
    (root / PCI / "1-5" / "1-5.3" / "1-5.3:1.0").mkdir(parents=True)                       # (the keyboard: neither a sound card nor a serial port)
    board = root / "devices/pci0000:00/0000:00:1f.3"
    board.mkdir(parents=True)
    (root / "class" / "sound" / "card0").mkdir(parents=True)
    (root / "class" / "sound" / "card0" / "id").write_text("PCH\n", encoding="utf-8")
    (root / "class" / "sound" / "card0" / "device").symlink_to(board)
    (root / "class" / "tty" / "ttyS0").mkdir(parents=True)
    (root / "class" / "tty" / "ttyS0" / "device").symlink_to(board)
    return root


STATION = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB3", "/dev/ttyUSB4", "/dev/ttyUSB5", "/dev/ttyUSB6", "/dev/ttyS0", "bt://AA:BB:CC:DD:EE:FF"]
CARDS = ["plughw:CARD=FTX1,DEV=0", "plughw:CARD=CODEC,DEV=0", "plughw:CARD=Dongle,DEV=0", "plughw:4,0", "plughw:CARD=PCH,DEV=0", "plughw:CARD=Gone,DEV=0"]


def _together(cards: dict[str, str | None], ports: dict[str, str | None], card: str) -> list[str]:
    return [d for d, token in ports.items() if token is not None and token == cards[card]]


@posix_only
def test_two_radios_on_one_computer_are_two_groups_each_card_with_its_own_ports(station: Path) -> None:
    cards, ports = usbtie.groups(CARDS, STATION, station)
    assert _together(cards, ports, "plughw:CARD=FTX1,DEV=0") == ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2"], "the FTX-1's three ports: the CP2105's two and the other chip's"
    assert _together(cards, ports, "plughw:CARD=CODEC,DEV=0") == ["/dev/ttyUSB3", "/dev/ttyUSB4"]
    assert usbtie.tied("plughw:CARD=FTX1,DEV=0", STATION, station) == ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2"], "the keying Direwolf is given follows the same rule"
    assert all(len(token or "") == 12 and "/" not in (token or "") for token in [*cards.values(), *ports.values()] if token is not None), "a token, no path"


@posix_only
def test_a_lone_cable_and_a_lone_dongle_on_a_desktop_hub_with_nothing_else_are_grouped(station: Path) -> None:
    cards, ports = usbtie.groups(CARDS, STATION, station)
    assert _together(cards, ports, "plughw:CARD=Dongle,DEV=0") == ["/dev/ttyUSB5"]


@posix_only
def test_a_hub_with_anything_else_on_it_is_no_radios_and_its_devices_stand_alone(station: Path) -> None:
    cards, ports = usbtie.groups(CARDS, STATION, station)
    assert cards["plughw:4,0"] is not None and _together(cards, ports, "plughw:4,0") == [], "a keyboard beside them: the dongle and the cable are not one radio"
    assert ports["/dev/ttyUSB6"] is not None and ports["/dev/ttyUSB6"] not in cards.values()


@posix_only
def test_what_is_not_on_the_usb_or_not_found_has_no_group(station: Path) -> None:
    cards, ports = usbtie.groups(CARDS, STATION, station)
    assert cards["plughw:CARD=PCH,DEV=0"] is None and cards["plughw:CARD=Gone,DEV=0"] is None, "the mainboard's sound, and a card that is not there"
    assert ports["/dev/ttyS0"] is None and ports["bt://AA:BB:CC:DD:EE:FF"] is None and ports["/dev/ttyUSB0"] is not None


@posix_only
def test_a_tree_that_cannot_be_read_tells_nothing(tmp_path: Path) -> None:
    (tmp_path / "sys").write_text("", encoding="utf-8")                                    # (not a folder)
    for root in (tmp_path / "none", tmp_path / "sys"):
        cards, ports = usbtie.groups(CARDS, STATION, root)
        assert set(cards.values()) == {None} and set(ports.values()) == {None}


def test_under_the_no_devices_switch_or_off_linux_every_token_is_null(under_the_switch: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    read: list[Path] = []
    monkeypatch.setattr(usbtie, "groups", lambda *a: read.append(a[2]))                    # (were the tree read, this would say so)
    assert usbtie.together(["plughw:1,0"], ["/dev/ttyUSB0"]) == ({"plughw:1,0": None}, {"/dev/ttyUSB0": None})
    monkeypatch.setattr(nodevices, "on", lambda: False)
    monkeypatch.setenv("NEOAPRS_SYS_ROOT", str(tmp_path))
    for system in ("win32", "darwin"):
        monkeypatch.setattr(sys, "platform", system)
        assert usbtie.together(["x|y"], ["COM3"]) == ({"x|y": None}, {"COM3": None})
    assert read == []


@posix_only
def test_a_by_id_link_to_a_port_is_in_the_group_of_the_port_it_names(station: Path, tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    (dev / "serial" / "by-id").mkdir(parents=True)
    (dev / "ttyUSB4").write_text("", encoding="utf-8")
    link = dev / "serial" / "by-id" / "usb-Silicon_Labs_CP2105-if01-port0"
    link.symlink_to(dev / "ttyUSB4")
    cards, ports = usbtie.groups(CARDS, [str(link), "/dev/ttyUSB3"], station)
    assert ports[str(link)] is not None and ports[str(link)] == ports["/dev/ttyUSB3"] == cards["plughw:CARD=CODEC,DEV=0"], "the link and the port are one device of one radio"
