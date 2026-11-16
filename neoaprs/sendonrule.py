"""What a change of the radios keeps (design section 3 of the round that made every radio equal): a radio that comes on never stops anything, and what a new object or a new bulletin starts with. Pure functions of the radios
before and after a change; the controller runs `kept_in_force` on every change of the radios (one added, switched on or off, removed, given a type that sends or one that only receives) and the store
writes what it gives in the transaction of that change (radiosql.put_kept). No I/O.

For each thing that has radios of its own (the beacon, the status, Ask around, Local info: each radio's tick, `radio/<id>/<key>`; every object and every bulletin of ours: its set; e-mail: `email/radio`):
if it was in force on some radios before the change and would be in force on none after it, it is ticked for those of them that can still send. So a station that grows from FM to FM and HF keeps
everything where it went, and the new radio carries its beacon alone (its other ticks are unticked by default). Ticked nowhere happens only where the operator switches off or removes the radios a thing was
ticked for while several others stay on. E-mail the same: with no choice stored or one that is not on, when a radio that sends comes on beside the one the mail went on, that one is written, so that the mail stays there (unless
internet gateways do not hear it and do hear the radio that comes on: then that one, as 0.20.0 sent it)."""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from .beaconrule import SEND_ON_KEYS, send_on_radios
from .emailrule import email_radio, gateway_heard
from .radiospec import RadioId, RadioSpec, in_force_set, live, senders, transmits, unheard_radio
from .radiotype import FM_ID


@dataclass(frozen=True)
class Kept:
    """What a change of the radios writes beside itself: the ticks `(radio, key)` to tick, the new sets of objects (by name) and bulletins (by slot), the e-mail radio to store (None: nothing)."""
    ticks: tuple[tuple[RadioId, str], ...] = ()
    objects: Mapping[str, tuple[RadioId, ...]] = field(default_factory=dict)
    bulletins: Mapping[str, tuple[RadioId, ...]] = field(default_factory=dict)
    email: RadioId | None = None

    def __bool__(self) -> bool:
        return bool(self.ticks or self.objects or self.bulletins or self.email is not None)


def _sets(things: Mapping[str, tuple[RadioId, ...]], before: list[RadioSpec], after: list[RadioSpec], still: set[RadioId]) -> dict[str, tuple[RadioId, ...]]:
    """The things (an object's, a bulletin's set of radios) in force before and on none after, each with the radios it was in force on that can still send added."""
    found = {}
    for name, ids in things.items():
        was = [id for id in in_force_set(ids, before) if id in still]
        if was and not in_force_set(ids, after):
            found[name] = tuple(sorted({*ids, *was}))
    return found


def kept_in_force(before: Iterable[RadioSpec], after: Iterable[RadioSpec], objects: Mapping[str, tuple[RadioId, ...]], bulletins: Mapping[str, tuple[RadioId, ...]],
                  email_choice: RadioId | None) -> Kept:
    """What the change from `before` to `after` must write so that nothing in force on a radio that can still send stops (`Kept`; empty when nothing). Only a radio that comes on (one that can send now
    and could not before: added, switched on, given a type that sends) can stop something; the change of the radios is read alone, each radio with the ticks it had before (a radio the station did not
    have before counted unticked, so that its default tick does not stand in for what it would stop), so that a save that also unticks something is not undone by it, and a save that changes ticks alone
    keeps nothing."""
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
    """The e-mail radio a change writes (None: nothing): while no choice is stored or the one stored is not on, the radio the mail went on, so that it stays there; but where that one is of a type internet
    gateways do not hear and a radio that comes on is one they hear, the first such radio that comes on, where 0.20.0 sent the mail."""
    if email_choice in still or (mail := email_radio(was, email_choice)) is None or mail not in still:
        return None
    came = [spec.id for spec in senders(now) if spec.id not in {s.id for s in senders(was)} and gateway_heard(spec)]
    by_id = {spec.id: spec for spec in now}
    return came[0] if came and not gateway_heard(by_id[mail]) else mail


def start_set(stored: Iterable[RadioId], specs: Iterable[RadioSpec]) -> tuple[RadioId, ...]:
    """The radios a new object or a new bulletin is ticked for (when the command names none): with one radio that can send, that one; else the radios the one saved last went on (`objects/send_on`,
    `bulletins/send_on`) while one of them is on; else the first radio that can send in the order of the boxes; while none is on, those of the radios saved last that are still the station's, else the first
    radio of the station that can send though it is off, and radio 1 only while the station has none (a new installation: the thing goes out once a radio is there)."""
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
    """The ids of a stored set ("1,3": a state row of what a new thing starts with); none for a row that is none or not one."""
    try:
        return tuple(sorted({int(part) for part in (text or "").split(",") if part.strip()}))
    except ValueError:
        return ()


def text_of(ids: Iterable[RadioId]) -> str:
    """A set of ids as it is stored: ascending, separated by commas."""
    return ",".join(str(id) for id in sorted(set(ids)))
