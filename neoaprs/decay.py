"""When what we put on the air of our own accord is sent again: the schedules of the specification's "Packet Timing" (chapter 2) and of its message chapter. Pure functions of a count and a path; the services
(services/ownobjects.py, services/ownbulletins.py) ask them and keep the times.

New information is sent more often than old: the decay algorithm sends a packet once and n seconds later, doubles n for each new transmission and, when n reaches the net cycle time, goes on at that rate.
The net cycle time follows the path (the spec's chapter 2, point 4): 10 minutes for a packet that goes direct or by one digipeater (WIDE2-1 is one), 20 for two, 30 for three or more.

* An object or an item (`object_wait_sec`): decay from FIRST_WAIT_SEC (60 s: 0, 1, 3, 7, 15 min ...), capped at the net cycle time of its path, until it is changed (then the decay starts again) or killed.
* A killed object or item (`kill_wait_sec`): KILL_SENDS transmissions, 0, 1 and 3 minutes after the kill, and then it is forgotten.
* A bulletin or a group bulletin ("sent a few times an hour for a few hours"): BULLETIN, an announcement ("less frequently but perhaps for several days"): ANNOUNCEMENT. Both go out at once, then
  after the waits of `early`, then every `every` seconds as long as the next one is no later than `lasts` seconds after the first (`bulletin_wait_sec`; None when it is over).

No packet of one thing goes out less than MIN_GAP_SEC after the one before it, whatever the change."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs.route import digipeaters, parse_alias

FIRST_WAIT_SEC = 60
MIN_GAP_SEC = 60                                     # the least between two packets of one object or bulletin, a change included
KILL_SENDS = 3
KILL_WAIT_SEC = 60
_NET_CYCLE_MIN = (10, 10, 20)                        # by the number of digipeaters: 0, 1, 2; 30 from three on
_NET_CYCLE_FAR_MIN = 30


def hops(path: tuple[str, ...]) -> int:
    """How many digipeaters the path asks for: each call or alias counts one, an alias of the form XXXn-N (WIDE2-2, TRACE3-3, SS3-3, HOP7-7) counts the N hops it has left (`WIDE2-2` is two, `WIDE1-1,WIDE2-1`
    is two); RFONLY, NOGATE and the internet's markers are no digipeater."""
    total = 0
    for address in digipeaters(path):
        alias = parse_alias(address)
        total += alias.hops if alias else 1
    return total


def net_cycle_sec(path: tuple[str, ...]) -> int:
    """The net cycle time of a path, in seconds: 10 minutes for none or one digipeater, 20 for two, 30 for three or more."""
    count = hops(path)
    return 60 * (_NET_CYCLE_MIN[count] if count < len(_NET_CYCLE_MIN) else _NET_CYCLE_FAR_MIN)


def object_wait_sec(sent: int, path: tuple[str, ...]) -> int:
    """How long after the `sent`-th transmission (1 or more) of a live object or item the next is due: 60, 120, 240 ... seconds, never more than the net cycle time of the path."""
    return min(FIRST_WAIT_SEC << (max(sent, 1) - 1), net_cycle_sec(path))


def first_due(changed_at: datetime, last_sent_at: datetime | None) -> datetime:
    """When the first packet of a thing that is new, changed or just killed is due: at once, but no sooner than MIN_GAP_SEC after the last packet of it (`last_sent_at`, None when there was none)."""
    return changed_at if last_sent_at is None else max(changed_at, last_sent_at + timedelta(seconds=MIN_GAP_SEC))


def kill_wait_sec(sent: int) -> int | None:
    """How long after the `sent`-th transmission (1 or more) of a killed object or item the next is due: 60 s, then 120 s; None after the last of KILL_SENDS (it is forgotten)."""
    return None if sent >= KILL_SENDS else KILL_WAIT_SEC << (max(sent, 1) - 1)


@dataclass(frozen=True, slots=True)
class Plan:
    early: tuple[int, ...]                           # the waits after the first, the second ... transmission, in seconds
    every: int                                       # the wait after the others
    lasts: int                                       # no transmission is made later than this many seconds after the first


BULLETIN = Plan(early=(120, 240), every=20 * 60, lasts=4 * 3600)
ANNOUNCEMENT = Plan(early=(120, 240), every=3600, lasts=72 * 3600)


def bulletin_wait_sec(plan: Plan, sent: int, since_first_sec: float) -> int | None:
    """How long after the `sent`-th transmission (1 or more) of a bulletin the next is due, `since_first_sec` after its first; None when that would be later than the plan lasts: it is over."""
    wait = plan.early[sent - 1] if 0 < sent <= len(plan.early) else plan.every
    return wait if since_first_sec + wait <= plan.lasts else None
