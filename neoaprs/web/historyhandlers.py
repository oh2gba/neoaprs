"""The handlers of the commands that are answered from the daemon's logs with a message of their own (neoaprs/web/dispatch.py): the weather of a station, the packets heard by the hour, what the statistics card counts beyond them, the speeds of a
station, the readings of a station's signal, the latest packets of a station and the positions of the replay of the map; and a station's track as its row has it. Importing this module registers them; neoaprs/web/handlers.py imports it, so importing that one registers every handler.
"""
from datetime import timedelta

from neoaprs.clock import iso
from neoaprs.geo import Thinning

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
    ctx.conn.send({"type": "weather_series", "call": cmd.call, "hours": cmd.hours, "points": weather_points(observations)})


@command(PacketHistory)
async def packet_history(ctx: Ctx, cmd: PacketHistory) -> None:
    """The packets heard in each of the last hours, the running one last, all of them or one station's (`call`, which the answer repeats): the hours of the clock, so that the bars of the page stand at round times.
    While `igate/enabled` is off none that came from APRS-IS is counted, as the stations topic shows none."""
    start = ctx.ctl.clock().replace(minute=0, second=0, microsecond=0) - timedelta(hours=cmd.hours - 1)
    counted = await ctx.ctl.packetlog.heard_by_hour(start, cmd.call, internet=ctx.ctl.config.igate_enabled)
    counts = [counted.get(start + timedelta(hours=i), 0) for i in range(cmd.hours)]
    ctx.conn.send({"type": "packet_history", "hours": cmd.hours, "call": cmd.call, "start": iso(start), "counts": counts})


@command(PacketStats)
async def packet_stats(ctx: Ctx, cmd: PacketStats) -> None:
    """What the statistics card counts from the packet log (neoaprs/packetstats.py), and what the iGate gated in the last hour while it is on."""
    config, igate = ctx.ctl.config, ctx.ctl.igate
    counted = await ctx.ctl.packetlog.stats.counted(config.station_call, config.igate_enabled)
    heard = sorted(counted.heard.items(), key=lambda item: (item[0] is None, item[0] or 0))
    sent = sorted(counted.sent.items(), key=lambda item: (item[0] is None, item[0] or 0))
    ctx.conn.send({"type": "packet_stats", "start": iso(counted.start), "hours": counted.hours, "heard": [{"radio": radio, "counts": counts} for radio, counts in heard],
                   "sent": [{"radio": radio, "beacons": kinds["beacon"], "messages": kinds["message"], "acks": kinds["ack"], "objects": kinds["object"], "other": kinds["other"], "repeated": kinds["repeated"]}
                            for radio, kinds in sent],
                   "packets": counted.packets, "frames": counted.frames, "repeated_hour": counted.repeated_hour,
                   "gated_hour": igate.gated_hour.count(ctx.ctl.clock()) if config.igate_enabled else None})


@command(SpeedSeries)
async def speed_series(ctx: Ctx, cmd: SpeedSeries) -> None:
    """The speeds the station reported in the last hours, the oldest first, for the speed graph of a moving station's card; while `igate/enabled` is off, only those of the positions heard on the radio."""
    speeds = await ctx.ctl.packetlog.speeds(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours), internet=ctx.ctl.config.igate_enabled)
    ctx.conn.send({"type": "speed_series", "call": cmd.call, "hours": cmd.hours, "points": [[iso(at), round(kmh, 1)] for at, kmh in speeds]})


@command(SignalSeries)
async def signal_series(ctx: Ctx, cmd: SignalSeries) -> None:
    """The readings of the station's signal in the last hours, the oldest first, for the signal graph of its card (none came from APRS-IS: a packet from the internet has no reading)."""
    readings = await ctx.ctl.packetlog.readings(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours))
    ctx.conn.send({"type": "signal_series", "call": cmd.call, "hours": cmd.hours, "points": [[iso(at), snr, rssi] for at, snr, rssi in readings]})


@command(StationTraffic)
async def station_traffic(ctx: Ctx, cmd: StationTraffic) -> None:
    """The latest TRAFFIC_KEPT packets of a station from the packet log, for its panel in the Stations tab: those it sent and the messages we sent to it, each as a row of the Packets tab with its number in the log
    as its id; while `igate/enabled` is off, none that came from APRS-IS."""
    config = ctx.ctl.config
    found = await ctx.ctl.packetlog.traffic(cmd.call, config.station_call, TRAFFIC_KEPT, internet=config.igate_enabled)
    ctx.conn.send({"type": "station_traffic", "call": cmd.call, "packets": [packet_row(number, packet) for number, packet in found]})


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


@command(StationTrack)
async def station_track(ctx: Ctx, cmd: StationTrack) -> None:
    """The station's track as its row of the topic `stations` has it now: with the internet hidden (`igate/enabled` off), the radio's side of a station heard both ways, and none for one known only from there."""
    station = ctx.ctl.stationbook.get(cmd.call)
    shown = None if station is None else station if ctx.ctl.config.igate_enabled else station.radio_view()
    if shown is None:
        raise UserError(f"{cmd.cmd}: there is no station {cmd.call!r}", "station.unknown", params={"call": cmd.call})
    ctx.conn.send({"type": "station_track", "call": cmd.call, "points": plain(shown.track)})
