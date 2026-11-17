"""A sound card's own levels (neoaprs/soundmixer.py, neoaprs/winmixer.py): on Linux the card's ALSA controls through a made-up ALSA library that the real calls are made to (the C-Media chip of an FTX-1 with
Speaker, Mic and its Auto Gain Control switch, a TI codec with PCM alone, a card with nothing of ours, one that is not there), the percent of a control's range both ways; on Windows the master volumes of the
card's two devices through a stand-in for Core Audio; and under the no-devices switch nothing is read or set and no library is loaded. No real card of this machine is touched: none may be."""
import ctypes
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

from neoaprs import soundmixer
from neoaprs.cardlevels import SystemMixer
from neoaprs.soundmixer import NONE, Alsa, Control, Levels, alsa_control_name, percent, pick, raw_of
from neoaprs.winmixer import Windows
from tests.test_no_devices import under_the_switch  # noqa: F401  (the fixture)

LOAD_ALSA = soundmixer.load_alsa          # (the real one: tests/support/guards.py puts one that finds no library in its place in every test)


@dataclass
class Elem:
    name: str
    playback: list[int] | None = None          # [low, high, raw]
    capture: list[int] | None = None
    index: int = 0
    switch: bool = False                       # a switch alone (the Auto Gain Control): no volume either way


@dataclass
class FakeAlsa:
    """The calls of the ALSA library the module makes, on made-up cards by control device (`hw:Device`): what is set is kept, and every call that is not a read is written down."""
    cards: dict[str, list[Elem]]
    calls: list[str] = field(default_factory=list)
    attached: str = ""

    def __post_init__(self) -> None:
        self._elems: list[Elem] = []

    def snd_mixer_open(self, handle: Any, mode: int) -> int:
        handle._obj.value = 1
        return 0

    def snd_mixer_attach(self, handle: Any, name: bytes) -> int:
        self.attached = name.decode()
        if self.attached not in self.cards:
            return -19                         # (ENODEV: the card is not there)
        self._elems = self.cards[self.attached]
        return 0

    def snd_mixer_selem_register(self, handle: Any, options: Any, classp: Any) -> int:
        return 0

    def snd_mixer_load(self, handle: Any) -> int:
        return 0

    def snd_mixer_close(self, handle: Any) -> int:
        self.calls.append(f"close {self.attached}")
        return 0

    def snd_mixer_first_elem(self, handle: Any) -> int | None:
        return 1 if self._elems else None

    def snd_mixer_elem_next(self, elem: int) -> int | None:
        return elem + 1 if elem < len(self._elems) else None

    def _e(self, elem: int) -> Elem:
        return self._elems[elem - 1]

    def snd_mixer_selem_get_name(self, elem: int) -> bytes:
        return self._e(elem).name.encode()

    def snd_mixer_selem_get_index(self, elem: int) -> int:
        return self._e(elem).index

    def __getattr__(self, call: str) -> Any:
        """The calls of either way (`snd_mixer_selem_has_playback_volume`, `..._get_capture_volume_range`, ...), on the made-up control."""
        for way in ("playback", "capture"):
            if call == f"snd_mixer_selem_has_{way}_volume":
                return lambda elem: int(getattr(self._e(elem), way) is not None)
            if call == f"snd_mixer_selem_get_{way}_volume_range":
                return lambda elem, low, high: self._out(low, getattr(self._e(elem), way)[0]) or self._out(high, getattr(self._e(elem), way)[1])
            if call == f"snd_mixer_selem_get_{way}_volume":
                return lambda elem, channel, value: self._out(value, getattr(self._e(elem), way)[2])
            if call == f"snd_mixer_selem_set_{way}_volume_all":
                return lambda elem, value: self._set(elem, way, value.value)
        raise AttributeError(call)

    @staticmethod
    def _out(pointer: Any, value: int) -> int:
        pointer._obj.value = value
        return 0

    def _set(self, elem: int, way: str, raw: int) -> int:
        self.calls.append(f"set {self._e(elem).name} {way} {raw}")
        getattr(self._e(elem), way)[2] = raw
        return 0


def ftx1_card() -> list[Elem]:
    """The FTX-1's C-Media chip as `amixer -c Device` shows it: Speaker at 14 of 0..37 (38 %), Mic with a monitor volume and a capture volume, the Auto Gain Control switch."""
    return [Elem("Speaker", playback=[0, 37, 14]), Elem("Mic", playback=[0, 31, 0], capture=[0, 16, 8]), Elem("Auto Gain Control", switch=True)]


def codec_card() -> list[Elem]:
    """A TI "USB AUDIO CODEC": PCM playback alone, no capture control."""
    return [Elem("PCM", playback=[0, 128, 128])]


def alsa(**cards: list[Elem]) -> tuple[Alsa, FakeAlsa]:
    lib = FakeAlsa({f"hw:{name}": elems for name, elems in cards.items()})
    return Alsa(lambda: lib), lib


def test_the_alsa_control_device_is_the_card_the_setting_names_and_none_for_a_device_that_names_no_card() -> None:
    assert [alsa_control_name(card) for card in ("plughw:CARD=Device,DEV=0", "plughw:1,0", "hw:2,0", "sysdefault:CARD=CODEC", "front:CARD=Device,DEV=0")] == ["hw:Device", "hw:1", "hw:2", "hw:CODEC", "hw:Device"]
    assert [alsa_control_name(card) for card in ("default", "pulse", "")] == ["", "", ""], "the system's own mixer is not the card's"


def test_a_percent_is_the_raw_value_within_the_range_both_ways() -> None:
    assert (percent(0, 37, 14), percent(0, 128, 128), percent(-10, 10, 0), percent(5, 5, 5)) == (38, 100, 50, 0)
    assert (raw_of(0, 37, 38), raw_of(0, 128, 100), raw_of(-10, 10, 50), raw_of(0, 37, 150), raw_of(0, 37, -3)) == (14, 128, 0, 37, 0)


def test_the_controls_are_the_first_of_their_names_the_card_has_and_mic_is_never_the_playback_one() -> None:
    controls = [Control("Mic", playback=(0, 31, 0), capture=(0, 16, 8)), Control("Speaker", playback=(0, 37, 14))]
    assert pick(controls, soundmixer.PLAYBACK_NAMES, "playback") == controls[1]
    assert pick(controls, soundmixer.CAPTURE_NAMES, "capture") == controls[0]
    assert pick([Control("Master", playback=(0, 1, 1)), Control("PCM", playback=(0, 1, 1))], soundmixer.PLAYBACK_NAMES, "playback") == Control("Master", playback=(0, 1, 1))
    assert pick([Control("Line", capture=(0, 1, 1))], soundmixer.CAPTURE_NAMES, "capture") is None


def test_the_ftx1s_card_has_both_levels_and_a_set_moves_the_volumes_alone_never_the_auto_gain_switch() -> None:
    mixer, lib = alsa(Device=ftx1_card())
    assert mixer.read("plughw:CARD=Device,DEV=0") == Levels(38, 50)
    assert mixer.write("plughw:CARD=Device,DEV=0", 70, 25) == Levels(70, 25)
    assert [c for c in lib.calls if c.startswith("set")] == ["set Speaker playback 26", "set Mic capture 4"], "the Speaker and the Mic's capture, nothing else: not the Mic's monitor, not the switch"
    assert lib.cards["hw:Device"][1].playback == [0, 31, 0] and all(c.endswith("hw:Device") for c in lib.calls if c.startswith("close")), "every mixer opened is closed"


def test_a_value_not_given_is_not_written() -> None:
    mixer, lib = alsa(Device=ftx1_card())
    assert mixer.write("plughw:CARD=Device,DEV=0", None, 25) == Levels(38, 25)
    assert [c for c in lib.calls if c.startswith("set")] == ["set Mic capture 4"]


def test_a_codec_with_pcm_alone_has_a_playback_level_and_no_capture_level_and_a_capture_value_is_not_written() -> None:
    mixer, lib = alsa(CODEC=codec_card())
    assert mixer.write("plughw:CARD=CODEC,DEV=0", None, 40) == Levels(100, None)
    assert not [c for c in lib.calls if c.startswith("set")]


def test_a_card_that_is_not_there_a_card_with_none_of_the_controls_and_no_library_have_no_levels() -> None:
    mixer, lib = alsa(Device=[Elem("Auto Gain Control", switch=True), Elem("Speaker", playback=[0, 9, 9], index=1)])
    assert mixer.read("plughw:CARD=Gone,DEV=0") == NONE and lib.calls == ["close hw:Gone"], "a card unplugged: the mixer is closed again and there are no levels"
    assert mixer.read("plughw:CARD=Device,DEV=0") == NONE, "a switch alone, and a second control of a name, are none of ours"
    assert mixer.read("default") == NONE
    assert Alsa(lambda: None).read("plughw:CARD=Device,DEV=0") == NONE, "a system without the library"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the ALSA library is Linux's")
def test_the_library_is_looked_for_by_its_name_and_none_is_no_library(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> Any:
        raise OSError(f"{name}: cannot open shared object file")
    monkeypatch.setattr(ctypes, "CDLL", missing)
    assert LOAD_ALSA() is None


@dataclass
class FakeCoreAudio:
    """Core Audio's master volumes by device id, as a test has them; what is put is kept."""
    volumes: dict[str, float]
    put_calls: list[tuple[str, float]] = field(default_factory=list)

    def get(self, device: str) -> float | None:
        return self.volumes.get(device)

    def put(self, device: str, scalar: float) -> None:
        self.put_calls.append((device, scalar))
        if device in self.volumes:
            self.volumes[device] = scalar


RECORDING, PLAYING = "{0.0.1.00000000}.{2301}", "{0.0.0.00000000}.{ca03}"
WINDOWS_CARD = f"{RECORDING}|{PLAYING}"


def test_on_windows_the_levels_are_the_master_volumes_of_the_cards_playing_and_recording_device() -> None:
    audio = FakeCoreAudio({RECORDING: 0.5, PLAYING: 0.384})
    mixer = Windows(audio)
    assert mixer.read(WINDOWS_CARD) == Levels(38, 50)
    assert mixer.write(WINDOWS_CARD, 70, None) == Levels(70, 50) and audio.put_calls == [(PLAYING, 0.7)], "the playing device's alone; a value not given is not written"
    assert Windows(FakeCoreAudio({PLAYING: 1.0})).read(WINDOWS_CARD) == Levels(100, None), "a recording device that is not there has no level"
    assert Windows(FakeCoreAudio({PLAYING: 1.0})).read(PLAYING) == Levels(100, None), "a card of one playing device"
    assert Windows(audio).read("default") == NONE, "an id that is no device of Core Audio's is not asked"


def test_under_the_no_devices_switch_nothing_is_read_or_set_and_no_library_is_loaded(under_the_switch: None, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    def forbidden(*args: object) -> Any:
        raise AssertionError("a real mixer was asked under the switch")
    monkeypatch.setattr(soundmixer, "load_alsa", forbidden)
    monkeypatch.setattr(soundmixer, "Alsa", forbidden)
    mixer = SystemMixer()
    assert mixer.read("plughw:CARD=Device,DEV=0") == NONE and mixer.write("plughw:CARD=Device,DEV=0", 50, 50) == NONE


def test_without_the_switch_the_system_mixer_is_alsa_on_linux_and_none_where_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEOAPRS_NO_DEVICES", raising=False)
    lib = FakeAlsa({"hw:Device": ftx1_card()})
    monkeypatch.setattr(soundmixer, "load_alsa", lambda: lib)
    monkeypatch.setattr(sys, "platform", "linux")
    assert SystemMixer().read("plughw:CARD=Device,DEV=0") == Levels(38, 50)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert SystemMixer().read("plughw:CARD=Device,DEV=0") == NONE, "macOS: no levels of the card's own"
