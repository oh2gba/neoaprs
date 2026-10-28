"""The packets by the hour on the wire: the command that asks how many were heard in each of the last hours and the message that answers it, for the graph of the statistics card (all the packets heard) and
for the one of a station's card (the packets of that station); and the speeds a moving station reported, for the speed graph of its card. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message

MAX_HOURS = 168


class PacketHistory(_Command):
    """Asks how many packets were heard (not sent by us) in each of the last `hours` hours: all of them, or those of one station (`call`). Answered with a `packet_history` message to the page that asked, or an
    `error` for hours out of range or a call that is empty; a station with no packets is answered with every count 0."""
    cmd: Literal["packet_history"]
    hours: int = Field(ge=1, le=MAX_HOURS, description="how far back to go: 24 for a day, 168 for a week")
    call: str | None = Field(default=None, min_length=1, max_length=64, description="only the packets whose sender (the source of the frame heard) is this station, as the `stations` topic has it; absent or null for every packet heard")


class PacketHistoryMsg(_Message):
    """The packets heard by the hour, the answer to `packet_history`: a count for each whole hour of the clock from `start`, the oldest first, as many as were asked for; the last is the hour that is running, so
    it counts what has come since the top of the hour."""
    type: Literal["packet_history"]
    hours: int = Field(ge=1, le=MAX_HOURS, description="the hours asked for")
    call: str | None = Field(description="the station asked about, null for every packet heard: a page that asked for several stations and for all of them tells the answers apart by it")
    start: Iso = Field(description="the top of the first hour counted, UTC")
    counts: list[int] = Field(description="the packets heard in each hour from `start`, the oldest first (an hour with none is 0)")


class SpeedSeries(_Command):
    """Asks for the speeds a station reported in its positions in the last `hours` hours. Answered with a `speed_series` message to the page that asked, or an `error` for a call that is empty or hours out of
    range; a station that reported no speed is answered with no points."""
    cmd: Literal["speed_series"]
    call: str = Field(min_length=1, max_length=64, description="the station, as the `stations` topic has it: its position packets are those whose sender (the source of the frame heard) it is")
    hours: int = Field(ge=1, le=MAX_HOURS, description="how far back to go: 24 for a day")


class SpeedSeriesMsg(_Message):
    """The speeds of one station, the answer to `speed_series`: one point for each position packet of it heard in the span that carried a speed (a course and speed after the position, a compressed position's,
    a Mic-E's), the oldest first (a packet that came by two digipeaters is two points)."""
    type: Literal["speed_series"]
    call: str = Field(description="the station asked about: a page with several cards open tells the answers apart by it")
    hours: int = Field(ge=1, le=MAX_HOURS, description="the hours asked for")
    points: list[tuple[Iso, float]] = Field(description="[time, speed_kmh] for each position that had a speed, the oldest first; a station standing still that says so has 0")
