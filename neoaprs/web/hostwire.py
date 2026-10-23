"""The daemon itself on the wire: `hello`, `ping` and `pong`, `status` and its request, and `error`. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py` (the unions, `TopicValues`)."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message


class Ping(_Command):
    """Answered with `pong`."""
    cmd: Literal["ping"]


class AskStatus(_Command):
    """Answered with `status` at once (the daemon also sends one every 10 s)."""
    cmd: Literal["status"]


class Hello(_Message):
    """The first message of a connection; `status` and the `state` of every topic follow it at once, so a page need not ask for them."""
    type: Literal["hello"]
    protocol: int = Field(description="the version of these messages: a page built for another one says so and loads itself again")
    version: str = Field(description="the version of the daemon")
    topics: list[str] = Field(description="the topics the page is following from the start: all of them (a page may `unsubscribe` from one)")


class Status(_Message):
    """What the daemon is, for the status bar: sent after `hello`, every 10 s, when asked (`status`), and when a packet of ours has gone out (the count of packets and the beacon's times have changed). It also says what the daemon costs the machine: the CPU share, the resident memory and the uptime."""
    type: Literal["status"]
    version: str = Field(description="the version of the daemon")
    started_at: Iso = Field(description="when the daemon started")
    packets: int = Field(description="how many packets the database holds")
    stations: int = Field(description="how many stations the station book holds")
    call: str = Field(description="our own call, from the settings; empty while none is set (nothing is transmitted then)")
    lat: float | None = Field(description="our own latitude, from the settings; null while none is set")
    lon: float | None = Field(description="our own longitude, from the settings; null while none is set")
    beacon_interval_min: int = Field(description="minutes between our position packets, from the settings; 0 is off")
    beacon_last_sent: Iso | None = Field(description="when the latest beacon was sent, by the timer or on request; null for none since the daemon started")
    beacon_next_due: Iso | None = Field(description="when the timer sends the next one; null while the interval is 0")
    station_status: str = Field(description="the text of the status report last sent in this run (services/rigstatus.py); empty until one has gone")
    rig_state: Literal["off", "on", "unused"] = Field(description="whether the radio the status is made from answers: `on`, `off` (rigctld is away or the radio is off, nothing is sent), or `unused` while `status/rigctld` is empty and the status is the static text")
    cpu_percent: float = Field(description="the daemon's CPU time (user and system) as a share of one core, in percent to a tenth, since the previous status that was at least a second before; the first counts from the start")
    rss_mb: float | None = Field(description="the daemon's resident memory in megabytes, to a tenth; null where the system does not say")
    uptime_sec: int = Field(description="seconds since the daemon started, by its clock")


class Pong(_Message):
    """The answer to `ping`."""
    type: Literal["pong"]
    now: Iso = Field(description="the daemon's clock")


class Error(_Message):
    """A command that could not be done. A frame the daemon could not understand is answered the same way, naming the command, the field and the problem; nothing was changed."""
    type: Literal["error"]
    text: str = Field(description="what could not be done and why, in a sentence; for a setting it begins with the key")
