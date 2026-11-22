"""Plain values describing the base map: its files, a size estimate and the state of the job."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Box = tuple[float, float, float, float]         # west, south, east, north, in degrees
State = Literal["none", "estimating", "downloading", "ready", "error"]
Step = Literal["", "build", "world", "area"]
Job = Literal["estimate", "fetch"]
# why a job cannot start or failed, as a code
Problem = Literal["no_position", "busy", "slow", "unreachable", "no_build", "too_big", "no_space", "failed"]


class MapError(Exception):
    """A job cannot start or finish. The text is for the log; `problem`, `params` for the page."""

    def __init__(self, text: str, problem: Problem = "failed", **params: int) -> None:
        super().__init__(text)
        self.problem: Problem = problem
        self.params = params


@dataclass(frozen=True)
class MapFile:
    name: str
    bytes: int
    modified: datetime
    bbox: Box | None
    min_zoom: int | None
    max_zoom: int | None
    build: str                                  # day of the Protomaps build it was cut from, or empty


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
    step: Step                                  # empty while no job runs
    percent: int | None                         # of the step; None if unknown
    downloaded: int | None                      # bytes of the file being made; None if there is none
    note: str                                   # log text about a stalled download; empty otherwise
    blocked: str                                # log text: why no job can start; empty if one can
    problem: str                                # log text: why the last job failed; empty if it did not
    estimate: Estimate | None
    radius_km: int                              # from the settings
    maxzoom: int
    box: Box | None                             # the box the settings make around the position
    detail: MapFile | None
    world: MapFile | None                       # the data folder's own, else the bundled one
    later: bool = False                         # detailed map not fetched yet; retried at next start
    retry: tuple[int, int] | None = None        # `note` as (this try, all tries)
    blocked_code: Literal["", "no_position", "busy"] = ""     # `blocked` as a code
    failure: MapError | None = None             # `problem` with its code and values
