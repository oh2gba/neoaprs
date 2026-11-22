"""What the operator has set for one station: its own path, RF only, and when to be alerted."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# Range in whole kilometres of the "comes within N km of me" alert distance.
ALERT_KM_MIN = 1
ALERT_KM_MAX = 1000


@dataclass(frozen=True, slots=True)
class Alert:
    """When to alert about a station: any of the three, each fired once per crossing."""

    # A packet is heard after half an hour or more of silence, or for the first time.
    on_air: bool = False
    # The station comes from farther than this to nearer (None: not watched).
    within_km: int | None = None
    # A packet is heard direct (no digipeater) after none was for half an hour or more.
    direct: bool = False

    @property
    def any(self) -> bool:
        return self.on_air or self.within_km is not None or self.direct


@dataclass(frozen=True, slots=True)
class Pref:
    # None: automatic (the heard path for the first attempts, else `beacon/path`);
    # (): direct, no digipeaters, chosen explicitly.
    path: tuple[str, ...] | None = None
    # Everything sent to the station ends its path with RFONLY, so iGates keep it off the internet.
    rf_only: bool = False
    # None: no alert set. An Alert that watches nothing is never kept.
    alert: Alert | None = None


@dataclass(frozen=True, slots=True)
class Fired:
    """An alert that fired: the station, the kind, the text for the log and alert command, the time.

    `km` is the distance of the station for `within`, with one decimal.
    """

    call: str
    kind: Literal["on_air", "within", "direct"]
    text: str
    at: datetime
    km: float | None = None
