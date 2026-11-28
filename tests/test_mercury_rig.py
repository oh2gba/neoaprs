"""A Mercury radio keyed through flrig or rigctld: Mercury keys nothing itself, waits longer before its
audio, and NeoAPRS keys the rig on its PTT ON and lets it go on PTT OFF, a stop, a lost control line and
its own limit (stand-ins: tests/support/fakemercury.py, tests/support/fakerig.py)."""

import time
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import direwolf, mercury, mercurychannel, mercurymodem, rigkeyer
from neoaprs.claims import Claims
from neoaprs.mercuryclaims import keying_claim
from neoaprs.rigkeyer import RIG_SILENT
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import remember_stop, until, until_started
from tests.support.fakemercury import Air, of_radio
from tests.support.fakerig import FakeFlrig, FakeRig, FakeRigctld
from tests.support.modemports import own_ports
from tests.test_mercury_modem import HF

FAKES = pytest.mark.parametrize("fake_kind", [FakeFlrig, FakeRigctld], ids=["flrig", "rigctld"])


@pytest.fixture(autouse=True)
def _quick(monkeypatch: pytest.MonkeyPatch) -> None:
    own_ports(monkeypatch)
    monkeypatch.setattr(rigkeyer, "PROBE_SEC", 0.05)
    monkeypatch.setattr(rigkeyer, "RETRY_SEC", (0.02, 0.05))
    monkeypatch.setattr(rigkeyer, "STOP_SEC", 0.5)


def test_the_rig_kinds_are_read_with_or_without_an_address_and_claim_no_serial_port() -> None:
    assert mercury.keying_of("flrig") == mercury.Keying("flrig") and mercury.keying_of(" RIGCTLD ").text == "rigctld"
    assert mercury.keying_of("flrig").address == ("127.0.0.1", 12345)
    assert mercury.keying_of("rigctld").address == ("127.0.0.1", 4532)
    remote = mercury.keying_of("rigctld:192.168.1.5:4533")
    assert remote.text == "rigctld:192.168.1.5:4533" and remote.address == ("192.168.1.5", 4533) and remote.rig
    assert mercury.keying_of("flrig:[::1]:12345").address == ("::1", 12345)
    for wrong in ("flrig:localhost", "rigctld:host:0", "rigctld:host:65536", "flrig::12345", "rigctld:h:x"):
        with pytest.raises(ValueError, match="not host:port") as e:
            mercury.keying_of(wrong)
        assert e.value.code == "setting.not_hostport"  # type: ignore[attr-defined]
    for wrong in ("flrig:a b:1", "rigctld:\x1b:1"):
        with pytest.raises(ValueError, match="not a way of keying"):
            mercury.keying_of(wrong)
    assert keying_claim(remote, "192.168.1.5:4533") is None and keying_claim(mercury.Keying("flrig"), None) is None
    assert keying_claim(mercury.Keying("rts", "COM3"), "COM3") == "COM3"


def test_the_daemons_own_choice_never_keys_through_a_rig_program() -> None:
    usb = [mercury.SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)]
    two = [*usb, mercury.SerialPort("/dev/ttyUSB1", 0x0403, 0x6001)]
    for card in ("USB Audio CODEC", "All-In-One-Cable", "HDA Intel PCH", ""):
        for ports in ([], usb, two):
            assert not mercury.choose_keying(card, ports).rig
            assert not direwolf.choose_keying(card, ports).rig and not direwolf.choose_keying(card, ports, []).rig


def test_mercury_keyed_by_a_rig_program_keys_nothing_itself_and_waits_for_the_rig_before_its_audio() -> None:
    for keying in (mercury.Keying("flrig"), mercury.Keying("rigctld", "10.0.0.2:4532")):
        assert mercury.command(["m"], "x.ini", "", keying)[-2:] == ["-P", "none"]
        text = mercury.ini_text(keying)
        assert f"[audio]\ntx_gain_db = -4\ntx_delay_ms = {mercury.RIG_TX_DELAY_MS}\n" in text
        assert "tx_leadin_ms" not in text
    for keying in (mercury.Keying("vox"), mercury.Keying("rts", "COM3"), mercury.Keying("cm108")):
        assert "tx_delay_ms" not in mercury.ini_text(keying), "the others keep Mercury's own 10 ms"
    assert 0 < mercury.RIG_TX_DELAY_MS <= 2000, "Mercury takes 0 to 2000 ms"
    assert mercury.RIG_FRAME_SEC == pytest.approx(4.09)


async def started(tmp_path: Path, fake: FakeRig, air: Air) -> tuple[mercurymodem.Mercury, fakemercury.FakeMercury]:
    station = air.station()
    await air.start()
    remember_stop(air.aclose)
    kind = "flrig" if isinstance(fake, FakeFlrig) else "rigctld"
    m = mercurymodem.Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=Backoff([0.1]),
        control_backoff=Backoff([0.05]),
        **of_radio(tmp_path),
    )
    m.ports = lambda: []
    remember_stop(m.stop)
    await m.start(replace(HF, mercury_keying=f"{kind}:127.0.0.1:{fake.port}"), attach=station.url)
    await until_started(lambda: m.state == "running" and m.frame_hold() == "")
    return m, station


@FAKES
async def test_ptt_on_keys_the_rig_at_once_and_ptt_off_lets_it_go(tmp_path: Path, fake_kind: type) -> None:
    fake = await fake_kind().start()
    m, station = await started(tmp_path, fake, Air(frame_sec=0.3))
    said = time.monotonic()
    station.say_control("PTT ON")
    await until(lambda: fake.ptt == 1)
    latency = fake.downs[-1] - said
    assert m.keyed and m.frame_hold() != ""
    station.say_control("PTT OFF")
    await until(lambda: fake.ptt == 0 and m.rig is not None and m.rig.state is False)
    assert latency < 0.1, f"{latency * 1000:.0f} ms from the modem's PTT ON to the rig program's key-down"
    assert m.rig_problem == ""


@FAKES
async def test_a_lost_control_line_and_a_stop_key_the_rig_up(tmp_path: Path, fake_kind: type) -> None:
    fake = await fake_kind().start()
    m, station = await started(tmp_path, fake, Air(frame_sec=0.3))
    station.say_control("PTT ON")
    await until(lambda: fake.ptt == 1)
    station.drop_control()
    await until(lambda: fake.ptt == 0)
    await until_started(lambda: m.state == "running")
    station.say_control("PTT ON")
    await until(lambda: fake.ptt == 1)
    await m.stop()
    assert fake.ptt == 0 and m.rig is None


@FAKES
@pytest.mark.expects_errors
async def test_a_ptt_on_without_its_ptt_off_is_ended_after_the_frame(
    tmp_path: Path, fake_kind: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mercurychannel, "RIG_FRAME_SEC", 0.2)
    monkeypatch.setattr(mercurychannel, "RIG_MARGIN_SEC", 0.1)
    fake = await fake_kind().start()
    m, station = await started(tmp_path, fake, Air(frame_sec=0.3))
    station.say_control("PTT ON")
    await until(lambda: fake.ptt == 1)
    await until(lambda: fake.ptt == 0)
    assert fake.ups[-1] - fake.downs[-1] < 0.6 and m.rig_problem == "rig_keyed_long"


@FAKES
async def test_a_rig_program_that_does_not_answer_holds_the_frames_and_the_radio_says_so(
    tmp_path: Path, fake_kind: type
) -> None:
    fake = await fake_kind().start()
    m, station = await started(tmp_path, fake, Air(frame_sec=0.3))
    fake.mode = "refuse"
    station.say_control("PTT ON")
    await until(lambda: m.rig_problem == "rig_silent")
    assert m.frame_hold() == RIG_SILENT
    station.say_control("PTT OFF")
    fake.mode = "ok"
    await until(lambda: m.rig_problem == "" and m.frame_hold() == "")


async def test_a_mercury_the_daemon_starts_for_flrig_gets_no_keying_of_its_own(tmp_path: Path) -> None:
    fake = await FakeFlrig().start()
    m = mercurymodem.Mercury(
        tmp_path, finder=fakemercury.program, backoff=Backoff([0.1]), **of_radio(tmp_path, claims=Claims())
    )
    m.ports = lambda: []
    remember_stop(m.stop)
    await m.start(replace(HF, mercury_keying=f"flrig:127.0.0.1:{fake.port}"))
    await until_started(lambda: m.state == "running")
    ini = (m.home / mercurymodem.INI_FILE).read_text()
    assert f"tx_delay_ms = {mercury.RIG_TX_DELAY_MS}" in ini and m.keying.rig
    assert not [c for c in m.claims.all() if c.kind == "keying"] if m.claims is not None else True
    await until(lambda: fake.keyed and fake.keyed[0].on is False)
    await m.stop()
