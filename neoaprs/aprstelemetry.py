"""APRS telemetry (APRS101 and 1.2, ch. 13): reports, base-91 telemetry and definition messages.

Reads the report `T#sss,aaa,...,bbbbbbbb`, the base-91 telemetry `|ss11...|` of a position comment,
and the definition messages `PARM.`, `UNIT.`, `EQNS.` and `BITS.`; `describe` combines them.
"""

import re
from dataclasses import dataclass, replace
from typing import NamedTuple

from neoaprs.units import base91

_SEQUENCE = re.compile(r"T#(?:MIC,?|(\d{1,5}),)")
_VALUE = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)")
_BITS = re.compile(r"[01]{1,8}")
_COMMENT_TELEMETRY = re.compile(r"\|((?:[!-{]{2}){2,7})\|")
_ANALOG, _DIGITAL = 5, 8
_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)$")
# largest believed magnitude of a value or coefficient; a*v^2 stays within a float
VALUE_LIMIT = 1e9
IDENTITY = (0.0, 1.0, 0.0)  # a channel with no equation


@dataclass(frozen=True, slots=True)
class Telemetry:
    """A telemetry report; `sequence` is None for `MIC`, `bits` is 0/1 text, B1 first."""

    sequence: int | None
    analog: list[float]
    bits: str
    comment: str = ""


@dataclass(frozen=True, slots=True)
class TelemetryDefinition:
    """What a station's definition messages have said so far; a list may stop at any field."""

    names: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    coefficients: tuple[tuple[float, float, float], ...] = ()
    sense: str = ""
    project: str = ""


class Channel(NamedTuple):
    name: str
    unit: str
    raw: float
    value: float  # a*raw^2 + b*raw + c


class Bit(NamedTuple):
    name: str
    on: bool  # the bit has the sense the definition gives (1 if none)


@dataclass(frozen=True, slots=True)
class TelemetryView:
    sequence: int | None
    channels: list[Channel]
    bits: list[Bit]
    project: str
    comment: str


def parse_telemetry(info: str) -> Telemetry | None:
    """Return the report in an information field (with its `T`); None if it is not one."""
    head = _SEQUENCE.match(info)
    if not head:
        return None
    fields = info[head.end() :].split(",")
    count = 0
    while count < min(_ANALOG, len(fields)) and _VALUE.fullmatch(fields[count]):
        count += 1
    if not count:
        return None
    analog, rest = [float(v) for v in fields[:count]], ",".join(fields[count:])
    # a run of nines too long for a number is infinity: no report
    if not all(abs(v) <= VALUE_LIMIT for v in analog):
        return None
    bits = _BITS.match(rest) if count == _ANALOG else None
    return Telemetry(
        None if head.group(1) is None else int(head.group(1)),
        analog,
        bits.group() if bits else "",
        rest[bits.end() if bits else 0 :].lstrip(",").strip(),
    )


def split_comment_telemetry(text: str) -> tuple[str, Telemetry | None]:
    """Return the comment without its base-91 telemetry `|ss1122...|`, and the report (or None)."""
    found = _COMMENT_TELEMETRY.search(text)
    if not found:
        return text, None
    digits = found.group(1).encode("ascii")
    values = [base91(digits[i : i + 2]) for i in range(0, len(digits), 2)]
    sequence, analog = values[0], values[1 : 1 + _ANALOG]
    bits = "".join("1" if values[-1] >> i & 1 else "0" for i in range(_DIGITAL)) if len(values) == 2 + _ANALOG else ""
    return (text[: found.start()] + text[found.end() :]).strip(), Telemetry(sequence, [float(v) for v in analog], bits)


def _numbers(items: list[str]) -> tuple[tuple[float, float, float], ...]:
    """Return the coefficients in groups of three; a short group or a non-number ends the list."""
    groups = []
    for i in range(0, min(len(items), 3 * _ANALOG) - 2, 3):
        triple = items[i : i + 3]
        if not all(_NUMBER.match(t.strip()) for t in triple):
            break
        numbers = (float(triple[0]), float(triple[1]), float(triple[2]))
        if not all(abs(n) <= VALUE_LIMIT for n in numbers):
            break
        groups.append(numbers)
    return tuple(groups)


def apply_definition(current: TelemetryDefinition, text: str) -> TelemetryDefinition | None:
    """Return `current` updated by a message that is one of the four definitions; else None."""
    head, body = text[:5], text[5:]
    if head == "PARM.":
        return replace(current, names=tuple(body.split(",")[: _ANALOG + _DIGITAL]))
    if head == "UNIT.":
        return replace(current, units=tuple(body.split(",")[: _ANALOG + _DIGITAL]))
    if head == "EQNS.":
        return replace(current, coefficients=_numbers(body.split(",")))
    if head == "BITS.":
        sense, _, project = body.partition(",")
        return replace(current, sense=sense if re.fullmatch(r"[01]{1,8}", sense) else "", project=project.strip())
    return None


def is_definition(text: str) -> bool:
    return text[:5] in ("PARM.", "UNIT.", "EQNS.", "BITS.")


def _at(items: tuple[str, ...], index: int, default: str) -> str:
    return items[index].strip() or default if index < len(items) else default


def describe(report: Telemetry, definition: TelemetryDefinition | None) -> TelemetryView:
    """Return the report with the station's names, units and coefficients (default A1.., B1..)."""
    d = definition or TelemetryDefinition()
    channels = []
    for i, raw in enumerate(report.analog):
        a, b, c = d.coefficients[i] if i < len(d.coefficients) else IDENTITY
        channels.append(
            Channel(_at(d.names, i, f"A{i + 1}"), _at(d.units, i, ""), raw, round(a * raw * raw + b * raw + c, 4))
        )
    bits = []
    for i, ch in enumerate(report.bits):
        sense = d.sense[i] if i < len(d.sense) else "1"
        bits.append(Bit(_at(d.names, _ANALOG + i, f"B{i + 1}"), ch == sense))
    return TelemetryView(report.sequence, channels, bits, d.project, report.comment)
