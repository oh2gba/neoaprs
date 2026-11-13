"""The address of a port (serial/port, serial/last_port, gps/device): a device path, or one of the four forms the program means. pyserial knows more schemes, one of which (`spy://`) writes a file of the sender's
choice the moment the port object is made, so the others are refused in the setting and again where the port is made."""
from dataclasses import replace
from pathlib import Path

import pytest
import serial  # type: ignore[import-untyped]

from neoaprs import nodevices, serialport
from neoaprs.config import DEFAULTS, Config, SettingError
from neoaprs.serialport import SerialError, SerialPort

KEYS = ("serial/port", "serial/last_port", "gps/device")
ATTRS = {"serial/port": "serial_port", "serial/last_port": "serial_last_port", "gps/device": "gps_device"}
REFUSED = ("spy:///dev/ttyUSB0?file={file}", "alt://socket://127.0.0.1:1", "loop://", "rfc2217://127.0.0.1:2217", "hwgrep://0403", "cp2110://0001:0002:00", "SPY:///dev/null?file={file}", " spy:///dev/null?file={file}",
           "unknown://x", "/dev/ttyUSB0?x://y", "://x")
ACCEPTED = ("", "/dev/ttyUSB0", "/dev/serial/by-id/usb-FTDI_FT232R-if00-port0", "COM3", r"\\.\COM12", "socket://127.0.0.1:8001", "tcp://127.0.0.1:8001", "TCP://localhost:8100", "bt://AA:BB:CC:DD:EE:FF",
            "ble://AA:BB:CC:DD:EE:FF", "socket://[::1]:8001")


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("address", REFUSED)
def test_a_scheme_the_program_does_not_mean_is_refused_when_the_setting_is_saved(key: str, address: str, tmp_path: Path) -> None:
    text = address.format(file=tmp_path / "victim")
    with pytest.raises(SettingError) as e:
        Config.check(key, text)
    assert (e.value.key, e.value.code) == (key, "setting.not_host") and e.value.params == {"value": text.strip()}
    with pytest.raises(SettingError):
        Config.checked(DEFAULTS, {key: text})
    assert not (tmp_path / "victim").exists()


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("address", ACCEPTED)
def test_a_device_path_and_the_four_forms_are_kept_as_they_were(key: str, address: str) -> None:
    assert Config.check(key, address) == address and getattr(Config.checked(DEFAULTS, {key: f"  {address}  "}), ATTRS[key]) == address


@pytest.mark.parametrize("key", KEYS)
def test_a_stored_address_that_is_refused_now_leaves_the_daemon_starting_with_the_default(key: str, caplog: pytest.LogCaptureFixture) -> None:
    config = Config.from_data({key: "spy:///dev/ttyUSB0?file=/tmp/x", "station/call": "OH2GBA"})
    assert getattr(config, ATTRS[key]) == "" and config.station_call == "OH2GBA" and key in caplog.text


@pytest.mark.parametrize("address", REFUSED)
def test_the_port_is_not_made_for_a_scheme_the_program_does_not_mean(address: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = address.format(file=tmp_path / "victim")
    made: list[str] = []
    monkeypatch.setattr(serial, "serial_for_url", lambda url, **kw: made.append(url))
    with pytest.raises(ValueError, match="is not an address or a name"):
        serialport._build(text, 9600)
    assert made == [] and not (tmp_path / "victim").exists()


@pytest.mark.parametrize("address", REFUSED)
async def test_opening_such_a_port_fails_with_the_reason_and_makes_no_file(address: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nodevices, "check_port", lambda path, level=0: None)         # (the guard of the tests would refuse first: the check under test is the adapter's own)
    text = address.format(file=tmp_path / "victim")
    port = SerialPort(text)
    with pytest.raises(SerialError, match="is not an address or a name"):
        await port.open()
    assert not port.is_open and not (tmp_path / "victim").exists() and list(tmp_path.iterdir()) == []


def test_the_accepted_forms_are_built_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    assert serialport._build("socket://127.0.0.1:8001", 9600).port == "socket://127.0.0.1:8001"
    assert serialport._build("tcp://127.0.0.1:8001", 9600).port == "socket://127.0.0.1:8001"
    assert serialport._build("bt://AA:BB:CC:DD:EE:FF", 9600).port == "bt://AA:BB:CC:DD:EE:FF" and serialport._build("ble://AA:BB:CC:DD:EE:FF", 9600).port == "ble://AA:BB:CC:DD:EE:FF"
    assert serialport._build("/dev/ttyUSB0", 9600).port == "/dev/ttyUSB0"


def test_the_default_config_has_no_port() -> None:
    assert replace(DEFAULTS).serial_port == "" == DEFAULTS.gps_device == DEFAULTS.serial_last_port
