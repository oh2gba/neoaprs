"""A radio as stored (`RadioSpec`), what one radio heard of a station, and choice rules. No I/O."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .coded import CodedError
from .radiotype import FM_ID as FM_ID, HF_ID as HF_ID, Kind, RadioId as RadioId, RadioType, RadioTypeError
from .radiotypes import kind_field, type_of

log = logging.getLogger("neoaprs.radiospec")

MAX_NAME = 8
# the English word of a kind, for the log
KIND_WORDS: Mapping[Kind, str] = {"fm": "FM", "hf": "Mercury", "lora": "LoRa"}


class RadioError(CodedError):
    """A refusal about a radio."""


@dataclass(frozen=True)
class RadioSpec:
    id: RadioId
    kind: Kind
    type: str  # RadioType.key, of this kind
    name: str  # what the operator typed, "" for none
    enabled: bool
    position: int  # the order of the boxes
    removed_at: datetime | None = None
    settings: Mapping[str, str] = field(default_factory=dict)  # its own keys as text

    def __hash__(self) -> int:
        return hash(
            (
                self.id,
                self.kind,
                self.type,
                self.name,
                self.enabled,
                self.position,
                self.removed_at,
                frozenset(self.settings.items()),
            )
        )

    @property
    def rtype(self) -> RadioType:
        """Return its type (RadioTypeError if unknown)."""
        return type_of(self.type)

    @property
    def removed(self) -> bool:
        return self.removed_at is not None

    def value(self, key: str) -> Any:
        """Return the parsed setting, or the default if absent or wrong (logged)."""
        found = kind_field(self.kind, key)
        if found is None:
            raise RadioError(f"radio/{self.id}/{key}: a radio of the kind {self.kind} has no such setting", "failed")
        text = self.settings.get(key)
        if text is not None:
            try:
                return found.parse(text)
            except ValueError as e:
                log.warning("radio/%d/%s: %s; the default %s is used", self.id, key, e, found.default or "(empty)")
        return found.parse(found.default)


@dataclass(frozen=True)
class RadioHeard:
    count: int
    last_at: datetime | None
    last_path: tuple[str, ...] = ()


NOT_HEARD = RadioHeard(0, None)


def live(specs: Iterable[RadioSpec]) -> list[RadioSpec]:
    """Return the radios not removed, by position."""
    return sorted((s for s in specs if s.removed_at is None), key=lambda s: (s.position, s.id))


def enabled(specs: Iterable[RadioSpec]) -> list[RadioSpec]:
    """Return the enabled radios by position."""
    return [s for s in live(specs) if s.enabled]


def transmits(spec: RadioSpec) -> bool:
    """Return whether the radio can send."""
    try:
        return spec.rtype.can.transmit
    except RadioTypeError:
        return False


def senders(specs: Iterable[RadioSpec]) -> list[RadioSpec]:
    """Return the enabled radios that can send."""
    return [s for s in enabled(specs) if transmits(s)]


def modem_radio(specs: Iterable[RadioSpec]) -> RadioId | None:
    """Return the radio a Mercury run by something else (--hf-port) is given to."""
    return min((s.id for s in live(specs) if s.type == "mercury"), default=None)


def number_in_kind(spec: RadioSpec, specs: Iterable[RadioSpec]) -> int:
    """Return the number of the radio within its kind (removed ones count after live ones)."""
    pool = list(specs)
    if spec.removed_at is None:
        return 1 + sum(1 for s in live(pool) if s.kind == spec.kind and s.id < spec.id)
    return 1 + sum(1 for s in pool if s.kind == spec.kind and (s.removed_at is None or s.id < spec.id))


def log_name(spec: RadioSpec, specs: Iterable[RadioSpec]) -> str:
    """Return the name typed, else the kind's word and its number ("Mercury 2")."""
    if spec.name:
        return spec.name
    number = number_in_kind(spec, specs)
    return KIND_WORDS[spec.kind] + (f" {number}" if number > 1 else "")


def told(name: str, id: RadioId) -> str:
    """Return the radio as a log line says it: "the LoRa 2 radio (radio 9)"; "radio 9" with no name."""
    return f"the {name} radio (radio {id})" if name else f"radio {id}"


def log_label(spec: RadioSpec, specs: Iterable[RadioSpec]) -> str:
    """Return the radio's name with its id ("LoRa 2 (radio 9)"): the id never shifts, the number may."""
    return f"{log_name(spec, specs)} (radio {spec.id})"


def unheard_radio(specs: Iterable[RadioSpec]) -> RadioId | None:
    """Return the first radio that can send, for what no fact names; None if none can."""
    on = senders(specs)
    return on[0].id if on else None


def in_force_choice(choice: RadioId | None, specs: Iterable[RadioSpec]) -> RadioId | None:
    """Return a station's stored radio as in force: the only sender, else the choice if valid."""
    on = senders(specs)
    if len(on) == 1:
        return on[0].id
    return choice if choice is not None and any(s.id == choice for s in on) else None


def in_force_set(ids: Iterable[RadioId], specs: Iterable[RadioSpec]) -> tuple[RadioId, ...]:
    """Return a stored set of radios as in force: the only sender, else the ticked ones."""
    on = senders(specs)
    if len(on) == 1:
        return (on[0].id,)
    ticked = set(ids)
    return tuple(s.id for s in on if s.id in ticked)


def check_name(text: str, specs: Iterable[RadioSpec], own: RadioId | None) -> str:
    """Return a name as kept, or raise RadioError (printable ASCII, unique among live radios)."""
    name = text.strip()
    if not name:
        return ""
    if len(name) > MAX_NAME or not (name.isascii() and name.isprintable()):
        raise RadioError(
            f"the name {name!r} cannot be a radio's: a name is at most {MAX_NAME} printable ASCII characters (letters, digits and the signs of the keyboard)",
            "radio.name_form",
            name=name,
            max=MAX_NAME,
        )
    taken = next((s for s in live(specs) if s.id != own and s.name.casefold() == name.casefold()), None)
    if taken is not None:
        raise RadioError(
            f"the name {name!r} is radio {taken.id}'s already: give this one another",
            "radio.name_taken",
            name=name,
            radio=taken.id,
        )
    return name
