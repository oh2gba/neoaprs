"""A radio as it is stored (`RadioSpec`: its id, kind, type, name, whether it is enabled, its place in the list, its own settings as text), what one radio heard of a station (`RadioHeard`), and the rules that read a
choice against the radios there are: which are live and enabled, the number of a radio within its kind and the name the log gives it, the main radio, and a stored choice or set of radios that names one that is
off or gone (plan §2). No I/O."""
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .coded import CodedError
from .radiotype import FM_ID as FM_ID, HF_ID as HF_ID, Kind, RadioId as RadioId, RadioType, RadioTypeError
from .radiotypes import kind_field, type_of

log = logging.getLogger("neoaprs.radiospec")

MAX_NAME = 8                         # the longest name of a radio: the label of its tag, its mark and its box
KIND_WORDS: Mapping[Kind, str] = {"fm": "FM", "hf": "HF", "lora": "LoRa"}     # the English word of a kind, for the log's name of a radio that has none of its own (the page has its catalogue's)


class RadioError(CodedError):
    """A refusal about a radio, with an English text naming `radio/<id>/<key>` or the radio's log name, and the code and values the page says it by (`radio.unknown`, `radio.last_enabled`,
    `radio.name_taken`, `radio.name_form`, `radio.type_kind`: scripts/errorcodes.py writes them into the page's list); `other` for one the page's commands cannot meet (a column that is no column)."""


@dataclass(frozen=True)
class RadioSpec:
    id: RadioId
    kind: Kind
    type: str                                    # RadioType.key, of this kind
    name: str                                    # what the operator typed; "" for none (a typed name is never empty)
    enabled: bool
    position: int                                # the order of the boxes and of "the first enabled"
    removed_at: datetime | None = None
    settings: Mapping[str, str] = field(default_factory=dict)     # its own keys as text (kind_fields)

    def __hash__(self) -> int:
        return hash((self.id, self.kind, self.type, self.name, self.enabled, self.position, self.removed_at, frozenset(self.settings.items())))

    @property
    def rtype(self) -> RadioType:
        """Its type's description (RadioTypeError for a key that is no type)."""
        return type_of(self.type)

    @property
    def removed(self) -> bool:
        return self.removed_at is not None

    def value(self, key: str) -> Any:
        """Its setting of this key, parsed by the field of its kind; the field's default when the setting is absent or wrong (a wrong one is logged with `radio/<id>/<key>`). RadioError for a key that is no field of its kind."""
        found = kind_field(self.kind, key)
        if found is None:
            raise RadioError(f"radio/{self.id}/{key}: a radio of the kind {self.kind} has no such setting")
        text = self.settings.get(key)
        if text is not None:
            try:
                return found.parse(text)
            except ValueError as e:
                log.warning("radio/%d/%s: %s; the default %s is used", self.id, key, e, found.default or "(empty)")
        return found.parse(found.default)


@dataclass(frozen=True)
class RadioHeard:
    """What one radio heard of a station (rule 3.3)."""
    count: int
    last_at: datetime | None
    last_path: tuple[str, ...] = ()


NOT_HEARD = RadioHeard(0, None)


def live(specs: Iterable[RadioSpec]) -> list[RadioSpec]:
    """The radios that are not removed, by position (then id)."""
    return sorted((s for s in specs if s.removed_at is None), key=lambda s: (s.position, s.id))


def enabled(specs: Iterable[RadioSpec]) -> list[RadioSpec]:
    """The radios that are enabled and not removed, by position (then id)."""
    return [s for s in live(specs) if s.enabled]


def transmits(spec: RadioSpec) -> bool:
    """Whether the radio can send (its type's `can.transmit`: a receive-only type cannot); False for a type that is not known, which nothing describes."""
    try:
        return spec.rtype.can.transmit
    except RadioTypeError:
        return False


def senders(specs: Iterable[RadioSpec]) -> list[RadioSpec]:
    """The radios that are enabled and can send, by position (then id): the only ones a rule picks to send on (the main radio, a message's, the beacon's, an object's, the email radio)."""
    return [s for s in enabled(specs) if transmits(s)]


def number_in_kind(spec: RadioSpec, specs: Iterable[RadioSpec]) -> int:
    """The number of the radio within its kind ("FM", "HF 2"): 1 for the first of its kind by id among the live radios; a removed one is numbered by id among all of its kind, so that it keeps its number."""
    pool = list(specs) if spec.removed_at is not None else live(specs)
    return 1 + sum(1 for s in pool if s.kind == spec.kind and s.id < spec.id)


def log_name(spec: RadioSpec, specs: Iterable[RadioSpec]) -> str:
    """What the log and the support bundle call the radio: the name typed, else the kind's word with its number after the first ("FM", "HF 2", "LoRa"). The page makes its own from its catalogue."""
    if spec.name:
        return spec.name
    number = number_in_kind(spec, specs)
    return KIND_WORDS[spec.kind] + (f" {number}" if number > 1 else "")


def main_radio(specs: Iterable[RadioSpec], chosen: RadioId | None) -> RadioId | None:
    """The main radio (plan §2): the one chosen while it is enabled and can send, else the first such by position, else None (no radio, or none that can send)."""
    on = senders(specs)
    if chosen is not None and any(s.id == chosen for s in on):
        return chosen
    return on[0].id if on else None


def in_force_choice(choice: RadioId | None, specs: Iterable[RadioSpec]) -> RadioId | None:
    """A station's stored radio as it is in force: with one radio that can send (`senders`) that one, whatever is stored; else the choice while it names such a radio; else None ("automatic")."""
    on = senders(specs)
    if len(on) == 1:
        return on[0].id
    return choice if choice is not None and any(s.id == choice for s in on) else None


def in_force_set(ids: Iterable[RadioId], specs: Iterable[RadioSpec], main: RadioId | None) -> tuple[RadioId, ...]:
    """A stored set of radios (an object's, the beacon's) as it is in force: with one radio that can send (`senders`) that one; else its ticks of such radios, by position; else the main radio; else none."""
    on = senders(specs)
    if len(on) == 1:
        return (on[0].id,)
    ticked = set(ids)
    found = tuple(s.id for s in on if s.id in ticked)
    return found or ((main,) if main is not None else ())


def check_name(text: str, specs: Iterable[RadioSpec], own: RadioId | None) -> str:
    """A name the operator typed for a radio, as it is kept: stripped, at most MAX_NAME printable ASCII characters, unique among the live radios but `own` (case folded); "" is none. RadioError says why not."""
    name = text.strip()
    if not name:
        return ""
    if len(name) > MAX_NAME or not (name.isascii() and name.isprintable()):
        raise RadioError(f"the name {name!r} cannot be a radio's: a name is at most {MAX_NAME} printable ASCII characters (letters, digits and the signs of the keyboard)", "radio.name_form", name=name, max=MAX_NAME)
    taken = next((s for s in live(specs) if s.id != own and s.name.casefold() == name.casefold()), None)
    if taken is not None:
        raise RadioError(f"the name {name!r} is radio {taken.id}'s already: give this one another", "radio.name_taken", name=name, radio=taken.id)
    return name
