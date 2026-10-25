"""The Bluetooth LE KISS port (neoaprs/btle.py) on a fake bleak and a fake device (tests/support/fakeble.py): the address and profile of a `ble://` port, the search of the device's services, reading with the timeout, writing in pieces,
a link that is lost, the library that is not installed, and the TNC that uses the port. No scan is made and no radio is touched."""
import sys
import threading
import time

import pytest

from neoaprs import ax25, btle, serialport
from neoaprs.btle import BleSerial, is_ble, parse_url, profile_for
from neoaprs.kiss import KissDecoder, encode
from neoaprs.serialholders import held_by, port_key
from neoaprs.serialport import SerialError, SerialPort, is_socket, is_url
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from tests.support.env import until
from tests.support.fakeble import ADDRESS, KISS_SERVICE, MOBILINKD, MOBILINKD_NOTIFY, MOBILINKD_WRITE, NUS_NOTIFY, UART_SERVICE, FakeBle, FakeBleakError

URL = f"ble://{ADDRESS}"


def ble_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("ble ") and t.is_alive()]


def opened(url: str = URL, timeout: float = 0.2) -> BleSerial:
    ser = BleSerial(None, timeout=timeout, write_timeout=2.0)
    ser.port = url
    ser.open()
    return ser


# ---- the address and the profile

@pytest.mark.parametrize("url,address,profile", [
    ("ble://00:11:22:33:44:55", "00:11:22:33:44:55", None),
    ("ble://aa:bb:cc:dd:ee:ff/", "AA:BB:CC:DD:EE:FF", None),
    ("  BLE://AA-BB-CC-DD-EE-FF/nus ", "AA:BB:CC:DD:EE:FF", "nus"),
    ("ble://AA:BB:CC:DD:EE:FF/Mobilinkd", "AA:BB:CC:DD:EE:FF", "mobilinkd"),
    ("ble://6e6c9c1a-0e5d-4a3b-9d6c-0123456789ab", "6E6C9C1A-0E5D-4A3B-9D6C-0123456789AB", None),          # (macOS gives a device a UUID in place of an address)
])
def test_the_address_and_the_profile_of_a_port(url: str, address: str, profile: str | None) -> None:
    got_address, got_profile = parse_url(url)
    assert got_address == address and (got_profile.name if got_profile else None) == profile


def test_a_service_uuid_names_a_service_of_no_known_profile() -> None:
    long = profile_for("0000FFE0-0000-1000-8000-00805F9B34FB")
    assert (long.name, long.service, long.write, long.notify) == ("custom", "0000ffe0-0000-1000-8000-00805f9b34fb", None, None)
    assert profile_for("ffe0").service == long.service


@pytest.mark.parametrize("url", ["ble://", "ble://AA:BB", "ble://AA:BB:CC:DD:EE:GG", "ble://AABBCCDDEEFF", "ble://AA:BB:CC:DD:EE:FF/nonsense", "ble://AA:BB:CC:DD:EE:FF/nus/2", "bt://AA:BB:CC:DD:EE:FF", "socket://h:1"])
def test_an_address_that_is_wrong_is_said_in_words(url: str) -> None:
    with pytest.raises(ValueError, match="ble://AA:BB:CC:DD:EE:FF|neither a BLE KISS profile"):
        parse_url(url)


def test_a_ble_port_is_a_url_without_a_speed_and_without_a_device_file() -> None:
    assert is_ble(URL) and is_ble(" BLE://x") and not is_ble("bt://AA:BB:CC:DD:EE:FF") and not is_ble("/dev/ttyUSB0")
    assert is_url(URL) and is_socket(URL) and port_key(URL) == URL.lower() and held_by(URL) == ""
    assert isinstance(serialport._build(URL, 9600), BleSerial)


# ---- the library that is not installed

def test_without_bleak_the_open_says_which_extra_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "bleak", None)               # (an import of it fails)
    with pytest.raises(OSError, match=r"pip install 'neoaprs\[ble\]'.*uv tool install 'neoaprs\[ble\]'"):
        btle.import_bleak()
    with pytest.raises(Exception, match=r"Could not open port ble://.*pip install 'neoaprs\[ble\]'"):
        opened()
    assert ble_threads() == []


async def test_the_line_says_it_in_the_same_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "bleak", None)
    with pytest.raises(SerialError, match=r"neoaprs\[ble\]"):
        await SerialPort(URL).open()


def test_the_library_that_is_installed_has_what_the_port_asks_of_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "bleak")                     # (the guard's stand-in goes; the real library is only looked at, never scanned with)
    bleak = pytest.importorskip("bleak")                          # (the extra `ble`)
    assert callable(bleak.BleakScanner.find_device_by_address) and issubclass(bleak.BleakError, Exception)
    for name in ("connect", "disconnect", "start_notify", "write_gatt_char"):
        assert callable(getattr(bleak.BleakClient, name)), name
    for name in ("services", "mtu_size", "is_connected"):
        assert isinstance(getattr(bleak.BleakClient, name), property), name


# ---- the profile search

def test_the_kiss_service_is_found_and_listened_to_and_the_log_says_so(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="neoaprs.btle")
    ble = FakeBle(monkeypatch)
    ser = opened()
    try:
        assert ser.is_open and ble.notifying == MOBILINKD_NOTIFY and ble.scans == [ADDRESS] and ble.connects == 1
        assert f"{ADDRESS}: connected, using the BLE KISS service of the Mobilinkd TNC3 and TNC4 and the aprs.fi apps (none was named)" in caplog.text
    finally:
        ser.close()


def test_the_nordic_uart_service_is_the_next_the_search_tries(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="neoaprs.btle")
    ble = FakeBle(monkeypatch, UART_SERVICE)
    ser = opened()
    try:
        assert ble.notifying == NUS_NOTIFY and "using the Nordic UART Service (none was named)" in caplog.text
        ser.write(b"x")
        assert ble.writes == [(b"x", False)], "(a characteristic that takes both kinds is written without a response)"
    finally:
        ser.close()


def test_a_device_with_both_services_is_used_by_the_first_profile_and_the_one_named_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch, {**UART_SERVICE, **KISS_SERVICE})
    ser = opened()
    assert ble.notifying == MOBILINKD_NOTIFY
    ser.close()
    ser = opened(f"{URL}/nus")
    try:
        assert ble.notifying == NUS_NOTIFY
    finally:
        ser.close()


def test_a_profile_that_is_named_is_the_only_one_tried(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch, KISS_SERVICE)
    with pytest.raises(Exception, match=r"Could not open port .*nus.*no Nordic UART Service.*its services: 00000001-ba2a"):
        opened(f"{URL}/nus")
    assert ble.disconnects == 1 and ble.notifying is None, "(nothing is left connected)"
    assert ble_threads() == []


def test_a_device_with_no_kiss_service_lists_what_it_has(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch, {"0000180f-0000-1000-8000-00805f9b34fb": [("00002a19-0000-1000-8000-00805f9b34fb", ["read", "notify"])]})
    with pytest.raises(Exception, match=r"no BLE KISS service.*its services: 0000180f"):
        opened()
    assert ble.disconnects == 1


def test_a_service_named_by_its_uuid_is_used_by_what_its_characteristics_can_do(monkeypatch: pytest.MonkeyPatch) -> None:
    uart = {"0000ffe0-0000-1000-8000-00805f9b34fb": [("0000ffe1-0000-1000-8000-00805f9b34fb", ["read", "write-without-response", "notify"])]}     # (an HM-10 module: one characteristic for both ways)
    ble = FakeBle(monkeypatch, uart)
    ser = opened(f"{URL}/ffe0")
    try:
        ser.write(b"hi")
        ble.feed(b"there")
        assert ser.read(5) == b"there" and ble.writes == [(b"hi", False)] and ble.notifying == "0000ffe1-0000-1000-8000-00805f9b34fb"
    finally:
        ser.close()


def test_a_service_of_a_profile_without_its_characteristics_is_not_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch, {MOBILINKD: [(MOBILINKD_WRITE, ["write-without-response"])]})
    with pytest.raises(Exception, match="no BLE KISS service"):
        opened()
    assert ble.disconnects == 1


# ---- open

def test_a_device_the_scan_does_not_find_is_out_of_reach(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ble.seen = False
    with pytest.raises(Exception, match=r"Could not open port ble://.*does not answer \(is it switched on, in range and not connected to a phone\?\)"):
        opened()
    assert ble.connects == 0 and ble_threads() == []


def test_a_connection_that_fails_says_what_bleak_said(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ble.connect_error = FakeBleakError("Device with address 00:11:22:33:44:55 was not found")
    with pytest.raises(Exception, match="was not found"):
        opened()
    ble.connect_error = TimeoutError()
    with pytest.raises(Exception, match="does not answer"):
        opened()
    assert ble_threads() == []


def test_a_port_is_opened_once_and_needs_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeBle(monkeypatch)
    with pytest.raises(Exception, match="configured"):
        BleSerial(None).open()
    ser = opened()
    try:
        with pytest.raises(Exception, match="already open"):
            ser.open()
    finally:
        ser.close()


# ---- read

def test_what_the_device_notifies_is_read_in_the_order_it_came(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ser = opened()
    try:
        ble.feed(b"abc")
        ble.feed(b"def")
        deadline = time.monotonic() + 5
        while ser.in_waiting < 6 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ser.in_waiting == 6
        assert ser.read(4) == b"abcd" and ser.in_waiting == 2 and ser.read(10) == b"ef", "(read ends with the time, not with the size)"
    finally:
        ser.close()


def test_a_read_waits_for_the_timeout_and_returns_what_there_is(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeBle(monkeypatch)
    ser = opened(timeout=0.15)
    try:
        started = time.monotonic()
        assert ser.read(1) == b"" and 0.1 <= time.monotonic() - started < 2.0
        ser.timeout = 0
        started = time.monotonic()
        assert ser.read(1) == b"" and time.monotonic() - started < 0.1, "(no timeout: no wait)"
    finally:
        ser.close()


def test_a_read_returns_as_soon_as_the_bytes_are_there(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ser = opened(timeout=10.0)
    try:
        threading.Timer(0.05, ble.feed, args=(b"xy",)).start()
        started = time.monotonic()
        assert ser.read(2) == b"xy" and time.monotonic() - started < 5.0
    finally:
        ser.close()


def test_cancel_read_ends_a_read_that_is_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeBle(monkeypatch)
    ser = opened(timeout=30.0)
    try:
        threading.Timer(0.05, ser.cancel_read).start()
        started = time.monotonic()
        assert ser.read(1) == b"" and time.monotonic() - started < 5.0
    finally:
        ser.close()


# ---- write

def test_a_write_is_cut_to_what_the_link_takes_and_is_without_a_response_where_the_characteristic_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch, chunk=20)
    ser = opened()
    try:
        data = bytes(range(45))
        assert ser.write(data) == 45
        assert ble.writes == [(data[:20], False), (data[20:40], False), (data[40:], False)]
        ble.writes.clear()
        ble.services[0].characteristics[0].max_write_without_response_size = 100            # (the link has settled on a longer MTU)
        ser.write(bytes(250))
        assert [len(w) for w, _ in ble.writes] == [100, 100, 50]
    finally:
        ser.close()


def test_a_characteristic_that_wants_a_response_is_written_with_one_in_pieces_of_the_mtu(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch, {MOBILINKD: [(MOBILINKD_WRITE, ["write"]), (MOBILINKD_NOTIFY, ["notify"])]}, mtu=247)
    ser = opened()
    try:
        ser.write(bytes(500))
        assert [(len(w), r) for w, r in ble.writes] == [(244, True), (244, True), (12, True)]
        ble.writes.clear()
        ble.mtu = 23
        ser.write(bytes(30))
        assert [len(w) for w, _ in ble.writes] == [20, 10], "(the smallest piece any link takes)"
    finally:
        ser.close()


def test_a_write_that_does_not_come_back_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ble.hold_writes = True
    ser = BleSerial(None, timeout=0.1, write_timeout=0.2)
    ser.port = URL
    ser.open()
    try:
        with pytest.raises(Exception, match="Write timeout"):
            ser.write(b"x")
    finally:
        ble.hold_writes = False
        ser.close()


def test_a_write_that_fails_is_an_error_and_the_link_is_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ser = opened()
    try:
        ble.write_error = FakeBleakError("GATT write failed")
        with pytest.raises(Exception, match="BLE write failed: GATT write failed"):
            ser.write(b"x")
        with pytest.raises(Exception, match="BLE link lost: GATT write failed"):
            ser.read(1)
    finally:
        ser.close()


# ---- the link is lost

def test_a_device_that_goes_away_raises_in_the_read_after_what_it_sent_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ser = opened(timeout=5.0)
    try:
        ble.feed(b"last")
        ble.drop()
        assert ser.read(4) == b"last"
        with pytest.raises(Exception, match="BLE link lost: the device disconnected"):
            ser.read(1)
        with pytest.raises(Exception, match="BLE link lost"):
            ser.write(b"x")
    finally:
        ser.close()


def test_closing_disconnects_and_ends_the_thread_and_a_closed_port_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ser = opened()
    assert len(ble_threads()) == 1
    ser.close()
    ser.close()
    assert ble.disconnects == 1 and ble_threads() == [] and not ser.is_open
    for call in (lambda: ser.read(1), lambda: ser.write(b"x"), lambda: ser.in_waiting):
        with pytest.raises(Exception, match="Attempting to use a port that is not open"):
            call()


# ---- as the line of the TNC

async def test_the_line_carries_kiss_both_ways(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    chunks: list[bytes] = []
    port = SerialPort(URL, 9600)
    port.data.connect(chunks.append)
    await port.open()
    try:
        frame = encode(b"hello", port=0)
        ble.feed(frame[:4])
        ble.feed(frame[4:])
        await until(lambda: b"".join(chunks) == frame)
        assert KissDecoder().feed(b"".join(chunks))[0].payload == b"hello"
        port.write(frame)
        await until(lambda: b"".join(w for w, _ in ble.writes) == frame)
    finally:
        port.close()
    await until(lambda: ble_threads() == [])
    assert not port.is_open and ble.disconnects == 1


async def test_the_line_is_dropped_when_the_device_goes_away(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    reasons: list[str] = []
    port = SerialPort(URL)
    port.dropped.connect(reasons.append)
    await port.open()
    ble.drop()
    await until(lambda: bool(reasons))
    assert not port.is_open and "disconnected" in reasons[0]
    await until(lambda: ble_threads() == [])


async def test_an_open_that_fails_is_a_serial_error_with_the_port_in_it(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    ble.seen = False
    with pytest.raises(SerialError, match=r"ble://00:11:22:33:44:55: Could not open port .*does not answer"):
        await SerialPort(URL).open()
    with pytest.raises(SerialError, match="ble://AA:BB:CC:DD:EE:FF"):
        await SerialPort("ble://nonsense").open()


async def test_the_tnc_opens_a_ble_port_again_when_the_radio_comes_back(monkeypatch: pytest.MonkeyPatch) -> None:
    ble = FakeBle(monkeypatch)
    tnc = Tnc(URL, profile=KISS, backoff=Backoff([0.05, 0.05]), fallback_probe=False, check_sec=0.0, settle_sec=0.0)
    await tnc.start()
    try:
        assert tnc.state is Source.State.CONNECTED and tnc.stats.opens == 1
        assert "9600" not in tnc.describe() and tnc.describe().startswith(f"{URL},")                    # (a BLE link has no speed)
        ble.feed(encode(ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA-7"), (), info=b"!6010.00N/02456.00E>hi")), port=0))
        await until(lambda: tnc.stats.frames_in == 1)
        ble.seen = False                                                 # switched off
        ble.drop()
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc.last_error and "lost" in tnc.last_error
        await until(lambda: len(ble.scans) >= 3 and "does not answer" in tnc.problem)
        ble.seen = True                                                  # switched on, in range
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.stats.opens == 2)
        raw = ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA-7"), (), info=b"!6010.00N/02456.00E>back"))
        assert await tnc.send(raw) is True
        await until(lambda: b"".join(w for w, _ in ble.writes).endswith(encode(raw, port=0)))
    finally:
        await tnc.stop()
    assert tnc.state is Source.State.STOPPED
    await until(lambda: ble_threads() == [])
