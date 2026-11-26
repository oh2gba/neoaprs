"""A saved setting restarts the radio it belongs to and no other (Controller._save, the registry's
`sync`): changing one radio's modem, sound card or tickbox keeps the other radio's line.
"""

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.mercury import Keying
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from tests.support.mercuryworld import World


async def both_radios(tmp_path: Path) -> World:
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.start()
    return w


def watch(tnc: Tnc) -> list[Source.State]:
    """Every state the radio goes to from now on."""
    seen: list[Source.State] = []
    tnc.state_changed.connect(seen.append)
    return seen


async def test_a_change_of_the_hf_radios_modem_restarts_the_hf_radio_and_the_fm_radio_keeps_its_line(
    tmp_path: Path,
) -> None:
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    fm_seen, hf_seen = watch(a.tnc), watch(a.hf)
    fm_line = a.tnc._generation
    assert await a.ctl.save_config(replace(a.ctl.config, mercury_sound_card="plughw:9,0"))
    await w.until(lambda: Source.State.STOPPED in hf_seen and a.hf.usable)
    assert hf_seen[0] is Source.State.STOPPED, "the Mercury radio was restarted"
    assert fm_seen == [] and a.tnc.state is Source.State.CONNECTED and a.tnc._generation == fm_line, (
        "the FM radio was not touched"
    )


async def test_the_hf_radio_switched_off_and_on_again_leaves_the_fm_radio_connected(tmp_path: Path) -> None:
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    fm_seen = watch(a.tnc)
    assert await a.ctl.save_config(replace(a.ctl.config, hf_enabled=False))
    await w.until(lambda: a.hf.state is Source.State.STOPPED)
    assert await a.ctl.save_config(replace(a.ctl.config, hf_enabled=True))
    await w.until(lambda: a.hf.usable)
    assert fm_seen == [] and a.tnc.state is Source.State.CONNECTED


async def test_a_change_of_the_fm_radios_speed_restarts_the_fm_radio_and_the_hf_radio_keeps_its_line(
    tmp_path: Path,
) -> None:
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    fm_seen, hf_seen = watch(a.tnc), watch(a.hf)
    hf_line = a.hf._generation
    assert await a.ctl.save_config(replace(a.ctl.config, serial_baud=19200))
    await w.until(lambda: Source.State.STOPPED in fm_seen and a.tnc.usable)
    assert hf_seen == [] and a.hf.state is Source.State.CONNECTED and a.hf._generation == hf_line, (
        "the Mercury radio was not touched"
    )
    assert a.tnc.baud == 19200


async def test_a_setting_of_neither_radio_restarts_neither(tmp_path: Path) -> None:
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    fm_seen, hf_seen = watch(a.tnc), watch(a.hf)
    assert await a.ctl.save_config(replace(a.ctl.config, station_comment="a new comment"))
    await w.until(lambda: True)
    assert fm_seen == [] and hf_seen == []


async def test_storing_the_sound_card_and_the_keying_the_modem_chose_itself_restarts_nothing(tmp_path: Path) -> None:
    """The page stores the daemon's proposal as the setting: the modem already runs with it, so it
    is no reason to restart (a card it does not run with is)."""
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    hf_seen = watch(a.hf)
    modem = a.mercury
    assert a.ctl.config.mercury_sound_card == "" and modem.state == "running"
    # What the program was started with, as its own choice
    modem.sound_card, modem.keying = "plughw:1,0", Keying("rts", "/dev/ttyUSB0")
    assert await a.ctl.save_config(
        replace(a.ctl.config, mercury_sound_card="plughw:1,0", mercury_keying="rts:/dev/ttyUSB0")
    )
    await asyncio.sleep(0.5)  # (a restart stops the HF radio at once)
    assert hf_seen == []
    assert await a.ctl.save_config(replace(a.ctl.config, mercury_sound_card="plughw:9,0"))
    await w.until(lambda: Source.State.STOPPED in hf_seen and a.hf.usable)


async def test_clearing_a_sound_card_that_was_set_restarts_the_modem_so_that_it_chooses_again(tmp_path: Path) -> None:
    """Storing the modem's own choice is no change; taking a stored one away is: the setting says
    "choose", and only a start chooses."""
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    fm_seen, hf_seen = watch(a.tnc), watch(a.hf)
    modem = a.mercury
    # What the program was started with, as its own choice
    modem.sound_card = "plughw:1,0"
    assert await a.ctl.save_config(replace(a.ctl.config, mercury_sound_card="plughw:1,0"))
    await asyncio.sleep(0.3)
    assert hf_seen == []
    assert await a.ctl.save_config(replace(a.ctl.config, mercury_sound_card=""))
    await w.until(lambda: Source.State.STOPPED in hf_seen and a.hf.usable)
    assert fm_seen == []


async def test_a_save_that_changes_both_radios_restarts_each_once_and_the_log_names_each(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    caplog.set_level(logging.INFO, "neoaprs.controller")
    caplog.clear()
    fm_line, hf_line = a.tnc._generation, a.hf._generation
    assert await a.ctl.save_config(replace(a.ctl.config, serial_baud=19200, mercury_keying="cm108"))
    assert a.ctl.radios.why == {FM_ID: "baud 9600 -> 19200", HF_ID: "keying default -> cm108"}
    await w.until(lambda: a.tnc.usable and a.hf.usable and a.tnc._generation > fm_line and a.hf._generation > hf_line)
    said = [r.getMessage() for r in caplog.records if r.name == "neoaprs.controller"]
    assert [line for line in said if "is restarted because" in line] == [
        "the FM radio (radio 1) is restarted because its settings changed: baud 9600 -> 19200",
        "the Mercury radio (radio 2) is restarted because its settings changed: keying default -> cm108",
    ]
    assert (
        len([line for line in said if line.startswith("the FM radio (radio 1) is started: ")])
        == len([line for line in said if line.startswith("the Mercury radio (radio 2) is started: ")])
        == 1
    )


async def test_the_log_says_which_radio_is_restarted_and_what_changed_in_its_settings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    w = await both_radios(tmp_path)
    a = w["OH2A"]
    caplog.set_level(logging.INFO, "neoaprs.controller")
    caplog.clear()
    assert await a.ctl.save_config(replace(a.ctl.config, mercury_sound_card="plughw:9,0"))
    await w.until(
        lambda: any(r.getMessage().startswith("the Mercury radio (radio 2) is started") for r in caplog.records)
    )
    said = [r.getMessage() for r in caplog.records if r.name == "neoaprs.controller"]
    [why] = [
        line
        for line in said
        if line.startswith("the Mercury radio (radio 2) is restarted because its settings changed")
    ]
    assert why.endswith("sound card default -> plughw:9,0")
    assert not any(line.startswith("the FM radio (radio 1) is restarted") for line in said), (
        "the FM radio was not touched"
    )
    assert any(line.startswith("the Mercury radio (radio 2) is started: the Mercury modem") for line in said)
    caplog.clear()
    assert await a.ctl.save_config(replace(a.ctl.config, serial_baud=19200))
    await w.until(lambda: a.tnc.usable)
    [why] = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("the FM radio (radio 1) is restarted because its settings changed")
    ]
    assert "baud 9600 -> 19200" in why
    assert await a.ctl.save_config(replace(a.ctl.config, hf_enabled=False))
    # The line comes after the modem is stopped too, which on Windows takes longer than the radio's
    # STOPPED
    await w.until(
        lambda: any(r.getMessage() == "the Mercury radio (radio 2) is off in the settings" for r in caplog.records)
    )
    assert a.hf.state is Source.State.STOPPED
    assert any(
        r.getMessage().startswith(
            "the Mercury radio (radio 2) is restarted because its settings changed: switched on or off: on -> off"
        )
        for r in caplog.records
    )
