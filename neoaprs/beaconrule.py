"""The beacon with many radios (plan rule 3.1): the interval in force on a radio, and the radios the beacon goes out on.

This is TODAY's rule, written with radios (config.Config.beacon_interval and the two beacons of today): the one interval of the station, 0 for off, raised to the HF floor for every radio while an HF radio is
enabled; the beacon on every enabled radio. It reads the floor as Config.beacon_interval does (radiorules.HF_BEACON_MIN_MIN), not from a radio's type, so that it gives a number for a radio of any type key.
Package R1 writes rule 3.1 in its place (each radio raised to its own floor, the beacon on the radios ticked for it). No I/O."""
from collections.abc import Iterable

from .radiorules import HF_BEACON_MIN_MIN
from .radiospec import RadioId, RadioSpec, enabled


def beacon_interval(station_min: int, spec: RadioSpec, specs: Iterable[RadioSpec]) -> int:
    """The beacon interval in force on the radio, in minutes (0: off): `beacon/interval_min`, raised to the HF floor (radiorules.HF_BEACON_MIN_MIN) while an HF radio is enabled, whichever radio this is."""
    hf_on = any(s.kind == "hf" for s in enabled(specs))
    return max(station_min, HF_BEACON_MIN_MIN) if station_min and hf_on else station_min


def beacon_radios(specs: Iterable[RadioSpec], main: RadioId | None) -> tuple[RadioId, ...]:
    """The radios the timed beacon goes out on: every enabled radio, by position (`main` is rule 3.1's, unused by today's rule)."""
    return tuple(s.id for s in enabled(specs))
