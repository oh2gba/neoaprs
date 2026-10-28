"""The replay of the map on the wire: the command that asks where the stations were over the last hours and the message that answers it, for the map's Replay (its right-click menu), which plays back how the
stations moved. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message

MAX_HOURS = 24
Point = tuple[Iso, float, float]


class PositionHistory(_Command):
    """Asks where the stations were in the last `hours` hours, for the replay of the map. Answered with a `position_history` message to the page that asked, or an `error` for hours out of range."""
    cmd: Literal["position_history"]
    hours: int = Field(ge=1, le=MAX_HOURS, description="how far back to go: the replay offers 1, 3, 6, 12 and 24, the choices of the Stations tab's On map for")


class PositionHistoryMsg(_Message):
    """The positions of the stations over the span asked for, the answer to `position_history`, from the packet log: every position heard in it (a station's own, or the one inside a third-party packet), the
    live objects and items heard by their names, and what we sent under our call (our beacons, and our objects by their names). A station's points are thinned: one less than 10 m from the point before it, or
    less than 30 s after it, is left out, and the last is always there. The latest 50 000 position packets at most are read: on a very busy feed the oldest part of a long span may be missing."""
    type: Literal["position_history"]
    hours: int = Field(ge=1, le=MAX_HOURS, description="the hours asked for")
    start: Iso = Field(description="where the span begins, UTC: `hours` hours before the daemon answered")
    stations: dict[str, list[Point]] = Field(description="[time, lat, lon] for each position kept, the oldest first, by the station's call (an object's or item's name); a station with no position in the span is not in it")
