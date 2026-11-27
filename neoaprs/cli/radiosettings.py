"""The radios of a database as the command line reads them.

Used by `neoaprs db`, `doctor` and the support bundle. Pure except `radio_tables`, which
raises when the tables cannot be read, so such a file is never taken for one without radios."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from neoaprs.config import KEYS, LAST_PORT, STATION_KEYS, Config
from neoaprs.configradios import radio_key_of
from neoaprs.dberror import Connection, Row
from neoaprs.migrations import schema_version
from neoaprs.radiospec import RadioId, RadioSpec
from neoaprs.radiosql import radio_rows, radio_settings
from neoaprs.radiotype import RadioType, RadioTypeError, stored_text, type_label
from neoaprs.radiotypes import kind_fields
from neoaprs.tncprofile import names_tcp, profile_of

# First schema version with radios as rows of their own.
RADIO_ROWS_FROM = 31
SHOWN_KEYS = tuple(key for key in KEYS if key in STATION_KEYS or key == "serial/last_port")


def in_force(rows: Mapping[str, str], radios: Sequence[RadioSpec]) -> Config:
    return Config.from_data(rows, radios=radios)


def shown_settings(config: Config) -> dict[str, str]:
    data = config.to_data()
    return {key: data[key] for key in SHOWN_KEYS}


def radio_tables(db: Connection) -> tuple[list[Row], list[Row]]:
    """Return the `radio` and `radio_setting` rows (none before 31); raise if unreadable."""
    if schema_version(db) < RADIO_ROWS_FROM:
        return [], []
    return radio_rows(db), radio_settings(db)


def stored_own(settings: Iterable[Row]) -> dict[tuple[RadioId, str], str]:
    return {(int(radio), str(key)): str(value) for radio, key, value in settings}


def stored_text_of(key: str, rows: Mapping[str, str]) -> str | None:
    """Return the stored text of a setting, None if not stored."""
    if key == "serial/last_port" and LAST_PORT in rows:
        return rows[LAST_PORT]
    return rows.get(key)


def own_key(key: str, radios: Iterable[RadioSpec]) -> tuple[RadioSpec | None, str] | None:
    """Split `radio/<id>/<key>` into (radio, own key); the radio is None for an unknown id.

    Return None for any other key; state rows such as `radio/<id>/last_port` are not settings.
    """
    found = radio_key_of(key)
    if found is None:
        return None
    id, own = found
    spec = next((s for s in radios if s.id == id), None)
    if spec is None:
        return None, own
    return (spec, own) if any(f.key == own for f in kind_fields(spec.kind)) else None


def type_or_none(spec: RadioSpec) -> RadioType | None:
    """Return the radio's type, or None for an unknown stored type."""
    try:
        return spec.rtype
    except RadioTypeError:
        return None


def type_words(spec: RadioSpec) -> str:
    """Return the radio's type by its name and key ("Packet, KISS TNC (kiss)"); the key alone if unknown."""
    rtype = type_or_none(spec)
    return spec.type if rtype is None else f"{type_label(rtype)} ({spec.type})"


def own_fields(spec: RadioSpec) -> list[str]:
    """Return the keys of a radio's settings in its type's order, then other stored ones."""
    rtype = type_or_none(spec)
    if rtype is None:
        return [f.key for f in kind_fields(spec.kind)]
    used = [f.key for f in rtype.fields]
    return [*used, *(f.key for f in kind_fields(spec.kind) if f.key not in used and f.key in spec.settings)]


def value_text(spec: RadioSpec, key: str) -> str:
    return stored_text(spec.value(key))


def reached(spec: RadioSpec) -> list[tuple[str, str]]:
    """Return how the radio is reached as (label, words) pairs."""
    rtype = type_or_none(spec)
    if rtype is None:
        return [("Type", f"{spec.type}: no type of this NeoAPRS")]
    if rtype.transport == "serial":
        speed = spec.value("baud") or profile_baud(rtype) or 9600
        return [("Port", spec.value("port") or "(found by searching)"), ("Speed", f"{speed} baud")]
    if rtype.transport == "tcp":
        return [
            (
                "Port",
                f"{spec.value('tcp_host')}:{spec.value('tcp_port')}"
                if spec.value("tcp_host")
                else "(no address chosen)",
            )
        ]
    if rtype.transport == "modem":
        return [
            ("Sound card", spec.value("sound_card") or "(the daemon's choice)"),
            ("Keying", spec.value("keying") or "(the daemon's choice)"),
        ]
    return [("Traffic", "made up: nothing goes on the air")]


def port_problem(spec: RadioSpec) -> str:
    """Return why the radio's type and port do not go together, "" if they do.

    A TCP type uses `tcp_host` and `tcp_port`, not a serial port; a `tcp://` port is fine."""
    rtype = type_or_none(spec)
    try:
        transport = profile_of(rtype.profile).transport if rtype is not None else ""
    except ValueError:
        return ""
    port = str(spec.value("port")) if any(f.key == "port" for f in kind_fields(spec.kind)) else ""
    if transport != "tcp" or not port or names_tcp(port):
        return ""
    assert rtype is not None
    return f"{type_label(rtype)} connects over TCP (radio/{spec.id}/tcp_host and tcp_port), not to the serial port {port}: clear radio/{spec.id}/port, or give the radio a serial type"


def profile_baud(rtype: RadioType) -> int | None:
    try:
        found: Any = profile_of(rtype.profile).baud
    except ValueError:
        return None
    return int(found) if found else None


def is_mercury(spec: RadioSpec) -> bool:
    rtype = type_or_none(spec)
    return rtype is not None and rtype.transport == "modem"
