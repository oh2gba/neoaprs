"""What a change of the radios keeps in force, and what a new thing starts with.

`kept_in_force` runs on every change; if a thing (beacon, status, objects, e-mail ...) was in
force on some radios and would be on none, it is ticked for those that can still send. No I/O.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from .beaconrule import SEND_ON_KEYS, send_on_radios
from .emailrule import email_radio, gateway_heard
from .radiospec import RadioId, RadioSpec, in_force_set, live, senders, transmits, unheard_radio
from .radiotype import FM_ID


@dataclass(frozen=True)
class Kept:
    """What a change of the radios writes: ticks, new object and bulletin sets, the e-mail radio."""
    ticks: tuple[tuple[RadioId, str], ...] = ()
    objects: Mapping[str, tuple[RadioId, ...]] = field(default_factory=dict)
    bulletins: Mapping[str, tuple[RadioId, ...]] = field(default_factory=dict)
    email: RadioId | None = None

    def __bool__(self) -> bool:
        return bool(self.ticks or self.objects or self.bulletins or self.email is not None)


def _sets(things: Mapping[str, tuple[RadioId, ...]], before: list[RadioSpec], after: list[RadioSpec], still: set[RadioId]) -> dict[str, tuple[RadioId, ...]]:
    """Return the things in force before and on none after, with the radios that can still send."""
    found = {}
    for name, ids in things.items():
        was = [id for id in in_force_set(ids, before) if id in still]
        if was and not in_force_set(ids, after):
            found[name] = tuple(sorted({*ids, *was}))
    return found


def kept_in_force(before: Iterable[RadioSpec], after: Iterable[RadioSpec], objects: Mapping[str, tuple[RadioId, ...]], bulletins: Mapping[str, tuple[RadioId, ...]],
                  email_choice: RadioId | None) -> Kept:
    """Return what the change from `before` to `after` must write so nothing in force stops."""
    was, now = list(before), list(after)
    still = {spec.id for spec in senders(now)}
    if not still - {spec.id for spec in senders(was)}:
        return Kept()
    had = {spec.id: spec.settings for spec in was}
    now = [replace(spec, settings=had[spec.id]) if spec.id in had else spec for spec in now]
    ticks = []
    for key in SEND_ON_KEYS:
        went = send_on_radios(key, was)
        if went and not send_on_radios(key, [spec if spec.id in had else replace(spec, settings={**spec.settings, key: "false"}) for spec in now]):
            ticks += [(id, key) for id in went if id in still]
    return Kept(tuple(ticks), _sets(objects, was, now, still), _sets(bulletins, was, now, still), _mail(was, now, still, email_choice))


def _mail(was: list[RadioSpec], now: list[RadioSpec], still: set[RadioId], email_choice: RadioId | None) -> RadioId | None:
    """Return the e-mail radio a change writes (None: nothing)."""
    if email_choice in still or (mail := email_radio(was, email_choice)) is None or mail not in still:
        return None
    came = [spec.id for spec in senders(now) if spec.id not in {s.id for s in senders(was)} and gateway_heard(spec)]
    by_id = {spec.id: spec for spec in now}
    return came[0] if came and not gateway_heard(by_id[mail]) else mail


def start_set(stored: Iterable[RadioId], specs: Iterable[RadioSpec]) -> tuple[RadioId, ...]:
    """Return the radios a new object or bulletin is ticked for when the command names none."""
    pool = list(specs)
    on = [spec.id for spec in senders(pool)]
    if len(on) == 1:
        return (on[0],)
    sending = {spec.id for spec in live(pool) if transmits(spec)}
    kept = tuple(sorted({id for id in stored if id in sending}))
    if set(kept) & set(on):
        return kept
    if (first := unheard_radio(pool)) is not None:
        return (first,)
    return kept or next(((spec.id,) for spec in live(pool) if transmits(spec)), (FM_ID,))


def ids_of(text: str | None) -> tuple[RadioId, ...]:
    """Return the ids of a stored set ("1,3": a state row of what a new thing starts with)."""
    try:
        return tuple(sorted({int(part) for part in (text or "").split(",") if part.strip()}))
    except ValueError:
        return ()


def text_of(ids: Iterable[RadioId]) -> str:
    """Return a set of ids as stored: ascending, separated by commas."""
    return ",".join(str(id) for id in sorted(set(ids)))
