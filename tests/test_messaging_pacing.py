"""Several messages written at once go out one after the other: `spacing_sec` between two attempts
on one radio (services/pace.py), and a message on another radio does not wait for that pause.
"""
from pathlib import Path

import pytest

from neoaprs.messagelog import MessageLog
from neoaprs.radiotype import HF_ID
from neoaprs.source import Source
from tests.support.storedb import log_at
from tests.test_messaging import Rig, started_rig, with_hf


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await started_rig(tmp_path, spacing_sec=10.0)


async def test_the_first_message_goes_at_once_and_the_others_written_with_it_follow_ten_seconds_apart(rig: Rig) -> None:
    for call in ("OH2AAA", "OH2BBB", "OH2CCC"):
        await rig.m.send(call, "Meeting at 18")
    assert len(rig.tnc.sent) == 1
    await rig.pass_time(9)
    assert len(rig.tnc.sent) == 1, "nothing before the spacing has passed"
    await rig.pass_time(1)
    assert len(rig.tnc.sent) == 2
    await rig.pass_time(10)
    assert len(rig.tnc.sent) == 3
    assert [line.split("::")[1][:9].strip() for line in rig.tnc.lines()] == ["OH2AAA", "OH2BBB", "OH2CCC"], "in the order they were written"
    assert [rig.state(n).attempts for n in (1, 2, 3)] == [1, 1, 1]


async def test_a_message_that_waits_for_its_turn_is_still_being_sent_with_no_attempt_used(rig: Rig) -> None:
    await rig.m.send("OH2AAA", "One")
    second = await rig.m.send("OH2BBB", "Two")
    assert (second.state, second.attempts) == ("sending", 0)


async def test_a_lone_message_is_not_delayed_when_the_last_one_went_longer_ago_than_the_spacing(rig: Rig) -> None:
    await rig.m.send("OH2AAA", "One")
    await rig.pass_time(10)
    await rig.m.send("OH2BBB", "Two")
    assert len(rig.tnc.sent) == 2


async def test_messages_that_waited_for_the_radio_go_out_spaced_when_it_is_back(rig: Rig) -> None:
    await rig.radio(Source.State.WAITING)
    for call in ("OH2AAA", "OH2BBB"):
        await rig.m.send(call, "Hello")
    assert len(rig.tnc.sent) == 0
    await rig.radio(Source.State.CONNECTED)
    assert len(rig.tnc.sent) == 1
    await rig.pass_time(10)
    assert len(rig.tnc.sent) == 2


async def test_the_pause_between_attempts_is_each_radios_own(tmp_path: Path) -> None:
    log, _, clock = await log_at(tmp_path, MessageLog)
    two = Rig(log, clock, spacing_sec=10.0, hf_enabled=True)
    hf = with_hf(two, two.radios)
    two.radios.hf_stations = ("OH2FAR", "OH2FAB")
    await two.start()
    await two.m.send("OH2AAA", "on FM")
    await two.m.send("OH2FAR", "on HF")
    assert (len(two.tnc.sent), len(hf.sent)) == (1, 1), "written at the same moment to stations on two radios: both go at once (before: HF waited for FM's pause)"
    await two.m.send("OH2BBB", "FM again")
    await two.m.send("OH2FAB", "HF again")
    assert (len(two.tnc.sent), len(hf.sent)) == (1, 1), "a second on each radio waits for that radio's pause"
    await two.pass_time(9)
    assert (len(two.tnc.sent), len(hf.sent)) == (1, 1)
    await two.pass_time(1)
    assert (len(two.tnc.sent), len(hf.sent)) == (2, 2), "ten seconds after, one more on each"
    assert [a.radio_id for n in (2, 4) for a in two.m.delivery.attempts_of(n)] == [HF_ID, HF_ID]
