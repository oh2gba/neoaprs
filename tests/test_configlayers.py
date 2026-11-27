"""Tests for the map layer settings (neoaprs/configlayers.py): `map/aircraft`, `map/aircraft_host`,
`map/ships` and `map/ships_host`, their validation, defaults, and form place.
"""

import json
from pathlib import Path

import pytest

from neoaprs import nodevices
from neoaprs.coded import CodedError
from neoaprs.config import DEFAULTS, KEYS, Config, SettingError
from neoaprs.configlayers import LAYER_ROWS, ais_address, ais_host_port, receiver_address
from neoaprs.web import access as web_access
from neoaprs.web.access import LOCAL_ONLY
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.env import Env

LAYER_KEYS = ("map/aircraft", "map/aircraft_host", "map/ships", "map/ships_host", "map/ships_key")
KEY = "k7m2-x9pq-4hrt"


def test_the_five_settings_come_straight_after_the_maps_source_with_their_defaults() -> None:
    at = KEYS.index("map/source")
    assert KEYS[at + 1 : at + 6] == LAYER_KEYS == tuple(key for _attr, key, _parse in LAYER_ROWS)
    assert {key: DEFAULTS.to_data()[key] for key in LAYER_KEYS} == {
        "map/aircraft": "none",
        "map/aircraft_host": "",
        "map/ships": "none",
        "map/ships_host": "",
        "map/ships_key": "",
    }
    assert (DEFAULTS.map_aircraft, DEFAULTS.map_aircraft_host, DEFAULTS.map_ships, DEFAULTS.map_ships_host) == (
        "none",
        "",
        "none",
        "",
    )


@pytest.mark.parametrize(
    ("key", "words"),
    [
        ("map/aircraft", ("none", "adsbfi", "adsblol", "radarcape", "receiver")),
        ("map/ships", ("none", "fintraffic", "aisstream", "receiver")),
    ],
)
def test_a_source_is_one_of_its_layers_words_in_any_case(key: str, words: tuple[str, ...]) -> None:
    for word in words:
        assert Config.check(key, f" {word.upper()} ") == word
    for wrong in ("", "adsb.fi", "fintraffic" if key == "map/aircraft" else "adsbfi", "on"):
        with pytest.raises(SettingError) as refused:
            Config.check(key, wrong)
        assert (refused.value.key, refused.value.code) == (key, "setting.not_among")


@pytest.mark.parametrize(
    "text",
    [
        "192.168.1.20",
        "pi.local",
        "[fe80::1]",
        "pi.local:8080",
        "192.168.1.20:30005",
        "[fe80::1]:8080",
        "adsb_feeder",
        "http://pi.local/tar1090/data/aircraft.json",
        "https://192.168.1.20:8443/data/aircraft.json",
    ],
)
def test_an_aircraft_receivers_address_is_a_host_a_host_and_port_or_a_whole_web_address_kept_as_typed(
    text: str,
) -> None:
    assert receiver_address(f"  {text} ") == text
    assert Config.check("map/aircraft_host", text) == text


@pytest.mark.parametrize(
    "text",
    [
        "fe80::1",
        "pi local",
        "pi.local:",
        "pi.local:0",
        "pi.local:65536",
        "pi.local:http",
        "ftp://pi.local/x",
        "http://",
        "http:///data",
        "file:///etc/passwd",
        "-help",
        "pi..local",
        "http://pi.local:99999/",
        "a\tb",
        "x" * 501,
        "pi.local/data",
        "pi.local:\u0663\u0660",
        "pi.local:\uff18\uff10",
    ],
)
def test_anything_else_is_not_the_address_of_a_receiver(text: str) -> None:
    with pytest.raises(CodedError) as refused:
        receiver_address(text)
    assert (refused.value.code, refused.value.params) == ("setting.not_receiver", {"value": text})
    with pytest.raises(SettingError) as said:
        Config.check("map/aircraft_host", text)
    assert (said.value.key, said.value.code) == ("map/aircraft_host", "setting.not_receiver")


@pytest.mark.parametrize(
    "text", ["192.168.1.20", "ais.local", "[fe80::1]", "ais.local:10110", "192.168.1.20:2000", "[fe80::1]:1"]
)
def test_an_ais_receivers_address_is_a_host_or_a_host_and_port(text: str) -> None:
    assert ais_address(f" {text}  ") == text
    assert Config.check("map/ships_host", text) == text


@pytest.mark.parametrize(
    "text",
    [
        "http://ais.local:10110",
        "tcp://ais.local",
        "ais.local:0",
        "ais.local:65536",
        "ais.local:",
        "fe80::1",
        "ais local",
        "x" * 501,
        "ais.local:\uff11\uff10",
    ],
)
def test_a_web_address_or_a_wrong_port_is_not_the_address_of_an_ais_receiver(text: str) -> None:
    with pytest.raises(SettingError) as refused:
        Config.check("map/ships_host", text)
    assert (refused.value.key, refused.value.code, refused.value.params) == (
        "map/ships_host",
        "setting.not_receiver",
        {"value": text},
    )


@pytest.mark.parametrize(
    ("text", "pair"),
    [
        ("", ("127.0.0.1", 10110)),
        ("ais.local", ("ais.local", 10110)),
        ("192.168.1.20:2000", ("192.168.1.20", 2000)),
        ("[fe80::1]", ("fe80::1", 10110)),
        ("[fe80::1]:1", ("fe80::1", 1)),
    ],
)
def test_an_ais_receivers_address_is_connected_to_at_its_host_and_port_and_at_10110_when_none_is_given(
    text: str, pair: tuple[str, int]
) -> None:
    assert ais_host_port(ais_address(text)) == pair


def test_an_empty_address_is_this_computer_and_is_kept_empty() -> None:
    assert receiver_address("") == receiver_address("   ") == ais_address("") == ""
    assert Config.check("map/aircraft_host", "") == Config.check("map/ships_host", " ") == ""


def test_a_stored_value_is_read_back_and_a_wrong_one_falls_back_to_its_default() -> None:
    rows = {
        "map/aircraft": "receiver",
        "map/aircraft_host": "pi.local:8080",
        "map/ships": "fintraffic",
        "map/ships_host": "ais.local",
        "map/ships_key": "0123456789abcdef0123456789abcdef01234567",
    }
    config = Config.from_data(rows)
    assert (config.map_aircraft, config.map_aircraft_host, config.map_ships, config.map_ships_host) == (
        "receiver",
        "pi.local:8080",
        "fintraffic",
        "ais.local",
    )
    assert {key: config.to_data()[key] for key in LAYER_KEYS} == rows
    wrong = Config.from_data(
        {"map/aircraft": "radar", "map/aircraft_host": "pi local", "map/ships": "adsbfi", "map/ships_host": "http://x"}
    )
    assert (wrong.map_aircraft, wrong.map_aircraft_host, wrong.map_ships, wrong.map_ships_host) == (
        "none",
        "",
        "none",
        "",
    )


def test_fintraffic_is_stored_wherever_the_station_is() -> None:
    """Whether it is offered is the station's position and radius (layerthing.offered): a save of it
    is not refused, and while it is not offered it counts as none."""
    far = Config.checked(Config.from_data({"station/lat": "50.11", "station/lon": "8.68"}), {"map/ships": "fintraffic"})
    assert far.map_ships == "fintraffic"


def test_no_setting_of_the_layers_is_kept_to_this_computer() -> None:
    assert not set(LAYER_KEYS) & LOCAL_ONLY


@pytest.fixture
def from_another_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """The address of this computer on the network is a made-up one, and every request comes from an
    address that is not this computer's."""
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: ["192.168.1.20"])
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for
    every test that does not ask for a fixture of this name): the receivers saved here are asked at
    the save (services/layers.py), and the addresses are made up."""
    monkeypatch.setenv(nodevices.ENV, "1")


async def test_a_page_of_another_device_with_the_key_sets_every_setting_of_the_layers(
    tmp_path: Path, from_another_device: None, under_the_switch: None
) -> None:
    e = Env(tmp_path, web=True, settings={"web/network": "true", "web/key": KEY})
    await e.start()
    answer = await e.fetch("/access", method="POST", body=json.dumps({"key": KEY}))
    assert answer.code == 204
    page = await e.ws(cookie=answer.headers["Set-Cookie"].split(";", 1)[0])
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    values = {
        "map/aircraft": "receiver",
        "map/aircraft_host": "192.168.1.30:8080",
        "map/ships": "receiver",
        "map/ships_host": "192.168.1.31:10110",
    }
    await page.send({"cmd": "set_config", "values": values})
    await page.until(lambda: e.ctl.config.map_ships_host == "192.168.1.31:10110")
    assert {key: (await e.ctl.store.settings())[key] for key in values} == values
    assert not page.of("error")
    await e.stop()


def test_a_receivers_address_with_a_name_and_a_password_in_it_is_refused() -> None:
    for typed in ("http://me:secret@pi.local/tar1090/data/aircraft.json", "https://me@pi.local/data/aircraft.json"):
        with pytest.raises(CodedError) as refused:
            receiver_address(typed)
        assert refused.value.code == "setting.not_receiver"
