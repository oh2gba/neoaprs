"""What the operator has set for one station, as a value: a path and a timeout of its own and whether it is RF only. The book that keeps them is `services/prefbook.py`."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pref:
    path: tuple[str, ...] | None = None       # None: none set (automatic: the heard path for the first attempts, else `beacon/path`); () is direct, no digipeaters, chosen explicitly (DIRECT)
    hide_after_min: int | None = None         # None: none set (the fixed 180 minutes, `HIDE_AFTER_MIN`, count); 0 is never
    rf_only: bool = False                     # True: everything we send to the station has RFONLY as its last path element, so that iGates keep it off the internet
