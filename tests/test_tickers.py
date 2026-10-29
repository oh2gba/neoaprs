"""The timers of the parts that had no guard of their own (neoaprs/tasks.py `every` is their loop): an exception in one round is logged and the timer goes on with the next."""
import asyncio
from pathlib import Path

import pytest

from neoaprs import controller
from neoaprs.controller import Controller
from neoaprs.services.beacon import Beacon
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.igateworld import iworld
from tests.support.stubtnc import StubTnc


class Fails:
    """A round that raises the first time it is run and counts the rounds."""

    def __init__(self) -> None:
        self.rounds = 0

    def __call__(self, *_: object) -> None:
        self.rounds += 1
        if self.rounds == 1:
            raise RuntimeError("one round fails")


@pytest.mark.expects_errors
async def test_the_beacon_timer_goes_on_after_a_round_that_fails(caplog: pytest.LogCaptureFixture) -> None:
    beacon = Beacon(StubTnc(), lambda: ON_AIR, FixedClock(), tick_sec=0.01)         # type: ignore[arg-type]
    remember_stop(beacon.stop)
    ticks = Fails()
    beacon._tick = ticks                                                           # type: ignore[method-assign]
    await beacon.start()
    await until(lambda: ticks.rounds >= 3)
    assert "the beacon ticker failed" in caplog.text and "one round fails" in caplog.text


@pytest.mark.expects_errors
async def test_the_igate_timer_goes_on_after_a_round_that_fails(caplog: pytest.LogCaptureFixture) -> None:
    w = await iworld(await fake_aprsis(), wait=False)
    ticks = Fails()
    w.igate.tick = ticks                                                           # type: ignore[method-assign]
    w.igate.tick_sec = 0.01
    ticker = asyncio.get_running_loop().create_task(w.igate._run())
    try:
        await until(lambda: ticks.rounds >= 3)
    finally:
        ticker.cancel()
    assert "the iGate ticker failed" in caplog.text


@pytest.mark.expects_errors
async def test_the_daily_care_of_the_database_and_the_recount_go_on_after_a_round_that_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(controller, "PRUNE_EVERY_SEC", 0.01)
    monkeypatch.setattr(controller, "RECOUNT_EVERY_SEC", 0.01)
    ctl = Controller(tmp_path, FixedClock())
    prunes, recounts = Fails(), Fails()
    ctl.prune = prunes                                                             # type: ignore[method-assign,assignment]
    ctl.stationbook.recount = recounts                                             # type: ignore[method-assign]
    tasks = [asyncio.get_running_loop().create_task(ctl._prune_daily()), asyncio.get_running_loop().create_task(ctl._recount_minutely())]
    try:
        await until(lambda: prunes.rounds >= 3 and recounts.rounds >= 3)
    finally:
        for task in tasks:
            task.cancel()
    assert "the daily care of the database failed" in caplog.text and "the recount of the station book failed" in caplog.text
