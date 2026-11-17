"""A sound card's own levels: its playback level (what the radio is given to transmit) and its capture level (what it takes from the radio), each 0 to 100 percent, read and set for the card as a radio's
settings name it (`sound_card`: `plughw:CARD=CODEC,DEV=0` on Linux, the pair of a Windows card's two devices, mercurycards.PAIR). A card has such a control or it has not: `Levels` says None where it has none,
and nothing is set there.

On Linux the controls are the card's ALSA simple mixer controls, through the ALSA library by ctypes (`Alsa`): the playback one is the first of PLAYBACK_NAMES the card has, the capture one the first of
CAPTURE_NAMES; their names differ by card (a C-Media chip has Speaker and Mic, a TI codec PCM alone), and a card with none of them has no control. Only volumes are read and set: no switch is ever touched,
a mute or the card's Auto Gain Control stays as the system has it. The percent is the control's raw value within its range, as `amixer` prints it. A system without the library has no control: no program
is run to find one. On Windows they are the master volume of the card's playing device and of its recording device (Core Audio, winmixer.py). Other systems have none.

`Mixer` is the one small interface: the radio's part (cardlevels.py) is given the system's (`cardlevels.SystemMixer`, which under the no-devices switch reads and sets nothing and loads no library), a
test its own. A control that cannot be read or set is said in the log at DEBUG and is no control: the operator can do nothing about it, and the radio works as it does without one."""
import ctypes
import logging
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger("neoaprs.soundmixer")

PLAYBACK_NAMES = ("Master", "Speaker", "PCM", "Headphone")     # the ALSA controls that are a card's playback level, the first the card has (not Mic: a C-Media chip's Mic has a playback volume too, its monitor)
CAPTURE_NAMES = ("Capture", "Mic")                            # the ones that are its capture level
ALSA_LIBRARY = "libasound.so.2"


@dataclass(frozen=True)
class Levels:
    tx: int | None = None                  # the card's playback level, 0 to 100; None: it has no such control (or it could not be read)
    rx: int | None = None                  # its capture level


NONE = Levels()


class Mixer(Protocol):
    def read(self, card: str) -> Levels:
        """The card's levels now. Blocks: for a thread."""
        ...

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        """Sets the levels that are not None where the card has the control, and says the levels after it. Blocks: for a thread."""
        ...


def percent(low: int, high: int, raw: int) -> int:
    """A control's raw value within its range as a percent of it."""
    return 0 if high <= low else max(0, min(100, round(100 * (raw - low) / (high - low))))


def raw_of(low: int, high: int, value: int) -> int:
    """The raw value of a percent within a control's range."""
    return low + round(max(0, min(100, value)) * (high - low) / 100)


@dataclass(frozen=True)
class Control:
    """An ALSA simple mixer control as `Alsa` reads it: its name, and its playback and capture volume where it has one, each (low, high, raw value)."""
    name: str
    playback: tuple[int, int, int] | None = None
    capture: tuple[int, int, int] | None = None


def pick(controls: Sequence[Control], names: Sequence[str], way: str) -> Control | None:
    """The control of a way ("playback", "capture"): the first of `names` the card has with a volume that way; None for a card with none of them."""
    for name in names:
        if (found := next((c for c in controls if c.name == name and getattr(c, way) is not None), None)) is not None:
            return found
    return None


_CARD = re.compile(r"(?:^|[:,])CARD=(?P<card>[^,]+)")
_NUMBERED = re.compile(r"^(?:plughw|hw):(?P<card>[^,]+)")


def alsa_control_name(card: str) -> str:
    """The ALSA control device of a sound card setting: `hw:CODEC` of `plughw:CARD=CODEC,DEV=0` (or any device with CARD=), `hw:1` of `plughw:1,0`; "" for one that names no card (`default`, `pulse`)."""
    found = _CARD.search(card) or _NUMBERED.match(card.strip())
    return f"hw:{found.group('card')}" if found else ""


class Alsa:
    """The card's ALSA simple mixer controls through the library (`load`: the ALSA library as ctypes has it, None where the system has none; a test gives its own)."""

    def __init__(self, load: Callable[[], Any] | None = None) -> None:
        self._load = load or load_alsa
        self._lib: Any = None
        self._loaded = False                                      # (the library is looked for once: a system without it is asked no more)

    def read(self, card: str) -> Levels:
        return self._session(card, None, None)

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        return self._session(card, tx, rx)

    def _session(self, card: str, tx: int | None, rx: int | None) -> Levels:
        name = alsa_control_name(card)
        if name and not self._loaded:
            self._lib, self._loaded = self._load(), True
        lib = self._lib if name else None
        if lib is None:
            return NONE
        try:
            with _mixer(lib, name) as elements:
                controls = [(elem, _control(lib, elem)) for elem in elements]
                out = pick([c for _, c in controls], PLAYBACK_NAMES, "playback")
                into = pick([c for _, c in controls], CAPTURE_NAMES, "capture")
                elem_of = {id(c): elem for elem, c in controls}
                if out is not None and out.playback is not None and tx is not None:
                    lib.snd_mixer_selem_set_playback_volume_all(elem_of[id(out)], ctypes.c_long(raw_of(out.playback[0], out.playback[1], tx)))
                if into is not None and into.capture is not None and rx is not None:
                    lib.snd_mixer_selem_set_capture_volume_all(elem_of[id(into)], ctypes.c_long(raw_of(into.capture[0], into.capture[1], rx)))
                return Levels(_now(lib, elem_of, out, "playback"), _now(lib, elem_of, into, "capture"))
        except OSError as e:
            log.debug("the levels of the sound card %s could not be had from ALSA: %s", card, e)
            return NONE


@contextmanager
def _mixer(lib: Any, name: str) -> Iterator[list[Any]]:
    """The simple mixer of the card's control device `name`, open, as the list of its elements; closed after. OSError when it cannot be opened (a card that is not there)."""
    handle = ctypes.c_void_p()
    if lib.snd_mixer_open(ctypes.byref(handle), 0) < 0:
        raise OSError("the mixer could not be opened")
    try:
        for step, code in (("attach", lib.snd_mixer_attach(handle, name.encode())), ("register", lib.snd_mixer_selem_register(handle, None, None)), ("load", lib.snd_mixer_load(handle))):
            if code < 0:
                raise OSError(f"{step} of {name} failed ({code})")
        elements, elem = [], lib.snd_mixer_first_elem(handle)
        while elem:
            elements.append(elem)
            elem = lib.snd_mixer_elem_next(elem)
        yield elements
    finally:
        lib.snd_mixer_close(handle)


def _control(lib: Any, elem: Any) -> Control:
    name = lib.snd_mixer_selem_get_name(elem)
    if lib.snd_mixer_selem_get_index(elem) != 0:
        return Control("")                                       # (a second control of a name: none of ours)
    return Control((name or b"").decode("utf-8", "replace"), _volume(lib, elem, "playback"), _volume(lib, elem, "capture"))


def _volume(lib: Any, elem: Any, way: str) -> tuple[int, int, int] | None:
    """The control's volume that way, (low, high, raw value of its first channel); None where it has none."""
    if not getattr(lib, f"snd_mixer_selem_has_{way}_volume")(elem):
        return None
    low, high, value = ctypes.c_long(), ctypes.c_long(), ctypes.c_long()
    if getattr(lib, f"snd_mixer_selem_get_{way}_volume_range")(elem, ctypes.byref(low), ctypes.byref(high)) < 0:
        return None
    if getattr(lib, f"snd_mixer_selem_get_{way}_volume")(elem, 0, ctypes.byref(value)) < 0:      # (channel 0: the front left, or the one channel of a mono control)
        return None
    return low.value, high.value, value.value


def _now(lib: Any, elem_of: dict[int, Any], control: Control | None, way: str) -> int | None:
    """The control's percent as it is now (read again after a set), None for no control."""
    if control is None:
        return None
    volume = _volume(lib, elem_of[id(control)], way)
    return None if volume is None else percent(*volume)


def load_alsa() -> Any:
    """The system's ALSA library with the signatures of the calls `Alsa` makes; None where there is none."""
    try:
        lib = ctypes.CDLL(ALSA_LIBRARY)
    except OSError as e:
        log.debug("no ALSA library (%s): the sound cards have no levels of their own here", e)
        return None
    handle, elem, long_p = ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long)
    signatures: dict[str, tuple[Any, list[Any]]] = {
        "snd_mixer_open": (ctypes.c_int, [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]), "snd_mixer_attach": (ctypes.c_int, [handle, ctypes.c_char_p]),
        "snd_mixer_selem_register": (ctypes.c_int, [handle, ctypes.c_void_p, ctypes.c_void_p]), "snd_mixer_load": (ctypes.c_int, [handle]), "snd_mixer_close": (ctypes.c_int, [handle]),
        "snd_mixer_first_elem": (elem, [handle]), "snd_mixer_elem_next": (elem, [elem]), "snd_mixer_selem_get_name": (ctypes.c_char_p, [elem]), "snd_mixer_selem_get_index": (ctypes.c_uint, [elem]),
    }
    for way in ("playback", "capture"):
        signatures |= {f"snd_mixer_selem_has_{way}_volume": (ctypes.c_int, [elem]), f"snd_mixer_selem_get_{way}_volume_range": (ctypes.c_int, [elem, long_p, long_p]),
                       f"snd_mixer_selem_get_{way}_volume": (ctypes.c_int, [elem, ctypes.c_int, long_p]), f"snd_mixer_selem_set_{way}_volume_all": (ctypes.c_int, [elem, ctypes.c_long])}
    for call, (restype, argtypes) in signatures.items():
        function = getattr(lib, call)
        function.restype, function.argtypes = restype, argtypes
    _quiet(lib)
    return lib


_QUIET = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)(lambda *said: None)     # (kept for the process's life: the library calls it)


def _quiet(lib: Any) -> None:
    """ALSA's library writes its own errors to the process's standard error ("Cannot get card index for Device" at every look at a card that is unplugged, every two seconds): they are taken by a
    handler that says nothing. A card that cannot be read is no level, which the row shows; the reason is nothing an operator can act on from that line."""
    setter = getattr(lib, "snd_lib_error_set_handler", None)
    if setter is not None:
        setter.restype, setter.argtypes = ctypes.c_int, [ctypes.c_void_p]
        setter(ctypes.cast(_QUIET, ctypes.c_void_p))
