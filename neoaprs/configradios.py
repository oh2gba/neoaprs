"""The radios of the settings. `Config.radios` holds them as they are stored (`radios_from_rows`: the rows of the tables `radio` and `radio_setting`, neoaprs/radiosql.py), and `RadioViews` gives `Config`
what is read of them. The rows of a radio's own state (its beacon's last send, the port its search found) are `radio_state_key`'s. No I/O.

Until the page and the wire name a radio by its id (wave 4 of the radio round; the views go in W3), today's flat keys stay as a view of radio 1, the FM radio (tnc/profile, fm/enabled, serial/port,
serial/baud, tcp/*, beacon/path, digi/enabled), and radio 2, the HF radio (hf/profile, hf/enabled, mercury/*): `FLAT_HOMES` says where each lives, `flat_value` reads one, `with_flat` puts values in, and
`FlatFields` gives `Config` the old attributes (`config.hf_enabled`) and takes them as keywords (`replace(config, hf_enabled=True)`)."""
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from .coded import CodedError
from .packetcodec import parse_stamp
from .radiospec import FM_ID, HF_ID, RadioError, RadioId, RadioSpec, enabled, live, main_radio, senders
from .radiotype import KINDS, Kind, stored_text
from .radiotypes import DEFAULT_TYPE, kind_field, kind_fields, recommended_path as kind_path

log = logging.getLogger("neoaprs.config")

FLAT_HOMES: Mapping[str, tuple[RadioId, str]] = {       # a flat attribute of Config, and where it lives: the radio, and its column (`type`, `enabled`) or its own key
    "tnc_profile": (FM_ID, "type"), "fm_enabled": (FM_ID, "enabled"), "serial_port": (FM_ID, "port"), "serial_baud": (FM_ID, "baud"), "tcp_host": (FM_ID, "tcp_host"), "tcp_port": (FM_ID, "tcp_port"),
    "beacon_path": (FM_ID, "path"), "digi_enabled": (FM_ID, "digipeat"),
    "hf_profile": (HF_ID, "type"), "hf_enabled": (HF_ID, "enabled"), "mercury_sound_card": (HF_ID, "sound_card"), "mercury_keying": (HF_ID, "keying"), "mercury_tx_gain_db": (HF_ID, "tx_gain_db"),
}
FLAT_KINDS: Mapping[RadioId, Kind] = {FM_ID: "fm", HF_ID: "hf"}       # the kind of the radio a flat key is a view of: a radio of the id and another kind is not it
FLAT_ON: Mapping[RadioId, bool] = {FM_ID: True, HF_ID: False}         # whether such a radio is on when a flat key makes it (today's defaults of fm/enabled and hf/enabled)


def _default_radio(id: RadioId) -> RadioSpec:
    kind = FLAT_KINDS[id]
    return RadioSpec(id, kind, DEFAULT_TYPE[kind], "", FLAT_ON[id], id, settings=MappingProxyType({f.key: f.default for f in kind_fields(kind)}))      # (read-only: every Config that says nothing shares them)


DEFAULT_RADIOS: tuple[RadioSpec, ...] = (_default_radio(FM_ID), _default_radio(HF_ID))       # the radios of settings that say nothing: today's FM radio, on, and HF radio, off (a database without radios has none: Config.from_data(rows, radios=()))


class FlatRadios(Protocol):
    """The flat settings the two radios of today are made of (Config's views)."""
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
    """Radio 1 (fm: tnc/profile, fm/enabled, the port, the speed and the TCP server from serial/* and tcp/*, the path from beacon/path, the digipeater from digi/enabled) and radio 2 (hf: hf/profile, hf/enabled,
    the sound card, the keying and the gain from mercury/*), the beacon on both: the two radios that flat values say."""
    fm = {"port": config.serial_port, "baud": stored_text(config.serial_baud), "tcp_host": config.tcp_host, "tcp_port": stored_text(config.tcp_port),
          "beacon": "true", "path": config.beacon_path, "digipeat": stored_text(config.digi_enabled)}
    hf = {"sound_card": config.mercury_sound_card, "keying": config.mercury_keying, "tx_gain_db": stored_text(config.mercury_tx_gain_db), "beacon": "true"}
    flat = (RadioSpec(FM_ID, "fm", config.tnc_profile, "", config.fm_enabled, 1, settings=fm), RadioSpec(HF_ID, "hf", config.hf_profile, "", config.hf_enabled, 2, settings=hf))
    return tuple(replace(spec, settings={**{f.key: f.default for f in kind_fields(spec.kind)}, **spec.settings}) for spec in flat)      # (the kind's other fields, which no flat key holds, at their defaults)


def radios_from_rows(rows: Iterable[Sequence[Any]], settings: Iterable[Sequence[Any]]) -> tuple[RadioSpec, ...]:
    """The radios as the database keeps them, by id: `rows` are radiosql.radio_rows (id, kind, type, name, enabled, position, removed_at) and `settings` radiosql.radio_settings (radio_id, key, value).
    A radio has the settings of its kind that are stored, as text: a key that is no setting of the kind is left out (the table keeps it), and a value that is wrong is left out and told once, with
    `radio/<id>/<key>`, so that the default is in force. A row whose kind is none is left out and told."""
    own: dict[RadioId, dict[str, str]] = {}
    for radio, key, value in settings:
        own.setdefault(int(radio), {})[str(key)] = str(value)
    found: list[RadioSpec] = []
    for id, kind, type, name, on, position, removed_at in rows:
        if kind not in KINDS:
            log.warning("radio %s is of the kind %r, which is none: it is left out", id, kind)
            continue
        found.append(RadioSpec(int(id), kind, str(type), str(name), bool(on), int(position), None if removed_at is None else parse_stamp(str(removed_at)), _checked(int(id), kind, own.get(int(id), {}))))
    return tuple(sorted(found, key=lambda spec: spec.id))


def _checked(id: RadioId, kind: Kind, stored: Mapping[str, str]) -> dict[str, str]:
    """The stored settings of a radio that are settings of its kind and values of them."""
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
    """The row of the settings table that keeps a radio's own state (services/memory.py): `radio/<id>/beacon_last_sent_at`, `radio/<id>/last_port`."""
    return f"radio/{radio}/{name}"


_RADIO_KEY = re.compile(r"radio/([1-9][0-9]*)/([^/]+)")


def radio_key_of(text: str) -> tuple[RadioId, str] | None:
    """The radio and its own key that a key `radio/<id>/<key>` names (radio_state_key's rows, and the wire's and the command line's keys of a radio's setting); None for a key that is no radio's."""
    found = _RADIO_KEY.fullmatch(text)
    return (int(found[1]), found[2]) if found else None


# ---- the flat keys as a view of radios 1 and 2

def _flat_radio(radios: Iterable[RadioSpec], id: RadioId) -> RadioSpec | None:
    """The radio a flat key of radio `id` is a view of: the one with that id, of the kind it has today, not removed; None when there is none (a removed radio's flat keys say the kind's defaults)."""
    return next((s for s in radios if s.id == id and s.kind == FLAT_KINDS[id] and not s.removed), None)


def flat_value(radios: Iterable[RadioSpec], attr: str) -> Any:
    """What a flat attribute says of these radios: the radio's type, whether it is on, or its own setting; for a radio that is not there, a radio that is off with the defaults of its kind."""
    id, key = FLAT_HOMES[attr]
    spec = _flat_radio(radios, id)
    if key == "enabled":
        return spec is not None and spec.enabled and not spec.removed
    spec = spec or _default_radio(id)
    return spec.type if key == "type" else _own_value(spec, key)


def _own_value(spec: RadioSpec, key: str) -> Any:
    """A radio's own setting as the flat field of before held it: the value of the stored text, the default when there is none, and for a text that is no value (one put into a Config unchecked, as
    `replace(config, beacon_path=...)` puts it: a stored one is checked when it is read from the database) the text itself, or the number it says, as the field kept whatever it was given."""
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
    """The radios with these flat values (attribute to value) put in, by id. A value that is what the radios say already changes nothing; one for a radio that is not there makes it (the FM radio on, the HF
    radio off, as the flat keys' defaults say)."""
    found = {s.id: s for s in radios}
    for attr, value in values.items():
        if flat_value(found.values(), attr) == value:
            continue
        id, key = FLAT_HOMES[attr]
        spec = _flat_radio(found.values(), id)
        if spec is None and id in found and found[id].removed:
            spec = found[id]                # (a removed radio keeps its row and takes no change: the store refuses the save)
        elif spec is None:
            if id in found:
                raise RadioError(f"radio {id} is of the kind {found[id].kind}: {attr} names no radio")
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
    """The radio's own path as the setting says it (`radio/<id>/path`: DIRECT none), empty the path its kind recommends (LoRa WIDE1-1); "" for a radio that is not there, is removed or whose kind has no
    path of its own, and for an empty one of a kind that recommends none (the station's symbol's then). A stored text that is no path (one put into a Config unchecked: a stored one is checked when it is
    read) is taken as it is."""
    spec = next((s for s in radios if s.id == radio and not s.removed), None)
    found = None if spec is None else kind_field(spec.kind, "path")
    if spec is None or found is None:
        return ""
    text = spec.settings.get("path", found.default)
    try:
        return str(found.parse(text)) or kind_path(spec.kind)
    except ValueError:
        return text


def flat_moved(attr: str, radios: Iterable[RadioSpec], main: RadioId | None) -> CodedError | None:
    """For a flat attribute, the refusal of its key (`serial/port`, `hf/enabled`) in one sentence that names where it is now: a radio's own key, `radio/<id>/<key>`, with the id of the main radio of that kind where
    the station has one (else of its first radio of the kind, else `<id>`), and for its Enable and type the command `radio_change`; None for any other attribute. The page's `set_config` says it, and `neoaprs db` for a radio's own key (its type and Enable it names by the radio's number, dbcmd.moved)."""
    if attr not in FLAT_HOMES:
        return None
    field = FLAT_HOMES[attr][1]
    if field in ("type", "enabled"):
        return CodedError(f"no such setting: it is radio_change's {field} now", "setting.unknown")
    found = flat_now(attr, radios, main)
    return CodedError(f"no such setting: it is radio/{'<id>' if found is None else found.id}/{field} now", "setting.unknown")


def flat_now(attr: str, radios: Iterable[RadioSpec], main: RadioId | None) -> RadioSpec | None:
    """The radio a flat attribute's value is on now (`flat_moved`): the main radio where it is of the attribute's kind, else the station's first radio of that kind; None when it has none."""
    ofkind = [spec for spec in live(radios) if spec.kind == FLAT_KINDS[FLAT_HOMES[attr][0]]]
    return next((spec for spec in ofkind if spec.id == main), ofkind[0] if ofkind else None)


def _view(attr: str) -> property:
    return property(lambda self: flat_value(self.radios, attr), doc=f"The flat view `{attr}` of radio {FLAT_HOMES[attr][0]} (configradios.FLAT_HOMES).")


if TYPE_CHECKING:
    @dataclass(frozen=True)
    class FlatFields:
        """For the type checker the flat names are fields of Config, as they were before the radios were stored, so that every `config.hf_enabled`, `Config(tnc_profile=...)` and
        `replace(config, serial_port=...)` is checked as it was. At run time (below) they are views and keywords."""
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
        """Today's flat names of radios 1 and 2 on `Config`: each a property that reads the radios (`flat_value`), and a keyword the constructor takes and puts into the radios (`accepting_flat`)."""

    for _attr in FLAT_HOMES:
        setattr(FlatFields, _attr, _view(_attr))


def accepting_flat[C](cls: type[C]) -> type[C]:
    """The class with a constructor that also takes the flat names as keywords and puts them into its `radios` (with_flat), so that `Config(hf_enabled=True)` and `replace(config, hf_enabled=True)` work as
    they did when the flat names were fields."""
    made = cls.__init__

    def __init__(self: Any, *args: Any, **values: Any) -> None:
        flat = {attr: values.pop(attr) for attr in tuple(values) if attr in FLAT_HOMES}
        made(self, *args, **values)
        if flat:
            object.__setattr__(self, "radios", with_flat(self.radios, flat))

    __init__.__wrapped__ = made         # type: ignore[attr-defined]  # (what inspect shows)
    setattr(cls, "__init__", __init__)  # noqa: B010  (assigning to __init__ by name is what mypy refuses)
    return cls


class RadioViews:
    """What is read of the radios of the settings, as `Config` gives it (its base)."""
    radios: tuple[RadioSpec, ...]
    main_choice: RadioId | None

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
        """Some radio is enabled and none of those can send (each is of a receive-only type): nothing is transmitted, as while RX only is ticked."""
        return bool(self.enabled_radios) and not senders(self.radios)

    @property
    def main_radio(self) -> RadioId | None:
        """The main radio (radiospec.main_radio): the one chosen while it is enabled and can send, else the first such by position, else none."""
        return main_radio(self.radios, self.main_choice)

    @staticmethod
    def check_radio(spec: RadioSpec, key: str, text: str) -> str:
        """The text of a radio's setting as it is stored; RadioError naming `radio/<id>/<key>` when the key is no setting of its kind or the text is not a value of it."""
        found, named = kind_field(spec.kind, key), f"radio/{spec.id}/{key}"
        if found is None:
            raise RadioError(f"{named}: a radio of the kind {spec.kind} has no such setting", "setting.unknown")
        try:
            return stored_text(found.parse(text))
        except CodedError as e:
            raise RadioError(f"{named}: {e}", e.code, **e.params) from None
        except ValueError as e:
            raise RadioError(f"{named}: {e}") from None

