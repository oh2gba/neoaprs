"""One flow at a time for each radio (neoaprs/radioflows.py, Controller.start_radio, repoint, hold_radio):
a restart, a repoint and a hold of one radio never run beside each other."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.mercurystall import STALL_SEC
from neoaprs.radioflows import RadioFlows
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Source
from neoaprs.tasks import TaskSet
from tests.support.env import Env, until, until_started
from tests.support.modemports import own_ports
from tests.test_mercury_modem import HF, _alive, modem, stopped

log = logging.getLogger("tests.flows")


class Works:
    """Flows that write down when they begin and end, and wait to be let go."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.gates: dict[str, asyncio.Event] = {}

    def work(self, name: str) -> Callable[[], Awaitable[None]]:
        gate = self.gates.setdefault(name, asyncio.Event())

        async def run() -> None:
            self.said.append(f"{name} began")
            try:
                await gate.wait()
            except asyncio.CancelledError:
                self.said.append(f"{name} cancelled")
                raise
            self.said.append(f"{name} ended")

        return run


def flows() -> tuple[RadioFlows, TaskSet]:
    tasks = TaskSet(log)
    return RadioFlows(tasks.spawn), tasks


async def test_a_second_restart_of_a_radio_begins_only_after_the_first_was_ended_and_another_radio_is_left_alone() -> (
    None
):
    f, tasks = flows()
    w = Works()
    f.begin(1, "restart", w.work("a"), "a")
    f.begin(3, "restart", w.work("other"), "other")
    await until(lambda: "a began" in w.said and "other began" in w.said)
    second = f.begin(1, "restart", w.work("b"), "b")
    await until(lambda: "b began" in w.said)
    assert w.said.index("a cancelled") < w.said.index("b began") and "other cancelled" not in w.said
    w.gates["b"].set()
    await second
    assert f.running(1) is None and f.running(3) == "restart"
    await tasks.cancel_all()


async def test_a_hold_ends_a_repoint_under_way_and_a_restart_after_it_waits_for_the_holds_stop_to_end() -> None:
    f, tasks = flows()
    w = Works()
    f.begin(2, "repoint", w.work("repoint"), "repoint")
    await until(lambda: "repoint began" in w.said)
    holding = asyncio.create_task(f.hold(2, w.work("stop"), "hold"))
    await until(lambda: "stop began" in w.said)
    assert w.said == ["repoint began", "repoint cancelled", "stop began"] and 2 in f.held
    f.release(2)
    restart = f.begin(2, "restart", w.work("start"), "start")
    await asyncio.sleep(0)
    assert "start began" not in w.said and "stop cancelled" not in w.said, "the stop is not cut short"
    w.gates["stop"].set()
    await holding
    await until(lambda: "start began" in w.said)
    w.gates["start"].set()
    await restart
    assert w.said[-3:] == ["stop ended", "start began", "start ended"]
    await tasks.cancel_all()


async def test_a_repoint_asked_during_a_restart_is_owed_to_its_end_and_one_asked_after_it_is_not() -> None:
    f, tasks = flows()
    w = Works()
    restart = f.begin(2, "restart", w.work("restart"), "restart")
    await until(lambda: "restart began" in w.said)
    assert f.owe_repoint(2) is True and f.running(2) == "restart"
    w.gates["restart"].set()
    await restart
    assert f.take_owed(2) is True and f.take_owed(2) is False
    assert f.owe_repoint(2) is False, "no restart under way: the repoint is a flow of its own"
    await tasks.cancel_all()


async def test_end_all_cancels_every_flow() -> None:
    f, tasks = flows()
    w = Works()
    f.begin(1, "restart", w.work("a"), "a")
    f.begin(2, "repoint", w.work("b"), "b")
    await until(lambda: len(w.said) == 2)
    await f.end_all()
    assert sorted(w.said) == ["a began", "a cancelled", "b began", "b cancelled"]
    assert f.running(1) is None and f.running(2) is None
    await tasks.cancel_all()


@pytest.mark.parametrize("last", ["stop", "restart"])
async def test_a_stall_restart_a_settings_restart_and_a_stop_at_once_end_as_the_last_request_asked_with_no_child_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, last: str
) -> None:
    own_ports(monkeypatch)
    f, tasks = flows()
    m = modem(tmp_path)
    runs: set[int] = set()
    m.changed.connect(lambda: runs.add(m.pid) if m.state == "running" and m.pid is not None else None)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        first = m.pid
        # Mercury's own restart of a stalled receive side: its run is ended in a thread, a start is due
        end = time.monotonic()
        for n in range(int(STALL_SEC * 10) + 1):
            m._capture_full(end - STALL_SEC - 0.1 + n / 10)
        assert m.stall.restarts == 1 and m.state == "waiting"
        # and, before that run is gone, a change of the settings and an untick of the same radio
        changed = replace(HF, mercury_tx_gain_db=-3.0)
        asks = {"restart": lambda: m.start(changed), "stop": m.stop}
        order = ["restart", "stop"] if last == "stop" else ["stop", "restart"]
        for kind in order:
            done = f.begin(HF_ID, "restart", asks[kind], kind)
        await done
        await asyncio.sleep(1.0)  # longer than the back-off of the stall's own start
        if last == "stop":
            assert m.state == "stopped" and m.pid is None
        else:
            await until_started(lambda: m.state == "running")
            assert m.pid is not None and m.pid != first
        alive = {pid for pid in runs | {first} if _alive(pid)}
        assert alive == ({m.pid} if last == "restart" else set()), "no run of the modem is left but the asked one"
    finally:
        await stopped(m)
        await tasks.cancel_all()


async def test_the_controller_ends_a_repoint_under_way_before_find_my_radio_holds_the_radio_and_repoints_no_held_radio(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path)
    await e.start()
    ctl, line = e.ctl, e.tnc
    opening, said = asyncio.Event(), []
    start = line.start

    async def slow_start() -> None:
        said.append("start")
        opening.set()
        await asyncio.sleep(3600)

    line.start = slow_start  # type: ignore[method-assign]
    ctl.repoint(FM_ID)
    await until(opening.is_set)
    assert ctl.flows.running(FM_ID) == "repoint"
    await ctl.hold_radio(FM_ID)
    assert line.state is Source.State.STOPPED and ctl.flows.running(FM_ID) is None
    ctl.repoint(FM_ID)
    assert ctl.flows.running(FM_ID) is None and said == ["start"], "a held radio is not repointed"
    line.start = start  # type: ignore[method-assign]
    ctl.release_radio(FM_ID)
    await until(lambda: line.usable, 15.0)


@pytest.mark.expects_errors
async def test_a_part_that_cannot_take_new_settings_leaves_the_others_told_and_the_save_true(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    e = Env(tmp_path)
    await e.start()
    ctl, told = e.ctl, []

    def broken() -> None:
        raise RuntimeError("an odd value")

    def broken_sync(config: object) -> list[int]:
        raise RuntimeError("the registry is confused")

    ctl.igate.settings_changed = broken  # type: ignore[method-assign]
    ctl.config_changed.connect(lambda config: told.append("config"))
    ctl.mapauto.settings_changed = lambda previous: told.append("map")  # type: ignore[method-assign]
    assert await ctl.save_config(replace(ctl.config, station_comment="changed"))
    assert told == ["config", "map"] and ctl.config.station_comment == "changed"
    assert "the settings are stored and in force, but the iGate could not take them" in caplog.text
    ctl.radios.sync = broken_sync  # type: ignore[method-assign]
    assert await ctl.save_config(replace(ctl.config, station_comment="again"))
    assert ctl.config.station_comment == "again", "the settings in force are the stored ones"
    assert "but the radios could not take them" in caplog.text
