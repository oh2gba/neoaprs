"""Read and set a sound card's playback and capture levels, each 0 to 100 percent.

On Linux the ALSA simple mixer is reached by ctypes (volumes only, never a switch); see winmixer.py
for Windows. A control that cannot be read or set is absent (None in `Levels`).
"""
import ctypes
import logging
import re
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger("neoaprs.soundmixer")

# ALSA controls that are a card's playback level, the first the card has. Not Mic: its playback
# volume is the monitor on some chips.
PLAYBACK_NAMES = ("Master", "Speaker", "PCM", "Headphone")
CAPTURE_NAMES = ("Capture", "Mic")
ALSA_LIBRARY = "libasound.so.2"


@dataclass(frozen=True)
class Levels:
    # Playback and capture levels, 0 to 100; None if the control is absent or unreadable.
    tx: int | None = None
    rx: int | None = None


NONE = Levels()


class Mixer(Protocol):
    def read(self, card: str) -> Levels:
        """Return the card's levels now. Blocks: call from a thread."""
        ...

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        """Set the levels that are not None; return the new levels. Blocks: call from a thread."""
        ...


def percent(low: int, high: int, raw: int) -> int:
    """Return a control's raw value as a percent of its range."""
    return 0 if high <= low else max(0, min(100, round(100 * (raw - low) / (high - low))))


def raw_of(low: int, high: int, value: int) -> int:
    """Return the raw value of a percent within a control's range."""
    return low + round(max(0, min(100, value)) * (high - low) / 100)


@dataclass(frozen=True)
class Control:
    """An ALSA simple mixer control: name, and playback and capture volume as (low, high, raw)."""
    name: str
    playback: tuple[int, int, int] | None = None
    capture: tuple[int, int, int] | None = None


def pick(controls: Sequence[Control], names: Sequence[str], way: str) -> Control | None:
    """Return the first of `names` the card has with a volume for `way`, or None."""
    for name in names:
        if (found := next((c for c in controls if c.name == name and getattr(c, way) is not None), None)) is not None:
            return found
    return None


_CARD = re.compile(r"(?:^|[:,])CARD=(?P<card>[^,]+)")
_NUMBERED = re.compile(r"^(?:plughw|hw):(?P<card>[^,]+)")


def alsa_control_name(card: str) -> str:
    """Return the ALSA control device of a card setting (`plughw:CARD=X,DEV=0` gives `hw:X`)."""
    found = _CARD.search(card) or _NUMBERED.match(card.strip())
    return f"hw:{found.group('card')}" if found else ""


class Alsa:
    """The card's ALSA simple mixer controls; `load` returns the ctypes library or None."""

    def __init__(self, load: Callable[[], Any] | None = None) -> None:
        self._load = load or load_alsa
        self._lib: Any = None
        # looked for once; the lock covers `present` on the loop against the mixer's thread
        self._loaded = False
        self._loading = threading.Lock()

    def read(self, card: str) -> Levels:
        return self._session(card, None, None)

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        return self._session(card, tx, rx)

    def present(self) -> bool:
        """Return True if the system has the library."""
        return self._library() is not None

    def _library(self) -> Any:
        with self._loading:
            if not self._loaded:
                self._loaded = True
                self._lib = self._load()
            return self._lib

    def _session(self, card: str, tx: int | None, rx: int | None) -> Levels:
        name = alsa_control_name(card)
        lib = self._library() if name else None
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
    """Open the simple mixer of control device `name` and yield its elements; raise OSError."""
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
        # A second control of the same name is ignored.
        return Control("")
    return Control((name or b"").decode("utf-8", "replace"), _volume(lib, elem, "playback"), _volume(lib, elem, "capture"))


def _volume(lib: Any, elem: Any, way: str) -> tuple[int, int, int] | None:
    """Return (low, high, raw value of the first channel) of the volume for `way`, or None."""
    if not getattr(lib, f"snd_mixer_selem_has_{way}_volume")(elem):
        return None
    low, high, value = ctypes.c_long(), ctypes.c_long(), ctypes.c_long()
    if getattr(lib, f"snd_mixer_selem_get_{way}_volume_range")(elem, ctypes.byref(low), ctypes.byref(high)) < 0:
        return None
    # Channel 0: front left, or the only channel of a mono control.
    if getattr(lib, f"snd_mixer_selem_get_{way}_volume")(elem, 0, ctypes.byref(value)) < 0:
        return None
    return low.value, high.value, value.value


def _now(lib: Any, elem_of: dict[int, Any], control: Control | None, way: str) -> int | None:
    """Return the control's current percent, read again after a set, or None without a control."""
    if control is None:
        return None
    volume = _volume(lib, elem_of[id(control)], way)
    return None if volume is None else percent(*volume)


def load_alsa() -> Any:
    """Return the ALSA library with the signatures `Alsa` needs, or None if it is missing."""
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
    try:
        for call, (restype, argtypes) in signatures.items():
            function = getattr(lib, call)
            function.restype, function.argtypes = restype, argtypes
    except AttributeError as e:
        log.info("the ALSA library lacks a call NeoAPRS makes (%s): the sound cards have no levels of their own here", e)
        return None
    _quiet(lib)
    return lib


# Module level so that it lives as long as the process: the library keeps calling it.
_QUIET = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)(lambda *said: None)


def _quiet(lib: Any) -> None:
    """Install an error handler that discards ALSA's messages (it prints for unplugged cards)."""
    setter = getattr(lib, "snd_lib_error_set_handler", None)
    if setter is not None:
        setter.restype, setter.argtypes = ctypes.c_int, [ctypes.c_void_p]
        setter(ctypes.cast(_QUIET, ctypes.c_void_p))
