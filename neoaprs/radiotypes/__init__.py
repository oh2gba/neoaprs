"""The registry of the types of radio: one module for each family of types and one line here for each (the LoRa proof adds `*dummylora.TYPES`). A type is a description here, a driver in the adapters found by
`RadioType.driver`, and its texts in the page's catalogues."""
from collections.abc import Mapping
from types import MappingProxyType

from neoaprs.radiotype import Field, Kind, RadioType, RadioTypeError
from neoaprs.radiotypes import dummy, kisstcp, mercury, serialtnc
from neoaprs.radiotypes.common import COMMON_FIELDS as COMMON_FIELDS

TYPES: tuple[RadioType, ...] = (*serialtnc.TYPES, *kisstcp.TYPES, *dummy.TYPES, *mercury.TYPES)
BY_KEY: Mapping[str, RadioType] = MappingProxyType({t.key: t for t in TYPES})
DEFAULT_TYPE: Mapping[Kind, str] = MappingProxyType({"fm": "kiss", "hf": "mercury", "lora": "dummy-lora"})      # a new radio of the kind (lora's type exists from wave 6)


def type_of(key: str) -> RadioType:
    """The type with this key; RadioTypeError naming the types there are."""
    try:
        return BY_KEY[key.strip()]
    except KeyError:
        raise RadioTypeError(f"{key!r} is not a type of radio (the types are {', '.join(BY_KEY)})") from None


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
