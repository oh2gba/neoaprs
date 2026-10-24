"""The handlers of the commands (neoaprs/web/dispatch.py): what each command of the page does to the daemon. Importing this module registers them.

A handler asks the daemon to change and says so with an exception (`UserError`); what the pages are told of the change comes from the signals of the parts (neoaprs/web/topics.py), never from the handler.
"""
import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from neoaprs.clock import iso
from neoaprs.coded import CodedError
from neoaprs.config import Config, SettingError
from neoaprs.mapstate import Job, MapError
from neoaprs.callsign import CallsignError
from neoaprs.message import MessagingError, normal_call
from neoaprs.ownbulletin import PostError
from neoaprs.ownobject import OwnError
from neoaprs.serialprobe import available_ports, can_search, paired_bluetooth_ports, with_links

from .beaconwire import BeaconNow, StatusNow
from .bulletinwire import BulletinDelete
from .dispatch import Ctx, UserError, command
from .hostwire import AskStatus, CheckUpdate, Ping
from .hubwire import Subscribe, Unsubscribe
from .mapwire import MapCancel, MapEstimate, MapFetch
from .ownwire import BulletinPost, BulletinUnpost, ObjectKill, ObjectSet
from .messagewire import AlertTest, ConversationDelete, MessageCancel, MessageDelete, MessageRetry, OverheardDelete, QueryStation, SendMessage
from .portwire import ListPorts
from .prefwire import ClearStationPath, ClearStationTimeout, SetStationPath, SetStationRfOnly, SetStationTimeout
from .configwire import SetConfig
from .stationwire import ForgetStation
from .tncwire import TncReconnect
from .updatewire import UpdateCancel, UpdateNow
from .views import weather_points
from .weatherwire import WeatherSeries


@contextmanager
def refused(name: str) -> Iterator[None]:
    """A part that refuses with a MessagingError (messaging, the station preferences): the reason is the page's error, after the name of the command. A refusal that only passes on the text of another
    (`MessagingError(str(e))`) has the code of that other."""
    try:
        yield
    except (MessagingError, OwnError, PostError) as e:
        cause = e.__context__ if e.code == "other" and isinstance(e.__context__, CodedError) else e
        raise UserError(f"{name}: {e}", cause.code, None, cause.params) from None


@command(Ping)
async def ping(ctx: Ctx, cmd: Ping) -> None:
    ctx.conn.send({"type": "pong", "now": iso(ctx.ctl.clock())})


@command(AskStatus)
async def status(ctx: Ctx, cmd: AskStatus) -> None:
    ctx.conn.send(await ctx.status())


@command(Subscribe)
async def subscribe(ctx: Ctx, cmd: Subscribe) -> None:
    unknown = ctx.hub.subscribe(ctx.conn, cmd.topics)
    if unknown:
        raise UserError("subscribe: no topic " + ", ".join(repr(n[:40]) for n in unknown[:3]) + (f" (and {len(unknown) - 3} more)" if len(unknown) > 3 else "") + f" (the topics are {', '.join(ctx.hub.topics)})", "topic.unknown",
                        params={"names": ", ".join(n[:40] for n in unknown[:3])})


@command(Unsubscribe)
async def unsubscribe(ctx: Ctx, cmd: Unsubscribe) -> None:
    ctx.hub.unsubscribe(ctx.conn, cmd.topics)


@command(ForgetStation)
async def forget_station(ctx: Ctx, cmd: ForgetStation) -> None:
    book = ctx.ctl.stationbook
    station = book.get(cmd.call)
    if station is None:
        raise UserError(f"forget_station: there is no station {cmd.call!r}", "station.unknown", params={"call": cmd.call})
    if station.own:
        raise UserError(f"forget_station: {cmd.call} is an object of ours: kill it (object_kill)", "station.is_object", params={"call": cmd.call})
    if not book.forget(cmd.call):
        raise UserError(f"forget_station: {cmd.call} is our own station, which stays", "station.is_own", params={"call": cmd.call})


@command(TncReconnect)
async def tnc_reconnect(ctx: Ctx, cmd: TncReconnect) -> None:
    ctx.ctl.start_tnc()


@command(ListPorts)
async def list_ports(ctx: Ctx, cmd: ListPorts) -> None:
    ports = await asyncio.to_thread(lambda: with_links(available_ports()) + paired_bluetooth_ports())   # (the system's lists are read from files, the registry and BlueZ: not on the loop); the by-id names and the user's own links too, then the paired Bluetooth devices
    ctx.conn.send({"type": "ports", "search": can_search(), "ports": [{"device": p.device, "description": p.description, "hwid": p.hwid, "vid": p.vid, "pid": p.pid} for p in ports]})


@command(BeaconNow)
async def beacon_now(ctx: Ctx, cmd: BeaconNow) -> None:
    beacon = ctx.ctl.beacon
    if not beacon.send_now("request"):
        raise UserError(f"beacon_now: nothing was sent: {beacon.problem}", "beacon.not_sent", params={"reason": beacon.problem})


@command(StatusNow)
async def status_now(ctx: Ctx, cmd: StatusNow) -> None:
    if problem := await ctx.ctl.rigstatus.send_now():
        raise UserError(f"status_now: nothing was sent: {problem}", "status.not_sent", params={"reason": problem})


@command(SendMessage)
async def send_message(ctx: Ctx, cmd: SendMessage) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.messaging.send(cmd.to, cmd.text)


@command(QueryStation)
async def query_station(ctx: Ctx, cmd: QueryStation) -> None:
    """A query goes to a station that is in the book and takes messages (else there is nobody to ask: the station is no object, item or ourselves, and not one whose position says it takes none)."""
    with refused(cmd.cmd):
        try:
            call = normal_call(cmd.call)
        except CallsignError as e:
            raise MessagingError(str(e)) from None
        station = ctx.ctl.stationbook.get(call)
        if station is None:
            raise UserError(f"{cmd.cmd}: there is no station {call!r}", "station.unknown", params={"call": call})
        if not station.can_message:
            raise UserError(f"{cmd.cmd}: {call} does not take messages: there is nobody to ask", "query.not_capable", params={"call": call})
        await ctx.ctl.messaging.asking.ask(call, cmd.kind)


@command(MessageRetry)
async def message_retry(ctx: Ctx, cmd: MessageRetry) -> None:
    with refused(cmd.cmd):
        ctx.ctl.messaging.retry(cmd.id)


@command(MessageCancel)
async def message_cancel(ctx: Ctx, cmd: MessageCancel) -> None:
    with refused(cmd.cmd):
        ctx.ctl.messaging.cancel(cmd.id)


@command(MessageDelete)
async def message_delete(ctx: Ctx, cmd: MessageDelete) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.messaging.delete(cmd.id)


@command(ConversationDelete)
async def conversation_delete(ctx: Ctx, cmd: ConversationDelete) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.messaging.delete_conversation(cmd.call)


@command(OverheardDelete)
async def overheard_delete(ctx: Ctx, cmd: OverheardDelete) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.messaging.delete_overheard(cmd.from_call, cmd.to_call)


@command(SetStationPath)
async def set_station_path(ctx: Ctx, cmd: SetStationPath) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.set_path(cmd.call, cmd.path)


@command(ClearStationPath)
async def clear_station_path(ctx: Ctx, cmd: ClearStationPath) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.clear_path(cmd.call)


@command(SetStationTimeout)
async def set_station_timeout(ctx: Ctx, cmd: SetStationTimeout) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.set_timeout(cmd.call, cmd.minutes)


@command(ClearStationTimeout)
async def clear_station_timeout(ctx: Ctx, cmd: ClearStationTimeout) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.clear_timeout(cmd.call)


@command(SetStationRfOnly)
async def set_station_rf_only(ctx: Ctx, cmd: SetStationRfOnly) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.set_rf_only(cmd.call, cmd.on)


@command(SetConfig)
async def set_config(ctx: Ctx, cmd: SetConfig) -> None:
    """Every value is checked before anything is stored (the first wrong one is the answer, with its key), and the settings in force are the base: a key that is left out keeps its value."""
    try:
        config = Config.checked(ctx.ctl.config, cmd.values)
    except SettingError as e:
        raise UserError(f"set_config: {e}", e.code, e.key, e.params) from None
    except ValueError as e:
        raise UserError(f"set_config: {e}") from None
    if not await ctx.ctl.save_config(config):
        raise UserError("set_config: the settings could not be stored (the database would not take them); nothing changed", "setting.not_stored")


@command(CheckUpdate)
async def update_check(ctx: Ctx, cmd: CheckUpdate) -> None:
    result = await ctx.ctl.updatecheck.check_now()
    ctx.conn.send({"type": "update_result", "outcome": result.outcome, "version": result.version, "text": result.reason})
    ctx.conn.send(await ctx.status())                                   # (the other pages have it at the next status, within 10 s)


@command(UpdateNow)
async def update_now(ctx: Ctx, cmd: UpdateNow) -> None:
    """Over the page's socket, which only a page of this computer or one that has logged in with the access key has (neoaprs/web/access.py), like every command that changes the daemon."""
    try:
        ctx.ctl.selfupdate.begin(cmd.version)
    except CodedError as e:
        raise UserError(f"update_now: {e}", e.code, params=e.params) from None


@command(UpdateCancel)
async def update_cancel(ctx: Ctx, cmd: UpdateCancel) -> None:
    try:
        ctx.ctl.selfupdate.cancel()
    except CodedError as e:
        raise UserError(f"update_cancel: {e}", e.code, params=e.params) from None


@command(WeatherSeries)
async def weather_series(ctx: Ctx, cmd: WeatherSeries) -> None:
    observations = await ctx.ctl.weatherlog.series(cmd.call, ctx.ctl.clock() - timedelta(hours=cmd.hours))
    ctx.conn.send({"type": "weather_series", "call": cmd.call, "hours": cmd.hours, "points": weather_points(observations)})


@command(AlertTest)
async def alert_test(ctx: Ctx, cmd: AlertTest) -> None:
    try:
        ok, text = await ctx.ctl.alerts.test()
    except ValueError as e:
        raise UserError(f"{cmd.cmd}: {e}") from None
    ctx.conn.send({"type": "alert_result", "ok": ok, "text": text})


@command(BulletinDelete)
async def bulletin_delete(ctx: Ctx, cmd: BulletinDelete) -> None:
    if not ctx.ctl.bulletins.delete(cmd.sender, cmd.slot):
        raise UserError(f"bulletin_delete: there is no entry {cmd.sender}/{cmd.slot} on the board", "bulletin.not_on_board", params={"sender": cmd.sender, "slot": cmd.slot})


def start_map_job(ctx: Ctx, job: Job, name: str) -> None:
    try:
        ctx.ctl.mapfetch.begin(job)
    except MapError as e:
        raise UserError(f"{name}: {e}") from None


@command(ObjectSet)
async def object_set(ctx: Ctx, cmd: ObjectSet) -> None:
    with refused(cmd.cmd):
        ctx.ctl.ownobjects.set(cmd.name, cmd.kind, cmd.lat, cmd.lon, cmd.symbol_table, cmd.symbol_code, cmd.comment, cmd.course_deg, cmd.speed_kmh, cmd.path)


@command(ObjectKill)
async def object_kill(ctx: Ctx, cmd: ObjectKill) -> None:
    with refused(cmd.cmd):
        ctx.ctl.ownobjects.kill(cmd.name)


@command(BulletinPost)
async def bulletin_post(ctx: Ctx, cmd: BulletinPost) -> None:
    with refused(cmd.cmd):
        ctx.ctl.ownbulletins.post(cmd.slot, cmd.text)


@command(BulletinUnpost)
async def bulletin_unpost(ctx: Ctx, cmd: BulletinUnpost) -> None:
    if not ctx.ctl.ownbulletins.delete(cmd.slot):
        raise UserError(f"bulletin_unpost: there is no bulletin {cmd.slot} of ours", "bulletin.not_posted", params={"slot": cmd.slot})


@command(MapEstimate)
async def map_estimate(ctx: Ctx, cmd: MapEstimate) -> None:
    start_map_job(ctx, "estimate", cmd.cmd)


@command(MapFetch)
async def map_fetch(ctx: Ctx, cmd: MapFetch) -> None:
    start_map_job(ctx, "fetch", cmd.cmd)


@command(MapCancel)
async def map_cancel(ctx: Ctx, cmd: MapCancel) -> None:
    if not ctx.ctl.mapfetch.cancel():
        raise UserError(f"{cmd.cmd}: no map job is running", "map.no_job")
