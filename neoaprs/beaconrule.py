"""The beacon with many radios (plan rule 3.1): the interval in force on a radio, and the radios the beacon goes out on.

One interval for the station (`beacon/interval_min`, 0 for off), raised on each radio to that radio's own floor (its type's `limits.beacon_min_min`: 20 minutes on an FM radio, 30 on an HF one), so that an FM
radio at 20 minutes is not slowed to 30 because an HF radio is on. Each radio has its own "beacon" tick (Send on, the field `beacon` of every type, ticked by default); the beacon goes out on the enabled radios
that are ticked, read as every stored set of radios is (`radiospec.in_force_set`): with one enabled radio on that one, and with every tick off on the main radio, so that the beacon is never off by its ticks
(Off is the interval's alone).
The status report has a Send on of its own, in the same pattern (`status_radios`): each radio's "status" tick (the field `status`, unticked by default), read as the beacon's are, so that while no radio that is on
is ticked (the operator has not chosen: what every radio stores until a tick is made) the status goes out on the main radio and follows it, as it did before it had a choice; on each radio it goes at
`status/interval_min` raised to that radio's own floor (`beacon_interval`: one rule for both). No I/O."""
from collections.abc import Iterable

from .radiospec import RadioId, RadioSpec, enabled, in_force_set, log_name, senders
from .radiotype import Limits, RadioTypeError
from .radiotypes import TYPES, kind_field, types_of

SETTING_MIN_MIN = 20                 # the shortest `beacon/interval_min` the settings take (config.MIN_BEACON_INTERVAL_MIN: a stored lower one is raised as the settings are read): a floor up to it raises nothing


def floor_of(spec: RadioSpec) -> int:
    """The shortest beacon interval the radio takes, in minutes: its type's. A radio of a type that is none (a row written by a newer program) takes the longest floor of its kind's types, or of all types where
    its kind has none, so that a radio nothing describes never beacons more often than a known one would."""
    try:
        return spec.rtype.limits.beacon_min_min
    except RadioTypeError:
        return max(t.limits.beacon_min_min for t in types_of(spec.kind) or TYPES)


def own_floor_min(floor_min: int) -> int:
    """The part of a radio's floor (minutes) that is its own: the floor where it is above what the setting holds by itself (SETTING_MIN_MIN: the FM radio's 20 minutes are the setting's own), else 0. A floor
    above it is about airtime (HF and LoRa, 30 minutes: a slow channel that is everyone's)."""
    return floor_min if floor_min > SETTING_MIN_MIN else 0


def repeat_floor_sec(limits: Limits) -> int:
    """The least time, in seconds, between two repeats of a live object of ours on a radio with these limits: its own floor (`own_floor_min`), so that a radio whose airtime is everyone's repeats an object
    no more often than it beacons; 0 (the decay's net cycle alone) on FM and wherever the floor is the setting's own."""
    return 60 * own_floor_min(limits.beacon_min_min)


def beacon_interval(station_min: int, spec: RadioSpec, specs: Iterable[RadioSpec] = ()) -> int:
    """The beacon interval in force on the radio, in minutes (0: off): `beacon/interval_min`, raised to the radio's own floor (`floor_of`, `own_floor_min`); the other radios change nothing of it (`specs`
    is the seam's, unused)."""
    floor = own_floor_min(floor_of(spec))
    return max(station_min, floor) if station_min and floor else station_min


def ticked(spec: RadioSpec, *, say: bool = False, key: str = "beacon") -> bool:
    """The radio's own "beacon" tick (Send on), or its "status" tick (`key`, the status's Send on): its setting, ticked where its type has no such field (a receive-only one: a tick it kept from another type
    is not read; no rule sends on such a radio, `radiospec.senders`), and where neither its type nor its kind is known (a type that is none is read by its kind's field). A stored text that is not true or
    false is the field's default; it is said in the log only where `say` (RadioSpec.value: the beacon's start), for this is read at every tick of every radio's beacon."""
    try:
        found = spec.rtype.field(key)
    except RadioTypeError:
        found = kind_field(spec.kind, key)
    if found is None:
        return True
    if say:
        return bool(spec.value(key))
    try:
        return bool(found.parse(spec.settings.get(key, found.default)))
    except ValueError:
        return bool(found.parse(found.default))


def beacon_radios(specs: Iterable[RadioSpec], main: RadioId | None) -> tuple[RadioId, ...]:
    """The radios the beacon goes out on, by position: the enabled radios that are ticked; the one enabled radio whatever its tick; the main radio when no enabled radio is ticked; none when none is enabled."""
    pool = list(specs)
    return in_force_set((s.id for s in pool if ticked(s)), pool, main)


def status_radios(specs: Iterable[RadioSpec], main: RadioId | None) -> tuple[RadioId, ...]:
    """The radios the status report goes out on, by position, read as the beacon's are (`in_force_set`): the enabled radios that can send whose "status" tick is ticked; the one such radio whatever its tick;
    the main radio while none is ticked (the operator has not chosen yet: every radio's `status` is false, the default, so the status follows the main radio as before it had a choice); none when no radio can send."""
    pool = list(specs)
    return in_force_set((s.id for s in pool if ticked(s, key="status")), pool, main)


def status_chosen(specs: Iterable[RadioSpec]) -> bool:
    """Whether the operator has chosen the radios of the status: an enabled radio that can send has its "status" tick ticked (else it follows the main radio)."""
    return any(ticked(s, key="status") for s in senders(specs))


def intervals(station_min: int, specs: Iterable[RadioSpec], main: RadioId | None) -> list[tuple[RadioSpec, int]]:
    """Each radio the beacon goes out on, by position, with the interval in force on it."""
    pool = list(specs)
    on = set(beacon_radios(pool, main))
    return [(s, beacon_interval(station_min, s)) for s in enabled(pool) if s.id in on]


def station_interval(station_min: int, specs: Iterable[RadioSpec], main: RadioId | None) -> int:
    """The shortest interval in force on a radio the beacon goes out on, in minutes: how often our position goes out on some radio (0: off). With no radio the setting as it is."""
    found = [minutes for _, minutes in intervals(station_min, specs, main)]
    return min(found) if found and station_min else station_min


def interval_words(station_min: int, specs: Iterable[RadioSpec], main: RadioId | None) -> str:
    """The intervals in force in English, for the support summary: `20 min` while every radio the beacon goes out on has the same, else each radio's by the name the log gives it, `20 min on FM, 30 min on HF`."""
    pool = list(specs)
    found = intervals(station_min, pool, main)
    if len({minutes for _, minutes in found}) <= 1:
        return f"{found[0][1] if found else station_min} min"
    return ", ".join(f"{minutes} min on {log_name(spec, pool)}" for spec, minutes in found)
