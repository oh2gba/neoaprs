"""The GPS and the moving station's beacon on the wire: the topic `gps`. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`. The settings that choose the source and how the station moves (`gps/*`,
`beacon/travel`) are in the topic `config` like the others."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Model


class GpsState(_Model):
    """The GPS receiver and what the beacon does with it: the latest fix, whether it can be used, and the beacon of a moving station. Told whole as it changes, at most once a second."""
    source: Literal["off", "gpsd", "serial"] = Field(description="`gps/source` as in force: where the fixes come from")
    state: Literal["off", "connecting", "no_fix", "fix", "stale"] = Field(description="`off`: no source is set; `connecting`: the line to gpsd or the receiver is not up and no fix has come; `no_fix`: it is up and the receiver has no fix; `fix`: the latest fix is fresh; "
                                                                                       "`stale`: the latest fix is older than 120 seconds and is not used (a mobile beacon sends nothing on it)")
    problem: str = Field(description="why there is no fix to use: the feed's own line (`Connection refused`, `the receiver has no position fix yet`) or that the latest fix is old; empty while the state is `fix` and for `off`")
    lat: float | None = Field(description="the latest fix, degrees north; null before the first fix of the source (a stale fix is still told, with its `fix_at`)")
    lon: float | None = Field(description="the latest fix, degrees east")
    altitude_m: float | None = Field(description="metres above mean sea level; null when the fix has none")
    speed_kmh: float | None = Field(description="kilometres per hour; null when the fix has none")
    course_deg: int | None = Field(description="degrees from north, 0 to 359; null when the fix has none")
    satellites: int | None = Field(description="the satellites used for the fix; null when the source does not say")
    fix_at: Iso | None = Field(description="when the latest fix was received, by the daemon's clock")
    mobile: bool = Field(description="`gps/source` is not `off`: the beacon follows the GPS. With no fresh fix nothing is sent at all (never the home position), which `state` and `problem` say")
    next_beacon_at: Iso | None = Field(description="when the next beacon by time is due, for the speed of the latest fix (a turn sends one sooner); null unless the beacon is mobile and has a fresh fix and has sent its first")
    last_beacon_reason: Literal["", "start", "time", "turn", "request"] = Field(description="why the latest mobile beacon of this run went out: `start` (the first fix), `time`, `turn` (a corner), `request` (Beacon now); empty before the first")
    last_beacon_at: Iso | None = Field(description="when it went out; null before the first")
