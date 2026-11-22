"""`neoaprs db radios` and `neoaprs db radios add`: list the stored radios and add one.

A radio is added with the checks of the page's Add (radioedits.new_radio)."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from neoaprs.cli.redaction import shown_value
from neoaprs.configradios import radios_from_rows
from neoaprs.dberror import SqlError
from neoaprs.radioedits import new_radio
from neoaprs.radiospec import RadioSpec, log_name
from neoaprs.store import Store

from .output import say
from .radiosettings import in_force, own_fields, radio_tables, stored_own, value_text

PROG = "neoaprs db"


@dataclass(frozen=True)
class Radios:
    """The radios as the daemon reads them, and their settings as stored (invalid texts too)."""

    specs: tuple[RadioSpec, ...] = ()
    own: Mapping[tuple[int, str], str] = field(default_factory=dict)


async def stored_radios(store: Store) -> Radios:
    """Return the stored radios; raise SqlError if they cannot be read.

    A failed read must not look like no radios, which Store.radios() cannot tell apart."""
    assert store.db is not None
    try:
        rows, settings = await store.db.read(radio_tables)
    except SqlError as e:
        raise SqlError(f"the radios cannot be read: {e}; restore a copy (neoaprs db restore)") from e
    return Radios(radios_from_rows(rows, settings), stored_own(settings))


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%SZ")


def radio_state(spec: RadioSpec) -> str:
    if spec.removed_at is not None:
        return f"removed {stamp(spec.removed_at)}"
    return "on" if spec.enabled else "off"


async def show_radios(store: Any) -> int:
    """Print each radio, removed ones last, with its settings: value in force, stored or default."""
    stored = await stored_radios(store)
    radios = stored.specs
    if not radios:
        say(f"{PROG}: this station has no radio yet: add one (radios add TYPE, or on the page)")
        return 0
    keys = {spec.id: own_fields(spec) for spec in radios}
    width = max(len(f"radio/{id}/{key}") for id, own in keys.items() for key in own)
    for spec in sorted(radios, key=lambda s: (s.removed_at is not None, s.position, s.id)):
        print(
            f"radio {spec.id}  {log_name(spec, radios)}  {spec.kind}  {spec.type}  {radio_state(spec)}  (position {spec.position})"
        )
        for key in keys[spec.id]:
            name = f"radio/{spec.id}/{key}"
            print(
                f"  {name:<{width}}  {shown_value(name, value_text(spec, key)):<18}  {'stored' if (spec.id, key) in stored.own else 'default'}"
            )
    return 0


async def add_radio(store: Store, type: str, name: str, on: bool) -> int:
    """Add a radio after the others, checked as the page's Add is; return the exit code."""
    rows, radios = await store.settings(), (await stored_radios(store)).specs
    try:
        spec = new_radio(in_force(rows, radios), type, name, on)
    except ValueError as e:
        say(f"{PROG}: {e}")
        return 2
    id = await store.add_radio(spec.kind, spec.type, spec.name, spec.enabled, spec.position, by_rows=True)
    if id is None:
        say(f"{PROG}: the radio could not be stored")
        return 1
    added = replace(spec, id=id)
    print(
        f"radio {id}  {log_name(added, (*radios, added))}  {spec.kind}  {spec.type}  {radio_state(added)}  (position {spec.position})"
    )
    return 0
