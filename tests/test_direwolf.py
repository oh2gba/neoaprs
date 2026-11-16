"""Direwolf as NeoAPRS knows it, pure (neoaprs/direwolf.py, neoaprs/winmm.py): the pins, the configuration the daemon writes for each keying on Linux and on Windows, the command lines of the radio's run and of
Tune and the keying test, the keying proposed for an FM interface, the transmit level, and every line the daemon reads of the program, copied from Direwolf 1.8.1's source (aprs-reference/direwolf-plan.md cites
the files and lines); the WinMM devices of a card against the listing of an IC-7300 beside a computer's own sound (3 Nov 2026)."""
import re

import pytest

from neoaprs import direwolf, winmm
from neoaprs.direwolf import DeviceLists, adevice, choose_keying, command, conf_text, gain_percent, own_card
from neoaprs.mercury import Keying, SerialPort, SoundCard, parse_sound_cards
from neoaprs.radiotypes import type_of, unavailable_types
from tests.test_mercury import WINDOWS_Z


def test_the_source_is_pinned_by_its_commit_and_its_sha256() -> None:
    assert direwolf.VERSION == "1.8.1" and re.fullmatch(r"[0-9a-f]{40}", direwolf.SOURCE_COMMIT)
    assert direwolf.SOURCE_URL == f"https://github.com/wb2osz/direwolf/archive/{direwolf.SOURCE_COMMIT}.tar.gz"
    assert re.fullmatch(r"[0-9a-f]{64}", direwolf.SOURCE_SHA256), "the SHA-256 of the pinned archive (scripts/build-direwolf builds nothing without it: docs/MAINTAINING.md, \"Moving the Direwolf pin\")"


def test_the_configuration_names_the_card_the_keying_and_the_one_kiss_port_and_turns_the_rest_off() -> None:
    head = "# written by NeoAPRS at every start\nADEVICE plughw:CARD=CODEC,DEV=0\nACHANNELS 1\nCHANNEL 0\nMODEM 1200\n"
    tail = "KISSPORT 0\nKISSPORT 8002\nAGWPORT 0\nDNSSD 0\n"
    card = adevice("plughw:CARD=CODEC,DEV=0")
    assert conf_text(card, Keying("vox"), 8002) == head + tail, "VOX: no PTT line"
    assert conf_text(card, Keying("cm108"), 8002) == head + "PTT CM108\n" + tail
    assert conf_text(card, Keying("rts", "/dev/ttyUSB0"), 8002) == head + "PTT /dev/ttyUSB0 RTS\n" + tail
    assert conf_text(card, Keying("dtr", "/dev/ttyUSB1"), 8002) == head + "PTT /dev/ttyUSB1 DTR\n" + tail
    windows = conf_text(adevice("{0.0.1.x}|{0.0.0.y}", (1, 3)), Keying("rts", "COM4"), 8003)
    assert windows.splitlines()[1:6] == ["ADEVICE 1 3", "ACHANNELS 1", "CHANNEL 0", "MODEM 1200", "PTT COM4 RTS"] and "KISSPORT 8003" in windows
    with pytest.raises(ValueError):
        adevice("")                                                    # (never the system's default device, which may be the computer's speakers)
    for text in (windows, conf_text(card, Keying("cm108"), 8002)):
        lines = text.splitlines()
        assert lines.index("KISSPORT 0") < lines.index(next(line for line in lines if line.startswith("KISSPORT ") and line != "KISSPORT 0")), "slot 0 cleared before the port is given"
        assert lines.index(next(line for line in lines if line.startswith("ADEVICE"))) < lines.index(next(line for line in lines if line.startswith("PTT"))), "the card before the keying (PTT CM108 looks up its HID)"
        assert not any(word in text for word in ("MYCALL", "DIGIPEAT", "BEACON", "IGSERVER", "GPSD")), "no call, no digipeater, beacon, iGate or GPS of Direwolf's own"


@pytest.mark.parametrize("device", ["/dev/ttyUSB0\nMYCALL OH2X", "COM4\rDIGIPEAT 0 0 WIDE", "/dev/tty USB0", "COM4\x00", "/dev/ttyUSB0\u2028PTT"])
def test_a_keying_device_that_would_add_a_line_or_a_word_to_the_configuration_is_refused(device: str) -> None:
    card = adevice("plughw:CARD=CODEC,DEV=0")
    with pytest.raises(ValueError):
        conf_text(card, Keying("rts", device), 8002)
    template = len(conf_text(card, Keying("rts", "/dev/ttyUSB0"), 8002).splitlines())
    for keying in (Keying("vox"), Keying("cm108"), Keying("rts", "/dev/ttyUSB0"), Keying("dtr", "COM12")):
        assert len(conf_text(card, keying, 8002).splitlines()) <= template, "never a line more than the fixed template"


def test_the_command_lines_of_the_run_of_tune_and_of_the_keying_test() -> None:
    assert command(["direwolf"], "r/direwolf.conf") == ["direwolf", "-c", "r/direwolf.conf", "-t", "0", "-q", "d", "-a", "2", "-d", "on", "-Q", "-G", "100"]
    assert command(["direwolf"], "c", -6)[-2:] == ["-G", "50"], "the transmit level as Direwolf's percentage"
    tune = command(["direwolf"], "c", 0, "tune")
    assert tune == ["direwolf", "-c", "c", "-t", "0", "-d", "on", "-Q", "-G", "100", "-x", "a"]
    assert command(["direwolf"], "c", 0, "key")[-2:] == ["-x", "p"] and command(["direwolf"], "c", 0, "key", vox=True)[-2:] == ["-x", "m"], "the PTT alone; the mark tone on VOX, which silence does not key"
    assert [gain_percent(db) for db in (0, -3, -6, -20, -99, 5)] == [100, 71, 50, 10, 1, 100]


def test_the_keying_proposed_is_an_aiocs_pin_else_the_serial_line_of_the_cards_interface_else_vox() -> None:
    digirig, ftdi = SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60), SerialPort("/dev/ttyUSB1", 0x0403, 0x6001)
    assert choose_keying("USB Audio Device", [digirig]) == Keying("rts", "/dev/ttyUSB0"), "a Digirig keys on RTS of its CP2102"
    assert choose_keying("All-In-One-Cable", []) == Keying("cm108"), "an AIOC by its CM108 pin"
    assert choose_keying("All-In-One-Cable", [ftdi]) == Keying("cm108"), "an AIOC keys by its pin whatever other cable is plugged in: the cable is not its"
    assert choose_keying("USB Audio Device", [digirig, ftdi]) == Keying("vox"), "two such ports and nothing ties one to the card: nobody's to tell"
    assert choose_keying("HDA Intel PCH", [ftdi]) == Keying("vox"), "the computer's own sound has no serial line of its own"
    assert choose_keying("USB PnP Sound Device", [SerialPort("bt://00:11", 0x10C4, 1)]) == Keying("vox"), "a Bluetooth line keys no interface"
    second = SerialPort("/dev/ttyUSB2", 0x10C4, 0xEA60)
    assert choose_keying("USB Audio Device", [digirig, second], tied=["/dev/ttyUSB2"]) == Keying("rts", "/dev/ttyUSB2"), "two Digirigs: each card its own port, where the USB says which"
    assert choose_keying("USB Audio Device", [digirig], tied=[]) == Keying("vox"), "the one port is another device's: not keyed"


def test_the_card_chosen_for_direwolf_is_the_radios_never_the_computers_own_sound() -> None:
    codec, pch = SoundCard("plughw:CARD=CODEC,DEV=0", "USB Audio CODEC", True, True), SoundCard("plughw:CARD=PCH,DEV=0", "HDA Intel PCH", True, True, True)
    assert own_card([codec, pch]) == "plughw:CARD=CODEC,DEV=0"
    assert own_card([SoundCard("plughw:1,0", "USB Audio CODEC", True, True, True)]) == "plughw:1,0", "the radio's card is the system's default: it is named by its id"
    assert own_card([pch]) == "" and own_card([]) == "", "the computer's own sound, or nothing listed: none"


def test_the_lines_the_daemon_reads_of_direwolf() -> None:
    assert direwolf.ready_port("Ready to accept KISS TCP client application 0 on port 8002 ...") == 8002          # kissnet.c:606
    assert direwolf.ready_port("Ready to accept KISS TCP client application 0 on port 8002 (radio channel 0) ...") == 8002
    assert direwolf.ready_port("Ready to accept AGW client application 0 on port 8000 ...") is None
    assert direwolf.bind_failed("Bind failed with error: 98") and direwolf.bind_failed("Some other application is probably already using port 8002.")      # kissnet.c:569-571
    assert direwolf.audio_open_error("Could not open audio device plughw:CARD=CODEC,DEV=0 for input") and direwolf.audio_open_error("Pointless to continue without audio device.")
    assert direwolf.keying_open_error("ERROR can't open device /dev/ttyUSB0 for channel 0 PTT control.")       # ptt.c:945
    assert direwolf.keying_open_error("Config file line 6: Could not determine USB Audio GPIO PTT device for audio output plughw:CARD=Device,DEV=0.")      # config.c:2185: it would run on unkeyed
    assert direwolf.keying_open_error("Could not open /dev/hidraw3 for write, errno=13") and direwolf.keying_open_error("Write to /dev/hidraw3 failed, n=-1, errno=32")    # cm108.c:1013, 1059
    assert not direwolf.keying_open_error("Could not open audio device plughw:1,0 for input")
    assert all(direwolf.is_error(line) for line in ("Could not open /dev/hidraw3 for write, errno=13", "Config file line 6: Could not determine USB Audio GPIO PTT device for audio output x."))
    assert direwolf.kiss_from_client("<<< Data frame from KISS client application, channel 0, total length = 25")      # kiss_frame.c:964 (`-d n`)
    assert not direwolf.kiss_from_client(">>> Data frame to KISS client application, channel 0, total length = 25")
    assert all(direwolf.kiss_dump(line) for line in ("<<< Data frame from KISS client application, channel 0, total length = 25", ">>> Data frame to KISS client application, channel 0, total length = 30",
                                                     "  000:  c0 00 82 a0 a4 a6 40 40 60 9e 90 64 8e 82 a8 61  ......@@`..d...a"))
    assert not direwolf.kiss_dump("OH2XYZ audio level = 48(12/9)   [NONE]   ___|||___") and not direwolf.kiss_dump("PTT 0 = 1")
    assert direwolf.wrong_device('"3" doesn\'t match any of the input devices.') and direwolf.wrong_device("Invalid output (transmit) audio device number 7.")
    assert direwolf.several_cm108("There are multiple USB Audio Devices with GPIO capability.")
    assert direwolf.level_of("OH2XYZ audio level = 48(12/9)   [NONE]   ___|||___") == 48
    assert direwolf.level_of("ADEVICE0: Sample rate approx. 44.1 k, 0 errors, receive audio level CH0 43") == 43, "the level as it is now, which Direwolf says every STATS_SEC (audio_stats.c)"
    assert direwolf.level_of("ADEVICE0: Sample rate approx. 44.1 k, 0 errors") is None and direwolf.level_of("Audio input level is too high.  Reduce so most stations are around 50.") is None
    assert direwolf.level_of("Digipeater WIDE2 (probably N3LEE-4) audio level = 28(10/6)   [NONE]   __|||||||") == 28        # ax25_pad.c:925, direwolf.c:1308
    assert direwolf.level_of("[0.4] OH2XYZ>APDW18,WIDE1-1:!6010.00N/02450.00E-") is None
    assert (direwolf.ptt_of("PTT 0 = 1"), direwolf.ptt_of("PTT 0 = 0"), direwolf.ptt_of("DCD 0 = 1")) == (True, False, None)       # ptt.c:1341
    assert (direwolf.dcd_of("DCD 0 = 1"), direwolf.dcd_of("DCD 0 = 0"), direwolf.dcd_of("PTT 0 = 1")) == (True, False, None)
    assert direwolf.is_error("Could not open audio device x for output") and not direwolf.is_error("Dire Wolf Release 1.8.1, November 2025")


def test_the_device_lists_say_which_winmm_devices_direwolf_chose() -> None:
    lines = DeviceLists()
    for line in ("Available audio input devices for receive (*=selected):", "    0: Microphone (Realtek(R) Audio)", " *  1: Microphone (USB Audio CODEC)   (channel 0)",
                 "Available audio output devices for transmit (*=selected):", " *  0: Speakers (Realtek(R) Audio)   (channel 0)", "    1: Speakers (USB Audio CODEC)", "Using audio device ..."):
        lines.feed(line)
    assert lines.selected == {"input": (1, "Microphone (USB Audio CODEC)"), "output": (0, "Speakers (Realtek(R) Audio)")}
    assert lines.wrong((1, 1)) and not lines.wrong((1, 0))


def test_a_card_is_one_winmm_input_and_one_output_whose_names_are_its_devices_cut_to_31_characters() -> None:
    cards = parse_sound_cards(WINDOWS_Z)
    radio = next(c for c in cards if c.name == "USB Audio CODEC")
    inputs = ["Microphone (Realtek High Defini", "Microphone (USB Audio CODEC)", "Line (Webcam)"]
    outputs = ["Speakers (Realtek High Definiti", "Speakers (USB Audio CODEC)", "Headphones (Realtek High Defini"]
    assert winmm.match(radio.name, inputs, outputs) == (1, 1)
    assert winmm.names_card("Microphone (Realtek High Defini", "Realtek High Definition Audio"), "a name cut at 31 characters"
    assert not winmm.names_card("Microphone (Realtek High", "Realtek High Definition Audio"), "a name shorter than 31 is whole: it must end with the card"
    assert winmm.match("USB Audio CODEC", inputs + ["Microphone (USB Audio CODEC)"], outputs) is None, "two inputs of the card: none"
    assert winmm.match("USB Audio CODEC", inputs, outputs[:1]) is None, "no output of the card: none"
    assert winmm.devices() == ([], []), "off Windows there is no WinMM"


def test_the_type_is_an_fm_radio_on_a_sound_card_offered_where_direwolf_is_carried() -> None:
    t = type_of("direwolf")
    assert (t.kind, t.driver, t.transport, t.name, t.text) == ("fm", "direwolf", "modem", "Sound card", "radio.type.direwolf")
    assert [f.key for f in t.fields] == ["sound_card", "keying", "tx_gain_db", "beacon", "status", "path", "digipeat"] and t.field("tx_gain_db").range == (-20, 0)    # type: ignore[union-attr]
    assert t.field("sound_card") is type_of("mercury").field("sound_card") and t.field("keying") is type_of("mercury").field("keying"), "one card and one keying line are one resource for both types"
    assert t.can.tune and t.can.key_test and t.can.tx_gain and t.can.rx_level and not t.can.scope and not t.can.find
    assert unavailable_types("darwin") == ("direwolf",) and unavailable_types("linux") == () and unavailable_types("win32") == ()


def test_a_keying_holds_its_serial_port_and_on_windows_cm108_holds_the_one_chip_of_the_station() -> None:
    from neoaprs.claims import Claim, Claims
    from neoaprs.mercuryclaims import keying_claim
    assert keying_claim(Keying("rts", "/dev/ttyUSB0"), "/dev/ttyUSB0", windows=False) == "/dev/ttyUSB0" and keying_claim(Keying("vox"), None, windows=True) is None
    assert keying_claim(Keying("cm108"), None, windows=False) is None, "elsewhere the pin is the card's own chip: the card's claim covers it"
    assert keying_claim(Keying("cm108"), None, windows=True) == "cm108", "on Windows a CM108 key is any CM108-class chip: one radio at a time, whatever its type"
    claims = Claims()
    assert claims.hold(Claim("keying", "cm108", 2)) is None
    assert claims.hold(Claim("keying", "cm108", 3)) == Claim("keying", "cm108", 2), "the Mercury modem keys by CM108: a Sound card radio does not, on Windows"
