"""What is known of the base map, as plain values: the files in the data folder, the size a dry run estimated, and the state of the job that makes them (neoaprs/services/mapfetch.py makes these, the page's server tells them)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Box = tuple[float, float, float, float]         # west, south, east, north, in degrees
State = Literal["none", "estimating", "downloading", "ready", "error"]
Step = Literal["", "tool", "build", "world", "area"]
Job = Literal["estimate", "fetch"]


class MapError(Exception):
    """The job cannot be started or cannot be done; the text says why."""


@dataclass(frozen=True)
class MapFile:
    name: str
    bytes: int
    modified: datetime
    bbox: Box | None
    min_zoom: int | None
    max_zoom: int | None
    build: str                                  # the day of the Protomaps build it was cut from, empty if not known


@dataclass(frozen=True)
class Estimate:
    bytes: int
    tiles: int
    radius_km: int
    maxzoom: int
    box: Box
    build: str


@dataclass(frozen=True)
class MapStatus:
    state: State
    step: Step                                  # what the job is doing now; empty while none is
    percent: int | None                         # of the step; None when it cannot say
    blocked: str                                # why no job can be started now, empty if one can
    problem: str                                # why the last job failed, empty if it did not
    estimate: Estimate | None
    radius_km: int                              # the settings
    maxzoom: int
    box: Box | None                             # the box the settings make round our position
    detail: MapFile | None
    world: MapFile | None
