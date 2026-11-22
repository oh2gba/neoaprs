"""The radios of the settings as the operator changes them: checks and edits before storing.

Each refusal is a `RadioError` naming the radio (an unknown type a `RadioTypeError`). No I/O.
"""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime

from .config import Config
from .pairsetting import without_radio
from .radiodriver import RunOverrides
from .radiospec import FM_ID, KIND_WORDS, RadioError, RadioId, RadioSpec, check_name, enabled, log_name
from .radiosql import CHANGEABLE
from .radioregistry import unavailable_types
from .radiotypes import BY_KEY, type_of
from .radiotype import RadioTypeError
from .sendonrule import Kept, kept_in_force
from .store import RadioWrite


# ---- what the start's log says of the radios
def start_notes(config: Config, run: RunOverrides) -> list[tuple[int, str]]:
    """Return the start's log notes with levels: no radio, or a run port no radio takes.

    --port belongs to radio 1 (a TNC), --hf-port to `RunOverrides.attach_to`; a Dummy opens none.
    """
    none = "this station has no radio yet" if not config.radios else "every radio of this station is removed"
    notes = [] if config.live_radios else [(logging.INFO, f"{none}: none runs until one is added (the setup guide, Settings, Radio, or neoaprs db radios add TYPE)")]
    for flag, given, id, driver in (("--port", run.port, FM_ID, "tnc"), ("--hf-port", run.hf_port, run.attach_to, "mercury")):
        if given and id is None:
            notes.append((logging.INFO, f"{flag} {given} is a Mercury radio's, and this station has none: it is taken once one is added"))
            continue
        spec = None if id is None else config.radio(id)
        if not given or (spec is not None and not spec.removed and spec.rtype.driver == driver and not spec.rtype.dummy):
            continue
        if spec is None:
            notes.append((logging.INFO, f"{flag} {given} is radio {id}'s, and this station has no radio {id}: it is taken once radio {id} is added, if its type opens such a port"))
        else:
            notes.append((logging.WARNING, f"{flag} {given} is not used: it is radio {id}'s, and radio {id} " + ("is removed" if spec.removed else f"is of the type {spec.type}, which opens no such port")))
    return notes


# ---- what a save writes of the radios
def radio_writes(before: Iterable[RadioSpec], after: Iterable[RadioSpec]) -> list[RadioWrite]:
    """Return the changed columns and own settings of each radio in force; no adds or removals."""
    was = {spec.id: spec for spec in before}
    writes: list[RadioWrite] = []
    for spec in after:
        old = was.get(spec.id)
        if old is None:
            continue
        columns = {column: getattr(spec, column) for column in CHANGEABLE if getattr(spec, column) != getattr(old, column)}
        values = {key: text for key, text in spec.settings.items() if old.settings.get(key) != text}
        if columns or values:
            writes.append(RadioWrite(spec, columns, values))
    return writes


def refusal(before: Iterable[RadioSpec], after: Iterable[RadioSpec]) -> str | None:
    """Return why a save is not stored, or None: it may neither add nor drop a radio."""
    was = {spec.id for spec in before}
    if new := [spec for spec in after if spec.id not in was]:
        return f"they bring radio {', '.join(str(spec.id) for spec in new)}, which only its adding makes"
    kept = {spec.id for spec in after if not spec.removed}
    gone = [spec for spec in before if not spec.removed and spec.id not in kept]
    return None if not gone else f"they leave out radio {', '.join(str(spec.id) for spec in gone)}, which only its removal takes away"


# ---- the checks of the operator's changes
# the last position a radio may have; the next one added must still fit the database integer
MAX_POSITION = 2**31 - 1


def kept_change(before: Config, after: Config, objects: Mapping[str, tuple[RadioId, ...]], bulletins: Mapping[str, tuple[RadioId, ...]]) -> tuple[Config, Kept]:
    """Return `after` with the ticks and e-mail radio kept in force over the radio change."""
    kept = kept_in_force(before.radios, after.radios, objects, bulletins, before.email_choice)
    if after.email_choice != before.email_choice:
        kept = replace(kept, email=None)
    return with_kept(after, kept), kept


def with_kept(config: Config, kept: Kept) -> Config:
    """Return the settings with the ticks and e-mail radio of `kept` put in."""
    if not kept.ticks and kept.email is None:
        return config
    ticks: dict[RadioId, dict[str, str]] = {}
    for id, key in kept.ticks:
        ticks.setdefault(id, {})[key] = "true"
    radios = tuple(replace(spec, settings={**spec.settings, **ticks[spec.id]}) if spec.id in ticks else spec for spec in config.radios)
    return replace(config, radios=radios, email_choice=config.email_choice if kept.email is None else kept.email)


def removed(config: Config, spec: RadioSpec, at: datetime) -> Config:
    """Return the settings with this radio removed at `at`: pairs dropped, e-mail choice cleared."""
    kept = replace(config, pairs=without_radio(config.pairs, spec.id))
    return put(replace(kept, email_choice=None) if kept.email_choice == spec.id else kept, replace(spec, removed_at=at))


def put(config: Config, spec: RadioSpec) -> Config:
    """Return the settings with this radio replacing the one of its id, or added."""
    others = tuple(s for s in config.radios if s.id != spec.id)
    return replace(config, radios=tuple(sorted((*others, spec), key=lambda s: s.id)))


def live_radio(config: Config, id: RadioId) -> RadioSpec:
    """Return the live (not removed) radio of the id; raise RadioError if there is none."""
    spec = config.radio(id)
    if spec is None or spec.removed:
        raise RadioError(f"radio {id}: there is no such radio" if spec is None else f"radio {id} ({log_name(spec, config.radios)}) is removed", "radio.unknown", radio=id)
    return spec


def _refuse_last(config: Config, spec: RadioSpec, what: str) -> None:
    # A radio of a type this build lacks runs nothing (radioregistry.py), so it does not count.
    if spec.enabled and [s.id for s in enabled(config.radios) if s.type in BY_KEY] == [spec.id]:
        raise RadioError(f"radio {log_name(spec, config.radios)} is the last one that is enabled: a station has at least one, so it cannot be {what}; turn another radio on first",
                         "radio.last_enabled", name=log_name(spec, config.radios))


def new_radio(config: Config, type: str, name: str = "", on: bool = True) -> RadioSpec:
    """Return a new radio placed last, id 0 until stored; raise RadioTypeError or RadioError."""
    rtype = type_of(type)
    if rtype.key in unavailable_types():
        raise RadioTypeError(f"{rtype.key!r} is not a type of radio of this installation (its program is not carried here)", "radio.unknown_type", type=rtype.key)
    live = config.live_radios
    return RadioSpec(0, rtype.kind, rtype.key, check_name(name, live, None), on, max((s.position for s in live), default=0) + 1)


def changed_radio(config: Config, id: RadioId, columns: Mapping[str, object]) -> RadioSpec:
    """Return the radio with name, type (of its own kind), enabled flag or position changed.

    Raise RadioError for what is not allowed; the last enabled radio cannot be switched off.
    """
    spec = live_radio(config, id)
    if unknown := sorted(set(columns) - set(CHANGEABLE)):
        # The page's commands change no other column.
        raise RadioError(f"radio {id}: its {', '.join(unknown)} cannot be changed (its {', '.join(CHANGEABLE)} can)", "failed")
    new = spec
    if "name" in columns:
        new = replace(new, name=check_name(str(columns["name"]), config.live_radios, id))
    if "type" in columns:
        rtype = type_of(str(columns["type"]))
        if rtype.key in unavailable_types():
            raise RadioTypeError(f"{rtype.key!r} is not a type of radio of this installation (its program is not carried here)", "radio.unknown_type", type=rtype.key)
        if rtype.kind != spec.kind:
            key, name = f"radio/{id}/type", log_name(spec, config.radios)
            raise RadioError(f"{key}: {rtype.key} is a type of another kind than radio {name} ({KIND_WORDS[spec.kind]})", "radio.type_kind", type=rtype.key, kind=KIND_WORDS[spec.kind], name=name)
        new = replace(new, type=rtype.key)
    if "enabled" in columns:
        if not isinstance(columns["enabled"], bool):
            raise RadioError(f"radio/{id}/enabled: true or false, not {columns['enabled']!r}", "failed")
        if not columns["enabled"]:
            _refuse_last(config, spec, "switched off")
        new = replace(new, enabled=columns["enabled"])
    if "position" in columns:
        position = columns["position"]
        if not isinstance(position, int) or isinstance(position, bool) or not 1 <= position <= MAX_POSITION:
            raise RadioError(f"radio/{id}/position: a whole number from 1 to {MAX_POSITION}, not {position!r}", "failed")
        new = replace(new, position=position)
    return new


def with_settings(config: Config, id: RadioId, values: Mapping[str, str]) -> RadioSpec:
    """Return the radio with these settings (key to text) put in, each checked by its field.

    Raise RadioError naming `radio/<id>/<key>` for the first wrong one.
    """
    spec = live_radio(config, id)
    return replace(spec, settings={**spec.settings, **{key: Config.check_radio(spec, key, text) for key, text in values.items()}})


def removable(config: Config, id: RadioId) -> RadioSpec:
    """Return the radio to remove; raise RadioError if there is none or it is the last enabled one.
    """
    spec = live_radio(config, id)
    _refuse_last(config, spec, "removed")
    return spec
