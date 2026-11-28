"""A Packet radio (Direwolf on a sound card) keyed through flrig or rigctld: Direwolf keys nothing
itself and sends longer flags first; its `PTT 0 = 1` and `PTT 0 = 0` lines key the rig."""

from pathlib import Path

import pytest

from neoaprs import direwolf, rigkeyer
from neoaprs.direwolf import conf_text
from neoaprs.mercury import Keying
from neoaprs.rigkeyer import RIG_SILENT
from tests.support import fakedirewolf
from tests.support.env import until, until_started
from tests.support.fakerig import FakeFlrig, FakeRigctld
from tests.test_direwolf_modem import CARD, _ports_of_this_test as _ports_of_this_test, kiss_send, modem, running

FAKES = pytest.mark.parametrize("fake_kind", [FakeFlrig, FakeRigctld], ids=["flrig", "rigctld"])


@pytest.fixture(autouse=True)
def _quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rigkeyer, "PROBE_SEC", 0.05)
    monkeypatch.setattr(rigkeyer, "RETRY_SEC", (0.02, 0.05))
    monkeypatch.setattr(rigkeyer, "STOP_SEC", 0.5)


def test_direwolf_keyed_by_a_rig_program_has_no_ptt_line_and_sends_longer_flags_first() -> None:
    for keying in (Keying("flrig"), Keying("rigctld", "10.0.0.2:4532")):
        text = conf_text("plughw:1,0", keying, 8002)
        assert "\nPTT " not in text and f"TXDELAY {direwolf.RIG_TXDELAY_MS // 10}\n" in text
    assert "TXDELAY" not in conf_text("plughw:1,0", Keying("vox"), 8002), "the others keep Direwolf's own 300 ms"
    assert direwolf.RIG_TXDELAY_MS > 300


def test_a_key_down_may_last_the_flags_the_frames_handed_and_the_tail() -> None:
    one = direwolf.keyed_limit(1200, 1)
    assert 3.5 < one < 5.0 and direwolf.keyed_limit(1200, 3) == pytest.approx(one + 2 * direwolf.frame_sec(1200))
    assert direwolf.frame_sec(300) == pytest.approx(4 * direwolf.frame_sec(1200))


@FAKES
async def test_a_frame_handed_to_direwolf_keys_the_rig_and_its_end_lets_it_go(tmp_path: Path, fake_kind: type) -> None:
    fake = await fake_kind().start()
    m = modem(tmp_path)
    kind = "flrig" if fake_kind is FakeFlrig else "rigctld"
    await m.start(CARD, f"{kind}:127.0.0.1:{fake.port}", 0)
    await running(m)
    await until(lambda: m.frame_hold() == "")
    assert "PTT" not in (m.home / direwolf.CONF_FILE).read_text()
    assert await kiss_send(m.kiss_port, b"\xc0\x00frame\xc0") == b"\xc0\x00frame\xc0"
    await until(lambda: len(fake.downs) == 1 and fake.ptt == 0 and m.rig is not None and m.rig.state is False)
    assert m.frames_keyed == 1 and m.rig_problem == ""
    await m.stop()


@FAKES
async def test_a_direwolf_that_dies_keyed_lets_the_rig_go(tmp_path: Path, fake_kind: type) -> None:
    fake = await fake_kind().start()
    m = modem(tmp_path, die_after_sec=1.5)
    kind = "flrig" if fake_kind is FakeFlrig else "rigctld"
    await m.start(CARD, f"{kind}:127.0.0.1:{fake.port}", 0)
    await running(m)
    m._line("PTT 0 = 1")  # as Direwolf says it; then it dies
    await until(lambda: fake.ptt == 1)
    await until_started(lambda: m.reason == "stopped")
    await until(lambda: fake.ptt == 0)
    await m.stop()


@FAKES
async def test_a_rig_program_that_stops_answering_holds_the_frames_of_a_packet_radio(
    tmp_path: Path, fake_kind: type
) -> None:
    fake = await fake_kind().start()
    m = modem(tmp_path)
    kind = "flrig" if fake_kind is FakeFlrig else "rigctld"
    await m.start(CARD, f"{kind}:127.0.0.1:{fake.port}", 0)
    await running(m)
    await until(lambda: m.frame_hold() == "")
    await fake.die()
    m._line("PTT 0 = 1")
    await until(lambda: m.rig_problem == "rig_silent" and m.frame_hold() == RIG_SILENT)
    await m.stop()


async def test_the_keying_test_of_a_radio_keyed_through_rigctld_keys_the_rig(tmp_path: Path) -> None:
    fake = await FakeRigctld().start()
    m = modem(tmp_path)
    await m.start(CARD, f"rigctld:127.0.0.1:{fake.port}", 0)
    await running(m)
    await until(lambda: m.frame_hold() == "")
    await m.key_test()
    await until_started(lambda: fake.ptt == 1)
    await until_started(lambda: not m.test and fake.ptt == 0)
    assert fakedirewolf.runs(m.home)[-2][-2:] == ["-x", "p"], "the test keys by the PTT alone, no tone"
    await m.stop()
