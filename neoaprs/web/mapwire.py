"""The base map on the wire: the topic `map` (what the map files are, and what the job that makes them is doing) and the commands that start and end a job. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Model

Box = list[float]


class MapFileInfo(_Model):
    """A map file in the data folder."""
    name: str = Field(description="`basemap.pmtiles` (the detailed map) or `basemap-world.pmtiles` (the world to zoom 5)")
    bytes: int = Field(ge=0)
    modified: Iso = Field(description="when the file was made")
    bbox: Box | None = Field(min_length=4, max_length=4, description="the area it covers, [west, south, east, north] in degrees, as its header says; null for a file whose header cannot be read")
    min_zoom: int | None
    max_zoom: int | None = Field(description="the deepest zoom it has tiles for; the page draws a deeper one from these")
    build: str = Field(description="the day (`20261022`) of the Protomaps build it was cut from; empty if not known (a file made by hand)")


class MapSizeEstimate(_Model):
    """What a dry run said: how big the detailed map will be for the area and the zoom it was made for."""
    bytes: int = Field(ge=0, description="the tiles it will hold")
    tiles: int = Field(ge=0)
    radius_km: int = Field(description="the radius it was estimated for; it is stale when `map/radius_km` is another number now")
    maxzoom: int = Field(description="the zoom it was estimated for")
    box: Box = Field(min_length=4, max_length=4, description="the area, [west, south, east, north]")
    build: str = Field(description="the day of the build it was estimated from; empty for a source that is not a daily build")


class MapState(_Model):
    """The base map: the files, the area and detail the settings ask for, the size estimated, and the job that is running. The value of the topic `map`, told whole at most four times a second."""
    state: Literal["none", "estimating", "downloading", "ready", "error"] = Field(
        description="`none`: there is no detailed map. `ready`: there is one. `estimating` and `downloading`: a job is running (`step` and `percent` say how far). `error`: the last job failed and `problem` says why; the map files are as they were")
    step: Literal["", "tool", "build", "world", "area"] = Field(
        description="what the running job is doing: fetching the pmtiles program (`tool`), looking for the latest build (`build`), making the world map (`world`) or the detailed map (`area`); empty while no job runs")
    percent: int | None = Field(ge=0, le=100, description="how far the step is; null when it cannot say (the program and the build have no bar)")
    blocked: str = Field(description="why no job can be started now (no position, or a job is running); empty when one can")
    problem: str = Field(description="why the last job failed; empty if it did not, and while a job runs")
    estimate: MapSizeEstimate | None = Field(description="the latest dry run (`map_estimate`); null before one, and after a download")
    radius_km: int = Field(description="`map/radius_km`")
    maxzoom: int = Field(description="`map/maxzoom`")
    box: Box | None = Field(min_length=4, max_length=4, description="the area those settings make round our position, [west, south, east, north]; null without a position")
    detail: MapFileInfo | None = Field(description="`basemap.pmtiles`; null if it is not there")
    world: MapFileInfo | None = Field(description="`basemap-world.pmtiles`; null if it is not there")


class MapEstimate(_Command):
    """Starts a dry run: how big the detailed map for `map/radius_km` and `map/maxzoom` round our position will be. Answered by the topic `map` (state `estimating`, then `estimate` filled in), or by an `error` when no job can start
    (no position, or a job is running). The pmtiles program is fetched first when it is not there."""
    cmd: Literal["map_estimate"]


class MapFetch(_Command):
    """Starts making the maps: the world map first when it is not there, then the detailed map for `map/radius_km` and `map/maxzoom` round our position, from `map/source` or the latest daily build. The progress is the topic
    `map`. An `error` when no job can start (no position, or a job is running)."""
    cmd: Literal["map_fetch"]


class MapCancel(_Command):
    """Ends the running job; the files it was making are removed and the maps stay as they were. An `error` when no job is running."""
    cmd: Literal["map_cancel"]
