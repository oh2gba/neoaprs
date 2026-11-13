"""What the log says of the HF radio and the Mercury modem, because a person who sends the support bundle is helped from it: the program found or not (and where it was looked for), the sound card with the reason it was
chosen, the keying, the ports, the command line, Mercury's own first lines, every busy channel and every keyed radio with how long it lasted, a hold that gives up, why the program ended, and each frame over HF with its
size and the modem's SNR. The lines are the evidence, so the tests read them."""
import logging
import time
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25, kiss, mercuryhelper
from neoaprs.mercury import SerialPort, SoundCard, card_reason, frame_words
from neoaprs.mercurymodem import Mercury
from neoaprs.source import Backoff
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import MERCURY
from tests.support import fakemercury
from tests.support.env import until_started
from tests.support.fakemercury import Air
from tests.test_mercury_modem import HF, QUICK, _ports_of_this_test, modem  # noqa: F401 (the fixture keeps two tests from taking the same ports)
from tests.test_tnc import ui_frame

CARDS = [SoundCard("plughw:1,0", "USB Audio CODEC", True, True), SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True)]


def lines(caplog: pytest.LogCaptureFixture, logger: str = "neoaprs.mercury") -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == logger]


def test_the_sound_card_is_said_with_the_reason_it_was_chosen() -> None:
    assert card_reason("plughw:1,0", "plughw:1,0", []) == "'plughw:1,0', from the settings"
    chosen = card_reason("plughw:1,0", "", [CARDS[0], SoundCard("plughw:0,0", "HDA Intel PCH", True, False, True)])
    assert chosen.startswith("'USB Audio CODEC' (plughw:1,0), chosen by NeoAPRS among the cards listed:") and "'HDA Intel PCH' (plughw:0,0)" in chosen
    assert card_reason("", "", CARDS).startswith("the system's default device; no card stood out among those listed: 'USB Audio CODEC' (plughw:1,0), 'HDA Intel PCH' (plughw:0,0)")
    assert card_reason("", "", []) == "the system's default device; no card stood out among those listed: none listed"


def test_a_frame_over_the_modem_is_said_with_its_size_and_the_snr_when_there_is_one() -> None:
    assert frame_words("in", 87, "OH2XYZ", -2.4) == "HF frame heard from OH2XYZ: 87 bytes, SNR -2 dB"
    assert frame_words("in", 87, "OH2XYZ", None) == "HF frame heard from OH2XYZ: 87 bytes"
    assert frame_words("out", 64, "OH2GBA", 3.0) == "HF frame sent from OH2GBA: 64 bytes"


async def test_the_start_says_the_program_the_sound_card_and_why_the_keying_the_ports_and_the_command_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    m = modem(tmp_path)
    m.ports = lambda: [SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)]
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.state == "running")
    finally:
        await m.stop()
    said = lines(caplog)
    assert any(line.startswith("Mercury program: ") and "(not the one NeoAPRS ships)" in line for line in said), "the path, and that it is not the shipped one (the tests' stand-in)"
    assert any(line.startswith("Mercury sound card: the system's default device; no card stood out among those listed: 'USB Audio CODEC' (plughw:1,0)") for line in said)
    assert any(line.startswith("Mercury keys the radio by rts:/dev/ttyUSB0 (chosen from the sound card") for line in said)
    assert f"Mercury ports: {m.broadcast_port} for KISS, {m.control_port} for control" in said
    [started] = [line for line in said if line.startswith("Mercury started (process")]
    assert f"-b {m.broadcast_port} -p {m.control_port}" in started and "-P serial -A /dev/ttyUSB0" in started
    assert "Mercury: starting" in said and "Mercury: running" in said and "Mercury: stopped" in said


async def test_the_sound_card_and_the_keying_of_the_settings_are_said_as_the_settings(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
    finally:
        await m.stop()
    said = lines(caplog)
    assert "Mercury sound card: 'plughw:1,0', from the settings" in said and "Mercury keys the radio by rts:/dev/ttyUSB0, from the settings" in said


async def test_a_program_that_is_not_there_is_said_with_the_place_it_was_looked_for(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    m = modem(tmp_path, program=False)
    await m.start(HF)
    await m.stop()
    [said] = [line for line in lines(caplog) if line.startswith("no Mercury program at")]
    assert said.endswith(str(mercuryhelper.expected_program()))


async def test_mercurys_own_first_lines_are_in_the_log_and_the_rest_only_when_the_log_asks_for_all(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury.program")
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
    finally:
        await m.stop()
    assert any("Mercury engine initialised" in line for line in lines(caplog, "neoaprs.mercury.program")), "what the program prints as it starts is in the log"
    program = mercuryhelper.Program(lambda code, last: None)
    caplog.set_level(logging.DEBUG, "neoaprs.mercury.program")
    caplog.clear()
    for number in range(mercuryhelper.STARTUP_LINES + 5):
        program._tell(f"[INF] line {number}")
    levels = [r.levelno for r in caplog.records if r.name == "neoaprs.mercury.program"]
    assert levels[:mercuryhelper.STARTUP_LINES] == [logging.INFO] * mercuryhelper.STARTUP_LINES and set(levels[mercuryhelper.STARTUP_LINES:]) == {logging.DEBUG}, "the first lines of a run at INFO, a busy program's later ones only at DEBUG"


async def test_a_program_that_ends_is_said_with_its_last_lines_and_the_start_after_the_back_off(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    m = Mercury(tmp_path, finder=lambda: fakemercury.program(die_after_sec=0.3), backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    await m.start(HF)
    try:
        await until_started(lambda: m.starts >= 2)
    finally:
        await m.stop()
    said = lines(caplog)
    [ended] = [line for line in said[:said.index("Mercury is started again in 0.1 s") + 1] if line.startswith("Mercury ended (exit 3)")]
    assert "its last lines: " in ended and "dies as told" in ended


async def test_a_busy_channel_and_a_keyed_radio_are_one_line_each_with_how_long_and_a_hold_that_gives_up_says_so_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    air = Air(frame_sec=0.2)
    station = air.station()
    await air.start()
    m = modem(tmp_path)
    try:
        await m.start(HF, attach=station.url)
        await until_started(lambda: m.state == "running")
        station.say_control("BUSY ON")
        await until_started(lambda: m.busy)
        station.say_control("BUSY OFF")
        await until_started(lambda: not m.busy)
        station.say_control("PTT ON")
        await until_started(lambda: m.keyed)
        station.say_control("PTT OFF")
        await until_started(lambda: not m.keyed)
        said = lines(caplog)
        assert any(line.startswith("Mercury: the channel was busy for ") and line.endswith(" s") for line in said)
        assert any(line.startswith("Mercury: the radio was keyed for ") and line.endswith("(frame 1)") for line in said)
        m.busy, m._busy_at = True, time.monotonic() - 1000
        m.keyed, m._keyed_at = True, time.monotonic() - 1000
        for _ in range(3):
            assert m.hold() == ""
        gave_up = [line for line in lines(caplog) if "no longer holds our frames" in line or "not believed" in line]
        assert len(gave_up) == 2, "the busy channel and the keyed radio, once each, however often the hold is asked"
    finally:
        await m.stop()
        await air.aclose()


async def test_tune_and_the_keying_test_are_said_when_they_are_refused(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    m = modem(tmp_path, program=False)
    with pytest.raises(Exception, match="not running"):
        await m.tune()
    with pytest.raises(Exception, match="not running"):
        await m.key_test()
    assert "Mercury: the tune tone was refused: the HF radio is not running" in lines(caplog)
    assert "Mercury: the keying test was refused: the HF radio is not running" in lines(caplog)


async def test_each_frame_over_hf_is_a_line_with_its_size_and_the_snr_of_the_modem(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.tnc")
    air = Air(frame_sec=0.05)
    a, b = air.station(), air.station()
    await air.start()
    m = modem(tmp_path)
    await m.start(HF, attach=b.url)
    tnc = Tnc(b.url, profile=MERCURY, check_sec=0.0, backoff=Backoff([0.05, 0.05]), fallback_probe=False)
    tnc.modem = m
    heard: list[str] = []
    tnc.packet.connect(lambda p: heard.append(p.source))
    await tnc.start()
    try:
        await until_started(lambda: m.state == "running")
        await b.connected()
        b.say_control("SN -2.5")
        await until_started(lambda: m.snr == -2.5)
        a.heard_bytes(kiss.encode(ax25.encode(ui_frame("OH2XYZ"))))
        await until_started(lambda: heard == ["OH2XYZ"])
        await until_started(lambda: tnc.usable)
        assert tnc.send_frame(ui_frame("OH2GBA"))
        size = len(ax25.encode(ui_frame("OH2XYZ")))
        said = lines(caplog, "neoaprs.tnc")
        assert f"HF frame heard from OH2XYZ: {size} bytes, SNR -2 dB" in said
        assert f"HF frame sent from OH2GBA: {len(ax25.encode(ui_frame('OH2GBA')))} bytes" in said
        assert tnc.label == "hf radio" and any(line.startswith("hf radio: opened ") for line in said), "a line says which radio it is about"
        await until_started(lambda: m.frames_keyed == 1 and not m.keyed)               # (the fake station keys for our frame, then lets go)
        b.say_control("BUSY ON")
        await until_started(lambda: m.busy)
        assert not tnc.send_frame(ui_frame("OH2GBA"))
        assert any(line.startswith("hf radio: a frame from OH2GBA (") and line.endswith("was not sent: the channel is busy") for line in lines(caplog, "neoaprs.tnc"))
    finally:
        await tnc.stop()
        await m.stop()
        await air.aclose()
