"""What NeoAPRS knows of the Mercury HF modem without running it (neoaprs/mercury.py, the profile, the settings): the one mode and its frame, the frame cap on what the daemon sends (the beacon's comment cut, a message refused with
a reason, the Tnc's last guard), the keying as the setting keeps it, the command line and the configuration the daemon writes, what `mercury -z` and the control port print, and the moving station's floor."""
import logging
import random
import re
from dataclasses import replace
from datetime import timedelta
from itertools import combinations
from pathlib import Path

import pytest

from neoaprs import ax25, mercury
from neoaprs.config import DEFAULTS, Config
from neoaprs.configlegacy import with_legacy
from neoaprs.message import MessagingError
from neoaprs.radiorules import FM, HF
from neoaprs.services.beacon import Beacon, BeaconError
from neoaprs.services.common import fit_frame, fixed_prefix, our_frame
from neoaprs.services.sender import SendError, Sender
from neoaprs.tncprofile import MERCURY, PROFILES, profile_of
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR
from tests.support.stubtnc import StubTnc
from tests.test_messaging import started_rig

HF_CONFIG: Config = replace(ON_AIR, hf_enabled=True, fm_enabled=False, beacon_path="DIRECT")


# ---- the mode and the frame

def test_the_one_mode_is_datac3_and_its_frame_carries_123_bytes_of_a_packet_in_under_four_seconds() -> None:
    assert (mercury.MODE, mercury.MODE_INDEX, mercury.FRAME_BYTES, mercury.HEADER_BYTES, mercury.MAX_PAYLOAD) == ("DATAC3", 1, 126, 3, 123)
    assert 3.5 < mercury.FRAME_SEC < 4.5 and mercury.DELIVERY_SEC >= 3.78, "the slowest delivery scripts/mercury-measure frame saw"
    assert MERCURY.max_frame == 123 and MERCURY.transport == "modem" and MERCURY.enter == () and not MERCURY.can_probe
    assert MERCURY not in PROFILES and all(p.rules.kind == "fm" for p in PROFILES) and MERCURY.rules.kind == "hf", "the Mercury profile is the HF radio's, never a type of the FM radio (neoaprs/radios.py)"
    with pytest.raises(ValueError):
        profile_of("mercury")


def test_the_hf_dials_are_in_the_region_1_digimode_segments_and_not_the_300_baud_one() -> None:
    assert [band for band, _ in mercury.FREQUENCIES] == [30, 40, 20, 6], "and 6 m, where the first test on the air ran (4 Nov 2026)"
    dials = {band: float(dial) for band, dial in mercury.FREQUENCIES}
    assert 10.130 <= dials[30] + 0.0012 and dials[30] + 0.0018 <= 10.150, "30 m: inside 10130-10150 kHz with the 1.2 to 1.8 kHz of audio above the dial"
    assert 7.050 <= dials[40] + 0.0012 and dials[40] + 0.0018 <= 7.060
    assert 14.101 <= dials[20] + 0.0012 and dials[20] + 0.0018 <= 14.112
    assert "10.1476" not in dict(mercury.FREQUENCIES).values()


def test_the_manuals_table_of_frequencies_is_the_constant_and_the_dial_of_the_page_is_the_forty_metre_one() -> None:
    """docs/RADIOS.md prints the dials of FREQUENCIES (30, 40, 20 and 6 m) and the page says the one of DIAL_BAND, with its mode spelled out: a number changed in one place and not the other fails here."""
    manual = (Path(__file__).resolve().parent.parent / "docs" / "RADIOS.md").read_text(encoding="utf-8")
    assert [(int(band), dial) for band, dial in re.findall(r"^\| (\d+) m \| ([\d.]+) MHz \|$", manual, re.MULTILINE)] == list(mercury.FREQUENCIES)
    assert mercury.DIAL_BAND == 40 and mercury.DIAL_TEXT == "7.0541 MHz USB"
    assert mercury.DIAL_TEXT.split()[0] in dict(mercury.FREQUENCIES).values() and mercury.DIAL_TEXT.endswith(" USB")


def test_the_overflow_is_what_the_modem_would_cut_off() -> None:
    assert mercury.overflow(b"x" * 123) == 0 and mercury.overflow(b"x" * 124) == 1 and mercury.overflow(b"x" * 140) == 17
    assert mercury.too_long(b"x" * 123) is None and mercury.too_long(b"x" * 131) == "131 bytes, the radio carries 123"
    assert mercury.ports_from(8100) == (8100, 8300) and mercury.ports_from(8101) == (8101, 8301)


# ---- the frame cap on what we send

def frame_of(info: bytes, path: tuple[str, ...] = ()) -> ax25.Frame:
    return our_frame(HF_CONFIG, path, info)


def test_the_fixed_part_of_a_report_is_never_cut_the_comment_is() -> None:
    assert fixed_prefix(b"=6010.00N/02456.00E-a comment") == 20
    assert fixed_prefix(b"!6010.00N/02456.00E-PHG5132comment") == 27, "the PHG extension stays"
    assert fixed_prefix(b"=6010.00N/02456.00E>088/036/A=000123 mobile") == 27, "course and speed stay"
    assert fixed_prefix(b"@092345z4903.50N/07201.75W>RNG0050 range") == 34
    assert fixed_prefix(b"=/5L!!<*e7>7P[/A=000123 comment") == 14, "a compressed position with its symbol"
    assert fixed_prefix(b";LEADER   *092345z6012.00N/02456.00E>090/020 convoy") == 44
    assert fixed_prefix(b")AID #!6015.00N/02458.00EA first aid") == 26
    assert fixed_prefix(b">211200zQRV 145.500") == 8 and fixed_prefix(b">no time") == 1
    assert fixed_prefix(b":OH2RDG   :Hello{01") == 11
    assert fixed_prefix(b"T#005,199,000") == 13 and fixed_prefix(b"") == 0, "what has no comment is never cut"


def test_a_frame_that_fits_or_has_no_limit_is_left_as_it_is_and_a_long_comment_is_cut_to_the_limit() -> None:
    frame = frame_of(b"=6010.00N/02456.00E-" + b"c" * 110)
    assert fit_frame(frame, None) is frame and fit_frame(frame, 200) is frame
    cut = fit_frame(frame, 123)
    assert len(ax25.encode(cut)) == 123 and cut.info == b"=6010.00N/02456.00E-" + b"c" * 87 and cut.info != frame.info
    with pytest.raises(ValueError, match="shortening its comment is not enough"):
        fit_frame(frame_of(b"T#005," + b"1," * 60, ("WIDE1-1", "WIDE2-1")), 123)                   # (telemetry has no comment to cut)
    with pytest.raises(ValueError):
        fit_frame(frame_of(b":OH2RDG   :" + b"m" * 67 + b"{01", ("WIDE1-1", "WIDE2-1", "WIDE3-1", "WIDE4-1", "WIDE5-1", "WIDE6-1", "WIDE7-1", "WIDE8-1")), 80)       # (the addressee stays: 6 bytes of text are not room enough)


def test_the_beacon_cuts_its_comment_to_the_radios_frame_and_says_so_once(caplog: pytest.LogCaptureFixture) -> None:
    tnc = StubTnc(max_frame=123, rules=replace(HF, paths=True))         # (a radio with a frame cap that carries paths: over HF itself no path goes, and a beacon with its 43-character comment is 86 bytes at most, under the cap)
    long = replace(HF_CONFIG, station_comment="A comment as long as the settings allow, 43", beacon_path="WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1,WIDE5-1,WIDE6-1,WIDE7-1")
    beacon = Beacon(tnc, lambda: long, FixedClock())
    frame = beacon.frame()
    assert len(ax25.encode(frame)) == 123 and frame.info == b"=6010.20N/02456.40E-A comment as long as the settings allo"
    assert len([r for r in caplog.records if "its comment is cut" in r.message]) == 1
    beacon.frame()
    assert len([r for r in caplog.records if "its comment is cut" in r.message]) == 1, "said once for the same cut"
    assert len(ax25.encode(Beacon(StubTnc(), lambda: long, FixedClock()).frame())) > 123, "a radio with no limit sends it whole"


def test_the_sender_cuts_an_objects_comment_and_refuses_what_cannot_be_cut() -> None:
    sender = Sender(StubTnc(max_frame=123), lambda: HF_CONFIG, FixedClock())
    info = b";LEADER   *092345z6012.00N/02456.00E>090/020 " + b"c" * 70
    frame = sender.frame(info, ())
    assert len(ax25.encode(frame)) == 123 and frame.info.startswith(info[:44])
    with pytest.raises(SendError, match="not enough"):
        sender.frame(b"T#005," + b"1," * 60, ("WIDE1-1", "WIDE2-1"))


async def test_a_message_that_the_radio_would_cut_is_refused_with_the_reason_and_a_message_that_fits_goes(tmp_path: Path) -> None:
    rig = await started_rig(tmp_path, tnc=StubTnc(max_frame=123, rules=replace(HF, paths=True)), hf_enabled=True, fm_enabled=False, beacon_path="WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1")        # (a radio with a frame cap that carries paths: over HF itself no path goes, and the longest message, 67 characters to a 9-character addressee with a reply-ack, is 100 bytes)
    sent = await rig.m.send("OH2RDG", "Hello Pekka")
    assert sent.state == "sending" and rig.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1::OH2RDG   :Hello Pekka{01}"]
    with pytest.raises(MessagingError) as refused:
        await rig.m.send("OH2RDG-10", "x" * 67)
    assert refused.value.code == "message.too_long_for_radio" and refused.value.params == {"length": 128, "max": 123, "cut": 5}, "the frame (126 bytes) and the two of a reply-ack number a later attempt may carry"
    assert len(rig.tnc.sent) == 1 and rig.m.get(2) is None, "nothing was kept or sent"
    fits = await rig.m.send("OH2RDG-10", "x" * 62)
    assert fits.state == "sending" and len(ax25.encode(rig.tnc.sent[-1])) == 121, "with the two bytes of room it is 123: the last that fits"


async def test_a_message_kept_before_the_radio_changed_waits_with_the_reason_when_it_does_not_fit_now(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rig = await started_rig(tmp_path, hf_enabled=True, fm_enabled=False, beacon_path="DIRECT")
    record = await rig.m.send("OH2RDG", "x" * 67)
    assert record.attempts == 1
    rig.tnc.max_frame = 90                                                # (the radio is one with a smaller frame now)
    await rig.pass_time(33)
    assert rig.state(record.id).attempts == 1 and "cannot be sent: the message is" in caplog.text and "(it waits)" in caplog.text


# ---- the keying, the command and the configuration

def test_the_keying_is_read_from_the_setting_and_written_back_the_same() -> None:
    assert mercury.keying_of("vox") == mercury.Keying("vox") and mercury.keying_of(" VOX ").text == "vox"
    assert mercury.keying_of("cm108").kind == "cm108"
    assert mercury.keying_of("rts:/dev/ttyUSB0") == mercury.Keying("rts", "/dev/ttyUSB0") and mercury.keying_of("DTR: COM3 ").text == "dtr:COM3"
    for wrong in ("", "ptt", "rts", "dtr:", "vox:/dev/ttyUSB0", "cm108:3"):
        with pytest.raises(ValueError, match="not a way of keying") as e:
            mercury.keying_of(wrong)
        assert e.value.code == "setting.not_keying"       # type: ignore[attr-defined]


def test_the_settings_keep_the_sound_card_and_the_keying_and_refuse_a_keying_that_is_none() -> None:
    assert DEFAULTS.mercury_sound_card == "" and DEFAULTS.mercury_keying == "", "empty: the daemon chooses"
    assert Config.check("mercury/keying", "  ") == "" and Config.check("mercury/keying", "vox") == "vox"
    assert Config.check("mercury/keying", " rts:/dev/ttyUSB0 ") == "rts:/dev/ttyUSB0" and Config.check("mercury/sound_card", " plughw:1,0 ") == "plughw:1,0"
    with pytest.raises(ValueError, match="mercury/keying.*not a way of keying"):
        Config.check("mercury/keying", "ptt")
    assert Config.from_data({"mercury/keying": "nonsense"}).mercury_keying == "", "a row edited by hand falls back to the default: the daemon's choice"
    hf = Config.checked(replace(DEFAULTS, serial_port="/dev/ttyUSB0"), {"hf/enabled": "true"})
    assert hf.hf_enabled and hf.fm_enabled and hf.serial_port == "/dev/ttyUSB0", "the HF radio is a tickbox beside the FM radio, whatever the FM radio's port"
    with pytest.raises(ValueError, match="not a TNC profile"):
        Config.checked(DEFAULTS, {"tnc/profile": "mercury"})


def test_a_stored_mercury_type_of_the_one_radio_becomes_the_hf_radio_and_the_fm_radio_has_the_default_type() -> None:
    rows = with_legacy({"tnc/profile": "mercury", "station/call": "OH2GBA"})
    config = Config.from_data(rows)
    assert config.hf_enabled and not config.fm_enabled and config.tnc_profile == DEFAULTS.tnc_profile and "tnc/profile" not in rows
    assert with_legacy({"tnc/profile": "mercury", "fm/enabled": "true"})["tnc/profile"] == "mercury", "left alone when a tickbox has a row of its own"


def test_the_command_line_names_the_configuration_the_mode_the_ports_the_sound_card_and_the_keying() -> None:
    assert mercury.command(["/usr/bin/mercury"], "/data/mercury.ini", "", mercury.Keying("vox")) == ["/usr/bin/mercury", "-C", "/data/mercury.ini", "-m", "1", "-b", "8100", "-p", "8300", "-P", "none"]
    assert mercury.command(["/usr/bin/mercury"], "C:\\Users\\John Doe\\mercury.ini", "USB Audio CODEC", mercury.Keying("rts", "COM3"), 8101, 8301)[1:] == \
        ["-C", "C:\\Users\\John Doe\\mercury.ini", "-m", "1", "-b", "8101", "-p", "8301", "-i", "USB Audio CODEC", "-o", "USB Audio CODEC", "-P", "serial", "-A", "COM3"]
    assert mercury.command(["python", "-m", "fake"], "x.ini", "plughw:1,0", mercury.Keying("cm108"))[-2:] == ["-P", "cm108"]
    assert mercury.command(["m"], "x.ini", "", mercury.Keying("dtr", "/dev/ttyUSB0"))[-4:] == ["-P", "serial", "-A", "/dev/ttyUSB0"]


def test_the_configuration_switches_the_busy_detector_on_names_the_line_and_keeps_no_message_store() -> None:
    text = mercury.ini_text(mercury.Keying("dtr", "COM3"))
    assert f"[channel]\nbusy_detect = true\nbusy_threshold_db = {mercury.BUSY_THRESHOLD_DB}\n" in text and "[store]\nenabled = false" in text and "line = dtr" in text and "keepalive_s = 10" in text
    assert "line = rts" in mercury.ini_text(mercury.Keying("vox")) and "line = rts" in mercury.ini_text(mercury.Keying("rts", "/dev/ttyUSB0"))


def test_the_configuration_has_the_lead_in_tone_for_vox_and_for_no_other_keying() -> None:
    assert f"[audio]\ntx_gain_db = 0\ntx_leadin_ms = {mercury.LEADIN_MS}\n" in mercury.ini_text(mercury.Keying("vox"))
    assert mercury.LEADIN_MS > 0
    for keying in (mercury.Keying("rts", "/dev/ttyUSB0"), mercury.Keying("dtr", "COM3"), mercury.Keying("cm108")):
        text = mercury.ini_text(keying)
        assert "tx_leadin_ms" not in text, f"{keying.kind} keys the radio itself: a tone ahead of the frame would only cost channel time"


# ---- the daemon's own choice of the sound card and the keying

CARDS = [mercury.SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True), mercury.SoundCard("plughw:1,0", "USB Audio CODEC", True, True, False), mercury.SoundCard("plughw:2,0", "HDMI", True, False, False)]
PORTS = [mercury.SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60), mercury.SerialPort("/dev/ttyS0", None, None), mercury.SerialPort("bt://AA:BB:CC:DD:EE:01", None, None)]


def test_the_sound_card_chosen_is_the_one_usb_card_that_records_and_plays_else_the_systems_default() -> None:
    assert mercury.choose_sound_card(CARDS) == "plughw:1,0", "an IC-7300's codec beside the computer's own card"
    assert mercury.choose_sound_card([CARDS[0], CARDS[2]]) == "", "no radio card: the system's default device, as Mercury takes it"
    assert mercury.choose_sound_card([]) == ""
    assert mercury.choose_sound_card([CARDS[0], mercury.SoundCard("plughw:1,0", "USB PnP Sound Device", True, True, False), mercury.SoundCard("plughw:3,0", "USB Audio Device", True, True, False)]) == "", "two USB dongles: nobody can tell, the operator picks"
    assert mercury.choose_sound_card([mercury.SoundCard("plughw:0,0", "USB AUDIO  CODEC USB Audio", True, True, False), mercury.SoundCard("plughw:3,0", "USB Audio Device USB Audio", True, True, False),
                                      mercury.SoundCard("plughw:2,0", "HD-Audio Generic ALCS1200A Analog", True, True, False)]) == "plughw:0,0", "a radio's codec beside a headset dongle (John's desk): the codec"
    assert mercury.choose_sound_card([CARDS[0], mercury.SoundCard("plughw:1,0", "Something Else", True, True, False)]) == "plughw:1,0", "the one card besides the default that does both"
    assert mercury.choose_sound_card([mercury.SoundCard("plughw:1,0", "USB Audio CODEC", True, True, True)]) == "", "a radio's card that is the default already is Mercury's default too"


def test_the_keying_chosen_is_rts_of_the_one_usb_serial_port_with_a_usb_sound_card_else_vox() -> None:
    assert mercury.choose_keying("USB Audio CODEC", PORTS) == mercury.Keying("rts", "/dev/ttyUSB0"), "an IC-7300 or a DigiRig: a CP2102 beside the codec"
    assert mercury.choose_keying("USB Audio CODEC", []) == mercury.Keying("vox"), "no serial port: the radio keys itself"
    assert mercury.choose_keying("HDA Intel PCH", PORTS) == mercury.Keying("vox"), "the computer's own card: no line is the radio's"
    assert mercury.choose_keying("", PORTS) == mercury.Keying("vox")
    two = [*PORTS, mercury.SerialPort("/dev/ttyUSB1", 0x0403, 0x6001)]
    assert mercury.choose_keying("USB PnP Sound Device", two) == mercury.Keying("vox"), "two USB serial ports: nobody can tell which keys the radio"
    assert mercury.choose_keying("USB PnP Sound Device", [mercury.SerialPort("COM3", 0x10C4, 0xEA60)]) == mercury.Keying("rts", "COM3")
    assert mercury.choose_keying("USB PnP Sound Device", [mercury.SerialPort("/dev/ttyUSB0", 0x303A, 0x1001)]) == mercury.Keying("vox"), "a development board's port is not a radio's"


def test_the_proposal_is_the_daemons_choice_else_the_default_card_else_the_first_that_records_and_plays() -> None:
    codec = mercury.SoundCard("plughw:1,0", "USB AUDIO  CODEC USB Audio", True, True, False)
    own = mercury.SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True)
    assert mercury.propose_sound_card([own, codec]) == "plughw:1,0", "the card the daemon would choose"
    assert mercury.choose_sound_card([own]) == "" and mercury.propose_sound_card([own]) == "plughw:0,0", "no radio card: the system's default device, named"
    dongles = [mercury.SoundCard("plughw:2,0", "USB PnP Sound Device", True, True, False), mercury.SoundCard("plughw:3,0", "USB Audio Device", True, True, False)]
    assert mercury.choose_sound_card(dongles) == "" and mercury.propose_sound_card(dongles) == "plughw:2,0", "two that nobody can tell apart: the first that records and plays"
    assert mercury.propose_sound_card([mercury.SoundCard("plughw:5,0", "Speakers", True, False, False)]) == "plughw:5,0", "else the first card"
    assert mercury.propose_sound_card([]) == ""


def test_the_proposed_keying_follows_the_proposed_card_and_is_empty_without_cards() -> None:
    codec = mercury.SoundCard("plughw:1,0", "USB AUDIO  CODEC USB Audio", True, True, False)
    usb = [mercury.SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)]
    assert mercury.propose_keying([codec], "plughw:1,0", usb) == "rts:/dev/ttyUSB0"
    assert mercury.propose_keying([codec], "plughw:1,0", []) == "vox"
    assert mercury.propose_keying([], "", usb) == ""


# ---- what the program prints

def test_the_sound_cards_of_mercury_z_are_read_one_card_for_both_directions() -> None:
    text = ("No configuration file found: running on built-in defaults.\nListing ALSA soundcards:\nplayback devices:\n"
            "device: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)\ndevice: name: 'HDA Intel PCH'  id: 'plughw:0,0'\n"
            "capture devices:\ndevice: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)\n")
    cards = mercury.parse_sound_cards(text)
    assert cards == [mercury.SoundCard("plughw:1,0", "USB Audio CODEC", True, True, True), mercury.SoundCard("plughw:0,0", "HDA Intel PCH", True, False, False)]
    assert mercury.parse_sound_cards("playback devices:\ndevice #1: Default (system route) id=default\ncapture devices:\ndevice #1: Default (system route) id=default\n") == [mercury.SoundCard("default", "Default (system route)", True, True, True)]
    assert mercury.parse_sound_cards("Listing ALSA soundcards:\nplayback devices:\ncapture devices:\n") == [] and mercury.parse_sound_cards("") == []
    assert mercury.parse_sound_cards("device: name: 'x'  id: 'y'\n") == [], "a device line before any list is nothing"


# What Mercury 1.9.21 lists on Windows (WASAPI): each card twice, a playing and a recording device with ids of their own (OH2GAX's IC-7300 beside the computer's own sound, 3 Nov 2026).
WINDOWS_Z = ("playback devices:\n"
             "device: name: 'Speakers (Realtek High Definition Audio)'  id: '{0.0.0.00000000}.{aaaa}'  (system default)\n"
             "device: name: 'Speakers (USB Audio CODEC)'  id: '{0.0.0.00000000}.{ca03}'\n"
             "device: name: 'Headphones (Realtek High Definition Audio)'  id: '{0.0.0.00000000}.{bbbb}'\n"
             "capture devices:\n"
             "device: name: 'Microphone (USB Audio CODEC)'  id: '{0.0.1.00000000}.{2301}'\n"
             "device: name: 'Microphone (Realtek High Definition Audio)'  id: '{0.0.1.00000000}.{cccc}'  (system default)\n"
             "device: name: 'Line (Webcam)'  id: '{0.0.1.00000000}.{dddd}'\n")


def test_the_two_devices_of_a_windows_card_are_one_card_that_records_from_the_one_and_plays_to_the_other() -> None:
    cards = mercury.parse_sound_cards(WINDOWS_Z)
    assert [(c.name, c.playback, c.capture, c.default) for c in cards] == [
        ("Realtek High Definition Audio (Microphone, Speakers)", True, True, True),
        ("Realtek High Definition Audio (Microphone, Headphones)", True, True, False),
        ("USB Audio CODEC", True, True, False),
        ("Line (Webcam)", False, True, False)], "one pair for each way a card with several devices can be used, and a device with no partner as it was"
    radio = next(c for c in cards if c.name == "USB Audio CODEC")
    assert radio.id == "{0.0.1.00000000}.{2301}|{0.0.0.00000000}.{ca03}" and mercury.choose_sound_card(cards) == radio.id
    argv = mercury.command(["mercury"], "m.ini", radio.id, mercury.Keying("vox"))
    assert argv[argv.index("-i") + 1] == "{0.0.1.00000000}.{2301}" and argv[argv.index("-o") + 1] == "{0.0.0.00000000}.{ca03}"
    assert mercury.endpoints("{0.0.1.00000000}.{dddd}") == ("{0.0.1.00000000}.{dddd}", ""), "a recording device alone: the system's default device plays"
    assert mercury.endpoints("{0.0.0.00000000}.{ca03}") == ("", "{0.0.0.00000000}.{ca03}") and mercury.endpoints("plughw:1,0") == ("plughw:1,0", "plughw:1,0")
    alone = mercury.command(["mercury"], "m.ini", "{0.0.0.00000000}.{ca03}", mercury.Keying("vox"))
    assert "-i" not in alone and alone[alone.index("-o") + 1] == "{0.0.0.00000000}.{ca03}"
    assert mercury.card_with(cards, "{0.0.0.00000000}.{ca03}") == radio.id == mercury.card_with(cards, "{0.0.1.00000000}.{2301}")
    assert mercury.card_with(cards, "{0.0.0.00000000}.{nope}") == "" and mercury.card_with(cards, "plughw:1,0") == ""
    vm = mercury.parse_sound_cards("playback devices:\ndevice: name: 'Speakers (High Definition Audio Device)'  id: '{0.0.0.00000000}.{a62b}'  (system default)\n"
                                   "capture devices:\ndevice: name: 'Microphone (High Definition Audio Device)'  id: '{0.0.1.00000000}.{9507}'  (system default)\n")
    assert vm == [mercury.SoundCard("{0.0.1.00000000}.{9507}|{0.0.0.00000000}.{a62b}", "High Definition Audio Device", True, True, True)], "John's Windows VM"


def test_a_linux_card_is_kept_by_its_name_as_a_reboot_renumbers_the_cards(tmp_path: Path) -> None:
    text = ("playback devices:\ndevice: name: 'USB Audio Device USB Audio'  id: 'plughw:0,0'\ndevice: name: 'USB AUDIO  CODEC USB Audio'  id: 'plughw:3,0'\n"
            "capture devices:\ndevice: name: 'USB Audio Device USB Audio'  id: 'plughw:0,0'\ndevice: name: 'USB AUDIO  CODEC USB Audio'  id: 'plughw:3,0'\n")
    cards = mercury.parse_sound_cards(text, {0: "Device", 3: "CODEC"})
    assert [(c.id, c.numbered) for c in cards] == [("plughw:CARD=Device,DEV=0", "plughw:0,0"), ("plughw:CARD=CODEC,DEV=0", "plughw:3,0")], "John's FTX-1 and FTdx101D, 4 Nov 2026"
    assert all(c.playback and c.capture for c in cards)
    assert [c.id for c in mercury.parse_sound_cards(text)] == ["plughw:0,0", "plughw:3,0"], "no names known: the numbers as listed"
    assert mercury.stable_alsa_id("hw:1,0", {1: "PCH"}) == "hw:CARD=PCH,DEV=0" and mercury.stable_alsa_id("default", {0: "x"}) == "default"
    argv = mercury.command(["mercury"], "m.ini", "plughw:CARD=CODEC,DEV=0", mercury.Keying("vox"))
    assert argv[argv.index("-i") + 1] == argv[argv.index("-o") + 1] == "plughw:CARD=CODEC,DEV=0"
    from neoaprs.mercuryhelper import alsa_card_names
    for number, name in ((0, "Device"), (3, "CODEC")):
        (tmp_path / f"card{number}").mkdir()
        (tmp_path / f"card{number}" / "id").write_text(name + "\n")
    (tmp_path / "cards").write_text("")
    assert alsa_card_names(tmp_path) == {0: "Device", 3: "CODEC"} and alsa_card_names(tmp_path / "none") == {}


def test_a_setting_that_names_one_device_of_a_windows_card_starts_mercury_on_both(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    from neoaprs import mercuryhelper
    listed: list[int] = []

    def fake_list(program: object, timeout_sec: float = 0) -> list[mercury.SoundCard]:
        listed.append(1)
        return mercury.parse_sound_cards(WINDOWS_Z)
    monkeypatch.setattr(mercuryhelper, "list_sound_cards", fake_list)
    with caplog.at_level(logging.INFO, logger="neoaprs.mercury"):
        card, _ = mercuryhelper.choose_setup(["mercury"], "{0.0.0.00000000}.{ca03}", "vox", lambda: [])
    assert card == "{0.0.1.00000000}.{2301}|{0.0.0.00000000}.{ca03}" and listed == [1]
    assert "both devices of the card whose one device the setting names" in caplog.text and "'USB Audio CODEC'" in caplog.text
    card, _ = mercuryhelper.choose_setup(["mercury"], "plughw:1,0", "vox", lambda: [])
    assert card == "plughw:1,0" and listed == [1], "a whole card in the setting: nothing is listed"
    card, _ = mercuryhelper.choose_setup(["mercury"], "{0.0.1.00000000}.{dddd}", "vox", lambda: [])
    assert card == "{0.0.1.00000000}.{dddd}", "a device with no partner stays as it is"


def test_the_lines_of_the_control_port_are_read_as_mercury_writes_them() -> None:
    assert mercury.parse_control_line("PTT ON") == mercury.ControlEvent("ptt", on=True, text="PTT ON")
    assert mercury.parse_control_line("PTT OFF\r").on is False and mercury.parse_control_line("BUSY ON").kind == "busy"
    assert mercury.parse_control_line("SN -2.5") == mercury.ControlEvent("snr", value=-2.5, text="SN -2.5")
    assert mercury.parse_control_line("BUFFER 126").value == 126.0 and mercury.parse_control_line("IAMALIVE").kind == "alive"
    assert mercury.parse_control_line("SN lots").kind == "other" and mercury.parse_control_line("REGISTERED OH2GBA").kind == "other"
    buffer = bytearray(b"PTT ON\rBUSY ON\r\nSN 3")
    assert mercury.split_control_lines(buffer) == ["PTT ON", "BUSY ON"] and bytes(buffer) == b"SN 3"
    buffer.extend(b".0\r")
    assert mercury.split_control_lines(buffer) == ["SN 3.0"] and not buffer


# ---- the rules of the HF radio: no path, no digipeater, no moving station, the beacon's own interval

def test_over_mercury_every_frame_goes_direct_whatever_the_path_settings_say_and_the_settings_are_kept() -> None:
    hf = replace(HF_CONFIG, beacon_path="WIDE1-1,WIDE2-1")
    tnc = StubTnc(max_frame=123)
    beacon = Beacon(tnc, lambda: hf, FixedClock())
    assert beacon.frame().path == () and hf.beacon_path_calls == ("WIDE1-1", "WIDE2-1"), "the frame is direct, the setting untouched"
    sender = Sender(tnc, lambda: hf, FixedClock())
    assert sender.frame(b">status", ("WIDE1-1",)).path == () and sender.frame(b">status", None).path == ()
    assert Beacon(StubTnc(), lambda: hf, FixedClock()).frame().path_text == "WIDE1-1,WIDE2-1", "the FM radio carries it"


async def test_over_mercury_a_message_and_its_ack_go_direct_even_to_a_station_with_a_path_of_its_own(tmp_path: Path) -> None:
    rig = await started_rig(tmp_path, tnc=StubTnc(max_frame=123), hf_enabled=True, fm_enabled=False, beacon_path="WIDE1-1,WIDE2-1")
    await rig.prefs.set_path("OH2RDG", "OH2RCH-2,WIDE2-1")
    record = await rig.m.send("OH2RDG", "x" * 67)
    assert record.attempts == 1 and rig.lines() == ["OH2GBA>APZNEO::OH2RDG   :" + "x" * 67 + "{01}"], "the longest message fits the frame with room for a reply-ack number, and goes direct"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert rig.lines()[-1] == "OH2GBA>APZNEO::OH2RDG   :ack12"
    assert [a.path for a in rig.m.delivery.attempts_of(record.id)] == [()], "the chain of the message shows direct only"


def test_over_mercury_a_moving_station_sends_its_timed_beacon_at_the_fix_and_the_one_interval_has_a_random_pause() -> None:
    moving = replace(HF_CONFIG, gps_source="gpsd", beacon_travel="car", beacon_interval_min=30)
    clock = FixedClock()
    beacon = Beacon(StubTnc(max_frame=123), lambda: moving, clock)
    assert beacon.interval_min == 30, "the one interval of the station"
    with pytest.raises(BeaconError, match="no GPS|fix"):
        beacon.frame()                                                           # (a moving station on HF: the timed beacon says where it is now, and nothing without a fresh fix)
    assert Beacon(StubTnc(max_frame=123), lambda: replace(moving, gps_source="off"), clock).frame().info.startswith(b"=6010.20N/02456.40E-"), "a fixed station: its home"
    paused = Beacon(StubTnc(max_frame=123), lambda: moving, clock)
    paused.jitter = lambda most: most / 2
    paused.last_sent, paused._started = clock(), clock()
    paused._plan(30)
    assert paused.next_due == clock() + timedelta(minutes=30) + timedelta(seconds=150), "the interval, then the pause"
    unpaused = Beacon(StubTnc(), lambda: replace(moving, gps_source="off", hf_enabled=False, fm_enabled=True, beacon_interval_min=20), clock)
    unpaused.jitter = lambda most: 999.0
    unpaused.last_sent, unpaused._started = clock(), clock()
    unpaused._plan(20)
    assert unpaused.next_due == clock() + timedelta(minutes=20), "the FM radio has no pause"
    assert HF.beacon_min_min == 30 and HF.beacon_jitter_sec == 300 and not HF.smart_beacon and not HF.paths and not HF.digipeat
    assert FM.paths and FM.digipeat and FM.smart_beacon and FM.beacon_jitter_sec == 0 and FM.max_frame is None


def test_the_one_beacon_interval_is_raised_to_30_minutes_while_the_hf_radio_is_on_and_is_todays_otherwise() -> None:
    assert DEFAULTS.beacon_interval_min == 0 and not hasattr(DEFAULTS, "hf_beacon_interval_min"), "one setting for both radios"
    fm_only = replace(DEFAULTS, beacon_interval_min=20)
    assert fm_only.beacon_interval() == 20, "with HF off, today's floor of 20"
    both = replace(fm_only, hf_enabled=True)
    assert both.beacon_interval() == 30, "with HF on, 30 at the least, for both beacons"
    assert replace(both, beacon_interval_min=60).beacon_interval() == 60 and replace(both, beacon_interval_min=0).beacon_interval() == 0, "a longer interval stays, Off stays Off"
    with pytest.raises(ValueError, match="no_radio|at least one radio"):
        Config.checked(DEFAULTS, {"fm/enabled": "false"})
    assert Config.checked(replace(DEFAULTS, hf_enabled=True), {"fm/enabled": "false"}).hf_enabled, "the FM radio may go when the HF one is on"


def test_the_random_pause_keeps_stations_with_the_same_interval_apart_on_the_simulated_hour() -> None:
    """Five fixed stations on the same hour and the same clock: without the pause they key up together every time; with it, two overlap in about a round in four, which the next round and the retry of a message absorb."""
    rng = random.Random(7)
    frame_sec = mercury.FRAME_SEC
    rounds = 2000
    together = sum(1 for _ in range(rounds) if any(abs(a - b) < frame_sec for a, b in combinations([0.0] * 5, 2)))
    assert together == rounds, "with no pause all five key together at the hour"
    overlapping = 0
    for _ in range(rounds):
        starts = [rng.uniform(0, HF.beacon_jitter_sec) for _ in range(5)]
        overlapping += any(abs(a - b) < frame_sec for a, b in combinations(starts, 2))
    assert 0.15 < overlapping / rounds < 0.35, overlapping / rounds
    pairs = sum(1 for _ in range(rounds) if abs(rng.uniform(0, HF.beacon_jitter_sec) - rng.uniform(0, HF.beacon_jitter_sec)) < frame_sec)
    assert pairs / rounds < 0.05, "two stations on one interval overlap in a few rounds of a hundred"



# ---- the ack of a message heard while the radio is held

class HeldTnc(StubTnc):
    """A connected radio that takes no frame while `held` says why: the modem transmits, or the channel is busy."""

    def __init__(self) -> None:
        super().__init__(max_frame=123)
        self.held = ""

    @property
    def usable(self) -> bool:
        return super().usable and not self.held

    def why_unusable(self) -> str:
        return self.held or super().why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return not self.held and super().send_frame(frame, raw)


async def test_the_ack_of_a_message_heard_while_the_radio_is_held_waits_and_goes_when_the_radio_takes_frames_again(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.messaging")
    tnc = HeldTnc()
    rig = await started_rig(tmp_path, tnc=tnc, hf_enabled=True, fm_enabled=False, beacon_path="DIRECT")
    tnc.held = "the channel is busy"                                     # (the frame was decoded while the sender's tail was still on the air: the busy detector holds us)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert rig.lines() == [] and len(rig.m.acks.waiting) == 1 and "waits: the channel is busy" in caplog.text
    await rig.pass_time(1)
    assert rig.lines() == [], "held still: nothing goes"
    tnc.held = ""
    await rig.pass_time(1)
    assert rig.lines() == ["OH2GBA>APZNEO::OH2RDG   :ack12"] and rig.m.acks.waiting == []
    assert "would not take it" not in caplog.text


async def test_an_ack_that_waited_longer_than_a_minute_is_dropped_because_the_sender_sends_again(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.messaging")
    tnc = HeldTnc()
    rig = await started_rig(tmp_path, tnc=tnc, hf_enabled=True, fm_enabled=False, beacon_path="DIRECT")
    tnc.held = "the radio is transmitting"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    await rig.pass_time(61)
    tnc.held = ""
    await rig.pass_time(1)
    assert rig.lines() == [] and rig.m.acks.waiting == [] and "is dropped: the sender sends again" in caplog.text


def test_the_lines_that_say_the_sound_card_could_not_be_opened_are_known_and_the_others_are_not() -> None:
    assert mercury.audio_open_error("22:16:22.912 [+0.003s] [ERR] [audio-play] error in audio->open(): 1: snd_pcm_hw_params_set_access: (-22) Invalid argument")
    assert mercury.audio_open_error("[ERR] [audio-cap] error in audio->open(): -1: No such device")
    assert mercury.audio_open_error("[ERR] [audio-play] Error in audio->init(): PulseAudio is not in this build")
    for line in ("[WRN] [modem-rx] decoder ring full (mode=12): dropped 100 samples so far", "[INF] [audio-play] opened plughw:1,0", "[ERR] [tcp-ctl] Control recv returned 0 (err=0), closing", "[ERR] [audio-play] Failed to allocate playback buffers"):
        assert not mercury.audio_open_error(line), line


def test_a_windows_radio_whose_two_devices_carry_different_numbers_is_one_card_and_two_alike_radios_stay_two() -> None:
    def listed(playing: list[str], recording: list[str]) -> str:
        return ("playback devices:\n" + "".join(f"device: name: '{name}'  id: '{{0.0.0.00000000}}.{{p{i}}}'\n" for i, name in enumerate(playing))
                + "capture devices:\n" + "".join(f"device: name: '{name}'  id: '{{0.0.1.00000000}}.{{r{i}}}'\n" for i, name in enumerate(recording)))
    realtek = ["Speakers (Realtek High Definition Audio)", "Headphones (Realtek High Definition Audio)"]
    cards = mercury.parse_sound_cards(listed([*realtek, "Speakers (2- USB Audio CODEC)"], ["Microphone (Realtek High Definition Audio)", "Microphone (USB Audio CODEC)"]))
    radio = [c for c in cards if "USB Audio CODEC" in c.name]
    assert [(c.name, c.id) for c in radio] == [("USB Audio CODEC", "{0.0.1.00000000}.{r1}|{0.0.0.00000000}.{p2}")], "a radio moved to another USB port: its devices numbered apart"
    assert mercury.choose_sound_card(cards) == radio[0].id, "the radio, not the computer's own headphones"
    two = mercury.parse_sound_cards(listed(["Speakers (USB Audio CODEC)", "Speakers (2- USB Audio CODEC)"], ["Microphone (2- USB Audio CODEC)", "Microphone (USB Audio CODEC)"]))
    assert [(c.name, c.id) for c in two] == [("USB Audio CODEC", "{0.0.1.00000000}.{r1}|{0.0.0.00000000}.{p0}"), ("2- USB Audio CODEC", "{0.0.1.00000000}.{r0}|{0.0.0.00000000}.{p1}")], \
        "two radios of the same codec: each by its own name"
    unsure = mercury.parse_sound_cards(listed(["Speakers (2- USB Audio CODEC)", "Speakers (3- USB Audio CODEC)"], ["Microphone (USB Audio CODEC)"]))
    assert all(not (c.playback and c.capture) for c in unsure), "which playing device goes with the microphone nobody can tell: each stays alone"
