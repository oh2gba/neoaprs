"""Handlers of the commands answered from the logs: weather, counts, speeds, signal, replay, track.

Importing this module registers them; handlers.py imports it.
"""

from datetime import timedelta

from neoaprs.clock import iso
from neoaprs.geo import Thinning
from neoaprs.shown import Shown

from .dispatch import Ctx, UserError, command
from .historywire import PacketHistory, PacketStats, SignalSeries, SpeedSeries
from .packetwire import TRAFFIC_KEPT, StationTraffic
from .replaywire import PositionHistory
from .stationwire import StationTrack
from .views import packet_row, replay_thinning, replay_tracks, weather_points
from .weatherwire import WeatherSeries
from .wirebase import plain


@command(WeatherSeries)
async def weather_series(ctx: Ctx, cmd: WeatherSeries) -> None:
    observations = await ctx.ctl.weatherlog.series(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours))
    ctx.conn.send(
        {"type": "weather_series", "call": cmd.call, "hours": cmd.hours, "points": weather_points(observations)}
    )


@command(PacketHistory)
async def packet_history(ctx: Ctx, cmd: PacketHistory) -> None:
    # Counts per clock hour so the page's bars stand at round times; APRS-IS packets count only
    # while the iGate is on, those an iGate put on the air while they are shown.
    start = ctx.ctl.clock().replace(minute=0, second=0, microsecond=0) - timedelta(hours=cmd.hours - 1)
    counted = await ctx.ctl.packetlog.heard_by_hour(
        start, cmd.call, internet=ctx.ctl.config.igate_enabled, gated=ctx.ctl.config.igate_show_gated
    )
    counts = [counted.get(start + timedelta(hours=i), 0) for i in range(cmd.hours)]
    ctx.conn.send(
        {"type": "packet_history", "hours": cmd.hours, "call": cmd.call, "start": iso(start), "counts": counts}
    )


@command(PacketStats)
async def packet_stats(ctx: Ctx, cmd: PacketStats) -> None:
    config, igate = ctx.ctl.config, ctx.ctl.igate
    counted = await ctx.ctl.packetlog.stats.counted(config.station_call, config.igate_enabled, config.igate_show_gated)
    heard = sorted(counted.heard.items(), key=lambda item: (item[0] is None, item[0] or 0))
    sent = sorted(counted.sent.items(), key=lambda item: (item[0] is None, item[0] or 0))
    ctx.conn.send(
        {
            "type": "packet_stats",
            "start": iso(counted.start),
            "hours": counted.hours,
            "heard": [{"radio": radio, "counts": counts} for radio, counts in heard],
            "sent": [
                {
                    "radio": radio,
                    "beacons": kinds["beacon"],
                    "messages": kinds["message"],
                    "acks": kinds["ack"],
                    "objects": kinds["object"],
                    "other": kinds["other"],
                    "repeated": kinds["repeated"],
                }
                for radio, kinds in sent
            ],
            "packets": counted.packets,
            "frames": counted.frames,
            "repeated_hour": counted.repeated_hour,
            "gated_hour": igate.gated_hour.count(ctx.ctl.clock()) if config.igate_gate else None,
        }
    )


@command(SpeedSeries)
async def speed_series(ctx: Ctx, cmd: SpeedSeries) -> None:
    config = ctx.ctl.config
    speeds = await ctx.ctl.packetlog.speeds(
        cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours), config.igate_enabled, config.igate_show_gated
    )
    ctx.conn.send(
        {
            "type": "speed_series",
            "call": cmd.call,
            "hours": cmd.hours,
            "points": [[iso(at), round(kmh, 1)] for at, kmh in speeds],
        }
    )


@command(SignalSeries)
async def signal_series(ctx: Ctx, cmd: SignalSeries) -> None:
    readings = await ctx.ctl.packetlog.readings(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours))
    ctx.conn.send(
        {
            "type": "signal_series",
            "call": cmd.call,
            "hours": cmd.hours,
            "points": [[iso(at), snr, rssi] for at, snr, rssi in readings],
        }
    )


@command(StationTraffic)
async def station_traffic(ctx: Ctx, cmd: StationTraffic) -> None:
    config = ctx.ctl.config
    found = await ctx.ctl.packetlog.traffic(
        cmd.call, config.station_call, TRAFFIC_KEPT, config.igate_enabled, config.igate_show_gated
    )
    ctx.conn.send(
        {
            "type": "station_traffic",
            "call": cmd.call,
            "packets": [packet_row(number, packet) for number, packet in found],
        }
    )


@command(PositionHistory)
async def position_history(ctx: Ctx, cmd: PositionHistory) -> None:
    # The replay starts at the oldest logged packet when the span reaches further back, so the
    # slider does not run over empty days. APRS-IS packets are left out while the iGate is off,
    # though the log still holds them.
    end = ctx.ctl.clock()
    start = end - timedelta(hours=cmd.hours)
    metres, seconds = replay_thinning(cmd.hours)
    config = ctx.ctl.config
    found = await ctx.ctl.packetlog.position_history(
        start,
        config.station_call,
        lambda: Thinning(metres, seconds),
        internet=config.igate_enabled,
        gated=config.igate_show_gated,
    )
    begins = start if found.begins is None else max(start, found.begins)
    ctx.conn.send(
        {
            "type": "position_history",
            "hours": cmd.hours,
            "start": iso(begins),
            "end": iso(end),
            "stations": replay_tracks(found.tracks),
        }
    )


@command(StationTrack)
async def station_track(ctx: Ctx, cmd: StationTrack) -> None:
    # With the iGate off, a station heard both ways shows only its radio track; an internet-only one
    # is unknown, and so is one heard only as an iGate put it on the air while those are not shown.
    station = ctx.ctl.stationbook.get(cmd.call)
    shown = None if station is None else Shown.of(ctx.ctl.config).station(station)
    if shown is None:
        raise UserError(f"{cmd.cmd}: there is no station {cmd.call!r}", "station.unknown", params={"call": cmd.call})
    ctx.conn.send({"type": "station_track", "call": cmd.call, "points": plain(shown.track)})
