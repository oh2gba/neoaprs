"""The packets by the hour on the wire: the command that asks how many were heard in each of the last hours and the message that answers it, for the graph of the statistics card (all the packets heard) and
for the one of a station's card (the packets of that station); what the statistics card counts beyond that (the packets by radio, what we sent, the packets that came by several ways); the speeds a moving station reported, for the speed graph of its card; and the readings of a station's signal, for the signal graph of its card. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import HISTORY_MAX_HOURS, Call, Iso, _Command, _Message, _Model


class PacketHistory(_Command):
    """Asks how many packets were heard (not sent by us) in each of the last `hours` hours: all of them, or those of one station (`call`). Answered with a `packet_history` message to the page that asked, or an
    `error` for hours out of range or a call that is empty; a station with no packets is answered with every count 0."""
    cmd: Literal["packet_history"]
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description=f"how far back to go: 24 for a day, {HISTORY_MAX_HOURS} for a week")
    call: Call | None = Field(default=None, description="only the packets whose sender (the source of the frame heard) is this station, as the `stations` topic has it; absent or null for every packet heard")


class PacketHistoryMsg(_Message):
    """The packets heard by the hour, the answer to `packet_history`: a count for each whole hour of the clock from `start`, the oldest first, as many as were asked for; the last is the hour that is running, so
    it counts what has come since the top of the hour."""
    type: Literal["packet_history"]
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="the hours asked for")
    call: str | None = Field(description="the station asked about, null for every packet heard: a page that asked for several stations and for all of them tells the answers apart by it")
    start: Iso = Field(description="the top of the first hour counted, UTC")
    counts: list[int] = Field(description="the packets heard in each hour from `start`, the oldest first (an hour with none is 0)")


class SpeedSeries(_Command):
    """Asks for the speeds a station reported in its positions in the last `hours` hours. Answered with a `speed_series` message to the page that asked, or an `error` for a call that is empty or hours out of
    range; a station that reported no speed is answered with no points."""
    cmd: Literal["speed_series"]
    call: Call = Field(description="the station, as the `stations` topic has it: its position packets are those whose sender (the source of the frame heard) it is")
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="how far back to go: 24 for a day")


class SpeedSeriesMsg(_Message):
    """The speeds of one station, the answer to `speed_series`: one point for each position packet of it heard in the span that carried a speed (a course and speed after the position, a compressed position's,
    a Mic-E's), the oldest first (a packet that came by two digipeaters is two points)."""
    type: Literal["speed_series"]
    call: str = Field(description="the station asked about: a page with several cards open tells the answers apart by it")
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="the hours asked for")
    points: list[tuple[Iso, float]] = Field(description="[time, speed_kmh] for each position that had a speed, the oldest first; a station standing still that says so has 0")


class SignalSeries(_Command):
    """Asks for the readings of a station's signal in the last `hours` hours: the SNR and the RSSI its radio measured of each packet heard direct from it (`snr` and `rssi` of a packet). Answered with a `signal_series`
    message to the page that asked, or an `error` for a call that is empty or hours out of range; a station heard on no radio that measures is answered with no points."""
    cmd: Literal["signal_series"]
    call: Call = Field(description="the station, as the `stations` topic has it: its packets are those whose source it is")
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="how far back to go: 24 for a day")


class SignalSeriesMsg(_Message):
    """The readings of one station's signal, the answer to `signal_series`: one point for each packet heard direct from it in the span that carried a reading, the oldest first, the latest 1000 at most. A digipeater's copy
    and a third-party packet are left out: their frame is another station's signal."""
    type: Literal["signal_series"]
    call: str = Field(description="the station asked about: a page with several cards open tells the answers apart by it")
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="the hours asked for")
    points: list[tuple[Iso, float | None, float | None]] = Field(description="[time, snr_db, rssi_dbm] for each packet with a reading, the oldest first; a reading the radio does not give is null (Mercury gives the SNR alone)")


class PacketStats(_Command):
    """Asks for what the statistics card counts from the packet log: the packets heard by the hour by radio, what went out on each radio, the packets that came by several ways and the copies sent and gated
    in the last hour. Answered with a `packet_stats` message to the page that asked."""
    cmd: Literal["packet_stats"]


class ChannelHours(_Model):
    """The packets one radio, or the internet, heard in each hour."""
    radio: int | None = Field(description="the radio that heard them, its id (a row of the topic `radios`, a removed one too); null for the internet")
    counts: list[int] = Field(description="the packets heard in each hour from the message's `start`, the oldest first, `hours` of them (an hour with none is 0)")


class RadioSent(_Model):
    """What went out on one radio in the last 24 hours, by what it was."""
    radio: int | None = Field(description="the radio it went out on, its id; null for what went to the internet")
    beacons: int = Field(ge=0, description="our positions and statuses")
    messages: int = Field(ge=0, description="our messages, bulletins among them")
    acks: int = Field(ge=0, description="our acks and rejects of messages")
    objects: int = Field(ge=0, description="our objects and items")
    other: int = Field(ge=0, description="anything else of ours: answers to queries, telemetry")
    repeated: int = Field(ge=0, description="the digipeater's copies of other stations' packets")


class PacketStatsMsg(_Message):
    """The answer to `packet_stats`. The packets heard (not sent by us; none from APRS-IS while `igate/enabled` is off) by the hour of the clock over the week the log keeps, or since its oldest packet when that is
    younger, for each radio and the internet that heard any, the running hour last; what went out and the packets heard more than once over the last 24 hours; the copies of the last 60 minutes. Hours that
    are over are counted once; the answer is at most a minute behind."""
    type: Literal["packet_stats"]
    start: Iso = Field(description="the top of the first hour counted, UTC")
    hours: int = Field(ge=1, le=HISTORY_MAX_HOURS, description="how many hours each list of `heard` has: from `start` to the running one")
    heard: list[ChannelHours] = Field(description="by radio, in the order of their ids, the internet last; one that heard nothing in the span is left out")
    sent: list[RadioSent] = Field(description="by radio, in the order of their ids; one that sent nothing in the last 24 hours is left out")
    packets: int = Field(ge=0, description="the packets the radios heard in the last 24 hours, a packet heard by several ways counted once (the same source, destination and information field within a minute of the clock)")
    frames: int = Field(ge=0, description="the frames those packets came in: `frames` less `packets` is how many came again by another way")
    repeated_hour: int = Field(ge=0, description="the copies the digipeater sent in the last 60 minutes")
    gated_hour: int | None = Field(description="the packets the iGate put on APRS-IS in the last 60 minutes; null while `igate/enabled` is off")
