"""The radios of the settings, as read from the database (radiosql.py). No I/O.

The flat keys (tnc/profile, hf/enabled, ...) are views of radio 1 (FM) and radio 2 (HF);
`FLAT_HOMES` says where each lives."""
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from .coded import CodedError
from .packetcodec import parse_stamp
from .radiospec import FM_ID, HF_ID, KIND_WORDS, RadioError, RadioId, RadioSpec, enabled, live, senders, unheard_radio
from .radiotype import KINDS, Kind, stored_text
from .radiotypes import DEFAULT_TYPE, kind_field, kind_fields, recommended_path as kind_path

log = logging.getLogger("neoaprs.config")

# Flat attribute of Config -> (radio, column or own key).
FLAT_HOMES: Mapping[str, tuple[RadioId, str]] = {
    "tnc_profile": (FM_ID, "type"), "fm_enabled": (FM_ID, "enabled"), "serial_port": (FM_ID, "port"), "serial_baud": (FM_ID, "baud"), "tcp_host": (FM_ID, "tcp_host"), "tcp_port": (FM_ID, "tcp_port"),
    "beacon_path": (FM_ID, "path"), "digi_enabled": (FM_ID, "digipeat"),
    "hf_profile": (HF_ID, "type"), "hf_enabled": (HF_ID, "enabled"), "mercury_sound_card": (HF_ID, "sound_card"), "mercury_keying": (HF_ID, "keying"), "mercury_tx_gain_db": (HF_ID, "tx_gain_db"),
}
FLAT_KINDS: Mapping[RadioId, Kind] = {FM_ID: "fm", HF_ID: "hf"}
# Whether the radio is on when a flat key creates it.
FLAT_ON: Mapping[RadioId, bool] = {FM_ID: True, HF_ID: False}


def _default_radio(id: RadioId) -> RadioSpec:
    kind = FLAT_KINDS[id]
    return RadioSpec(id, kind, DEFAULT_TYPE[kind], "", FLAT_ON[id], id, settings=MappingProxyType({f.key: f.default for f in kind_fields(kind)}))


DEFAULT_RADIOS: tuple[RadioSpec, ...] = (_default_radio(FM_ID), _default_radio(HF_ID))


class FlatRadios(Protocol):
    @property
    def tnc_profile(self) -> str: ...
    @property
    def fm_enabled(self) -> bool: ...
    @property
    def serial_port(self) -> str: ...
    @property
    def serial_baud(self) -> int | None: ...
    @property
    def tcp_host(self) -> str: ...
    @property
    def tcp_port(self) -> int: ...
    @property
    def beacon_path(self) -> str: ...
    @property
    def digi_enabled(self) -> bool: ...
    @property
    def hf_profile(self) -> str: ...
    @property
    def hf_enabled(self) -> bool: ...
    @property
    def mercury_sound_card(self) -> str: ...
    @property
    def mercury_keying(self) -> str: ...
    @property
    def mercury_tx_gain_db(self) -> int: ...


def radios_from_flat(config: FlatRadios) -> tuple[RadioSpec, ...]:
    """Return radio 1 (FM) and radio 2 (HF) as the flat values say, with the beacon on."""
    fm = {"port": config.serial_port, "baud": stored_text(config.serial_baud), "tcp_host": config.tcp_host, "tcp_port": stored_text(config.tcp_port),
          "beacon": "true", "path": config.beacon_path, "digipeat": stored_text(config.digi_enabled)}
    hf = {"sound_card": config.mercury_sound_card, "keying": config.mercury_keying, "tx_gain_db": stored_text(config.mercury_tx_gain_db), "beacon": "true"}
    flat = (RadioSpec(FM_ID, "fm", config.tnc_profile, "", config.fm_enabled, 1, settings=fm), RadioSpec(HF_ID, "hf", config.hf_profile, "", config.hf_enabled, 2, settings=hf))
    # Fields no flat key holds get their defaults.
    return tuple(replace(spec, settings={**{f.key: f.default for f in kind_fields(spec.kind)}, **spec.settings}) for spec in flat)


def radios_from_rows(rows: Iterable[Sequence[Any]], settings: Iterable[Sequence[Any]]) -> tuple[RadioSpec, ...]:
    """Return the radios by id from the radio rows and settings.

    Settings of another kind or with a wrong value are left out; an unknown kind is skipped."""
    own: dict[RadioId, dict[str, str]] = {}
    for radio, key, value in settings:
        own.setdefault(int(radio), {})[str(key)] = str(value)
    found: list[RadioSpec] = []
    for id, kind, type, name, on, position, removed_at in rows:
        if kind not in KINDS:
            log.warning("radio %s is of the kind %r, which is none: it is left out", id, kind)
            continue
        found.append(RadioSpec(int(id), kind, str(type), str(name), bool(on), int(position), None if removed_at is None else parse_stamp(str(removed_at)), _checked(int(id), kind, own.get(int(id), {}))))
    return _kind_words_dropped(tuple(sorted(found, key=lambda spec: spec.id)))


def _kind_words_dropped(specs: tuple[RadioSpec, ...]) -> tuple[RadioSpec, ...]:
    """Clear a name equal to a kind's word: unnamed radios are shown by it, so they would clash."""
    words = {word.casefold() for word in KIND_WORDS.values()}
    return tuple(replace(spec, name="") if spec.name.casefold() in words else spec for spec in specs)


def _checked(id: RadioId, kind: Kind, stored: Mapping[str, str]) -> dict[str, str]:
    kept: dict[str, str] = {}
    for key, text in stored.items():
        field = kind_field(kind, key)
        if field is None:
            continue
        try:
            field.parse(text)
        except ValueError as e:
            log.warning("radio/%d/%s: %s; the default %s is used", id, key, e, field.default or "(empty)")
            continue
        kept[key] = text
    return kept


def radio_state_key(radio: RadioId, name: str) -> str:
    """Return the settings row key of a radio's state, `radio/<id>/<name>`."""
    return f"radio/{radio}/{name}"


_RADIO_KEY = re.compile(r"radio/([1-9][0-9]*)/([^/]+)")


def radio_key_of(text: str) -> tuple[RadioId, str] | None:
    found = _RADIO_KEY.fullmatch(text)
    return (int(found[1]), found[2]) if found else None


def _flat_radio(radios: Iterable[RadioSpec], id: RadioId) -> RadioSpec | None:
    """Return the radio `id` if it has the expected kind and is not removed, else None."""
    return next((s for s in radios if s.id == id and s.kind == FLAT_KINDS[id] and not s.removed), None)


def flat_value(radios: Iterable[RadioSpec], attr: str) -> Any:
    """Return the value of a flat attribute; a missing radio reads as off with the defaults."""
    id, key = FLAT_HOMES[attr]
    spec = _flat_radio(radios, id)
    if key == "enabled":
        return spec is not None and spec.enabled and not spec.removed
    spec = spec or _default_radio(id)
    return spec.type if key == "type" else _own_value(spec, key)


def _own_value(spec: RadioSpec, key: str) -> Any:
    """Return a radio's own setting: the parsed text, or the default if none.

    Text that does not parse (put in unchecked by `replace`) is returned as is or as its number."""
    found = kind_field(spec.kind, key)
    assert found is not None, key
    text = spec.settings.get(key)
    if text is None:
        return found.parse(found.default)
    try:
        return found.parse(text)
    except ValueError:
        if found.kind == "bool":
            return text == "true"
        if found.kind == "int":
            return int(text) if text.lstrip("-").isdigit() else found.parse(found.default)
        return text


def with_flat(radios: Iterable[RadioSpec], values: Mapping[str, Any]) -> tuple[RadioSpec, ...]:
    """Return the radios with these flat values (attribute to value) put in."""
    found = {s.id: s for s in radios}
    for attr, value in values.items():
        if flat_value(found.values(), attr) == value:
            continue
        id, key = FLAT_HOMES[attr]
        spec = _flat_radio(found.values(), id)
        if spec is None and id in found and found[id].removed:
            # A removed radio takes no change; the store refuses the save.
            spec = found[id]
        elif spec is None:
            if id in found:
                raise RadioError(f"radio {id} is of the kind {found[id].kind}: {attr} names no radio", "failed")
            spec = replace(_default_radio(id), settings={})
        if key == "type":
            spec = replace(spec, type=str(value))
        elif key == "enabled":
            spec = replace(spec, enabled=bool(value))
        else:
            spec = replace(spec, settings={**spec.settings, key: stored_text(value)})
        found[id] = spec
    return tuple(found[id] for id in sorted(found))


def path_text(radios: Iterable[RadioSpec], radio: RadioId) -> str:
    """Return the radio's `path`, or its kind's recommended path if empty; "" if it has none."""
    spec = next((s for s in radios if s.id == radio and not s.removed), None)
    found = None if spec is None else kind_field(spec.kind, "path")
    if spec is None or found is None:
        return ""
    text = spec.settings.get("path", found.default)
    try:
        return str(found.parse(text)) or kind_path(spec.kind)
    except ValueError:
        return text


def flat_moved(attr: str, radios: Iterable[RadioSpec]) -> CodedError | None:
    """Return the refusal for a flat key that moved to a radio's own key, else None."""
    if attr not in FLAT_HOMES:
        return None
    field = FLAT_HOMES[attr][1]
    if field in ("type", "enabled"):
        return CodedError(f"no such setting: it is radio_change's {field} now", "setting.unknown")
    found = flat_now(attr, radios)
    return CodedError(f"no such setting: it is radio/{'<id>' if found is None else found.id}/{field} now", "setting.unknown")


def flat_now(attr: str, radios: Iterable[RadioSpec]) -> RadioSpec | None:
    """Return the lowest-id live radio of the attribute's kind, or None."""
    return min((spec for spec in live(radios) if spec.kind == FLAT_KINDS[FLAT_HOMES[attr][0]]), key=lambda spec: spec.id, default=None)


def _view(attr: str) -> property:
    return property(lambda self: flat_value(self.radios, attr), doc=f"The flat view `{attr}` of radio {FLAT_HOMES[attr][0]} (configradios.FLAT_HOMES).")


if TYPE_CHECKING:
    @dataclass(frozen=True)
    class FlatFields:
        """For the type checker the flat names are fields of Config."""
        tnc_profile: str = ""
        serial_port: str = ""
        serial_baud: int | None = None
        tcp_host: str = ""
        tcp_port: int = 0
        hf_enabled: bool = False
        hf_profile: str = ""
        mercury_sound_card: str = ""
        mercury_keying: str = ""
        mercury_tx_gain_db: int = 0
        fm_enabled: bool = True
        beacon_path: str = ""
        digi_enabled: bool = False
else:
    class FlatFields:
        """The flat names of radios 1 and 2 on `Config`: properties over the radios."""

    for _attr in FLAT_HOMES:
        setattr(FlatFields, _attr, _view(_attr))


def accepting_flat[C](cls: type[C]) -> type[C]:
    """Make the constructor of `cls` accept the flat names as keywords (put into `radios`)."""
    made = cls.__init__

    def __init__(self: Any, *args: Any, **values: Any) -> None:
        flat = {attr: values.pop(attr) for attr in tuple(values) if attr in FLAT_HOMES}
        made(self, *args, **values)
        if flat:
            object.__setattr__(self, "radios", with_flat(self.radios, flat))

    __init__.__wrapped__ = made  # type: ignore[attr-defined]  # what inspect shows
    setattr(cls, "__init__", __init__)  # noqa: B010  (mypy refuses assigning to __init__)
    return cls


class RadioViews:
    radios: tuple[RadioSpec, ...]

    def radio(self, id: RadioId) -> RadioSpec | None:
        return next((s for s in self.radios if s.id == id), None)

    @property
    def live_radios(self) -> list[RadioSpec]:
        return live(self.radios)

    @property
    def enabled_radios(self) -> list[RadioSpec]:
        return enabled(self.radios)

    @property
    def listens_only(self) -> bool:
        return bool(self.enabled_radios) and not senders(self.radios)

    @property
    def unheard_radio(self) -> RadioId | None:
        return unheard_radio(self.radios)

    @staticmethod
    def check_radio(spec: RadioSpec, key: str, text: str) -> str:
        """Return the setting text as stored; raise RadioError if invalid."""
        found, named = kind_field(spec.kind, key), f"radio/{spec.id}/{key}"
        if found is None:
            raise RadioError(f"{named}: a radio of the kind {spec.kind} has no such setting", "setting.unknown")
        try:
            return stored_text(found.parse(text))
        except CodedError as e:
            raise RadioError(f"{named}: {e}", e.code, **e.params) from None
        except ValueError as e:
            raise RadioError(f"{named}: {e}", "failed") from None

