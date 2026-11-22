"""Tests for how the Controller starts the radios (neoaprs/controller.py, neoaprs/radioregistry.py):
each in its own task, restarts of one or all, and starts that continue when Mercury or the key
file fails.
"""
import asyncio
import logging
from pathlib import Path

import pytest

from neoaprs.message import MessagingError
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Source
from tests.support.env import Env, idle_for, until
from tests.support.mercuryworld import World


async def two_radios(tmp_path: Path) -> tuple[World, Env]:
    w = World(tmp_path, frame_sec=0.1)
    e = await w.add("OH2A", fm=True, hf=True)
    return w, e


async def test_the_hf_radio_starts_while_the_fm_radio_is_still_looking_for_its_port(tmp_path: Path) -> None:
    w, e = await two_radios(tmp_path)

    async def looking() -> None:
        e.tnc._set_state(Source.State.CONNECTING)
        await asyncio.sleep(3600)

    e.tnc.start = looking                                                           # type: ignore[method-assign]
    await w.air.start()
    await e.start(connected=False)
    await until(lambda: e.hf.usable and e.mercury.running)
    assert e.tnc.state is Source.State.CONNECTING


async def test_one_radio_is_restarted_alone_with_its_modem_and_all_of_them_together(tmp_path: Path) -> None:
    w, e = await two_radios(tmp_path)
    await w.air.start()
    await e.start()
    await until(lambda: e.tnc.usable and e.hf.usable and e.mercury.running, 15.0)
    seen: dict[int, list[Source.State]] = {FM_ID: [], HF_ID: []}
    e.tnc.state_changed.connect(seen[FM_ID].append)
    e.hf.state_changed.connect(seen[HF_ID].append)
    modem_starts: list[bool] = []
    start = e.mercury.start

    async def counted(*args: object, **kwargs: object) -> None:
        modem_starts.append(True)
        await start(*args, **kwargs)                                                # type: ignore[arg-type]

    e.mercury.start = counted                                                   # type: ignore[method-assign]
    e.ctl.start_radio(FM_ID)
    await until(lambda: Source.State.STOPPED in seen[FM_ID] and e.tnc.usable, 15.0)
    assert seen[HF_ID] == [] and modem_starts == [], "radio 1 alone: the HF radio kept its line and its modem"
    seen[FM_ID].clear()
    e.ctl.start_radio(HF_ID)
    await until(lambda: Source.State.STOPPED in seen[HF_ID] and e.hf.usable and e.mercury.running, 15.0)
    assert seen[FM_ID] == [] and modem_starts == [True], "radio 2 alone, its modem first"
    seen[HF_ID].clear()
    e.ctl.start_tnc()
    await until(lambda: Source.State.STOPPED in seen[FM_ID] and Source.State.STOPPED in seen[HF_ID] and e.tnc.usable and e.hf.usable, 15.0)
    assert modem_starts == [True, True] and e.beacon.running and e.beacon_2.running


async def test_a_start_that_is_still_looking_for_the_port_is_ended_by_the_next_start_of_that_radio_and_no_other(tmp_path: Path) -> None:
    w, e = await two_radios(tmp_path)
    looks: list[str] = []

    async def looking() -> None:
        looks.append("began")
        e.tnc._set_state(Source.State.CONNECTING)
        try:
            await asyncio.sleep(3600)
        finally:
            looks.append("ended")

    e.tnc.start = looking                                                           # type: ignore[method-assign]
    await w.air.start()
    await e.start(connected=False)
    await until(lambda: looks == ["began"] and e.hf.usable, 15.0)
    hf_line = e.hf._generation
    e.ctl.start_radio(FM_ID)
    await until(lambda: looks == ["began", "ended", "began"], 15.0)
    assert [t.get_name() for t in e.ctl.tasks if t.get_name() in ("tnc", "hf")] == ["tnc"], "one start of radio 1 under way, the one before ended"
    assert e.hf.usable and e.hf._generation == hf_line, "the HF radio was not touched"
    await e.stop()
    assert looks == ["began", "ended", "began", "ended"] and len(e.ctl.tasks) == 0, "the stop ends the start that is still looking"


async def test_the_radios_start_all_the_same_when_the_modem_cannot_be_started(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    w, e = await two_radios(tmp_path)

    async def refuses(*args: object, **kwargs: object) -> None:
        raise OSError("no such program")

    e.mercury.start = refuses                                                   # type: ignore[method-assign]
    await w.air.start()
    with caplog.at_level(logging.ERROR, logger="neoaprs.controller"):
        await e.start(connected=False)
        await until(lambda: e.tnc.usable and e.hf.state is Source.State.CONNECTED)
    assert "the Mercury modem could not be started" in caplog.text


async def test_the_daemon_starts_without_our_key_when_the_key_file_cannot_be_made(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = Env(tmp_path)

    async def cannot() -> None:
        raise MessagingError("the key could not be kept: Read-only file system")

    e.ctl.keyring.load = cannot                                                     # type: ignore[method-assign]
    with caplog.at_level(logging.ERROR, logger="neoaprs.controller"):
        await e.start()
    assert e.ctl.running and "encrypted messages are off: the key could not be kept" in caplog.text


async def test_a_save_while_find_my_radio_holds_the_radio_starts_it_once_after_the_search_and_not_during_it(tmp_path: Path) -> None:
    e = Env(tmp_path / "data")
    await e.start()
    await e.until_connected()
    ctl, starts = e.ctl, []
    real_start = e.tnc.start

    async def counted() -> None:
        starts.append(e.tnc.baud)
        await real_start()

    e.tnc.start = counted                                                           # type: ignore[method-assign]
    try:
        # (what Find my radio does before it tries the ports: services/radiofinder.py)
        await ctl.hold_radio(FM_ID)
        assert e.tnc.state is Source.State.STOPPED
        # (from the radio's box, or another page, while the search runs)
        assert await ctl.save_radio_settings(FM_ID, {"baud": "4800"})
        await idle_for(0.3)
        assert starts == [] and e.tnc.state is Source.State.STOPPED, "the radio the search holds is not started by a save: the search and its line would want one port"
        ctl.release_radio(FM_ID)
        await until(lambda: e.tnc.state is not Source.State.STOPPED)
        await idle_for(0.2)
        assert starts == [4800], "started once, when the search let go, with the settings as they are now"
    finally:
        await e.stop()
