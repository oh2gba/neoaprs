"""A radio's state and problem as the page shows them, and the devices its settings name.

`radio_health` is the one decision: the radio's settings and the table of resources, then its
line (tnchealth.py). The devices are also what refuses a save naming one another radio holds.
"""

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from .claims import PORT_KINDS, Claims
from .radiospec import RadioSpec, log_name
from .radiotype import RadioId, RadioTypeError, ResourceKind
from .serialprobe import claim_value, keying_device
from .source import Source
from .tnc import Tnc
from .tnchealth import STOPPED, RadioHealth, line_health


class RadioLine(Protocol):
    """A radio at work as the decision needs it: its line and the driver it was made by."""

    @property
    def line(self) -> Tnc: ...
    @property
    def driver_key(self) -> str: ...


def line_of(spec: RadioSpec, radio: RadioLine | None) -> Tnc | None:
    """Return the radio's line, or None when it is not run for these settings (removed, a new type)."""
    if radio is None or spec.removed:
        return None
    try:
        return radio.line if radio.driver_key == spec.rtype.driver else None
    except RadioTypeError:
        return None


def radio_health(spec: RadioSpec, specs: Sequence[RadioSpec], radio: RadioLine | None, claims: Claims) -> RadioHealth:
    """Return the radio's state and problem; an unticked or removed radio is stopped with none."""
    line = line_of(spec, radio)
    if line is None or not spec.enabled:
        return STOPPED
    health = line_health(line)
    if line.state is not Source.State.CONNECTED and (held := held_elsewhere(spec, specs, claims)) is not None:
        return replace(
            health, code="radio.resource_held", params={"resource": held[1], "holder": held[2], "held_by": held[3]}
        )
    if health.code == "radio.not_connected":
        return replace(health, params={"name": log_name(spec, specs)})
    return health


def claimed_value(kind: str, text: str) -> str:
    """Return the value a setting holds in the resource table (claims.py); "" for none."""
    return (
        (claim_value(keying_device(text) if kind == "keying" else text) or "") if kind in PORT_KINDS else text.strip()
    )


def devices(spec: RadioSpec) -> list[tuple[str, ResourceKind, str]]:
    """Return (field key, device kind, value) for each non-empty device the settings name."""
    try:
        fields = spec.rtype.fields
    except RadioTypeError:
        return []
    found = (
        (f.key, f.claims, claimed_value(f.claims, spec.settings.get(f.key, f.default))) for f in fields if f.claims
    )
    return [(key, kind, value) for key, kind, value in found if kind is not None and value]


def one_device(a: ResourceKind, b: ResourceKind) -> bool:
    """Return True if the two kinds name one device (any serial port use counts as one)."""
    return a == b or (a in PORT_KINDS and b in PORT_KINDS)


def removed_name(id: RadioId, specs: Sequence[RadioSpec]) -> str | None:
    """Return the log name of a removed radio, or None if it is not removed or unknown."""
    spec = next((s for s in specs if s.id == id), None)
    return None if spec is None or not spec.removed else log_name(spec, specs)


def holder_id(holder: RadioId | None, specs: Sequence[RadioSpec]) -> RadioId:
    """Return the holder's radio id for the ports' `held_by`.

    0 for the GPS receiver or an unknown holder.
    """
    return holder if holder is not None and any(s.id == holder for s in specs) else 0


def holder_name(holder: RadioId | None, specs: Sequence[RadioSpec]) -> str:
    """Return the holder's log name, or `GPS` for the receiver or an unknown holder."""
    named = next((s for s in specs if s.id == holder), None)
    return "GPS" if named is None else log_name(named, specs)


def held_elsewhere(spec: RadioSpec, specs: Sequence[RadioSpec], claims: Claims) -> tuple[str, str, str, RadioId] | None:
    """Return (field key, device kind, holder name, holder id) for the first device another holds.

    Return None if there is none.
    """
    for key, kind, value in devices(spec):
        holder = next(
            (c for c in claims.all() if c.holder != spec.id and c.value == value and one_device(c.kind, kind)), None
        )
        if holder is not None:
            return key, kind, holder_name(holder.holder, specs), holder_id(holder.holder, specs)
    return None
