"""What the operator has set for one station, as a value: a path, a timeout and a number of attempts of its own, each optional. The book that keeps them is `services/prefbook.py`."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pref:
    path: tuple[str, ...] | None = None       # None: none set (`beacon/path` counts); () is direct, no digipeaters
    hide_after_min: int | None = None         # None: none set (`map/hide_after_min` counts); 0 is never
    attempts: int | None = None               # None: none set (`messages/attempts` counts); 1 to 10, the attempts a message to the station is given
    rf_only: bool = False                     # True: everything we send to the station has RFONLY as its last path element, so that iGates keep it off the internet
