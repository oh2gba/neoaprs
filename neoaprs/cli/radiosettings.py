"""The radios of a database as the command line reads them (`neoaprs db`, `neoaprs doctor`, the support bundle): the settings in force with the radios stored, a radio's own settings as they are stored,
and how a radio is reached, in a few words. Pure but for `radio_tables`, which the callers run on their connection.

A file whose radio tables cannot be read is never read as one without radios (`radio_tables` raises); a new installation has none until the operator adds one."""
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from neoaprs.config import KEYS, LAST_PORT, STATION_KEYS, Config
from neoaprs.configradios import radio_key_of
from neoaprs.dberror import Connection, Row
from neoaprs.migrations import schema_version
from neoaprs.radiospec import RadioId, RadioSpec
from neoaprs.radiosql import radio_rows, radio_settings
from neoaprs.radiotype import RadioType, RadioTypeError, stored_text
from neoaprs.radiotypes import kind_fields
from neoaprs.tncprofile import names_tcp, profile_of

RADIO_ROWS_FROM = 31                      # the version of the database from which the radios are rows of their own (migration 31, neoaprs/migrationsteps31.py)
SHOWN_KEYS = tuple(key for key in KEYS if key in STATION_KEYS or key == "serial/last_port")       # the settings `neoaprs db list` and the bundle show, in the form's order: the station's, and radio 1's last port (a radio's own are `radio/<id>/<key>`)


def in_force(rows: Mapping[str, str], radios: Sequence[RadioSpec]) -> Config:
    """The settings in force as the daemon reads them, with the radios stored (none for a new installation)."""
    return Config.from_data(rows, radios=radios)


def shown_settings(config: Config) -> dict[str, str]:
    """The settings of SHOWN_KEYS as text, in force."""
    data = config.to_data()
    return {key: data[key] for key in SHOWN_KEYS}


def radio_tables(db: Connection) -> tuple[list[Row], list[Row]]:
    """The rows of `radio` and of `radio_setting` as they are stored (radiosql.py), none in a file older than migration 31. Raises the error of SQLite when they cannot be read, so that a file whose
    radios cannot be read is never taken for one that has none (Store.radios() gives none for both)."""
    if schema_version(db) < RADIO_ROWS_FROM:
        return [], []
    return radio_rows(db), radio_settings(db)


def stored_own(settings: Iterable[Row]) -> dict[tuple[RadioId, str], str]:
    """The radios' own settings as they are stored, by radio and key: a text that is no value too (RadioSpec.settings leaves it out, and its default is in force)."""
    return {(int(radio), str(key)): str(value) for radio, key, value in settings}


def stored_text_of(key: str, rows: Mapping[str, str]) -> str | None:
    """The text a setting is stored as, None when it is not stored (its default is in force): its row of the settings table, and for `serial/last_port` radio 1's own state row, which is read in its
    place."""
    if key == "serial/last_port" and LAST_PORT in rows:
        return rows[LAST_PORT]
    return rows.get(key)


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


def port_problem(spec: RadioSpec) -> str:
    """Why the radio's type and its own port do not go together, "" when they do: a TCP type connects to its KISS server (its `tcp_host` and `tcp_port`), not to a serial device (a `tcp://` address
    in its port is fine)."""
    rtype = type_or_none(spec)
    try:
        transport = profile_of(rtype.profile).transport if rtype is not None else ""
    except ValueError:
        return ""
    port = str(spec.value("port")) if any(f.key == "port" for f in kind_fields(spec.kind)) else ""
    if transport != "tcp" or not port or names_tcp(port):
        return ""
    assert rtype is not None
    return f"{rtype.name} connects over TCP (radio/{spec.id}/tcp_host and tcp_port), not to the serial port {port}: clear radio/{spec.id}/port, or give the radio a serial type"


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

