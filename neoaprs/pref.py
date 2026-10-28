"""What the operator has set for one station, as a value: a path of its own, whether it is RF only, and when to be alerted about it. The book that keeps them is `services/prefbook.py`, the watch that fires the alerts `services/stationalerts.py`."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ALERT_KM_MIN = 1                              # the distance of "comes within N km of me": a whole number of kilometres in this range
ALERT_KM_MAX = 1000


@dataclass(frozen=True, slots=True)
class Alert:
    """When the operator wants to be told about a station: any of the three, each fired once for each crossing (services/stationalerts.py)."""
    on_air: bool = False                      # a packet of it is heard after it was silent for half an hour or more, or for the first time
    within_km: int | None = None              # it comes from farther than this to this near us (None: not watched)
    direct: bool = False                      # a packet of it is heard direct (no digipeater) after none was for half an hour or more

    @property
    def any(self) -> bool:
        return self.on_air or self.within_km is not None or self.direct


@dataclass(frozen=True, slots=True)
class Pref:
    path: tuple[str, ...] | None = None       # None: none set (automatic: the heard path for the first attempts, else `beacon/path`); () is direct, no digipeaters, chosen explicitly (DIRECT)
    rf_only: bool = False                     # True: everything we send to the station has RFONLY as its last path element, so that iGates keep it off the internet
    alert: Alert | None = None                # None: no alert is set for the station (an Alert that watches nothing is never kept: it is None)


@dataclass(frozen=True, slots=True)
class Fired:
    """An alert that fired: the station, what happened (it came on the air, it came within the distance, it was heard direct), the words for the log and the alert command ("OH2XYZ is on the air"), when, and for
    `within` how far the station is (km, one decimal)."""
    call: str
    kind: Literal["on_air", "within", "direct"]
    text: str
    at: datetime
    km: float | None = None
