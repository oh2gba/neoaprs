"""Several messages written at once (to several stations) go out one after the other: between two attempts of any messages `spacing_sec` pass (neoaprs/services/messaging.py)."""
from pathlib import Path

import pytest

from neoaprs.messagelog import MessageLog
from neoaprs.source import Source
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.storedb import store_at
from tests.test_messaging import Rig


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    r = Rig(MessageLog(store.db, clock), clock, spacing_sec=10.0)
    await r.start()
    return r


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
