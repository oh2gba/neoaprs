"""The part of the beacon that is a moving station's (`beacon/mobile`): what it sends and what it remembers of what it sent.

The information field is a compressed position (`=` and the 13 bytes of `compressed_position`: position, symbol, course and speed from the GPS fix) followed by the comment: the altitude `/A=aaaaaa` when the fix has one, then the station's
comment, which is cut to the 40 characters a compressed report may carry. There is no PHG extension: a compressed position cannot hold one, and it belongs to a station that stays where it is.

`MobilePlan` is the beacon's memory of its last beacon (when, the course the station had, why), the input of SmartBeaconing (neoaprs/smartbeacon.py), and the answer to the page about it. `Positions` is what the beacon needs of the
GPS service: the fix to send now, or why there is none."""
from datetime import datetime
from typing import Protocol

from neoaprs.aprsposition import compressed_comment, compressed_position
from neoaprs.config import Config
from neoaprs.gpsfix import Fix
from neoaprs.smartbeacon import Decision, Reason, Sent, SmartSettings, decide

REASONS: tuple[Reason, ...] = ("start", "time", "turn")


class Positions(Protocol):
    """What the mobile beacon needs of the GPS service."""
    def current(self) -> Fix | None: ...
    def why_none(self) -> str: ...


def mobile_info(config: Config, fix: Fix) -> bytes:
    """The information field of a mobile beacon for this fix: `=`, the compressed position with the station's symbol, then the comment. Raises ValueError for a position or a symbol that cannot be sent."""
    position = compressed_position(fix.lat, fix.lon, config.station_symbol_table, config.station_symbol_code, fix.course_deg, fix.speed_kmh)
    return b"=" + position + compressed_comment(fix.altitude_m, config.station_comment).encode("ascii")


class MobilePlan:
    def __init__(self) -> None:
        self.last: Sent | None = None                          # the last beacon of this run: when, and the course the station had
        self.last_reason: Reason | None = None

    def check(self, settings: SmartSettings, fix: Fix, now: datetime) -> Decision:
        """What SmartBeaconing says about this fix now."""
        return decide(settings, self.last, now, fix.speed_kmh, fix.course_deg)

    def sent(self, fix: Fix, now: datetime, reason: str) -> None:
        """A beacon went out with this fix; `reason` is what SmartBeaconing said (start, time, turn), and anything else a request."""
        self.last, self.last_reason = Sent(now, fix.course_deg), next((r for r in REASONS if r == reason), "request")
