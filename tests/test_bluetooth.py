"""The classic Bluetooth serial port (neoaprs/btserial.py, btsdp.py, btpaired.py) on a fake device (tests/support/fakebluetooth.py): the address of a `bt://` port, the question to the device's service directory,
reading and writing, a link that dies and the Tnc that opens it again, the list of paired devices from BlueZ's own words, and that the port list and the search leave Bluetooth alone. No Bluetooth socket is made."""
import errno
import json
import socket
import struct
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs import ax25, btpaired, btsdp, serialprobe
from neoaprs.btserial import BluetoothSerial, is_bluetooth, parse_url
from neoaprs.kiss import KissDecoder, encode
from neoaprs.serialholders import held_by, port_key
from neoaprs.serialport import SerialError, SerialPort, is_socket, is_url
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from tests.support.env import until
from tests.support.fakebluetooth import ADDRESS, FakeBluetooth, answer, element, record, sequence, uuid16

URL = f"bt://{ADDRESS}"
REAL_RUN = btpaired._run                    # (the guard of the tests puts a stand-in in its place for each test)


@pytest.fixture
def device(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBluetooth]:
    fake = FakeBluetooth(monkeypatch)
    yield fake
    fake.close()


# ---- the address

@pytest.mark.parametrize("url,expected", [
    ("bt://00:11:22:33:44:55", ("00:11:22:33:44:55", None)),
    ("bt://aa:bb:cc:dd:ee:ff", ("AA:BB:CC:DD:EE:FF", None)),
    ("BT://AA-BB-CC-DD-EE-FF/2", ("AA:BB:CC:DD:EE:FF", 2)),
    ("  bt://AA:BB:CC:DD:EE:FF/30/ ", ("AA:BB:CC:DD:EE:FF", 30)),
])
def test_a_bluetooth_port_is_an_address_and_maybe_a_channel(url: str, expected: tuple[str, int | None]) -> None:
    assert parse_url(url) == expected


@pytest.mark.parametrize("url", ["bt://", "bt://AA:BB", "bt://AA:BB:CC:DD:EE:GG", "bt://AA:BB:CC:DD:EE:FF/0", "bt://AA:BB:CC:DD:EE:FF/31", "bt://AA:BB:CC:DD:EE:FF/x", "bt://AA:BB:CC:DD:EE:FF/2/3", "bt://AABBCCDDEEFF", "socket://h:1"])
def test_an_address_that_is_not_one_is_refused_with_the_way_to_write_it(url: str) -> None:
    with pytest.raises(ValueError, match="bt://AA:BB:CC:DD:EE:FF|RFCOMM channel"):
        parse_url(url)


def test_a_bluetooth_port_is_a_url_and_a_socket_without_a_file_or_a_speed() -> None:
    assert is_bluetooth(URL) and is_bluetooth(" BT://x") and not is_bluetooth("/dev/rfcomm0") and not is_bluetooth("socket://h:1")
    assert is_url(URL) and is_socket(URL) and port_key(URL) == URL.lower() and held_by(URL) == ""


# ---- the service directory

def test_the_question_is_the_serial_port_service_and_its_protocols() -> None:
    assert btsdp.request(0x1101, 4, 1).hex() == "060001000d3503191101040035030900" + "0400"


def test_the_answer_gives_the_rfcomm_channel() -> None:
    pdu = answer(7, sequence(record(2)))
    lists, state = btsdp.read_answer(pdu, 7)
    assert state == b"" and btsdp.rfcomm_channels(btsdp.parse_elements(lists)) == [2]


def test_the_first_of_several_services_is_the_one_and_other_protocols_are_not_channels() -> None:
    other = sequence(element(1, struct.pack(">H", 4)), sequence(sequence(uuid16(0x0100)), sequence(uuid16(0x000F), element(1, bytes([9])))))
    assert btsdp.rfcomm_channels(btsdp.parse_elements(sequence(other, record(5), record(3)))) == [5, 3]


@pytest.mark.parametrize("pdu", [b"", b"\x07\x00", answer(1, b"")[:-1], b"\x06" + answer(1, b"")[1:], answer(2, b"")])
def test_an_answer_that_is_none_is_refused(pdu: bytes) -> None:
    with pytest.raises(btsdp.SdpError):
        btsdp.read_answer(pdu, 1)


@pytest.mark.parametrize("data", [b"\x35", b"\x35\x05\x08", b"\x25\x09ab", b"\x19\x11", b"\x35\x02" * 20])
def test_elements_that_are_cut_off_or_nest_too_deep_are_refused(data: bytes) -> None:
    with pytest.raises(btsdp.SdpError):
        btsdp.parse_elements(data)


def test_the_directory_is_asked_and_the_channel_comes_back(device: FakeBluetooth) -> None:
    assert btsdp.serial_channels(ADDRESS) == [2]
    assert device.sdp_connects == [(ADDRESS, btsdp.SDP_PSM)] and device.asked[0].asked[0][0] == btsdp.SEARCH_ATTRIBUTES


def test_an_answer_in_pieces_is_put_together(device: FakeBluetooth) -> None:
    device.parts = 3
    assert btsdp.serial_channels(ADDRESS) == [2]
    assert len(device.asked[0].asked) == 3


def test_a_device_that_lists_no_serial_port_or_answers_nonsense_has_no_channel(device: FakeBluetooth) -> None:
    device.channel = None
    assert btsdp.serial_channels(ADDRESS) == []
    device.garbage = True
    assert btsdp.serial_channels(ADDRESS) == []


def test_a_device_that_cannot_be_reached_is_not_asked_twice(device: FakeBluetooth) -> None:
    device.sdp_error = OSError(errno.EHOSTDOWN, "Host is down")
    with pytest.raises(OSError, match="Host is down"):
        btsdp.serial_channels(ADDRESS)


# ---- open, read, write, close

async def test_the_port_opens_on_the_channel_in_the_address_and_carries_bytes_both_ways(device: FakeBluetooth) -> None:
    chunks: list[bytes] = []
    port = SerialPort(f"{URL}/2", 9600)
    port.data.connect(chunks.append)
    await port.open()
    try:
        await device.connected()
        assert port.is_open and device.connects == [(ADDRESS, 2)] and device.sdp_connects == []
        frame = encode(b"hello", port=0)
        device.feed(frame)
        await until(lambda: b"".join(chunks) == frame)
        assert port.write(frame) == len(frame)
        big = bytes(range(256)) * 40
        port.write(big)
        assert await device.said(len(frame) + len(big)) == frame + big
        assert KissDecoder().feed(frame)[0].payload == b"hello"
    finally:
        port.close()
    assert not port.is_open


async def test_without_a_channel_the_device_says_which(device: FakeBluetooth) -> None:
    device.channel = 3
    port = SerialPort(URL)
    await port.open()
    try:
        assert device.connects == [(ADDRESS, 3)]
    finally:
        port.close()


async def test_a_device_that_lists_no_serial_port_is_tried_on_the_usual_channels_and_the_log_says_which_connected(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="neoaprs.btserial")
    device = FakeBluetooth(monkeypatch, channel=3)
    device.garbage = True
    port = SerialPort(URL)
    await port.open()
    try:
        assert device.connects == [(ADDRESS, 1), (ADDRESS, 2), (ADDRESS, 3)]
        assert f"{ADDRESS}: connected on RFCOMM channel 3" in caplog.text and "nothing on RFCOMM channel 1" in caplog.text
    finally:
        port.close()
        device.close()


async def test_a_listed_channel_that_is_not_served_is_followed_by_the_usual_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    device = FakeBluetooth(monkeypatch, channel=1)
    device.listed = [5, 4]
    port = SerialPort(URL)
    await port.open()
    try:
        assert device.connects == [(ADDRESS, 5), (ADDRESS, 4), (ADDRESS, 1)]
    finally:
        port.close()
        device.close()


async def test_a_device_that_serves_nothing_anywhere_says_connection_refused_after_the_last_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    device = FakeBluetooth(monkeypatch, channel=9)
    device.garbage = True
    with pytest.raises(SerialError, match="Connection refused"):
        await SerialPort(URL).open()
    assert [c for _, c in device.connects] == [1, 2, 3]
    device.close()


async def test_a_device_that_is_out_of_range_is_not_tried_on_every_channel(device: FakeBluetooth) -> None:
    device.fail(OSError(errno.EHOSTDOWN, "Host is down"))
    with pytest.raises(SerialError, match="Host is down"):
        await SerialPort(URL).open()
    assert len(device.connects) == 1


async def test_what_is_written_just_before_the_close_still_goes_out(device: FakeBluetooth) -> None:
    port = SerialPort(f"{URL}/2")
    await port.open()
    port.write(b"last words")
    port.close()
    assert await device.said(10) == b"last words"


@pytest.mark.parametrize("error,words", [
    (OSError(errno.ECONNREFUSED, "Connection refused"), "Connection refused"),
    (OSError(errno.EHOSTDOWN, "Host is down"), "Host is down"),
    (TimeoutError("timed out"), "no answer from the device"),
])
async def test_a_device_that_does_not_answer_is_an_error_with_its_words(device: FakeBluetooth, error: OSError, words: str) -> None:
    device.fail(error)
    port = SerialPort(f"{URL}/2")
    with pytest.raises(SerialError) as e:
        await port.open()
    assert words in str(e.value) and URL in str(e.value) and not port.is_open


async def test_a_wrong_channel_is_refused_by_the_device(device: FakeBluetooth) -> None:
    port = SerialPort(f"{URL}/7")
    with pytest.raises(SerialError, match="Connection refused"):
        await port.open()
    assert device.connects == [(ADDRESS, 7)]


async def test_an_address_that_is_wrong_and_a_system_without_bluetooth_are_said_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SerialError, match="bt://AA:BB:CC:DD:EE:FF"):
        await SerialPort("bt://nonsense").open()
    monkeypatch.setattr("neoaprs.btserial.available", lambda: False)
    with pytest.raises(SerialError, match="COM port"):
        await SerialPort(URL).open()


def test_the_port_class_is_the_socket_port_of_pyserial() -> None:
    ser = BluetoothSerial(None, baudrate=9600, timeout=0.1)
    ser.port = URL
    assert not ser.is_open and ser.portstr == URL and ser.dtr is not None


# ---- the link is lost, and found again

async def test_a_device_that_goes_away_drops_the_line(device: FakeBluetooth) -> None:
    reasons: list[str] = []
    port = SerialPort(f"{URL}/2")
    port.dropped.connect(reasons.append)
    await port.open()
    await device.connected()
    device.drop()
    await until(lambda: bool(reasons))
    assert not port.is_open and "disconnected" in reasons[0]


async def test_the_tnc_opens_a_bluetooth_port_again_when_the_radio_comes_back(device: FakeBluetooth) -> None:
    tnc = Tnc(f"{URL}/2", profile=KISS, backoff=Backoff([0.05, 0.05]), fallback_probe=False, check_sec=0.0, settle_sec=0.0)
    await tnc.start()
    try:
        assert tnc.state is Source.State.CONNECTED and tnc.stats.opens == 1
        assert "9600" not in tnc.describe() and tnc.describe().startswith(f"{URL}/2,")        # (a Bluetooth link has no speed)
        await device.connected()
        device.fail(OSError(errno.EHOSTDOWN, "Host is down"))            # switched off
        device.drop()
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc.last_error and "lost" in tnc.last_error
        await until(lambda: len(device.connects) >= 3 and "Host is down" in tnc.problem)       # tried again, and the radio said why not
        device.fail(None)                                               # switched on, in range
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.stats.opens == 2)
        await device.connected()
        device.feed(encode(ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA-7"), (), info=b"!6010.00N/02456.00E>hi")), port=0))
        await until(lambda: tnc.stats.frames_in == 1)
    finally:
        await tnc.stop()
    assert tnc.state is Source.State.STOPPED and device.connects[-1] == (ADDRESS, 2)


async def test_the_search_for_the_radio_does_not_look_at_bluetooth(device: FakeBluetooth, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[list[str]] = []
    monkeypatch.setattr(btpaired, "_run", lambda command: asked.append(command) or "")
    tnc = Tnc(pattern=str(tmp_path / "*"), backoff=Backoff([30.0]), fallback_probe=True)
    await tnc.start()
    try:
        assert tnc.state is Source.State.WAITING
    finally:
        await tnc.stop()
    assert asked == [] and device.connects == [] and device.sdp_connects == []


# ---- the paired devices

def prop(kind: str, data: object) -> dict[str, object]:
    return {"type": kind, "data": data}


def device_object(address: str, name: str, *, paired: bool = True, uuids: list[str] | None = None, alias: str | None = None) -> dict[str, dict[str, object]]:
    props: dict[str, object] = {"Address": prop("s", address), "Name": prop("s", name), "Alias": prop("s", alias or name), "Paired": prop("b", paired), "Connected": prop("b", False)}
    if uuids is not None:
        props["UUIDs"] = prop("as", uuids)
    return {"org.bluez.Device1": props, "org.freedesktop.DBus.Properties": {}}


SPP, HEADSET, GATT = "00001101-0000-1000-8000-00805f9b34fb", "0000111e-0000-1000-8000-00805f9b34fb", "0000180f-0000-1000-8000-00805f9b34fb"


def busctl_output() -> str:
    """What `busctl --system --json=short call org.bluez / org.freedesktop.DBus.ObjectManager GetManagedObjects` prints, for a machine with an adapter and five devices."""
    objects = {
        "/org/bluez": {"org.bluez.AgentManager1": {}},
        "/org/bluez/hci0": {"org.bluez.Adapter1": {"Address": prop("s", "80:00:00:00:00:01")}},
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01": device_object("AA:BB:CC:DD:EE:01", "TH-D74", uuids=[SPP.upper(), HEADSET]),
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_02": device_object("AA:BB:CC:DD:EE:02", "Mobilinkd TNC3", uuids=[SPP]),
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_03": device_object("AA:BB:CC:DD:EE:03", "Headset", uuids=[HEADSET]),
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_04": device_object("AA:BB:CC:DD:EE:04", "Seen but not paired", paired=False, uuids=[SPP]),
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_05": device_object("AA:BB:CC:DD:EE:05", "Sensor", uuids=[GATT]),
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_06": device_object("AA:BB:CC:DD:EE:06", "Not yet resolved"),
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_07": device_object("AA:BB:CC:DD:EE:07", "", uuids=[SPP], alias="AA-BB-CC-DD-EE-07"),
    }
    return json.dumps({"type": "a{oa{sa{sv}}}", "data": [objects]})


def test_the_paired_devices_with_a_serial_port_come_from_the_words_of_bluez() -> None:
    found = btpaired.from_busctl(busctl_output())
    assert [(d.address, d.name) for d in found] == [
        ("AA:BB:CC:DD:EE:01", "TH-D74"), ("AA:BB:CC:DD:EE:02", "Mobilinkd TNC3"), ("AA:BB:CC:DD:EE:06", "Not yet resolved"), ("AA:BB:CC:DD:EE:07", "")]


@pytest.mark.parametrize("output", ["", "not json", "{}", '{"data": []}', '{"data": [3]}', '{"data": [{"/x": 3}]}', '{"data": [{"/x": {"org.bluez.Device1": 3}}]}'])
def test_an_answer_that_is_not_the_list_gives_no_devices(output: str) -> None:
    assert btpaired.from_busctl(output) == []


def test_bluetoothctl_lines_are_the_fallback() -> None:
    text = "Device aa:bb:cc:dd:ee:01 TH-D74\nDevice AA:BB:CC:DD:EE:02 Mobilinkd TNC3\nDevice AA:BB:CC:DD:EE:03\nNEW Device x y\n\nnonsense\n"
    assert [(d.address, d.name) for d in btpaired.from_bluetoothctl(text)] == [("AA:BB:CC:DD:EE:01", "TH-D74"), ("AA:BB:CC:DD:EE:02", "Mobilinkd TNC3"), ("AA:BB:CC:DD:EE:03", "")]


def test_the_devices_are_asked_for_with_busctl_and_by_bluetoothctl_where_there_is_no_busctl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(btpaired.sys, "platform", "linux")
    asked: list[str] = []

    def run(command: list[str]) -> str:
        asked.append(command[0])
        return busctl_output() if command[0] == "busctl" else "Device AA:BB:CC:DD:EE:09 Fallback\n"

    assert [d.name for d in btpaired.paired_devices(run)] == ["", "Mobilinkd TNC3", "Not yet resolved", "TH-D74"] and asked == ["busctl"]
    asked.clear()
    assert [d.name for d in btpaired.paired_devices(lambda c: "" if c[0] == "busctl" or asked.append(c[0]) else "")] == []
    assert asked == ["bluetoothctl"]
    assert [d.address for d in btpaired.paired_devices(lambda c: "Device AA:BB:CC:DD:EE:09 Fallback\n" if c[0] == "bluetoothctl" else "")] == ["AA:BB:CC:DD:EE:09"]


def test_no_devices_where_there_is_no_bluez_and_none_on_other_systems(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(btpaired.sys, "platform", "linux")
    assert btpaired.paired_devices(lambda command: "") == []
    monkeypatch.setattr(btpaired.sys, "platform", "win32")
    assert btpaired.paired_devices(lambda command: pytest.fail("asked")) == []


def test_the_tests_do_not_ask_bluez_unless_they_say_so() -> None:
    assert btpaired.paired_devices() == []


def test_a_command_that_is_missing_or_fails_gives_nothing() -> None:
    assert REAL_RUN(["neoaprs-no-such-command-anywhere"]) == ""
    assert REAL_RUN([sys.executable, "-c", "raise SystemExit(3)"]) == ""
    assert REAL_RUN([sys.executable, "-c", "print('x')"]).strip() == "x"


def test_the_port_list_names_them_bt_and_the_name_of_the_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(btpaired.sys, "platform", "linux")
    monkeypatch.setattr(btpaired, "_run", lambda command: busctl_output())
    ports = serialprobe.paired_bluetooth_ports()
    assert [(p.device, p.description) for p in ports] == [
        ("bt://AA:BB:CC:DD:EE:07", "Bluetooth device"), ("bt://AA:BB:CC:DD:EE:02", "Bluetooth: Mobilinkd TNC3"), ("bt://AA:BB:CC:DD:EE:06", "Bluetooth: Not yet resolved"), ("bt://AA:BB:CC:DD:EE:01", "Bluetooth: TH-D74")]
    assert all(p.hwid == "" and p.vid is None and p.pid is None for p in ports)


def test_listing_never_makes_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The list is read from BlueZ's records: a device is not connected to, nor asked, to be listed."""
    monkeypatch.setattr(btpaired.sys, "platform", "linux")
    monkeypatch.setattr(btpaired, "_run", lambda command: busctl_output())
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("a socket was made to list the devices"))
    assert len(serialprobe.paired_bluetooth_ports()) == 4
