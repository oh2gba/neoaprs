"""The beacon with many radios (plan rule 3.1): the interval in force and where it goes out.

One interval for the station (`beacon/interval_min`, 0 for off), raised on each radio to that
radio's own floor. Each radio has its own "beacon" tick (Send on), and so have the other senders.
"""

from collections.abc import Iterable

from .radiospec import RadioId, RadioSpec, enabled, in_force_set, log_name
from .radiotype import Limits, RadioTypeError
from .radiotypes import TYPES, kind_field, types_of

# shortest `beacon/interval_min` the settings take; a floor up to it raises nothing
SETTING_MIN_MIN = 20


def floor_of(spec: RadioSpec) -> int:
    """Return the radio type's shortest beacon interval in minutes.

    An unknown type takes the longest floor of its kind, so it never beacons too often.
    """
    try:
        return spec.rtype.limits.beacon_min_min
    except RadioTypeError:
        return max(t.limits.beacon_min_min for t in types_of(spec.kind) or TYPES)


def own_floor_min(floor_min: int) -> int:
    """Return the floor where it is above SETTING_MIN_MIN (shared airtime), else 0."""
    return floor_min if floor_min > SETTING_MIN_MIN else 0


def repeat_floor_sec(limits: Limits) -> int:
    """Return the least seconds between repeats of a live object on a radio."""
    return 60 * own_floor_min(limits.beacon_min_min)


def beacon_interval(station_min: int, spec: RadioSpec, specs: Iterable[RadioSpec] = ()) -> int:
    """Return the beacon interval in force on the radio, in minutes (0: off); `specs` is unused."""
    floor = own_floor_min(floor_of(spec))
    return max(station_min, floor) if station_min and floor else station_min


def ticked(spec: RadioSpec, *, say: bool = False, key: str = "beacon") -> bool:
    """Return the radio's tick (Send on) for `key`; ticked where the type has no such field."""
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


def beacon_radios(specs: Iterable[RadioSpec]) -> tuple[RadioId, ...]:
    """Return the radios the beacon goes out on, by position."""
    return send_on_radios("beacon", specs)


# things whose Send on is a radio tick `radio/<id>/<key>`
SEND_ON_KEYS = ("beacon", "status", "ask", "local_info")


def send_on_radios(key: str, specs: Iterable[RadioSpec]) -> tuple[RadioId, ...]:
    """Return the radios that send the thing `key` (one of SEND_ON_KEYS), by position."""
    pool = list(specs)
    return in_force_set((s.id for s in pool if ticked(s, key=key)), pool)


def intervals(station_min: int, specs: Iterable[RadioSpec]) -> list[tuple[RadioSpec, int]]:
    """Return each radio the beacon goes out on, by position, with the interval in force on it."""
    pool = list(specs)
    on = set(beacon_radios(pool))
    return [(s, beacon_interval(station_min, s)) for s in enabled(pool) if s.id in on]


def station_interval(station_min: int, specs: Iterable[RadioSpec]) -> int:
    """Return the shortest interval in force on a radio the beacon goes out on (0: off)."""
    found = [minutes for _, minutes in intervals(station_min, specs)]
    return min(found) if found and station_min else station_min


def interval_words(station_min: int, specs: Iterable[RadioSpec]) -> str:
    """Return the intervals for the support summary: `20 min`, or `20 min on FM, 30 min on HF`."""
    pool = list(specs)
    found = intervals(station_min, pool)
    if len({minutes for _, minutes in found}) <= 1:
        return f"{found[0][1] if found else station_min} min"
    return ", ".join(f"{minutes} min on {log_name(spec, pool)}" for spec, minutes in found)
