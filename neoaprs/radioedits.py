"""The radios of the settings as the operator changes them (plan §2): what the controller's `add_radio`, `change_radio`, `remove_radio` and `save_radio_settings` check before anything is stored (each
refusal a `RadioError` of neoaprs/radiospec.py naming the radio, uncoded until the wire names a radio; a type that is none a `RadioTypeError`), the radios of the settings with one of them changed, what a
save of the settings writes of the radios (`radio_writes`: a radio the flat keys of today first name is new, and is written with its id), and the stand-in of a database that has no radio yet.

The stand-in (until a new installation starts with no radio and the setup guide adds the first: package W3 deletes it): at the start, on a database whose table `radio` is empty, the radios today's program
would run are written first, with the ids they have always had (`seed`): radio 1, the FM radio, from the flat values in force, and radio 2, the HF radio, when the run was given its Mercury (--hf-port) or a
row of the settings names it; their flat rows become theirs as migration 31 made them (neoaprs/radiosql.py `seed_radios`, which decides by its first insert that there is no radio). From then on the
database is one with radios. Only when the radios cannot be read at all (`Store.radios()` gave none, which can be a failed read) does the daemon run today's FM radio as the flat values say it
(`stand_in`), and then it writes no radio: no row may ever name a radio that has no row. No I/O but the Store's."""
import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace

from .config import MESSAGE_RADIOS, SETTINGS, Config
from .configradios import FLAT_HOMES
from .radiodriver import RunOverrides
from .radiospec import FM_ID, HF_ID, KIND_WORDS, RadioError, RadioId, RadioSpec, check_name, enabled, log_name
from .radiosql import CHANGEABLE
from .radiotypes import BY_KEY, DEFAULT_TYPE, type_of
from .radiotype import Kind
from .store import RadioWrite, Store

log = logging.getLogger("neoaprs.controller")

SeedRow = tuple[RadioId, str, str, bool, int]       # id, kind, type, enabled, position
FLAT_KEYS = frozenset({s.key for s in SETTINGS if s.attr in FLAT_HOMES} | {"tnc/enter_kiss"})      # the rows the radios of today are read from (with the rule of an older version: configlegacy.py)


# ---- the stand-in
def _type(text: str, kind: Kind) -> str:
    found = BY_KEY.get(text)
    return text if found is not None and found.kind == kind else DEFAULT_TYPE[kind]


def seed_rows(rows: Mapping[str, str], run: RunOverrides) -> list[SeedRow]:
    """The radios today's program would run on these settings rows: radio 1 from the flat values in force (with the rules of an older version: configlegacy.py), and radio 2 when this run was given its
    Mercury (--hf-port) or a row names it (a row `hf/*` or `mercury/*`, the type `mercury` of the build before two radios, a station's choice `hf`)."""
    flat = Config.from_data({key: text for key, text in rows.items() if key in FLAT_KEYS})       # (the radios' rows alone: what is wrong of the station's is told once, by the load)
    try:
        chosen = json.loads(rows.get(MESSAGE_RADIOS) or "{}")
    except ValueError:
        chosen = {}
    named = bool(run.hf_port) or flat.hf_enabled or any(key.startswith(("hf/", "mercury/")) for key in rows) or (isinstance(chosen, dict) and "hf" in chosen.values())
    fm: SeedRow = (FM_ID, "fm", _type(flat.tnc_profile, "fm"), flat.fm_enabled, 1)
    return [fm, (HF_ID, "hf", _type(flat.hf_profile, "hf"), flat.hf_enabled, 2)] if named else [fm]


async def seed(store: Store, run: RunOverrides) -> bool:
    """The stand-in's radios written, where the database has no radio (decided by the database, never by a read that gave none), from the settings rows the same transaction reads (`seed_rows`);
    whether they were, said in the log."""
    radios = await store.seed_radios(lambda rows: seed_rows(rows, run))
    if not radios:
        return False
    words = [f"radio {id} the {kind.upper()} radio ({type}, {'on' if on else 'off'})" for id, kind, type, on, _ in radios]
    log.info("the database had no radio: %s %s written from the settings", " and ".join(words), "is" if len(words) == 1 else "are")
    return True


def stand_in(rows: Mapping[str, str]) -> tuple[RadioSpec, ...]:
    """Today's FM radio as the flat values among the rows say it, for a run whose radios could not be read: put in force, never stored."""
    spec = Config.from_data(rows).radio(FM_ID)
    assert spec is not None, "the flat values have radio 1"
    return (spec,)


# ---- what a save writes of the radios
def radio_writes(before: Iterable[RadioSpec], after: Iterable[RadioSpec]) -> list[RadioWrite]:
    """What differs of the radios between the settings in force and the ones a save brings: a radio that is new (with its id and its own settings), and of the others the columns and the own settings
    that changed. A removal is no write of a save (`Controller.remove_radio`)."""
    was = {spec.id: spec for spec in before}
    writes: list[RadioWrite] = []
    for spec in after:
        old = was.get(spec.id)
        if old is None:
            writes.append(RadioWrite(spec, True, {}, dict(spec.settings)))
            continue
        columns = {column: getattr(spec, column) for column in CHANGEABLE if getattr(spec, column) != getattr(old, column)}
        values = {key: text for key, text in spec.settings.items() if old.settings.get(key) != text}
        if columns or values:
            writes.append(RadioWrite(spec, False, columns, values))
    return writes


def refusal(before: Iterable[RadioSpec], after: Iterable[RadioSpec], writes: list[RadioWrite], stand_in: bool) -> str | None:
    """Why a save is not stored, or None: one that changes a radio while the radios could not be read at the start (the stand-in), and one that leaves out a radio in force, which only its removal takes
    away (`Controller.remove_radio`, whose transaction clears what names it)."""
    if writes and stand_in:
        return "they change a radio, and the radios could not be read at the start"
    kept = {spec.id for spec in after if not spec.removed}
    gone = [spec for spec in before if not spec.removed and spec.id not in kept]
    return None if not gone else f"they leave out radio {', '.join(str(spec.id) for spec in gone)}, which only its removal takes away"


def held(stand_in: bool, what: str) -> bool:
    """Whether the operator's change of a radio waits for a start that reads the radios (the stand-in is in force), told in the log."""
    if stand_in:
        log.warning("%s: the radios could not be read at the start, and no change of a radio is stored until the next start", what)
    return stand_in


# ---- the checks of the operator's changes
def put(config: Config, spec: RadioSpec) -> Config:
    """The settings with this radio in the place of the one of its id, or added."""
    others = tuple(s for s in config.radios if s.id != spec.id)
    return replace(config, radios=tuple(sorted((*others, spec), key=lambda s: s.id)))


def live_radio(config: Config, id: RadioId) -> RadioSpec:
    """The radio of the id, which is not removed; RadioError when there is none."""
    spec = config.radio(id)
    if spec is None or spec.removed:
        raise RadioError(f"radio {id}: there is no such radio" if spec is None else f"radio {id} ({log_name(spec, config.radios)}) is removed", "radio.unknown", radio=id)
    return spec


def _refuse_last(config: Config, spec: RadioSpec, what: str) -> None:
    if spec.enabled and [s.id for s in enabled(config.radios)] == [spec.id]:
        raise RadioError(f"the {log_name(spec, config.radios)} radio is the last one that is enabled: a station has at least one, so it cannot be {what}; turn another radio on first",
                         "radio.last_enabled", name=log_name(spec, config.radios))


def new_id(config: Config, kind: Kind) -> RadioId:
    """The id a radio added now is to have: 0, the database's own choice, where there is a radio 2. Where there is none (HF was never set up), today's flat keys still make radio 2 the HF radio
    (configradios.FLAT_HOMES, until W3 deletes them), so an HF radio added then is radio 2, and a radio of another kind takes the id after 2 and after every radio there is."""
    if config.radio(HF_ID) is not None:
        return 0
    return HF_ID if kind == "hf" else max([HF_ID, *(spec.id for spec in config.radios)]) + 1


def new_radio(config: Config, type: str, name: str = "", on: bool = True) -> RadioSpec:
    """A radio of the type to add, after the others (its id `new_id`'s: 0 is the database's choice, until it is stored); RadioTypeError for a type that is none, RadioError for a name that cannot be."""
    rtype = type_of(type)
    live = config.live_radios
    return RadioSpec(new_id(config, rtype.kind), rtype.kind, rtype.key, check_name(name, live, None), on, max((s.position for s in live), default=0) + 1)


def changed_radio(config: Config, id: RadioId, columns: Mapping[str, object]) -> RadioSpec:
    """The radio with its name, its type (of its own kind), its tickbox or its place changed; RadioError for what it cannot be (the last enabled radio is not switched off)."""
    spec = live_radio(config, id)
    if unknown := sorted(set(columns) - set(CHANGEABLE)):
        raise RadioError(f"radio {id}: its {', '.join(unknown)} cannot be changed (its {', '.join(CHANGEABLE)} can)")
    new = spec
    if "name" in columns:
        new = replace(new, name=check_name(str(columns["name"]), config.live_radios, id))
    if "type" in columns:
        rtype = type_of(str(columns["type"]))
        if rtype.kind != spec.kind:
            key, name = f"radio/{id}/type", log_name(spec, config.radios)
            raise RadioError(f"{key}: {rtype.key} is a type of another kind of radio than the {name} radio ({KIND_WORDS[spec.kind]})", "radio.type_kind", type=rtype.key, kind=KIND_WORDS[spec.kind], name=name)
        new = replace(new, type=rtype.key)
    if "enabled" in columns:
        if not isinstance(columns["enabled"], bool):
            raise RadioError(f"radio/{id}/enabled: true or false, not {columns['enabled']!r}")
        if not columns["enabled"]:
            _refuse_last(config, spec, "switched off")
        new = replace(new, enabled=columns["enabled"])
    if "position" in columns:
        position = columns["position"]
        if not isinstance(position, int) or isinstance(position, bool) or position < 1:
            raise RadioError(f"radio/{id}/position: a whole number from 1, not {position!r}")
        new = replace(new, position=position)
    return new


def with_settings(config: Config, id: RadioId, values: Mapping[str, str]) -> RadioSpec:
    """The radio with these own settings (key to text) put in, each checked by the field of its kind and kept as the program writes it; RadioError naming `radio/<id>/<key>` for the first that is wrong."""
    spec = live_radio(config, id)
    return replace(spec, settings={**spec.settings, **{key: Config.check_radio(spec, key, text) for key, text in values.items()}})


def removable(config: Config, id: RadioId) -> RadioSpec:
    """The radio that is to be removed; RadioError when there is none, or when it is the last one that is enabled."""
    spec = live_radio(config, id)
    _refuse_last(config, spec, "removed")
    return spec
