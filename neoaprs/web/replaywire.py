"""The replay of the map on the wire: the command that asks where the stations were over the last hours and the message that answers it, for the map's Replay (its right-click menu), which plays back how the
stations moved. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from neoaprs.config import STATION_HOURS
from neoaprs.policy import LOG_KEEP_DAYS

from .wirebase import HISTORY_MAX_HOURS, Iso, _Command, _Message

SPAN_DAYS = (2, 3, LOG_KEEP_DAYS)           # the spans of more than a day the replay offers, in days, after the hours of the Stations tab's On map for; the longest is all the packet log keeps
GLIDE_MAX_MIN = 15                          # the page drives a station between two of its points at most this far apart in time; across a longer gap it waits, then jumps (ui/src/lib/replay.ts)
Point = tuple[Iso, float, float]


class PositionHistory(_Command):
    """Asks where the stations were in the last `hours` hours, for the replay of the map. Answered with a `position_history` message to the page that asked, or an `error` for hours out of range."""
    cmd: Literal["position_history"]
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description=f"how far back to go: the replay offers {', '.join(map(str, STATION_HOURS))} (the choices of the Stations tab's On map for) and "
                       f"{', '.join(str(d * 24) for d in SPAN_DAYS)} ({', '.join(map(str, SPAN_DAYS))} days; the packet log keeps {LOG_KEEP_DAYS})")


class PositionHistoryMsg(_Message):
    """The positions of the stations over the span asked for, the answer to `position_history`, from the packet log: every position heard in it (a station's own, or the one inside a third-party packet), the
    live objects and items heard by their names, and what we sent under our call (our beacons, and our objects by their names). While `igate/enabled` (Internet stations) is off, no packet that came from
    APRS-IS is in it, whenever it was received: what was heard on the radio only, an iGate's third-party packets too, as the stations topic shows then. A station's points are thinned, the more the longer the span (REPLAY_THINNING
    of neoaprs/web/views.py): up to a day, a point less than 10 m from the point kept before it or less than 30 s after it is left out; up to three days, 200 m and 2 minutes; a week, 300 m and 5 minutes.
    The last point is always there, and so is the one where a station still was just before it moved off. The latest 1 000 000 position packets at most are read: on a feed busier than that, the span
    begins at the first of them."""
    type: Literal["position_history"]
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="the hours asked for")
    start: Iso = Field(description="where the replay begins, UTC: `hours` hours before `end`, or the oldest packet the log keeps when that is later (a daemon that has run for less than the span, or a log "
                                   "busier than the packets read)")
    end: Iso = Field(description="where the replay ends, UTC: when the daemon answered")
    stations: dict[str, list[Point]] = Field(description="[time, lat, lon] for each position kept, the oldest first, by the station's call (an object's or item's name); a station with no position in the span is not in it")
