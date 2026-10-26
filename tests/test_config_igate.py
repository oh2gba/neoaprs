"""The settings of the receive-only iGate (`igate/enabled`, `igate/server`, `igate/password`): their defaults, what each accepts and refuses with the code the page goes by, the address, and a password that is in no line of the log."""
import logging

import pytest

from neoaprs.config import DEFAULTS, KEYS, Config, SettingError


def refused(key: str, text: str) -> SettingError:
    with pytest.raises(SettingError) as raised:
        Config.check(key, text)
    return raised.value


def test_the_igate_is_off_with_the_round_robin_server_and_no_passcode() -> None:
    assert (DEFAULTS.igate_enabled, DEFAULTS.igate_server, DEFAULTS.igate_password) == (False, "rotate.aprs2.net:14580", "")
    assert DEFAULTS.igate_address == ("rotate.aprs2.net", 14580)
    assert [k for k in KEYS if k.startswith("igate/")] == ["igate/enabled", "igate/server", "igate/password"]


@pytest.mark.parametrize(("text", "stored"), [("19628", "19628"), (" 19628 ", "19628"), ("0", "0"), ("32767", "32767"), ("00123", "123"), ("", "")])
def test_a_passcode_is_digits_up_to_15_bits(text: str, stored: str) -> None:
    assert Config.check("igate/password", text) == stored
    assert Config.from_data({"igate/password": text}).igate_password == stored


@pytest.mark.parametrize("text", ["abc", "32768", "12 34", "1.5", "+5", "٣٤٥", "0x10", "19628a"])
def test_a_passcode_that_is_not_one_is_refused_with_its_code_and_without_the_text(text: str) -> None:
    error = refused("igate/password", text)
    assert error.key == "igate/password" and error.code == "setting.not_passcode" and error.params == {"max": 32767}
    assert text not in str(error), "(the sentence does not repeat what was typed: it may be a password)"


def test_the_passcode_that_only_reads_is_refused_for_an_igate() -> None:
    error = refused("igate/password", "-1")
    assert error.code == "setting.passcode_read_only" and error.key == "igate/password"


@pytest.mark.parametrize(("text", "address"), [("rotate.aprs2.net:14580", ("rotate.aprs2.net", 14580)), ("euro.aprs2.net:10152", ("euro.aprs2.net", 10152)), ("127.0.0.1:1", ("127.0.0.1", 1)), ("[::1]:14580", ("::1", 14580))])
def test_a_server_is_host_and_port(text: str, address: tuple[str, int]) -> None:
    assert Config.check("igate/server", text) == text
    assert Config.from_data({"igate/server": text}).igate_address == address


def test_an_empty_server_is_a_valid_setting_with_no_address() -> None:
    assert Config.check("igate/server", "") == ""
    assert Config.from_data({"igate/server": ""}).igate_address is None


@pytest.mark.parametrize("text", ["rotate.aprs2.net", ":14580", "host:0", "host:65536", "host:x", "two words:14580", "[]:1"])
def test_a_server_that_is_not_host_and_port_is_refused(text: str) -> None:
    error = refused("igate/server", text)
    assert error.code == "setting.not_server" and error.key == "igate/server" and error.params == {"value": text}


def test_the_switch_is_true_or_false() -> None:
    assert Config.check("igate/enabled", " TRUE ") == "true" and Config.from_data({"igate/enabled": "true"}).igate_enabled is True
    assert refused("igate/enabled", "maybe").code == "setting.not_boolean"


def test_a_passcode_that_is_wrong_in_the_database_is_not_written_to_the_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    config = Config.from_data({"igate/password": "hunter2-secret"})
    assert config.igate_password == "" and caplog.records, "(the default is used, and it is said)"
    assert "hunter2-secret" not in caplog.text
    caplog.clear()
    Config.from_data({"igate/password": "-1"})
    assert "igate/password" in caplog.text


def test_the_settings_are_written_back_as_they_were_read() -> None:
    c = Config.from_data({"igate/enabled": "true", "igate/server": "euro.aprs2.net:14580", "igate/password": "19628"})
    assert Config.from_data(c.to_data()) == c and c.to_data()["igate/password"] == "19628"
