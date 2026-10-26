"""The frequency specification of APRS (Bob Bruninga's "AFRS", freqspec.txt of aprs.org): the voice frequency a station, a repeater or a net can be called on, in the "local information" text.

Two forms are read. In the free-text comment of a position, an object or an item, or in a status text, the first ten bytes are the frequency, `FFF.FFFMHz` (or `FFF.FF MHz` with a blank, to 10 kHz; a microwave band
is `A96.000MHz` for 1296 MHz or `1.296GHz`), and what follows may be fields of four bytes separated by spaces: the tone `Tnnn` (CTCSS to transmit), `Cnnn` (CTCSS both ways), `Dnnn` (a DCS code),
`Toff` (no tone) or `1750` (tone burst), where a lower-case first letter means narrow modulation; the offset `+nnn` or `-nnn` in units of 10 kHz (`-000` is simplex); the range `Rnnm` or `Rnnk`; the
receive frequency `FFF.FFFrx`. Only the frequency is required, and the fields may come in any order. In an object whose name is `FFF.FFxyz` or `FFF.FFF-z` the frequency is the name, and the fields
begin at the start of the comment. The unit is read in any case, since radios differ; text that does not begin with one of these forms (`145.500 MHz`, `QRV 145.500MHz`) is not read for a frequency.

Pure code, like the rest of the foundation."""
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .units import MILE_KM

_MHZ = re.compile(r"(?:(\d{3}\.\d{3}|\d{3}\.\d{2} )|([A-O])(\d{2}\.\d{3}))MHz(?= |$)|(\d{1,2}\.\d{3})GHz(?= |$)", re.IGNORECASE)
_NAME = re.compile(r"(\d{3}\.\d{2}\d?+)(?=.)")                  # the frequency of an object name: two or three decimals, then at least one character that makes the name unique
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
    """A frequency to call on, with the fields the specification adds to it; None (or False) is a field that was not sent."""
    mhz: float                                  # the transmit frequency, MHz
    tone_hz: int | None = None                  # the CTCSS tone of `Tnnn` and `Cnnn`, whole hertz (the spec drops the tenths: 107 is 107.2)
    tone_both: bool = False                     # `Cnnn`: the tone is needed to receive as well
    tone_off: bool = False                      # `Toff`: no tone, no DCS
    dcs: str | None = None                      # the DCS code of `Dnnn`, three digits as sent
    tone_burst: bool = False                    # `1750`: a 1750 Hz tone burst opens the repeater
    narrow: bool = False                        # the first letter of the tone field was lower case: narrow modulation
    offset_khz: int | None = None               # `+nnn` / `-nnn`, kHz from the transmit frequency; 0 is simplex; None when the standard offset is meant
    range_km: float | None = None               # `Rnnm` / `Rnnk`, the nominal range
    rx_mhz: float | None = None                 # a separate receive frequency (`FFF.FFFrx`, or the frequency of the comment of an object that is named by its own)


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


# The fields after the frequency: the slot each one takes (a slot is filled once), its pattern and what it says.
_FIELDS: tuple[tuple[str, re.Pattern[str], Callable[[re.Match[str]], dict[str, Any]]], ...] = (
    ("tone", _TONE, _tone),
    ("tone", _TONE_OFF, lambda f: {"tone_off": True, "narrow": f.group(1).islower()}),
    ("tone", _BURST, lambda f: {"tone_burst": True, "narrow": f.group(1) == "l"}),
    ("offset", _OFFSET, lambda f: {"offset_khz": int(f.group()) * _OFFSET_UNIT_KHZ}),
    ("range", _RANGE, _range),
    ("rx", _RX, lambda f: {"rx_mhz": float(f.group(1))}),
)


def _fields(text: str, frequency: Frequency) -> tuple[Frequency, str]:
    """`frequency` with the fields at the start of `text`, and the rest of the text: the fields end at the first word that is none, or that fills a slot twice."""
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
    """The frequency at the start of `text` (the free text of a position or a status, after any data extension; one "/" or blank in front of it is a delimiter) and the text without it and its fields.
    None, and the text as it is, when it does not begin with a frequency."""
    start = text.lstrip(" ")
    if start.startswith("/"):
        start = start[1:].lstrip(" ")
    found = _MHZ.match(start)
    if not found:
        return text, None
    frequency, rest = _fields(start[found.end():], Frequency(_mhz(found)))
    return rest, frequency


def name_frequency(name: str) -> float | None:
    """The frequency an object or item name is: `FFF.FFxyz`, `FFF.FFF-z`, `FFF.FFFyz` (MHz); None for any other name."""
    found = _NAME.match(name.rstrip())
    return None if found is None else float(found.group(1))


def named_frequency(name: str, frequency: Frequency | None, comment: str) -> tuple[Frequency | None, str]:
    """The frequency of an object or item, and its comment: the name's when it is one (`frequency` is what split_frequency found at the start of the `comment`, if anything). A comment of such an object
    begins with the fields themselves; when it also begins with a frequency, the name is the transmit frequency and the comment's the one to receive on."""
    mhz = name_frequency(name)
    if mhz is None:
        return frequency, comment
    if frequency is None:
        return _fields(comment, Frequency(mhz))
    receive = frequency.rx_mhz if frequency.rx_mhz is not None else (frequency.mhz if frequency.mhz != mhz else None)
    return replace(frequency, mhz=mhz, rx_mhz=receive), comment


def frequency_text(frequency: Frequency) -> str:
    """What a frequency says, on one line: "145.775 MHz, tone 118 Hz, -600 kHz, range 40 km"."""
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
