"""Tests for Tune and the keying test of the HF radio (neoaprs/mercurymodem.py, neoaprs/mercury.py):
tone start and stop, frame holding, refusals, and the page commands `radio_tune` and
`radio_key_test`."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.claims import Claim
from neoaprs.coded import CodedError
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import (
    KEY_TEST_LEVEL_DBFS,
    key_test_level,
    KEY_TEST_SEC,
    TUNE_LEVEL_DBFS,
    TUNE_OFF,
    TUNE_SEC,
    TUNE_TONE_HZ,
    tune_command,
)
from neoaprs.mercurymodem import TRANSMITTING, Mercury
from neoaprs import mercurytune
from neoaprs.mercurytune import NOT_RUNNING
from neoaprs.radiotype import HF_ID
from neoaprs.source import Backoff
from tests.support.env import START_SEC, Env, until_started
from tests.support.fakemercury import Air, FakeMercury, of_radio

HF: Config = replace(
    DEFAULTS,
    hf_enabled=True,
    fm_enabled=False,
    mercury_keying="rts:/dev/ttyUSB0",
    mercury_sound_card="plughw:1,0",
    station_call="OH2GBA",
)


def test_the_tone_and_its_length_are_mercurys_own_numbers_and_the_keying_test_is_the_quiet_second() -> None:
    assert TUNE_TONE_HZ == 1000 and TUNE_LEVEL_DBFS == -15.0, (
        "Mercury's TUNE tone and its default level: VARA's, inside the 1200 to 1800 Hz the modes occupy"
    )
    assert 5.0 <= TUNE_SEC <= 30.0, "long enough for an automatic tuner and a meter, well under Mercury's 60 s deadline"
    assert KEY_TEST_SEC == 1.0 and KEY_TEST_LEVEL_DBFS == -60.0, (
        "what Mercury's own -Q keys for, at the quietest level TUNE takes"
    )
    assert (
        tune_command(TUNE_LEVEL_DBFS) == "TUNE -15"
        and tune_command(KEY_TEST_LEVEL_DBFS) == "TUNE -60"
        and TUNE_OFF == "TUNE OFF"
    )


async def running(tmp_path: Path, air: Air) -> tuple[Mercury, FakeMercury]:
    station = air.station()
    await air.start()
    m = Mercury(tmp_path, backoff=Backoff([0.1, 0.1]), control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path))
    m.ports = lambda: []
    await m.start(HF, attach=station.url)
    await until_started(lambda: m.state == "running")
    return m, station


async def test_tune_keys_the_radio_with_the_tone_holds_our_frames_and_stops_by_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mercurytune, "TUNE_SEC", 0.3)
    air = Air(frame_sec=0.2)
    m, station = await running(tmp_path, air)
    try:
        assert m.test == "" and m.hold() == ""
        assert m.held() == [Claim("modem_ports", str(m.broadcast_port), HF_ID)], (
            "the attached Mercury's pair is the radio's; its card and keying are the program's own, chosen by nobody here"
        )
        await m.tune()
        assert m.test == "tune" and m.hold() == TRANSMITTING and m.describe() == "Mercury DATAC3, tuning"
        await until_started(lambda: station.tuned == ["TUNE -15"] and m.keyed)
        await until_started(lambda: m.test == "")
        # (the TUNE OFF is written at the end; the fake station reads it a moment later, longer on a
        # slow runner)
        await until_started(lambda: station.tuned == ["TUNE -15", "TUNE OFF"] and not m.keyed)
        assert m.hold() == "" and m.describe() == "Mercury DATAC3, listening"
    finally:
        await m.stop()
        await air.aclose()
    assert m.held() == [], "let go at the stop"


async def test_a_second_press_stops_the_tone_early_and_the_keying_test_is_one_quiet_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mercurytune, "KEY_TEST_SEC", 0.2)
    air = Air(frame_sec=0.2)
    m, station = await running(tmp_path, air)
    try:
        await m.tune()
        await until_started(lambda: m.keyed)
        await m.tune_stop()
        assert m.test == ""
        await until_started(lambda: not m.keyed)
        assert station.tuned == ["TUNE -15", "TUNE OFF"]
        await m.tune_stop()  # (nothing on: nothing said)
        assert station.tuned == ["TUNE -15", "TUNE OFF"]
        await m.key_test()
        assert m.test == "key" and m.hold() == TRANSMITTING and m.describe() == "Mercury DATAC3, keyed"
        await until_started(lambda: m.test == "")
        await until_started(lambda: station.tuned[2:] == ["TUNE -60", "TUNE OFF"])
    finally:
        await m.stop()
        await air.aclose()


async def test_the_keying_test_of_a_radio_that_keys_on_audio_sends_the_tune_tone_and_of_a_line_stays_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VOX keys on audio: a silent test would leave the radio in receive. RTS, DTR and CM108 key the
    line whatever the tone is."""
    monkeypatch.setattr(mercurytune, "KEY_TEST_SEC", 0.2)
    assert [key_test_level(k) for k in ("vox", "rts", "dtr", "cm108")] == [
        TUNE_LEVEL_DBFS,
        KEY_TEST_LEVEL_DBFS,
        KEY_TEST_LEVEL_DBFS,
        KEY_TEST_LEVEL_DBFS,
    ]
    for keying, sent in (("vox", "TUNE -15"), ("cm108", "TUNE -60"), ("dtr:/dev/ttyUSB0", "TUNE -60")):
        air = Air(frame_sec=0.2)
        station = air.station()
        await air.start()
        m = Mercury(tmp_path, backoff=Backoff([0.1, 0.1]), control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path))
        m.ports = lambda: []
        await m.start(replace(HF, mercury_keying=keying), attach=station.url)
        try:
            await until_started(lambda m=m: m.state == "running")
            await m.key_test()
            await until_started(lambda m=m: m.test == "")
            await until_started(lambda station=station, sent=sent: station.tuned == [sent, "TUNE OFF"])
        finally:
            await m.stop()
            await air.aclose()


async def test_the_tone_is_refused_while_the_modem_is_not_running_or_the_radio_is_not_free_and_a_stop_ends_a_tone_under_way(
    tmp_path: Path,
) -> None:
    air = Air(frame_sec=0.2)
    m, station = await running(tmp_path, air)
    try:
        station.say_control("BUSY ON")
        await until_started(lambda: m.busy)
        with pytest.raises(CodedError, match="the channel is busy") as refused:
            await m.tune()
        assert refused.value.code == "hf.held" and station.tuned == []
        station.say_control("BUSY OFF")
        await until_started(lambda: not m.busy)
        await m.key_test()
        # (a stop takes the tone with it; afterwards nothing runs)
        with pytest.raises(CodedError, match=NOT_RUNNING):
            await m.stop()
            await m.tune()
        assert station.tuned == ["TUNE -60", "TUNE OFF"] and m.test == ""
    finally:
        await m.stop()
        await air.aclose()


async def test_the_page_asks_for_tune_and_the_keying_test_and_is_refused_while_rx_only_is_ticked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mercurytune, "TUNE_SEC", 0.3)
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    page = await e.ws()
    modem = lambda: page.topics.get("radios", {}).get("2", {}).get("modem") or {}  # noqa: E731
    await page.until(lambda: modem().get("state") == "running", START_SEC)
    assert modem()["frequencies"][0] == {"band": "80 m", "dial": "3.5850 MHz USB"}, (
        "the daemon owns the frequencies the page shows"
    )
    await page.send({"cmd": "radio_tune", "radio": 2, "on": True})
    await page.until(lambda: modem()["test"] == "tune" and modem()["keyed"])
    await page.send({"cmd": "radio_tune", "radio": 2, "on": False})
    await page.until(lambda: modem()["test"] == "")
    await page.send({"cmd": "radio_key_test", "radio": 2})
    await page.until(lambda: modem()["test"] == "key")
    await page.until(lambda: modem()["test"] == "", START_SEC)
    assert station.tuned == ["TUNE -15", "TUNE OFF", "TUNE -15", "TUNE OFF"], (
        "(the keying here is the default, VOX: the test sends the tone)"
    )
    await e.ctl.change_config(lambda c: replace(c, station_transmit=False))
    for cmd in ({"cmd": "radio_tune", "radio": 2, "on": True}, {"cmd": "radio_key_test", "radio": 2}):
        await page.send(cmd)
        error = await page.expect("error")
        assert error["code"] == "transmit.off"
    assert station.tuned[4:] == []
    await e.ctl.change_config(lambda c: replace(c, station_transmit=True, station_call=""))
    for cmd in ({"cmd": "radio_tune", "radio": 2, "on": True}, {"cmd": "radio_key_test", "radio": 2}):
        await page.send(cmd)
        error = await page.expect("error")
        assert error["code"] == "transmit.call" and error["params"]["why"] == "call.none" and "call" in error["text"], (
            "no call to send under: no tone either (coded: the page says it in its language)"
        )
    assert station.tuned[4:] == []
    await e.stop()
    await asyncio.sleep(0)
    await air.aclose()


async def attached(tmp_path: Path, air: Air, reconnect_sec: float) -> tuple[Mercury, FakeMercury]:
    """A Mercury run elsewhere whose control line comes back `reconnect_sec` after it is lost."""
    station = air.station()
    await air.start()
    m = Mercury(tmp_path, backoff=Backoff([0.1]), control_backoff=Backoff([reconnect_sec]), **of_radio(tmp_path))
    m.ports = lambda: []
    await m.start(HF, attach=station.url)
    await until_started(lambda: m.state == "running" and station.control_connections == 1)
    return m, station


async def test_a_tone_that_ends_while_the_control_line_is_down_is_ended_when_the_line_is_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TUNE has no length: an unwritten TUNE OFF would leave the radio keyed with no Stop on the page."""
    monkeypatch.setattr(mercurytune, "TUNE_SEC", 0.2)
    air = Air(frame_sec=0.2)
    m, station = await attached(tmp_path, air, reconnect_sec=3.0)
    try:
        await m.tune()
        await until_started(lambda: station.tuned == ["TUNE -15"])
        station.drop_control()
        await until_started(lambda: m.state == "starting")
        assert m.test == "tune" and m.hold() == TRANSMITTING, "the tone may still be on: the page keeps its Stop"
        await until_started(lambda: station.tuned == ["TUNE -15", "TUNE OFF"] and m.test == "")
        assert station.control_connections == 2 and m.state == "running"
    finally:
        await m.stop()
        await air.aclose()


async def test_stop_while_the_control_line_is_down_is_written_when_it_is_back(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    m, station = await attached(tmp_path, air, reconnect_sec=3.0)
    try:
        await m.tune()
        await until_started(lambda: station.tuned == ["TUNE -15"])
        station.drop_control()
        await until_started(lambda: m.state == "starting")
        await m.tune_stop()
        assert m.test == "tune", "nothing told Mercury yet"
        await until_started(lambda: station.tuned == ["TUNE -15", "TUNE OFF"] and m.test == "")
    finally:
        await m.stop()
        await air.aclose()


async def test_a_stop_without_the_control_line_ends_the_program_which_drops_the_keying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Run:
        running = True
        stopped = 0

        def stop(self) -> None:
            self.running = False
            self.stopped += 1

    m = Mercury(tmp_path, backoff=Backoff([60.0]), **of_radio(tmp_path))
    run = Run()
    monkeypatch.setattr(m, "_program", run)
    m._config, m.state, m.test = HF, "starting", "tune"
    try:
        await m.tune_stop()
        assert m.state == "waiting" and m.problem == mercurytune.OFF_UNSENT and m.test == ""
        await until_started(lambda: run.stopped == 1)
    finally:
        await m.stop()


async def test_the_radios_stop_writes_an_owed_tune_off(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    m, station = await attached(tmp_path, air, reconnect_sec=3.0)
    try:
        await m.tune()
        await until_started(lambda: station.tuned == ["TUNE -15"])
        m._off_owed, m.test = True, ""
        await m.stop()
        await until_started(lambda: station.tuned == ["TUNE -15", "TUNE OFF"])
        assert m.test == "" and not m._off_owed
    finally:
        await m.stop()
        await air.aclose()
