"""When what we put on the air on our own accord is sent again (spec chapter 2 "Packet Timing").

Pure functions of a count and a path. The wait doubles for each transmission until the path's
net cycle time (10 minutes for 0-1 digipeaters, 20 for two, 30 for more)."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs.route import digipeaters, parse_alias

FIRST_WAIT_SEC = 60
MIN_GAP_SEC = 60  # the least between two packets of one thing
KILL_SENDS = 3
KILL_WAIT_SEC = 60
# Minutes by number of digipeaters (0, 1, 2); 30 from three on.
_NET_CYCLE_MIN = (10, 10, 20)
_NET_CYCLE_FAR_MIN = 30


def hops(path: tuple[str, ...]) -> int:
    """Return how many digipeaters the path asks for (an alias XXXn-N counts N; markers none)."""
    total = 0
    for address in digipeaters(path):
        alias = parse_alias(address)
        total += alias.hops if alias else 1
    return total


def net_cycle_sec(path: tuple[str, ...]) -> int:
    """Return the net cycle time of a path in seconds: 10 min for 0-1 digipeaters, 20 for 2."""
    count = hops(path)
    return 60 * (_NET_CYCLE_MIN[count] if count < len(_NET_CYCLE_MIN) else _NET_CYCLE_FAR_MIN)


def object_wait_sec(sent: int, path: tuple[str, ...], floor_sec: int = 0) -> int:
    """Return seconds until the next transmission after the `sent`-th of a live object.

    60, 120, 240 ... capped at the path's net cycle time, or `floor_sec` if longer."""
    return min(FIRST_WAIT_SEC << (max(sent, 1) - 1), max(net_cycle_sec(path), floor_sec))


def first_due(changed_at: datetime, last_sent_at: datetime | None) -> datetime:
    """Return when the first packet of a new, changed or killed thing is due (MIN_GAP_SEC rule)."""
    return changed_at if last_sent_at is None else max(changed_at, last_sent_at + timedelta(seconds=MIN_GAP_SEC))


def kill_wait_sec(sent: int) -> int | None:
    """Return seconds until the next transmission of a killed object; None after KILL_SENDS."""
    return None if sent >= KILL_SENDS else KILL_WAIT_SEC << (max(sent, 1) - 1)


@dataclass(frozen=True, slots=True)
class Plan:
    early: tuple[int, ...]  # waits after the first, second ... transmission, in seconds
    every: int  # the wait after the others
    lasts: int  # no transmission later than this after the first


BULLETIN = Plan(early=(120, 240), every=20 * 60, lasts=4 * 3600)
ANNOUNCEMENT = Plan(early=(120, 240), every=3600, lasts=72 * 3600)


def bulletin_wait_sec(plan: Plan, sent: int, since_first_sec: float, floor_sec: int = 0) -> int | None:
    """Return seconds until the next transmission of a bulletin; None when the plan has run out."""
    wait = plan.early[sent - 1] if 0 < sent <= len(plan.early) else max(plan.every, floor_sec)
    return wait if since_first_sec + wait <= plan.lasts else None
