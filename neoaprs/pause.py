"""The random pause before a send by the clock, so that stations that keep the same time do not key up together."""

import random
from collections.abc import Callable
from datetime import datetime, timedelta

# seconds of pause, drawn in [0, most]
Draw = Callable[[float], float]


def uniform(most: float) -> float:
    """Return a pause drawn evenly in [0, most] seconds."""
    return random.uniform(0.0, most)  # noqa: S311 (not for security)


# the services' default; tests set it to a fixed draw
draw: Draw = uniform


def share(jitter: Draw, most: float) -> float:
    """Return the drawn pause as a share of `most`, in [0, 1]; 0 without calling `jitter` when most <= 0."""
    if most <= 0:
        return 0.0
    return min(max(jitter(most) / most, 0.0), 1.0)


def capped(share: float, most: float, *rooms: float) -> timedelta:
    """Return the pause: the share of `most`, or of the smallest room when that is less."""
    return timedelta(seconds=share * max(0.0, min((most, *rooms))))


def latest(base: datetime, end: datetime | None) -> float:
    """Return the room in seconds from `base` to `end` (none without an end)."""
    return float("inf") if end is None else (end - base).total_seconds()


def anchor(slot: tuple[datetime, float] | None, sent: datetime) -> datetime:
    """Return what the next wait counts from: the slot of a send that went in it, else when it went.

    `slot` is the slot's time and how late in it the send may go, in seconds."""
    if slot is None or not slot[0] <= sent <= slot[0] + timedelta(seconds=slot[1]):
        return sent  # late, or before its slot: a clock set back
    return slot[0]
