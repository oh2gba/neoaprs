"""Keying a radio through flrig or rigctld (neoaprs/rigptt.py, neoaprs/rigkeyer.py) against stand-ins
that record each key-down and key-up and can hang, refuse, leave the rig keyed or die mid-frame."""

import logging
import time

import pytest

from neoaprs import rigkeyer
from neoaprs.rigkeyer import RIG_SILENT, RigKeyer
from neoaprs.rigptt import Flrig, Rigctld, RigRefused
from tests.support.env import remember_stop, until
from tests.support.fakerig import FakeFlrig, FakeRig, FakeRigctld

ANSWER_SEC = 0.3


@pytest.fixture(autouse=True)
def _quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rigkeyer, "PROBE_SEC", 0.05)
    monkeypatch.setattr(rigkeyer, "RETRY_SEC", (0.02, 0.05))
    monkeypatch.setattr(rigkeyer, "STOP_SEC", 0.5)


FAKES = pytest.mark.parametrize("fake_kind", [FakeFlrig, FakeRigctld], ids=["flrig", "rigctld"])


async def keyer_on(fake: FakeRig) -> tuple[RigKeyer, list[str]]:
    client = (Flrig if isinstance(fake, FakeFlrig) else Rigctld)("127.0.0.1", fake.port, ANSWER_SEC)
    changes: list[str] = []
    keyer = RigKeyer(client, lambda: changes.append(keyer.problem))
    keyer.start()
    remember_stop(keyer.stop)
    return keyer, changes


@FAKES
async def test_a_key_down_and_its_key_up_reach_the_rig_program_and_the_key_down_is_quick(fake_kind: type) -> None:
    fake = await fake_kind().start()
    keyer, _ = await keyer_on(fake)
    await until(lambda: keyer.holds() == "" and keyer.answering)
    asked = time.monotonic()
    keyer.key(True, 10.0)
    await until(lambda: fake.ptt == 1 and keyer.state is True)
    latency = fake.downs[0] - asked
    keyer.key(False)
    await until(lambda: fake.ptt == 0 and keyer.state is False)
    assert [k.on for k in fake.keyed] == [False, True, False], "the first key-up is the start's own"
    assert latency < 0.1 and keyer.latency_sec is not None, f"a key-down took {latency:.3f} s to reach the program"
    assert keyer.problem == "" and keyer.holds() == ""


@FAKES
@pytest.mark.expects_errors
async def test_a_key_down_the_modem_never_ends_is_ended_by_its_own_limit_and_the_radio_shows_it(
    fake_kind: type, caplog: pytest.LogCaptureFixture
) -> None:
    fake = await fake_kind().start()
    keyer, changes = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    keyer.key(True, 0.3)
    await until(lambda: fake.ptt == 1)
    await until(lambda: fake.ptt == 0)
    held = fake.ups[-1] - fake.downs[-1]
    assert 0.25 < held < 0.6, f"keyed for {held:.2f} s against a limit of 0.3 s"
    assert keyer.problem == "rig_keyed_long" and "rig_keyed_long" in changes
    assert any(
        "keyed for longer than its frame" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR
    )
    keyer.key(False)  # the modem's late PTT OFF
    assert keyer.problem == "rig_keyed_long", "a key-down cut by the limit is shown until one ends by itself"
    keyer.key(True, 5.0)
    keyer.key(False)
    await until(lambda: keyer.problem == "" and fake.ptt == 0 and keyer.state is False)


@FAKES
async def test_a_program_that_refuses_the_key_down_holds_the_frames_until_it_keys_again(fake_kind: type) -> None:
    fake = await fake_kind().start()
    keyer, changes = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    fake.mode = "refuse"
    keyer.key(True, 5.0)
    await until(lambda: keyer.problem == "rig_silent")
    assert keyer.holds() == RIG_SILENT and RIG_SILENT.code == "radio.rig_silent"
    assert fake.ptt == 0 and not keyer.want, "the key-down is given up and a key-up is asked for"
    fake.mode = "ok"
    await until(lambda: keyer.problem == "" and keyer.holds() == "")
    assert fake.ptt == 0 and fake.keyed[-1].on is False and changes[-1] == ""


@FAKES
@pytest.mark.expects_errors
async def test_a_program_that_hangs_mid_frame_is_asked_for_the_key_up_until_it_confirms(
    fake_kind: type, caplog: pytest.LogCaptureFixture
) -> None:
    fake = await fake_kind().start()
    keyer, _ = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    keyer.key(True, 5.0)
    await until(lambda: fake.ptt == 1 and keyer.state is True)
    fake.mode = "hang"
    keyer.key(False)
    await until(lambda: keyer.problem == "rig_silent" and keyer.holds() == RIG_SILENT)
    assert fake.ptt == 1
    assert any("may still be keyed" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    fake.mode = "ok"
    await until(lambda: fake.ptt == 0 and keyer.problem == "" and keyer.state is False)
    assert any("confirmed the key-up" in r.getMessage() for r in caplog.records)


@FAKES
@pytest.mark.expects_errors
async def test_a_program_that_dies_mid_frame_gets_the_key_up_once_it_is_back(fake_kind: type) -> None:
    fake = await fake_kind().start()
    keyer, _ = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    keyer.key(True, 5.0)
    await until(lambda: fake.ptt == 1 and keyer.state is True)
    await fake.die()
    keyer.key(False)
    await until(lambda: keyer.problem == "rig_silent")
    back = fake_kind(port=fake.port, ptt=1)
    await back.start()
    await until(lambda: back.ptt == 0 and keyer.state is False and keyer.problem == "")


@FAKES
@pytest.mark.expects_errors
async def test_a_rig_that_stays_keyed_after_the_key_up_is_asked_again(fake_kind: type) -> None:
    fake = await fake_kind().start()
    keyer, _ = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    keyer.key(True, 5.0)
    await until(lambda: keyer.state is True)
    fake.mode = "stuck"
    keyer.key(False)
    await until(lambda: len(fake.ups) >= 3 and keyer.problem == "rig_silent")
    fake.mode = "ok"
    await until(lambda: fake.ptt == 0 and keyer.state is False and keyer.problem == "")


@FAKES
async def test_a_stop_keys_up_a_rig_that_is_keyed(fake_kind: type) -> None:
    fake = await fake_kind().start()
    keyer, _ = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    keyer.key(True, 5.0)
    await until(lambda: keyer.state is True)
    await keyer.stop()
    assert fake.ptt == 0 and fake.keyed[-1].on is False


@pytest.mark.expects_errors
async def test_a_stop_that_cannot_get_the_key_up_says_so_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    fake = await FakeRigctld().start()
    keyer, _ = await keyer_on(fake)
    await until(lambda: keyer.state is False)
    keyer.key(True, 5.0)
    await until(lambda: keyer.state is True)
    await fake.die()
    await keyer.stop()
    assert any(
        "did not confirm the key-up before NeoAPRS stopped" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.ERROR
    )


@FAKES
async def test_a_program_that_is_not_running_at_the_start_holds_the_frames_and_is_found_when_it_comes(
    fake_kind: type,
) -> None:
    gone = await fake_kind().start()
    port = gone.port
    await gone.die()
    keyer, _ = await keyer_on(gone)
    await until(lambda: keyer.problem == "rig_silent")
    assert keyer.holds() == RIG_SILENT
    fake = await fake_kind(port=port).start()
    await until(lambda: keyer.problem == "" and keyer.holds() == "")
    assert fake.keyed == [fake.keyed[0]] and fake.keyed[0].on is False, "only the start's key-up, nothing keyed"


async def test_flrig_without_a_radio_and_rigctld_refusing_are_refusals_with_words_for_the_log() -> None:
    flrig = await FakeFlrig(mode="refuse").start()
    with pytest.raises(RigRefused, match="no radio connected"):
        await Flrig("127.0.0.1", flrig.port, ANSWER_SEC).set(True)
    await Flrig("127.0.0.1", flrig.port, ANSWER_SEC).probe()  # its server still answers
    rigctld = await FakeRigctld(mode="refuse").start()
    with pytest.raises(RigRefused, match="RPRT -1"):
        await Rigctld("127.0.0.1", rigctld.port, ANSWER_SEC).set(True)
    with pytest.raises(RigRefused, match="no answer in 0.3 s"):
        hang = await FakeRigctld(mode="hang").start()
        await Rigctld("127.0.0.1", hang.port, ANSWER_SEC).probe()
