"""The refusal of a device another holds names the holder as the page does (the two forms of a
radio's name: after the noun, "radio FM 2"), and the GPS receiver by its own words: it is no
radio."""

from pathlib import Path

import pytest

from neoaprs.claims import Claim, Claims
from neoaprs.config import Config, SettingError
from neoaprs.radiospec import RadioSpec
from neoaprs.web.confighandlers import refuse_held
from neoaprs.web.radioview import claimed_value


def kiss(id: int, port: str) -> RadioSpec:
    return RadioSpec(id, "fm", "kiss", "", True, id, settings={"port": port})


def held_text(claims: Claims, before: Config, after: Config) -> tuple[str, dict[str, object]]:
    with pytest.raises(SettingError) as held:
        refuse_held(before, after, claims)
    return str(held.value), held.value.params


def test_a_device_another_radio_names_is_in_use_by_that_radio_after_the_noun() -> None:
    before = Config(radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3"), kiss(6, "")))
    text, params = held_text(
        Claims(), before, Config(radios=(kiss(1, "/dev/ttyUSB0"), kiss(5, "/dev/ttyUSB3"), kiss(6, "/dev/ttyUSB3")))
    )
    assert params["held_by"] == 5 and text.endswith(
        "radio/6/port: the device is in use by radio FM 2: choose another"
    ), text


def test_a_device_the_gps_receiver_holds_is_in_use_by_the_gps_receiver() -> None:
    claims = Claims()
    claims.hold(Claim("serial", claimed_value("serial", "/dev/ttyUSB3"), None))
    before = Config(radios=(kiss(1, "/dev/ttyUSB0"), kiss(6, "")))
    text, params = held_text(claims, before, Config(radios=(kiss(1, "/dev/ttyUSB0"), kiss(6, "/dev/ttyUSB3"))))
    assert (params["holder"], params["held_by"]) == ("GPS", 0) and text.endswith(
        "radio/6/port: the device is in use by the GPS receiver: choose another"
    ), text


def mercury(id: int, card: str) -> RadioSpec:
    return RadioSpec(id, "hf", "mercury", "", True, id, settings={"sound_card": card})


def test_a_sound_card_named_by_its_number_is_the_card_another_radio_names_or_holds_by_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One card, two ways of naming it (`plughw:1,0` while ALSA knows card 1 as CODEC): the save is
    refused, whether the other radio names the card in its settings or holds it in the station's
    table."""
    card1 = tmp_path / "asound" / "card1"
    card1.mkdir(parents=True)
    (card1 / "id").write_text("CODEC\n")
    monkeypatch.setenv("NEOAPRS_ALSA_ROOT", str(tmp_path / "asound"))
    before = Config(radios=(mercury(2, "plughw:CARD=CODEC,DEV=0"), mercury(5, "")))
    text, params = held_text(
        Claims(), before, Config(radios=(mercury(2, "plughw:CARD=CODEC,DEV=0"), mercury(5, "plughw:1,0")))
    )
    assert params["held_by"] == 2 and text.endswith(
        "radio/5/sound_card: the device is in use by radio Mercury: choose another"
    ), text
    claims = Claims()
    claims.hold(Claim("sound_card", "plughw:CARD=CODEC,DEV=0", 2))
    before = Config(radios=(mercury(2, ""), mercury(5, "")))
    text, params = held_text(claims, before, Config(radios=(mercury(2, ""), mercury(5, "plughw:1,0"))))
    assert params["held_by"] == 2, text
    # (another card: let through)
    refuse_held(before, Config(radios=(mercury(2, ""), mercury(5, "plughw:2,0"))), claims)
