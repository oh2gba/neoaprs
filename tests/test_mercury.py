"""What NeoAPRS knows of the Mercury HF modem without running it (neoaprs/mercury.py, the profile, the settings): the one mode and its frame, the frame cap on what the daemon sends (the beacon's comment cut, a message refused with
a reason, the Tnc's last guard), the keying as the setting keeps it, the command line and the configuration the daemon writes, what `mercury -z` and the control port print, and the moving station's floor."""
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25, mercury
from neoaprs.config import DEFAULTS, Config
from neoaprs.message import MessagingError
from neoaprs.services.beacon import Beacon
from neoaprs.services.common import fit_frame, fixed_prefix, our_frame
from neoaprs.services.sender import SendError, Sender
from neoaprs.tncprofile import MERCURY, PROFILES, profile_of
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR
from tests.support.stubtnc import StubTnc
from tests.test_messaging import started_rig

HF: Config = replace(ON_AIR, tnc_profile="mercury", beacon_path="DIRECT")


# ---- the mode and the frame

def test_the_one_mode_is_datac3_and_its_frame_carries_123_bytes_of_a_packet_in_under_four_seconds() -> None:
    assert (mercury.MODE, mercury.MODE_INDEX, mercury.FRAME_BYTES, mercury.HEADER_BYTES, mercury.MAX_PAYLOAD) == ("DATAC3", 1, 126, 3, 123)
    assert 3.5 < mercury.FRAME_SEC < 4.5 and mercury.DELIVERY_SEC > mercury.FRAME_SEC
    assert MERCURY.max_frame == 123 and MERCURY.transport == "modem" and MERCURY.enter == () and not MERCURY.can_probe
    assert profile_of("mercury") is MERCURY and MERCURY in PROFILES and PROFILES.index(MERCURY) == len(PROFILES) - 2, "before the Dummy, after the real TNCs"


def test_the_frequencies_are_three_dials_in_the_region_1_digimode_segments_and_not_the_300_baud_one() -> None:
    assert [band for band, _ in mercury.FREQUENCIES] == [30, 40, 20]
    dials = {band: float(dial) for band, dial in mercury.FREQUENCIES}
    assert 10.130 <= dials[30] + 0.0012 and dials[30] + 0.0018 <= 10.150, "30 m: inside 10130-10150 kHz with the 1.2 to 1.8 kHz of audio above the dial"
    assert 7.050 <= dials[40] + 0.0012 and dials[40] + 0.0018 <= 7.060
    assert 14.101 <= dials[20] + 0.0012 and dials[20] + 0.0018 <= 14.112
    assert "10.1476" not in dict(mercury.FREQUENCIES).values()


def test_the_overflow_is_what_the_modem_would_cut_off() -> None:
    assert mercury.overflow(b"x" * 123) == 0 and mercury.overflow(b"x" * 124) == 1 and mercury.overflow(b"x" * 140) == 17
    assert mercury.too_long(b"x" * 123) is None and mercury.too_long(b"x" * 131) == "131 bytes, the radio carries 123"
    assert mercury.ports_from(8100) == (8100, 8300) and mercury.ports_from(8101) == (8101, 8301)


# ---- the frame cap on what we send

def frame_of(info: bytes, path: tuple[str, ...] = ()) -> ax25.Frame:
    return our_frame(HF, path, info)


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
    tnc = StubTnc(max_frame=123)
    long = replace(HF, station_comment="A comment as long as the settings allow, 43", beacon_path="WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1,WIDE5-1,WIDE6-1,WIDE7-1")
    beacon = Beacon(tnc, lambda: long, FixedClock())
    frame = beacon.frame()
    assert len(ax25.encode(frame)) == 123 and frame.info == b"=6010.20N/02456.40E-A comment as long as the settings allo"
    assert len([r for r in caplog.records if "its comment is cut" in r.message]) == 1
    beacon.frame()
    assert len([r for r in caplog.records if "its comment is cut" in r.message]) == 1, "said once for the same cut"
    assert len(ax25.encode(Beacon(StubTnc(), lambda: long, FixedClock()).frame())) > 123, "a radio with no limit sends it whole"


def test_the_sender_cuts_an_objects_comment_and_refuses_what_cannot_be_cut() -> None:
    sender = Sender(StubTnc(max_frame=123), lambda: HF, FixedClock())
    info = b";LEADER   *092345z6012.00N/02456.00E>090/020 " + b"c" * 70
    frame = sender.frame(info, ())
    assert len(ax25.encode(frame)) == 123 and frame.info.startswith(info[:44])
    with pytest.raises(SendError, match="not enough"):
        sender.frame(b"T#005," + b"1," * 60, ("WIDE1-1", "WIDE2-1"))


async def test_a_message_that_the_radio_would_cut_is_refused_with_the_reason_and_a_message_that_fits_goes(tmp_path: Path) -> None:
    rig = await started_rig(tmp_path, tnc=StubTnc(max_frame=123), tnc_profile="mercury", beacon_path="WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1")
    sent = await rig.m.send("OH2RDG", "Hello Pekka")
    assert sent.state == "sending" and rig.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1::OH2RDG   :Hello Pekka{01}"]
    with pytest.raises(MessagingError) as refused:
        await rig.m.send("OH2RDG-10", "x" * 67)
    assert refused.value.code == "message.too_long_for_radio" and refused.value.params == {"length": 128, "max": 123, "cut": 5}, "the frame (126 bytes) and the two of a reply-ack number a later attempt may carry"
    assert len(rig.tnc.sent) == 1 and rig.m.get(2) is None, "nothing was kept or sent"
    fits = await rig.m.send("OH2RDG-10", "x" * 62)
    assert fits.state == "sending" and len(ax25.encode(rig.tnc.sent[-1])) == 121, "with the two bytes of room it is 123: the last that fits"


async def test_a_message_kept_before_the_radio_changed_waits_with_the_reason_when_it_does_not_fit_now(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rig = await started_rig(tmp_path, tnc_profile="mercury", beacon_path="DIRECT")
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
    assert DEFAULTS.mercury_sound_card == "" and DEFAULTS.mercury_keying == "vox"
    assert Config.check("mercury/keying", " rts:/dev/ttyUSB0 ") == "rts:/dev/ttyUSB0" and Config.check("mercury/sound_card", " plughw:1,0 ") == "plughw:1,0"
    with pytest.raises(ValueError, match="mercury/keying.*not a way of keying"):
        Config.check("mercury/keying", "ptt")
    assert Config.from_data({"mercury/keying": "nonsense"}).mercury_keying == "vox", "a row edited by hand falls back to the default"
    with pytest.raises(ValueError, match="not to the serial port /dev/ttyUSB0"):
        Config.checked(replace(DEFAULTS, serial_port="/dev/ttyUSB0"), {"tnc/profile": "mercury"})
    assert Config.checked(DEFAULTS, {"tnc/profile": "mercury", "serial/port": "tcp://127.0.0.1:8100"}).profile is MERCURY, "a Mercury something else runs"


def test_the_command_line_names_the_configuration_the_mode_the_ports_the_sound_card_and_the_keying() -> None:
    assert mercury.command(["/usr/bin/mercury"], "/data/mercury.ini", "", mercury.Keying("vox")) == ["/usr/bin/mercury", "-C", "/data/mercury.ini", "-m", "1", "-b", "8100", "-p", "8300", "-P", "none"]
    assert mercury.command(["/usr/bin/mercury"], "C:\\Users\\John Doe\\mercury.ini", "USB Audio CODEC", mercury.Keying("rts", "COM3"), 8101, 8301)[1:] == \
        ["-C", "C:\\Users\\John Doe\\mercury.ini", "-m", "1", "-b", "8101", "-p", "8301", "-i", "USB Audio CODEC", "-o", "USB Audio CODEC", "-P", "serial", "-A", "COM3"]
    assert mercury.command(["python", "-m", "fake"], "x.ini", "plughw:1,0", mercury.Keying("cm108"))[-2:] == ["-P", "cm108"]
    assert mercury.command(["m"], "x.ini", "", mercury.Keying("dtr", "/dev/ttyUSB0"))[-4:] == ["-P", "serial", "-A", "/dev/ttyUSB0"]


def test_the_configuration_switches_the_busy_detector_on_names_the_line_and_keeps_no_message_store() -> None:
    text = mercury.ini_text(mercury.Keying("dtr", "COM3"))
    assert "[channel]\nbusy_detect = true" in text and "[store]\nenabled = false" in text and "line = dtr" in text and "keepalive_s = 10" in text
    assert "line = rts" in mercury.ini_text(mercury.Keying("vox")) and "line = rts" in mercury.ini_text(mercury.Keying("rts", "/dev/ttyUSB0"))


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


# ---- the moving station

def test_a_moving_station_over_mercury_beacons_no_oftener_than_every_five_minutes_and_the_other_radios_as_before() -> None:
    hf = replace(HF, gps_source="gpsd", beacon_travel="car")
    assert hf.smart.fast_sec == 300.0 and hf.smart.turn_min_sec == 300.0 and hf.smart.slow_sec == 1800.0 and hf.smart.fast_kmh == 100.0
    assert replace(hf, tnc_profile="kiss").smart.fast_sec == 60.0 and replace(hf, beacon_travel="foot").smart.fast_sec == 300.0
    assert mercury.BEACON_FLOOR_SEC == 300


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
    rig = await started_rig(tmp_path, tnc=tnc, tnc_profile="mercury", beacon_path="DIRECT")
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
    rig = await started_rig(tmp_path, tnc=tnc, tnc_profile="mercury", beacon_path="DIRECT")
    tnc.held = "the radio is transmitting"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    await rig.pass_time(61)
    tnc.held = ""
    await rig.pass_time(1)
    assert rig.lines() == [] and rig.m.acks.waiting == [] and "is dropped: the sender sends again" in caplog.text
