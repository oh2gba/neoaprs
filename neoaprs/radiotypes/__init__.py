"""Registry of the radio types: one module per family of types, one line here for each.

A type is a description here, a driver found by `RadioType.driver`, and texts in the page's
catalogues.
"""
import sys
from collections.abc import Mapping
from types import MappingProxyType

from neoaprs.radiotype import Field, Kind, RadioType, RadioTypeError
from neoaprs.radiotypes import dummy, dummylora, kisstcp, lora, mercury, serialtnc, soundcard, tnctext
from neoaprs.radiotypes.common import COMMON_FIELDS as COMMON_FIELDS

# The order of the page's lists (types_of, Add radio): sound card interfaces first, then KISS
# TNCs, then text TNCs from newest to oldest, then the operator's own program on the network.
TYPES: tuple[RadioType, ...] = (*soundcard.TYPES, *serialtnc.TYPES, *kisstcp.TYPES, *tnctext.TYPES, *dummy.TYPES, *mercury.TYPES, *lora.TYPES, *dummylora.TYPES)
BY_KEY: Mapping[str, RadioType] = MappingProxyType({t.key: t for t in TYPES})
# The type of a new radio of each kind. For LoRa it is the iGate on the network, the only type
# that both speaks KISS directly and reports the signal to a client.
DEFAULT_TYPE: Mapping[Kind, str] = MappingProxyType({"fm": "kiss", "hf": "mercury", "lora": "lora-tcp"})


def type_of(key: str) -> RadioType:
    """Return the type with this key; raise RadioTypeError naming the valid keys."""
    try:
        return BY_KEY[key.strip()]
    except KeyError:
        raise RadioTypeError(f"{key!r} is not a type of radio (the types are {', '.join(BY_KEY)})", "radio.unknown_type", type=key) from None


def types_of(kind: Kind) -> tuple[RadioType, ...]:
    """Return the types of the kind in page order: real ones as in TYPES, Dummy types last."""
    mine = [t for t in TYPES if t.kind == kind]
    return (*(t for t in mine if not t.dummy), *(t for t in mine if t.dummy))


def kind_fields(kind: Kind) -> tuple[Field, ...]:
    """Return every field a radio of the kind may store: its types' fields, common ones last.

    A radio keeps the values of a type it leaves.
    """
    found: dict[str, Field] = {}
    for t in types_of(kind):
        for f in t.fields:
            found.setdefault(f.key, f)
    common = [f.key for f in COMMON_FIELDS]
    return (*(f for key, f in found.items() if key not in common), *(found[key] for key in common if key in found))


def kind_field(kind: Kind, key: str) -> Field | None:
    """Return the field of this key that a radio of the kind may store, or None."""
    return next((f for f in kind_fields(kind) if f.key == key), None)


def recommended_path(kind: Kind) -> str:
    """Return the path recommended for a radio of the kind with no path of its own (LoRa: WIDE1-1).

    "" means none is recommended and the station symbol's applies (Config.recommended_path).
    """
    return next((t.recommended_path for t in types_of(kind) if t.recommended_path), "")


def unavailable_types(system: str | None = None) -> tuple[str, ...]:
    """Return the keys of types whose program this system lacks (macOS has no Direwolf).

    The page does not offer them.
    """
    on = system or sys.platform
    return tuple(t.key for t in TYPES if t.systems and on not in t.systems)
