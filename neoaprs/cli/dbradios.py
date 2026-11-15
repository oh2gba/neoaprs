"""`neoaprs db radios` and `neoaprs db radios add` (neoaprs/cli/dbcmd.py is the command): the radios of the database as they are stored, each with its own settings, and a radio added as the page's Add adds
one (radioedits.new_radio's checks); the database gives it its number."""
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
    """The radios of the database: as the daemon reads them (a wrong value left out, told once) and their own settings as they are stored (a text that is no value too)."""
    specs: tuple[RadioSpec, ...] = ()
    own: Mapping[tuple[int, str], str] = field(default_factory=dict)


async def stored_radios(store: Store) -> Radios:
    """The radios as they are stored. SqlError, with the way back, when the file's radios cannot be read: such a file is never read or written as one without radios, whose flat rows nothing
    reads once its radios are rows (Store.radios() gives none for a failed read too; Store.read_radios() tells it apart)."""
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
    """`radios`: each radio, the removed ones last, with its own settings in the order its type lists them: the value in force, and whether it is stored or the default."""
    stored = await stored_radios(store)
    radios = stored.specs
    if not radios:
        say(f"{PROG}: this station has no radio yet: add one (radios add TYPE, or on the page)")
        return 0
    keys = {spec.id: own_fields(spec) for spec in radios}
    width = max(len(f"radio/{id}/{key}") for id, own in keys.items() for key in own)
    for spec in sorted(radios, key=lambda s: (s.removed_at is not None, s.position, s.id)):
        print(f"radio {spec.id}  {log_name(spec, radios)}  {spec.kind}  {spec.type}  {radio_state(spec)}  (position {spec.position})")
        for key in keys[spec.id]:
            name = f"radio/{spec.id}/{key}"
            print(f"  {name:<{width}}  {shown_value(name, value_text(spec, key)):<18}  {'stored' if (spec.id, key) in stored.own else 'default'}")
    return 0


async def add_radio(store: Store, type: str, name: str, on: bool) -> int:
    """`radios add TYPE [NAME]`: a radio of the type after the others, checked as the daemon checks the page's Add (radioedits.new_radio: a type there is, a name no other radio has), on unless `--off`;
    the database gives it its id. The exit code."""
    rows, radios = await store.settings(), (await stored_radios(store)).specs
    try:
        spec = new_radio(in_force(rows, radios), type, name, on)
    except ValueError as e:
        say(f"{PROG}: {e}")
        return 2
    id = await store.add_radio(spec.kind, spec.type, spec.name, spec.enabled, spec.position)
    if id is None:
        say(f"{PROG}: the radio could not be stored")
        return 1
    added = replace(spec, id=id)
    print(f"radio {id}  {log_name(added, (*radios, added))}  {spec.kind}  {spec.type}  {radio_state(added)}  (position {spec.position})")
    return 0
