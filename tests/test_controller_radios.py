"""How the Controller brings the two radios up (neoaprs/controller.py): together, so that an FM radio that is still looking for its port does not keep the HF radio stopped; the radios started all the same when the
Mercury modem cannot be started; and the daemon up all the same when the key file of encrypted messages cannot be made."""
import asyncio
import logging
from pathlib import Path

import pytest

from neoaprs.message import MessagingError
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
