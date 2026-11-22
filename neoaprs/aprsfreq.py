"""The APRS frequency specification (freqspec.txt of aprs.org): the voice frequency to call on.

The text starts with the frequency (`FFF.FFFMHz`), then optional four-byte fields: tone, DCS,
offset, range, receive frequency. In an object named `FFF.FFxyz` the name is the frequency.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .units import MILE_KM

_MHZ = re.compile(r"(?:(\d{3}\.\d{3}|\d{3}\.\d{2} )|([A-O])(\d{2}\.\d{3}))MHz(?= |$)|(\d{1,2}\.\d{3})GHz(?= |$)", re.IGNORECASE)
_NAME = re.compile(r"(\d{3}\.\d{2}\d?+)(?=.)")
_MICROWAVE_BASE = {"A": 1200, "B": 2300, "C": 2400, "D": 3400, "E": 5600, "F": 5700, "G": 5800, "H": 10100, "I": 10200, "J": 10300, "K": 10400, "L": 10500, "M": 24000, "N": 24100, "O": 24200}
_TONE = re.compile(r"([TCDtcd])(\d{3})")
_TONE_OFF = re.compile(r"([Tt])off", re.IGNORECASE)
_BURST = re.compile(r"([1l])750")
_OFFSET = re.compile(r"[+-]\d{3}")
_RANGE = re.compile(r"R(\d{2,3})([mk])", re.IGNORECASE)
_RX = re.compile(r"(\d{3}\.\d{2,3})rx", re.IGNORECASE)
_OFFSET_UNIT_KHZ = 10


@dataclass(frozen=True, slots=True)
class Frequency:
    """A frequency to call on; None or False means the field was not sent."""
    mhz: float
    tone_hz: int | None = None  # whole hertz as sent (107 means 107.2)
    tone_both: bool = False  # `Cnnn`: the tone is needed to receive too
    tone_off: bool = False
    dcs: str | None = None
    tone_burst: bool = False  # `1750`
    narrow: bool = False
    offset_khz: int | None = None  # 0 is simplex; None: standard offset
    range_km: float | None = None
    rx_mhz: float | None = None


def _mhz(found: re.Match[str]) -> float:
    if found.group(1):
        return float(found.group(1))
    if found.group(2):
        return float(_MICROWAVE_BASE[found.group(2).upper()] + float(found.group(3)))
    return round(float(found.group(4)) * 1000, 3)


def _tone(found: re.Match[str]) -> dict[str, Any]:
    kind, hertz, narrow = found.group(1).upper(), int(found.group(2)), found.group(1).islower()
    if kind == "D":
        return {"dcs": found.group(2), "narrow": narrow}
    if hertz == 0:
        return {"tone_off": True, "narrow": narrow}
    return {"tone_hz": hertz, "tone_both": kind == "C", "narrow": narrow}


def _range(found: re.Match[str]) -> dict[str, Any]:
    distance = int(found.group(1))
    return {"range_km": float(distance) if found.group(2).lower() == "k" else round(distance * MILE_KM, 1)}


# Fields after the frequency: slot (filled once), pattern, meaning.
_FIELDS: tuple[tuple[str, re.Pattern[str], Callable[[re.Match[str]], dict[str, Any]]], ...] = (
    ("tone", _TONE, _tone),
    ("tone", _TONE_OFF, lambda f: {"tone_off": True, "narrow": f.group(1).islower()}),
    ("tone", _BURST, lambda f: {"tone_burst": True, "narrow": f.group(1) == "l"}),
    ("offset", _OFFSET, lambda f: {"offset_khz": int(f.group()) * _OFFSET_UNIT_KHZ}),
    ("range", _RANGE, _range),
    ("rx", _RX, lambda f: {"rx_mhz": float(f.group(1))}),
)


def _fields(text: str, frequency: Frequency) -> tuple[Frequency, str]:
    """Return `frequency` with the fields at the start of `text`, and the rest of the text."""
    taken: set[str] = set()
    rest = text
    while rest:
        word, _, after = rest.lstrip(" ").partition(" ")
        step = next(((slot, make(found)) for slot, pattern, make in _FIELDS if slot not in taken and (found := pattern.fullmatch(word))), None)
        if step is None:
            break
        taken.add(step[0])
        frequency, rest = replace(frequency, **step[1]), after
    return frequency, rest.strip()


def split_frequency(text: str) -> tuple[str, Frequency | None]:
    """Return the frequency at the start of `text` and the text without it; None if absent.

    One "/" or blank in front of the frequency is a delimiter.
    """
    start = text.lstrip(" ")
    if start.startswith("/"):
        start = start[1:].lstrip(" ")
    found = _MHZ.match(start)
    if not found:
        return text, None
    frequency, rest = _fields(start[found.end():], Frequency(_mhz(found)))
    return rest, frequency


def name_frequency(name: str) -> float | None:
    """Return the frequency an object or item name is (`FFF.FFxyz`), else None."""
    found = _NAME.match(name.rstrip())
    return None if found is None else float(found.group(1))


def named_frequency(name: str, frequency: Frequency | None, comment: str) -> tuple[Frequency | None, str]:
    """Return the frequency of an object or item and its comment.

    If the comment also starts with a frequency, the name's is transmit and the comment's receive.
    """
    mhz = name_frequency(name)
    if mhz is None:
        return frequency, comment
    if frequency is None:
        return _fields(comment, Frequency(mhz))
    receive = frequency.rx_mhz if frequency.rx_mhz is not None else (frequency.mhz if frequency.mhz != mhz else None)
    return replace(frequency, mhz=mhz, rx_mhz=receive), comment


def frequency_text(frequency: Frequency) -> str:
    """Return one line describing a frequency."""
    parts = [f"{frequency.mhz:.3f} MHz"]
    if frequency.tone_hz is not None:
        parts.append(f"tone {frequency.tone_hz} Hz{' both ways' if frequency.tone_both else ''}")
    if frequency.dcs is not None:
        parts.append(f"DCS {frequency.dcs}")
    if frequency.tone_off:
        parts.append("no tone")
    if frequency.tone_burst:
        parts.append("tone burst 1750 Hz")
    if frequency.narrow:
        parts.append("narrow")
    if frequency.offset_khz is not None:
        parts.append("simplex" if frequency.offset_khz == 0 else f"{frequency.offset_khz:+d} kHz")
    if frequency.range_km is not None:
        parts.append(f"range {frequency.range_km:.0f} km")
    if frequency.rx_mhz is not None:
        parts.append(f"receive {frequency.rx_mhz:.3f} MHz")
    return ", ".join(parts)
