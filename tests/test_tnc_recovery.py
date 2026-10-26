"""The radio recovers by itself, with no click on Reconnect: a radio that is silent (the port open, no answer) when it comes back, a port that goes away and comes back (a USB adapter plugged in again) and, where the radio is not
searched for (Windows, macOS), an adapter that comes back as another COM port. The Tnc runs on fake radios (TCP servers on the loopback) with short periods; the pieces of each case are tested closer in tests/test_silent.py, tests/test_tnc.py and
tests/test_tnc_pty.py."""
from types import SimpleNamespace

import pytest

from neoaprs import serialprobe
from neoaprs.serialprobe import AdapterId, PortInfo
from neoaprs.serialport import SerialError
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncfollow import AdapterFollow
from tests.support.env import idle_for, until
from tests.support.fakeradio import FakeRadio
from tests.test_silent import silent_rig
from tests.test_tnc import Rigs, kiss_of, stops_rigs, tiny_backoff, ui_frame

FTDI = (0x0403, 0x6001)


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


@pytest.fixture
def no_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows: the radio is not looked for among the ports, it is the port that was named."""
    monkeypatch.setattr(serialprobe, "sys", SimpleNamespace(platform="win32"))


def usb(device: str, serial: str = "", ids: tuple[int, int] = FTDI) -> PortInfo:
    return PortInfo(device, "USB Serial Port", f"USB VID:PID={ids[0]:04X}:{ids[1]:04X}" + (f" SER={serial}" if serial else " LOCATION=1-2"), ids[0], ids[1])


# ---- a silent radio

@stops_rigs
async def test_a_silent_radio_that_is_switched_on_is_connected_again_without_a_click(rig: Rigs) -> None:
    r, _ = await silent_rig(rig)
    assert r.tnc.state is Source.State.SILENT and r.tnc.usable is False
    r.radio.feed(kiss_of(ui_frame()))                              # the radio is switched on and sends a packet
    await until(lambda: r.tnc.state is Source.State.CONNECTED and r.tnc.usable, 3.0)
    assert len(r.packets) == 1 and r.tnc.silent_since is None and r.tnc.stats.opens == 1, "the same open line: nothing was restarted"


@stops_rigs
async def test_a_silent_radio_whose_adapter_was_plugged_in_again_is_connected_again_without_a_click(rig: Rigs) -> None:
    r, _ = await silent_rig(rig, probe_sec=0.05)
    r.radio.drop()                                                 # the cable is pulled while the radio is silent
    await until(lambda: r.tnc.state is Source.State.WAITING)
    await until(lambda: r.tnc.state in (Source.State.CONNECTED, Source.State.SILENT) and r.tnc.stats.opens == 2, 5.0)    # (the radio listens still: the adapter is back)
    r.radio.feed(kiss_of(ui_frame()))
    await until(lambda: r.tnc.state is Source.State.CONNECTED and len(r.packets) == 1, 3.0)


# ---- a port that goes away and comes back

@pytest.mark.usefixtures("no_search")
async def test_a_com_port_that_goes_away_and_comes_back_is_opened_again_where_nothing_is_searched() -> None:
    radio = FakeRadio()
    await radio.start()
    tnc = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=True)
    packets = []
    tnc.packet.connect(packets.append)
    try:
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED
        await radio.connected()
        radio.refuse()                                             # the adapter is pulled out: the port is gone and a try to open it fails
        radio.drop()
        await until(lambda: tnc.state is Source.State.WAITING)
        assert "lost" in (tnc.last_error or "")
        await radio.accept()                                       # and plugged in: the same name
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.stats.opens == 2)
        radio.feed(kiss_of(ui_frame()))
        await until(lambda: len(packets) == 1)
    finally:
        await tnc.stop()
        await radio.aclose()


# ---- an adapter that comes back as another port

class TwoAdapters:
    """The system's list of ports, which a test changes: the radio is on the first fake radio's port, then on the second's."""

    def __init__(self, first: FakeRadio, second: FakeRadio, serial: str) -> None:
        self.first, self.second, self.serial = first, second, serial
        self.listed = [usb(first.url, serial)]

    def move(self) -> None:
        self.first.refuse()
        self.first.drop()
        self.listed = [usb(self.second.url, self.serial)]

    def __call__(self) -> list[PortInfo]:
        return list(self.listed)


@pytest.mark.usefixtures("no_search")
@pytest.mark.parametrize("serial", ["A50285BI", ""])
async def test_an_adapter_that_comes_back_as_another_port_is_followed_to_it(monkeypatch: pytest.MonkeyPatch, serial: str) -> None:
    first, second = FakeRadio(), FakeRadio()
    await first.start()
    await second.start()
    ports = TwoAdapters(first, second, serial)
    monkeypatch.setattr(serialprobe, "available_ports", ports)
    tnc = Tnc(first.url, backoff=tiny_backoff(), fallback_probe=True)
    packets = []
    tnc.packet.connect(packets.append)
    try:
        await tnc.start()
        await first.connected()
        assert tnc.path == first.url
        ports.move()                                                # COM5 is gone, the adapter is COM7 now
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.path == second.url)
        assert tnc.port == first.url, "the setting is not changed: the adapter is what is followed"
        assert any("is gone; the adapter is on" in line for line in tnc.lines)
        await second.connected()
        second.feed(kiss_of(ui_frame()))
        await until(lambda: len(packets) == 1)
    finally:
        await tnc.stop()
        await first.aclose()
        await second.aclose()


@pytest.mark.usefixtures("no_search")
async def test_an_adapter_without_a_serial_number_is_not_followed_when_two_ports_look_alike_and_the_operator_chooses(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second, third = FakeRadio(), FakeRadio(), FakeRadio()
    for radio in (first, second, third):
        await radio.start()
    ports = TwoAdapters(first, second, "")
    monkeypatch.setattr(serialprobe, "available_ports", ports)
    tnc = Tnc(first.url, backoff=tiny_backoff(), fallback_probe=True)
    try:
        await tnc.start()
        await first.connected()
        ports.move()
        ports.listed.append(usb(third.url))                         # another adapter of the same kind: which one is the radio?
        await until(lambda: tnc.state is Source.State.WAITING and tnc.stats.opens == 1)
        await idle_for(0.4)                                         # (several tries)
        assert tnc.stats.opens == 1 and second.connections == 0 and third.connections == 0
    finally:
        await tnc.stop()
        for radio in (first, second, third):
            await radio.aclose()


def test_the_adapter_is_told_by_its_serial_number_and_a_port_that_is_still_listed_is_not_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    ports = [usb("COM5", "AAA"), usb("COM6", "BBB"), PortInfo("COM1", "Communications Port", "ACPI\\PNP0501", None, None)]
    monkeypatch.setattr(serialprobe, "available_ports", lambda: list(ports))
    assert serialprobe.identity_of("COM6") == AdapterId(*FTDI, "BBB")
    assert serialprobe.identity_of("COM1") is None and serialprobe.identity_of("COM9") is None
    adapter = AdapterId(*FTDI, "BBB")
    assert serialprobe.moved_to(adapter, "COM6") is None, "listed: something else keeps it"
    ports[:] = [usb("COM5", "AAA"), usb("COM7", "BBB")]
    assert serialprobe.moved_to(adapter, "COM6") == "COM7", "the same serial number among others of its kind"
    assert serialprobe.moved_to(AdapterId(*FTDI, "CCC"), "COM6") is None
    assert serialprobe.moved_to(None, "COM6") is None


def test_an_adapter_with_no_serial_number_is_followed_only_when_it_is_the_one_of_its_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    ports = [usb("COM7", ids=(0x1A86, 0x7523))]
    monkeypatch.setattr(serialprobe, "available_ports", lambda: list(ports))
    adapter = AdapterId(0x1A86, 0x7523, "")
    assert serialprobe.moved_to(adapter, "COM5") == "COM7"
    ports.append(usb("COM8", ids=(0x1A86, 0x7523)))
    assert serialprobe.moved_to(adapter, "COM5") is None
    ports[:] = [usb("COM7", "XYZ", ids=(0x1A86, 0x7523))]
    assert serialprobe.moved_to(adapter, "COM5") is None, "an adapter that has a serial number is another one"


async def test_where_the_radio_is_searched_for_the_adapter_is_not_followed_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serialprobe, "available_ports", lambda: [usb("/dev/ttyUSB0", "AAA")])
    monkeypatch.setattr(serialprobe, "sys", SimpleNamespace(platform="linux"))
    follow = AdapterFollow()
    opened: list[str] = []

    async def opener(path: str) -> str:
        opened.append(path)
        if path == "/dev/ttyUSB0":
            return path
        raise SerialError("gone")

    assert await follow.open("/dev/ttyUSB0", True, opener, print) == ("/dev/ttyUSB0", "/dev/ttyUSB0")
    monkeypatch.setattr(serialprobe, "available_ports", lambda: [usb("/dev/ttyUSB1", "AAA")])
    with pytest.raises(SerialError):
        await follow.open("/dev/ttyUSB0", True, lambda path: opener("/dev/ttyUSB9"), print)      # (the search for the radio does this on Linux, not the name)
    assert follow.active is False
