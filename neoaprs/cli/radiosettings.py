"""The radios of a database as the command line reads them (`neoaprs db`, `neoaprs doctor`, the support bundle): the settings in force with the radios stored, where a flat key of radios 1 and 2
(configradios.FLAT_HOMES: `tnc/profile`, `serial/port`, `hf/enabled`, `mercury/*` ...) lives once the radios are rows, and how a radio is reached, in a few words. Pure but for `radio_tables`,
which the callers run on their connection.

A database whose radios are not rows yet (a file older than migration 31) or that has none (a new installation: no radio is written until the daemon makes one) is read as before, from the flat keys
among the settings rows: what the daemon runs on such a database too. A file whose radios are rows and whose radio tables cannot be read is neither (`radio_tables` raises): its flat rows are never
read or written in their place."""
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from neoaprs.config import BY_KEY, DEFAULTS, LAST_PORT, SETTINGS, Config
from neoaprs.configradios import FLAT_HOMES, FLAT_KINDS, radio_key_of
from neoaprs.dberror import Connection, Row
from neoaprs.migrations import schema_version
from neoaprs.radiospec import KIND_WORDS, RadioId, RadioSpec, log_name
from neoaprs.radiosql import radio_rows, radio_settings
from neoaprs.radiotype import RadioType, RadioTypeError, stored_text
from neoaprs.radiotypes import kind_fields
from neoaprs.tncprofile import profile_of

RADIO_ROWS_FROM = 31                      # the version of the database from which the radios are rows of their own (migration 31, neoaprs/migrationsteps31.py)
FLAT_KEY_OF: Mapping[tuple[RadioId, str], str] = {FLAT_HOMES[s.attr]: s.key for s in SETTINGS if s.attr in FLAT_HOMES}     # (radio, its column or own key) -> the flat key that is its view


def in_force(rows: Mapping[str, str], radios: Sequence[RadioSpec]) -> Config:
    """The settings in force as the daemon reads them: with the radios stored, from them (the flat keys of radios 1 and 2 are their view); with none, from the flat keys among the rows."""
    return Config.from_data(rows, radios=radios or None)


def radio_tables(db: Connection) -> tuple[list[Row], list[Row]]:
    """The rows of `radio` and of `radio_setting` as they are stored (radiosql.py), none in a file older than migration 31. Raises the error of SQLite when they cannot be read, so that a file whose
    radios cannot be read is never taken for one that has none (Store.radios() gives none for both)."""
    if schema_version(db) < RADIO_ROWS_FROM:
        return [], []
    return radio_rows(db), radio_settings(db)


def stored_own(settings: Iterable[Row]) -> dict[tuple[RadioId, str], str]:
    """The radios' own settings as they are stored, by radio and key: a text that is no value too (RadioSpec.settings leaves it out, and its default is in force)."""
    return {(int(radio), str(key)): str(value) for radio, key, value in settings}


def flat_view(rows: Mapping[str, str], radios: Sequence[RadioSpec]) -> dict[str, str]:
    """Every setting as text, in force (`in_force`), but a flat key of a radio this station does not have (none of that id and kind, or a removed one) shows its default: a removed radio's old
    values are no setting of the station's."""
    shown, defaults = in_force(rows, radios).to_data(), DEFAULTS.to_data()
    return {key: defaults[key] if (home := flat_home(key, radios)) is not None and home[2] is None else text for key, text in shown.items()}


def flat_home(key: str, radios: Iterable[RadioSpec]) -> tuple[RadioId, str, RadioSpec | None] | None:
    """For a flat key of radios 1 and 2 on a database whose radios are stored (`radios` not empty): the radio's id, its column (`type`, `enabled`) or own key, and the radio, or None when this
    station has no such radio (none of the id and the kind, or a removed one). None for any other key, and for every key while no radio is stored."""
    specs = list(radios)
    setting = BY_KEY.get(key)
    if not specs or setting is None or setting.attr not in FLAT_HOMES:
        return None
    id, own = FLAT_HOMES[setting.attr]
    return id, own, next((s for s in specs if s.id == id and s.kind == FLAT_KINDS[id] and not s.removed), None)


def now_on(id: RadioId, own: str, specs: Sequence[RadioSpec]) -> str:
    """Where the flat key of radio `id`, which the station has not (`flat_home`), is now: the own key (`radio/3/port`), the Enable or the type of the station's first radio of that kind by position that is not
    removed, as the end of a sentence; "" for a station with no radio of the kind."""
    other = next((s for s in sorted(specs, key=lambda s: s.position) if s.id != id and s.kind == FLAT_KINDS[id] and not s.removed), None)
    if other is None:
        return ""
    where = f"radio {other.id}'s {'Enable' if own == 'enabled' else 'type'} (Settings tab, Radio)" if own in ("type", "enabled") else f"radio/{other.id}/{own}"
    return f"; this station's {KIND_WORDS[FLAT_KINDS[id]]} radio is radio {other.id} ({log_name(other, specs)}): it is {where} now"


def stored_text_of(key: str, rows: Mapping[str, str], radios: Sequence[RadioSpec], own_rows: Mapping[tuple[RadioId, str], str]) -> str | None:
    """The text a setting is stored as, None when it is not stored (its default is in force). With the radios stored, a flat key of a radio is its radio's: the type and whether it is on are always
    stored with the radio, an own key is its row of `radio_setting` (`own_rows`: the radio and its own key to the text as it is stored, a wrong one too), and `serial/last_port` is radio 1's own
    state row; every other key is its row of the settings table."""
    if radios and key == "serial/last_port" and LAST_PORT in rows:
        return rows[LAST_PORT]
    home = flat_home(key, radios)
    if home is None:
        return rows.get(key)
    id, own, spec = home
    if spec is None:
        return None
    if own == "type":
        return spec.type
    if own == "enabled":
        return stored_text(spec.enabled)
    return own_rows.get((id, own))


def own_key(key: str, radios: Iterable[RadioSpec]) -> tuple[RadioSpec | None, str] | None:
    """For a key `radio/<id>/<key>` that names a setting of a radio (a field of its kind): the radio (None when there is no radio of that id) and its own key; None for a key that is no radio's
    setting (the rows of a radio's state, `radio/<id>/last_port`, are not settings)."""
    found = radio_key_of(key)
    if found is None:
        return None
    id, own = found
    spec = next((s for s in radios if s.id == id), None)
    if spec is None:
        return None, own
    return (spec, own) if any(f.key == own for f in kind_fields(spec.kind)) else None


def type_or_none(spec: RadioSpec) -> RadioType | None:
    """The radio's type, None for a stored type this NeoAPRS does not know."""
    try:
        return spec.rtype
    except RadioTypeError:
        return None


def own_fields(spec: RadioSpec) -> list[str]:
    """The keys of a radio's own settings in the order its type lists them, then those of its kind that another type of the kind uses (a value it keeps from a type it had)."""
    rtype = type_or_none(spec)
    used = [f.key for f in rtype.fields] if rtype is not None else []
    return [*used, *(f.key for f in kind_fields(spec.kind) if f.key not in used)]


def value_text(spec: RadioSpec, key: str) -> str:
    """A radio's own setting as text, the value in force: the stored one, else the default of its field."""
    return stored_text(spec.value(key))


def reached(spec: RadioSpec) -> list[tuple[str, str]]:
    """How the radio is reached, as (label, words) for a summary or a checklist: the port and the speed of a serial line, the server of a KISS server, the sound card and the keying of a modem."""
    rtype = type_or_none(spec)
    if rtype is None:
        return [("Type", f"{spec.type}: no type of this NeoAPRS")]
    if rtype.transport == "serial":
        speed = spec.value("baud") or profile_baud(rtype) or 9600
        return [("Port", spec.value("port") or "(found by searching)"), ("Speed", f"{speed} baud")]
    if rtype.transport == "tcp":
        return [("Port", f"{spec.value('tcp_host')}:{spec.value('tcp_port')}" if spec.value("tcp_host") else "(no address chosen)")]
    if rtype.transport == "modem":
        return [("Sound card", spec.value("sound_card") or "(the daemon's choice)"), ("Keying", spec.value("keying") or "(the daemon's choice)")]
    return [("Traffic", "made up: nothing goes on the air")]


def profile_baud(rtype: RadioType) -> int | None:
    """The speed of the line of the type's profile, None for one with none of its own."""
    try:
        found: Any = profile_of(rtype.profile).baud
    except ValueError:
        return None
    return int(found) if found else None


def is_mercury(spec: RadioSpec) -> bool:
    """Whether the radio is a modem that the daemon starts (the Mercury HF modem), whose sound cards a report lists."""
    rtype = type_or_none(spec)
    return rtype is not None and rtype.transport == "modem"

