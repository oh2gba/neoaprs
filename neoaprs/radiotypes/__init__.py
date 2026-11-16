"""The registry of the types of radio: one module for each family of types and one line here for each. A type is a description here, a driver in the adapters found by
`RadioType.driver`, and its texts in the page's catalogues."""
import sys
from collections.abc import Mapping
from types import MappingProxyType

from neoaprs.radiotype import Field, Kind, RadioType, RadioTypeError
from neoaprs.radiotypes import dummy, dummylora, kisstcp, lora, mercury, serialtnc, soundcard, tnctext
from neoaprs.radiotypes.common import COMMON_FIELDS as COMMON_FIELDS

# The order is the order of the page's lists (types_of, Add radio): what most operators have first (a sound card interface, then a KISS TNC), the TNCs told by text from the newest to the oldest, the operator's own
# program on the network, and the type that only receives last.
TYPES: tuple[RadioType, ...] = (*soundcard.TYPES, *serialtnc.TYPES, *kisstcp.TYPES, *tnctext.TYPES, *dummy.TYPES, *mercury.TYPES, *lora.TYPES, *dummylora.TYPES)
BY_KEY: Mapping[str, RadioType] = MappingProxyType({t.key: t for t in TYPES})
DEFAULT_TYPE: Mapping[Kind, str] = MappingProxyType({"fm": "kiss", "hf": "mercury", "lora": "lora-tcp"})      # a new radio of the kind (LoRa: the iGate at home on the network, which speaks KISS as it comes and alone says the signal to a client)


def type_of(key: str) -> RadioType:
    """The type with this key; RadioTypeError naming the types there are."""
    try:
        return BY_KEY[key.strip()]
    except KeyError:
        raise RadioTypeError(f"{key!r} is not a type of radio (the types are {', '.join(BY_KEY)})", "radio.unknown_type", type=key) from None


def types_of(kind: Kind) -> tuple[RadioType, ...]:
    """The types of the kind in the order the page lists them: the real ones in the order of TYPES, the Dummy last (it is for trying the program out; a person looking for their radio finds the real ones first)."""
    mine = [t for t in TYPES if t.kind == kind]
    return (*(t for t in mine if not t.dummy), *(t for t in mine if t.dummy))


def kind_fields(kind: Kind) -> tuple[Field, ...]:
    """Every field a radio of the kind may store: the union of its types' fields by key, their own first and the common ones last (a radio keeps the values of a type it leaves)."""
    found: dict[str, Field] = {}
    for t in types_of(kind):
        for f in t.fields:
            found.setdefault(f.key, f)
    common = [f.key for f in COMMON_FIELDS]
    return (*(f for key, f in found.items() if key not in common), *(found[key] for key in common if key in found))


def kind_field(kind: Kind, key: str) -> Field | None:
    """The field of this key that a radio of the kind may store (kind_fields); None for a key that is none."""
    return next((f for f in kind_fields(kind) if f.key == key), None)


def recommended_path(kind: Kind) -> str:
    """The path of our frames on a radio of the kind whose own path is empty, as its types recommend it (LoRa WIDE1-1); "" where they recommend none: the station's symbol's then (Config.recommended_path)."""
    return next((t.recommended_path for t in types_of(kind) if t.recommended_path), "")


def unavailable_types(system: str | None = None) -> tuple[str, ...]:
    """The keys of the types whose program this kind of installation does not carry (a Mac carries no Direwolf), on this system or the one named: the page does not offer them, and a radio of one is not added."""
    on = system or sys.platform
    return tuple(t.key for t in TYPES if t.systems and on not in t.systems)
