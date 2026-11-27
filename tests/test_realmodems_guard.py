"""Tests for the refusal of tests/realmodems (real modems on virtual sound cables): they run only with their
variable, on Linux with no sound card, on the null sinks and ALSA devices of their own asoundrc, and a
run without the variable collects none of them."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from tests.realmodems.stations import ASOUNDRC, ENV, STATIONS, Machine, Radio, Station, cards, refusal, sinks

ROOT = Path(__file__).resolve().parent.parent
CABLES = ROOT / "tests" / "realmodems" / "cables"
NO_CARDS = "--- no soundcards ---\n"
A_CARD = """\
 0 [CODEC          ]: USB-Audio - USB Audio CODEC
                      Burr-Brown from TI USB Audio CODEC at usb-0000:00:14.0-2, full speed
"""
NULL_SINKS = "".join(
    f"{n}\t{name}\tPipeWire\tfloat32le 1ch 48000Hz\tSUSPENDED\n"
    for n, name in enumerate(("vhf_a_out", "vhf_g_out", "hf_g_out", "hf_b_out", "p300_h1_out", "p300_h2_out"), 1)
)
RUNNER = Machine(NO_CARDS, NULL_SINKS, ASOUNDRC.read_text(encoding="utf-8"), "linux")
ON = {ENV: "1"}


def test_the_cards_and_the_sinks_are_read() -> None:
    assert cards(NO_CARDS) == {} and cards(A_CARD) == {"CODEC": "USB-Audio"}
    assert sinks(NULL_SINKS) == {"vhf_a_out", "vhf_g_out", "hf_g_out", "hf_b_out", "p300_h1_out", "p300_h2_out"}


def test_the_virtual_cables_alone_let_the_stations_run_with_or_without_alsa_in_the_kernel() -> None:
    assert refusal(ON, RUNNER) == ""
    assert refusal(ON, replace(RUNNER, cards=None)) == ""


def test_without_the_variable_nothing_runs() -> None:
    assert ENV in refusal({}, RUNNER)
    assert ENV in refusal({ENV: "yes"}, RUNNER)


def test_a_computer_with_a_sound_card_is_refused() -> None:
    assert "CODEC" in refusal(ON, replace(RUNNER, cards=A_CARD))


def test_off_linux_nothing_runs() -> None:
    assert refusal(ON, replace(RUNNER, platform="win32"))


def test_another_asoundrc_or_another_sink_is_refused() -> None:
    assert "asoundrc" in refusal(ON, replace(RUNNER, asoundrc=None))
    assert "asoundrc" in refusal(ON, replace(RUNNER, asoundrc="pcm.!default { type hw card 0 }\n"))
    speakers = NULL_SINKS + "5\talsa_output.pci-0000_00_1f.3.analog-stereo\tmodule-alsa-card.c\ts16le 2ch\tIDLE\n"
    assert "sinks" in refusal(ON, replace(RUNNER, sinks=speakers))
    assert "sinks" in refusal(ON, replace(RUNNER, sinks=None))


def test_a_station_on_a_device_that_is_not_virtual_is_refused() -> None:
    elsewhere = Station("OH2AA", 60.0, 24.0, (Radio("direwolf", "plughw:CARD=CODEC,DEV=0"),))
    assert "plughw:CARD=CODEC" in refusal(ON, RUNNER, (*STATIONS, elsewhere))


def test_each_station_plays_into_its_own_sink_and_hears_only_the_other_end() -> None:
    lines = ASOUNDRC.read_text(encoding="utf-8").split("pcm.")[1:]
    ends = {line.split()[0]: line for line in lines}
    assert sorted(ends) == sorted(r.sound_card for s in STATIONS for r in s.radios)
    for name, other in (("vhf_a", "vhf_g"), ("hf_g", "hf_b"), ("p300_h1", "p300_h2")):
        for one, two in ((name, other), (other, name)):
            assert f'playback.pcm {{ type pipewire playback_node "{one}_out" }}' in ends[one]
            assert f'capture.pcm {{ type pipewire capture_node "{two}_in" }}' in ends[one]
    # an end's source is its own sink's monitor
    assert 'master="${end}_out.monitor" source_name="${end}_in"' in CABLES.read_text(encoding="utf-8")


def test_a_run_without_the_variable_collects_none_of_the_real_modem_tests() -> None:
    env = {k: v for k, v in os.environ.items() if k != ENV}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "tests/realmodems"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert "test_digipeating" not in done.stdout and done.returncode == 5, done.stdout + done.stderr
