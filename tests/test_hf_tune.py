"""Tune and the keying test of the HF radio (neoaprs/mercurymodem.py, Mercury's own TUNE command on its control port, neoaprs/mercury.py): the tone keys the radio through the modem and stops by itself, a second press
stops it early, the keying test is the quiet second, both hold our frames meanwhile, both are refused while the modem is not running or the radio is not free, and the page asks for them with `hf_tune` and
`hf_key_test` and is refused while RX only is ticked (`transmit.off`)."""
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercurymodem
from neoaprs.coded import CodedError
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import KEY_TEST_LEVEL_DBFS, KEY_TEST_SEC, TUNE_LEVEL_DBFS, TUNE_OFF, TUNE_SEC, TUNE_TONE_HZ, tune_command
from neoaprs.mercurymodem import NOT_RUNNING, TRANSMITTING, Mercury
from neoaprs.source import Backoff
from tests.support.env import Env, until
from tests.support.fakemercury import Air, FakeMercury

HF: Config = replace(DEFAULTS, hf_enabled=True, fm_enabled=False, mercury_keying="rts:/dev/ttyUSB0", mercury_sound_card="plughw:1,0", station_call="OH2GBA")


def test_the_tone_and_its_length_are_mercurys_own_numbers_and_the_keying_test_is_the_quiet_second() -> None:
    assert TUNE_TONE_HZ == 1000 and TUNE_LEVEL_DBFS == -15.0, "Mercury's TUNE tone and its default level: VARA's, inside the 1200 to 1800 Hz the modes occupy"
    assert 5.0 <= TUNE_SEC <= 30.0, "long enough for an automatic tuner and a meter, well under Mercury's 60 s deadline"
    assert KEY_TEST_SEC == 1.0 and KEY_TEST_LEVEL_DBFS == -60.0, "what Mercury's own -Q keys for, at the quietest level TUNE takes"
    assert tune_command(TUNE_LEVEL_DBFS) == "TUNE -15" and tune_command(KEY_TEST_LEVEL_DBFS) == "TUNE -60" and TUNE_OFF == "TUNE OFF"


async def running(tmp_path: Path, air: Air) -> tuple[Mercury, FakeMercury]:
    station = air.station()
    await air.start()
    m = Mercury(tmp_path, backoff=Backoff([0.1, 0.1]), control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    await m.start(HF, attach=station.url)
    await until(lambda: m.state == "running")
    return m, station


async def test_tune_keys_the_radio_with_the_tone_holds_our_frames_and_stops_by_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercurymodem, "TUNE_SEC", 0.3)
    air = Air(frame_sec=0.2)
    m, station = await running(tmp_path, air)
    try:
        assert m.test == "" and m.hold() == ""
        await m.tune()
        assert m.test == "tune" and m.hold() == TRANSMITTING and m.describe() == "Mercury DATAC3, tuning"
        await until(lambda: station.tuned == ["TUNE -15"] and m.keyed)
        await until(lambda: m.test == "", 2.0)
        await until(lambda: station.tuned == ["TUNE -15", "TUNE OFF"] and not m.keyed)                  # (the TUNE OFF is written at the end; the fake station reads it a moment later, longer on a slow runner)
        assert m.hold() == "" and m.describe() == "Mercury DATAC3, listening"
    finally:
        await m.stop()
        await air.aclose()


async def test_a_second_press_stops_the_tone_early_and_the_keying_test_is_one_quiet_second(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercurymodem, "KEY_TEST_SEC", 0.2)
    air = Air(frame_sec=0.2)
    m, station = await running(tmp_path, air)
    try:
        await m.tune()
        await until(lambda: m.keyed)
        await m.tune_stop()
        assert m.test == ""
        await until(lambda: not m.keyed)
        assert station.tuned == ["TUNE -15", "TUNE OFF"]
        await m.tune_stop()                                                   # (nothing on: nothing said)
        assert station.tuned == ["TUNE -15", "TUNE OFF"]
        await m.key_test()
        assert m.test == "key" and m.hold() == TRANSMITTING and m.describe() == "Mercury DATAC3, keyed"
        await until(lambda: m.test == "", 2.0)
        await until(lambda: station.tuned[2:] == ["TUNE -60", "TUNE OFF"])
    finally:
        await m.stop()
        await air.aclose()


async def test_the_tone_is_refused_while_the_modem_is_not_running_or_the_radio_is_not_free_and_a_stop_ends_a_tone_under_way(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    m, station = await running(tmp_path, air)
    try:
        station.say_control("BUSY ON")
        await until(lambda: m.busy)
        with pytest.raises(CodedError, match="the channel is busy") as refused:
            await m.tune()
        assert refused.value.code == "hf.held" and station.tuned == []
        station.say_control("BUSY OFF")
        await until(lambda: not m.busy)
        await m.key_test()
        with pytest.raises(CodedError, match=NOT_RUNNING):                  # (a stop takes the tone with it; afterwards nothing runs)
            await m.stop()
            await m.tune()
        assert station.tuned == ["TUNE -60", "TUNE OFF"] and m.test == ""
    finally:
        await m.stop()
        await air.aclose()


async def test_the_page_asks_for_tune_and_the_keying_test_and_is_refused_while_rx_only_is_ticked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercurymodem, "TUNE_SEC", 0.3)
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    page = await e.ws()
    await page.send({"cmd": "subscribe", "topics": ["hf"]})
    await page.until(lambda: page.topics["hf"]["modem"]["state"] == "running")
    await page.send({"cmd": "hf_tune", "on": True})
    await page.until(lambda: page.topics["hf"]["modem"]["test"] == "tune" and page.topics["hf"]["modem"]["keyed"])
    await page.send({"cmd": "hf_tune", "on": False})
    await page.until(lambda: page.topics["hf"]["modem"]["test"] == "")
    await page.send({"cmd": "hf_key_test"})
    await page.until(lambda: page.topics["hf"]["modem"]["test"] == "key")
    await page.until(lambda: page.topics["hf"]["modem"]["test"] == "", 3.0)
    assert station.tuned == ["TUNE -15", "TUNE OFF", "TUNE -60", "TUNE OFF"]
    await e.ctl.change_config(lambda c: replace(c, station_transmit=False))
    for cmd in ({"cmd": "hf_tune", "on": True}, {"cmd": "hf_key_test"}):
        await page.send(cmd)
        error = await page.expect("error")
        assert error["code"] == "transmit.off"
    assert station.tuned[4:] == []
    await e.ctl.change_config(lambda c: replace(c, station_transmit=True, station_call=""))
    for cmd in ({"cmd": "hf_tune", "on": True}, {"cmd": "hf_key_test"}):
        await page.send(cmd)
        error = await page.expect("error")
        assert error["code"] == "other" and "call" in error["text"], "no call to send under: no tone either"
    assert station.tuned[4:] == []
    await e.stop()
    await asyncio.sleep(0)
    await air.aclose()
