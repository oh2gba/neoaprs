"""How the Controller brings the radios of the registry up (neoaprs/controller.py, neoaprs/radioregistry.py): each in a task of its own, so that an FM radio that is still looking for its port does not keep the HF
radio stopped; one radio restarted alone (`start_radio`) and all of them together (`start_tnc`); a start that is still looking ended by the next start of the same radio; the radios started all the same when
the Mercury modem cannot be started; and the daemon up all the same when the key file of encrypted messages cannot be made."""
import asyncio
import logging
from pathlib import Path

import pytest

from neoaprs.message import MessagingError
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Source
from tests.support.env import Env, until
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
    await until(lambda: e.hf.usable and e.ctl.mercury.running)
    assert e.tnc.state is Source.State.CONNECTING


async def test_one_radio_is_restarted_alone_with_its_modem_and_all_of_them_together(tmp_path: Path) -> None:
    w, e = await two_radios(tmp_path)
    await w.air.start()
    await e.start()
    await until(lambda: e.tnc.usable and e.hf.usable and e.ctl.mercury.running, 15.0)
    seen: dict[int, list[Source.State]] = {FM_ID: [], HF_ID: []}
    e.tnc.state_changed.connect(seen[FM_ID].append)
    e.hf.state_changed.connect(seen[HF_ID].append)
    modem_starts: list[bool] = []
    start = e.ctl.mercury.start

    async def counted(*args: object, **kwargs: object) -> None:
        modem_starts.append(True)
        await start(*args, **kwargs)                                                # type: ignore[arg-type]

    e.ctl.mercury.start = counted                                                   # type: ignore[method-assign]
    e.ctl.start_radio(FM_ID)
    await until(lambda: Source.State.STOPPED in seen[FM_ID] and e.tnc.usable, 15.0)
    assert seen[HF_ID] == [] and modem_starts == [], "radio 1 alone: the HF radio kept its line and its modem"
    seen[FM_ID].clear()
    e.ctl.start_radio(HF_ID)
    await until(lambda: Source.State.STOPPED in seen[HF_ID] and e.hf.usable and e.ctl.mercury.running, 15.0)
    assert seen[FM_ID] == [] and modem_starts == [True], "radio 2 alone, its modem first"
    seen[HF_ID].clear()
    e.ctl.start_tnc()
    await until(lambda: Source.State.STOPPED in seen[FM_ID] and Source.State.STOPPED in seen[HF_ID] and e.tnc.usable and e.hf.usable, 15.0)
    assert modem_starts == [True, True] and e.ctl.beacon.running and e.ctl.hf_beacon.running


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

    e.ctl.mercury.start = refuses                                                   # type: ignore[method-assign]
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
