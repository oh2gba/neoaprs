"""APRS telemetry (APRS101 and 1.2, chapter 13): the report `T#sss,aaa,aaa,aaa,aaa,aaa,bbbbbbbb` (a sequence number, up to five analog values and up to eight bits, then perhaps a comment), the base-91
telemetry `|ss11...|` in the comment of a position (`split_comment_telemetry`), and the four definitions a
telemetry station sends as messages to itself: `PARM.` the names of the channels, `UNIT.` their units and the labels of the bits, `EQNS.` the coefficients a, b and c of `a*v^2 + b*v + c` for each analog
channel, `BITS.` the sense of the eight bits and a project title. `describe` puts a report and its definitions together: the scaled values, with names and units.

Pure code, like the rest of the foundation."""
import re
from dataclasses import dataclass, replace
from typing import NamedTuple

_SEQUENCE = re.compile(r"T#(?:MIC,?|(\d{1,5}),)")
_VALUE = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)")
_BITS = re.compile(r"[01]{1,8}")
_COMMENT_TELEMETRY = re.compile(r"\|((?:[!-{]{2}){2,7})\|")
_ANALOG, _DIGITAL = 5, 8
_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)$")
IDENTITY = (0.0, 1.0, 0.0)                                  # the coefficients of a channel that has no equation: the value as it was sent


@dataclass(frozen=True, slots=True)
class Telemetry:
    """A telemetry report: the sequence number (None for the `MIC` of a Mic-E unit), the analog values as sent (1 to 5), the bits as a text of 0 and 1 (B1 first; up to 8, empty for none) and the
    comment after them."""
    sequence: int | None
    analog: list[float]
    bits: str
    comment: str = ""


@dataclass(frozen=True, slots=True)
class TelemetryDefinition:
    """What the definition messages of one station said so far: names and units of the 5 analog channels then the 8 bits (a list may stop at any field), the coefficients of the analog channels, the sense
    of the bits (a text of 0 and 1) and the project title."""
    names: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    coefficients: tuple[tuple[float, float, float], ...] = ()
    sense: str = ""
    project: str = ""


class Channel(NamedTuple):
    name: str
    unit: str
    raw: float
    value: float                                            # a*raw^2 + b*raw + c


class Bit(NamedTuple):
    name: str
    on: bool                                                # the bit has the sense the definition gives (1 when there is none)


@dataclass(frozen=True, slots=True)
class TelemetryView:
    sequence: int | None
    channels: list[Channel]
    bits: list[Bit]
    project: str
    comment: str


def parse_telemetry(info: str) -> Telemetry | None:
    """The report in an information field (with its `T`); None when it is not one. As APRS 1.2 has it: the sequence number, or `MIC` with or without a comma; 1 to 5 analog values of any width,
    signed, with a decimal point (`-7.3`); the bits (1 to 8 of them) only after the fifth value; then the comment."""
    head = _SEQUENCE.match(info)
    if not head:
        return None
    fields = info[head.end():].split(",")
    count = 0
    while count < min(_ANALOG, len(fields)) and _VALUE.fullmatch(fields[count]):
        count += 1
    if not count:
        return None
    analog, rest = [float(v) for v in fields[:count]], ",".join(fields[count:])
    bits = _BITS.match(rest) if count == _ANALOG else None
    return Telemetry(None if head.group(1) is None else int(head.group(1)), analog, bits.group() if bits else "", rest[bits.end() if bits else 0:].strip())


def split_comment_telemetry(text: str) -> tuple[str, Telemetry | None]:
    """The comment of a position without the base-91 telemetry `|ss11223344556677|` that APRS 1.2 lets it carry (after the text, before a `!DAO!` and a Mic-E type code), and the report: the sequence
    and 1 to 5 channels of two base-91 bytes each (0 to 8280), then, after the fifth, the bits as one more such number (its lowest bit is B1); None when the comment has none."""
    found = _COMMENT_TELEMETRY.search(text)
    if not found:
        return text, None
    values = [(ord(pair[0]) - 33) * 91 + ord(pair[1]) - 33 for pair in (found.group(1)[i:i + 2] for i in range(0, len(found.group(1)), 2))]
    sequence, analog = values[0], values[1:1 + _ANALOG]
    bits = "".join("1" if values[-1] >> i & 1 else "0" for i in range(_DIGITAL)) if len(values) == 2 + _ANALOG else ""
    return (text[:found.start()] + text[found.end():]).strip(), Telemetry(sequence, [float(v) for v in analog], bits)


def _numbers(items: list[str]) -> tuple[tuple[float, float, float], ...]:
    """The coefficients in groups of three; a group that is cut short or has a field that is no number ends the list."""
    groups = []
    for i in range(0, min(len(items), 3 * _ANALOG) - 2, 3):
        triple = items[i:i + 3]
        if not all(_NUMBER.match(t.strip()) for t in triple):
            break
        groups.append((float(triple[0]), float(triple[1]), float(triple[2])))
    return tuple(groups)


def apply_definition(current: TelemetryDefinition, text: str) -> TelemetryDefinition | None:
    """`current` with what a message says, when its text is one of the four definitions; None for any other text."""
    head, body = text[:5], text[5:]
    if head == "PARM.":
        return replace(current, names=tuple(body.split(",")[:_ANALOG + _DIGITAL]))
    if head == "UNIT.":
        return replace(current, units=tuple(body.split(",")[:_ANALOG + _DIGITAL]))
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
    """The report with the names, units and coefficients a station has defined (the numbers as they were sent, named A1 to A5 and B1 to B8, when it has not)."""
    d = definition or TelemetryDefinition()
    channels = []
    for i, raw in enumerate(report.analog):
        a, b, c = d.coefficients[i] if i < len(d.coefficients) else IDENTITY
        channels.append(Channel(_at(d.names, i, f"A{i + 1}"), _at(d.units, i, ""), raw, round(a * raw * raw + b * raw + c, 4)))
    bits = []
    for i, ch in enumerate(report.bits):
        sense = d.sense[i] if i < len(d.sense) else "1"
        bits.append(Bit(_at(d.names, _ANALOG + i, f"B{i + 1}"), ch == sense))
    return TelemetryView(report.sequence, channels, bits, d.project, report.comment)
