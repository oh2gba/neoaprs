"""The handlers of the commands that are answered from the daemon's logs with a message of their own (neoaprs/web/dispatch.py): the weather of a station, the packets heard by the hour, the speeds of a
station and the positions of the replay of the map. Importing this module registers them; neoaprs/web/handlers.py imports it, so importing that one registers every handler.
"""
from datetime import timedelta

from neoaprs.clock import iso
from neoaprs.geo import Thinning

from .dispatch import Ctx, command
from .historywire import PacketHistory, SpeedSeries
from .replaywire import PositionHistory
from .views import replay_thinning, replay_tracks, weather_points
from .weatherwire import WeatherSeries


@command(WeatherSeries)
async def weather_series(ctx: Ctx, cmd: WeatherSeries) -> None:
    observations = await ctx.ctl.weatherlog.series(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours))
    ctx.conn.send({"type": "weather_series", "call": cmd.call, "hours": cmd.hours, "points": weather_points(observations)})


@command(PacketHistory)
async def packet_history(ctx: Ctx, cmd: PacketHistory) -> None:
    """The packets heard in each of the last hours, the running one last, all of them or one station's (`call`, which the answer repeats): the hours of the clock, so that the bars of the page stand at round times.
    While `igate/enabled` is off none that came from APRS-IS is counted, as the stations topic shows none."""
    start = ctx.ctl.clock().replace(minute=0, second=0, microsecond=0) - timedelta(hours=cmd.hours - 1)
    counted = await ctx.ctl.packetlog.heard_by_hour(start, cmd.call, internet=ctx.ctl.config.igate_enabled)
    counts = [counted.get(start + timedelta(hours=i), 0) for i in range(cmd.hours)]
    ctx.conn.send({"type": "packet_history", "hours": cmd.hours, "call": cmd.call, "start": iso(start), "counts": counts})


@command(SpeedSeries)
async def speed_series(ctx: Ctx, cmd: SpeedSeries) -> None:
    """The speeds the station reported in the last hours, the oldest first, for the speed graph of a moving station's card; while `igate/enabled` is off, only those of the positions heard on the radio."""
    speeds = await ctx.ctl.packetlog.speeds(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours), internet=ctx.ctl.config.igate_enabled)
    ctx.conn.send({"type": "speed_series", "call": cmd.call, "hours": cmd.hours, "points": [[iso(at), round(kmh, 1)] for at, kmh in speeds]})


@command(PositionHistory)
async def position_history(ctx: Ctx, cmd: PositionHistory) -> None:
    """Where the stations were over the last hours, for the replay of the map: the positions of the packet log, thinned by the span (neoaprs/web/views.py), to the page that asked. The replay begins at the
    oldest packet the log keeps when the span reaches back further, so that its slider does not run over days of nothing. While `igate/enabled` is off it shows what the stations topic does, no packet that
    came from APRS-IS: the log keeps them for LOG_KEEP_DAYS after the switch went off, and they are left out in the reading."""
    end = ctx.ctl.clock()
    start = end - timedelta(hours=cmd.hours)
    metres, seconds = replay_thinning(cmd.hours)
    config = ctx.ctl.config
    found = await ctx.ctl.packetlog.position_history(start, config.station_call, lambda: Thinning(metres, seconds), internet=config.igate_enabled)
    begins = start if found.begins is None else max(start, found.begins)
    ctx.conn.send({"type": "position_history", "hours": cmd.hours, "start": iso(begins), "end": iso(end), "stations": replay_tracks(found.tracks)})
