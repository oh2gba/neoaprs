"""The packets by the hour on the wire: the command that asks how many were heard in each of the last hours and the message that answers it, for the graph of the statistics card. Models like the rest of
the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message

MAX_HOURS = 168


class PacketHistory(_Command):
    """Asks how many packets were heard (not sent by us) in each of the last `hours` hours. Answered with a `packet_history` message to the page that asked, or an `error` for hours out of range."""
    cmd: Literal["packet_history"]
    hours: int = Field(ge=1, le=MAX_HOURS, description="how far back to go: 24 for a day, 168 for a week")


class PacketHistoryMsg(_Message):
    """The packets heard by the hour, the answer to `packet_history`: a count for each whole hour of the clock from `start`, the oldest first, as many as were asked for; the last is the hour that is running, so
    it counts what has come since the top of the hour."""
    type: Literal["packet_history"]
    hours: int = Field(ge=1, le=MAX_HOURS, description="the hours asked for")
    start: Iso = Field(description="the top of the first hour counted, UTC")
    counts: list[int] = Field(description="the packets heard in each hour from `start`, the oldest first (an hour with none is 0)")
