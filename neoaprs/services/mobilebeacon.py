"""The mobile beacon (`gps/source` is not `off`): its frame and its memory of the last send.

The information field is a compressed position plus altitude and comment. `MobilePlan` remembers
the last beacon (time, course, reason) as input to SmartBeaconing."""
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
    """Return the information field for this fix; raise ValueError if it cannot be sent."""
    position = compressed_position(fix.lat, fix.lon, config.station_symbol_table, config.station_symbol_code, fix.course_deg, fix.speed_kmh)
    return b"=" + position + compressed_comment(fix.altitude_m, config.station_comment).encode("ascii")


class MobilePlan:
    def __init__(self) -> None:
        self.last: Sent | None = None                          # time and course of the last beacon
        self.last_reason: Reason | None = None

    def check(self, settings: SmartSettings, fix: Fix, now: datetime) -> Decision:
        """Return the SmartBeaconing decision for this fix."""
        return decide(settings, self.last, now, fix.speed_kmh, fix.course_deg)

    def sent(self, fix: Fix, now: datetime, reason: str) -> None:
        """Record a send; a `reason` other than start, time or turn is stored as "request"."""
        self.last, self.last_reason = Sent(now, fix.course_deg), next((r for r in REASONS if r == reason), "request")
