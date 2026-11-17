"""The handlers of the commands (neoaprs/web/dispatch.py): what each command of the page does to the daemon. Importing this module registers them, with those answered from the logs (neoaprs/web/historyhandlers.py).

The settings and the alert's Test are in neoaprs/web/confighandlers.py. A handler asks the daemon to change and says so with an exception (`UserError`); what the pages are told of the change comes from the signals of the parts (neoaprs/web/topics.py), never from the handler.
"""
import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict

from neoaprs.clock import iso
from neoaprs.coded import CodedError, code_of
from neoaprs.mapstate import Job, MapError
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.message import MessagingError
from neoaprs.ownbulletin import PostError
from neoaprs.ownobject import OwnError
from neoaprs.pref import Alert
from neoaprs.direwolfmodem import DirewolfModem, proposal as sound_card_proposal
from neoaprs.mercurymodem import left_out, proposal
from neoaprs.claims import PORT_KINDS, Claims
from neoaprs.radiospec import FM_ID
from neoaprs.radiotype import ResourceKind
from neoaprs.radiosearch import Trying
from neoaprs.serialprobe import available_ports, can_find, can_search, claim_value, paired_bluetooth_ports, with_links
from neoaprs.usbtie import together

from .beaconwire import BeaconNow, StatusNow
from .bulletinwire import BulletinDelete
from . import historyhandlers  # noqa: F401  (the commands answered from the logs: importing it registers them)
from . import confighandlers  # noqa: F401  (set_config and the alert's Test: importing it registers them)
from . import skedhandlers  # noqa: F401  (the sked board: importing it registers its commands)
from .dispatch import Ctx, UserError, command
from .radiohandlers import named_radio, sending_radio  # (the commands that name a radio: importing it registers them)
from .hostwire import AskStatus, CheckUpdate, Ping, ReleaseNotes
from .hubwire import Subscribe, Unsubscribe
from .mapwire import MapCancel, MapEstimate, MapFetch, MapWanted
from .ownwire import BulletinPost, BulletinUnpost, ObjectKill, ObjectSet
from .messagewire import ConversationDelete, ForgetStationKey, MessageCancel, MessageDelete, MessageRetry, NewMessageKey, OverheardDelete, QueryStation, SendKey, SendMessage
from .qruwire import AskQru
from .generalwire import GeneralQuery
from .portwire import FindRadio, FindRadioCancel, ListPorts
from .prefwire import ClearStationPath, SetStationAlert, SetStationPath, SetStationRfOnly
from .stationwire import ForgetAllStations, ForgetStation
from .supportwire import PageError
from .updatewire import UpdateCancel, UpdateNow


log = logging.getLogger("neoaprs.web")


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


@command(ForgetAllStations)
async def forget_all_stations(ctx: Ctx, cmd: ForgetAllStations) -> None:
    await ctx.ctl.forget_stations()


def _holder(claims: Claims, kind: ResourceKind, value: str | None) -> int | None:
    """Who of the station holds the device (a radio's id, 0 for the GPS receiver); None for nobody of ours."""
    held = next((c for c in claims.all() if value is not None and c.value == value and (c.kind == kind or {c.kind, kind} <= PORT_KINDS)), None)
    return None if held is None else held.holder or 0


@command(ListPorts)
async def list_ports(ctx: Ctx, cmd: ListPorts) -> None:
    """The ports and, for a radio named that has a modem on a sound card, the sound cards, each with who of the station holds it; the proposals leave out what the others hold."""
    radio, claims = None if cmd.radio is None else named_radio(ctx, cmd.cmd, cmd.radio), ctx.ctl.radios.claims
    modem = None if radio is None else radio.driver.modem
    ports = await asyncio.to_thread(lambda: with_links(available_ports()) + paired_bluetooth_ports())   # (the system's lists are read from files, the registry and BlueZ: not on the loop); the by-id names and the user's own links too, then the paired Bluetooth devices
    cards = await asyncio.to_thread(modem.sound_cards) if modem is not None else []        # (the modem's program is run for its list: only while the radio has a modem on a sound card)
    on_card, on_port = await asyncio.to_thread(together, [c.id for c in cards], [p.device for p in ports])     # (which of them sit on one radio's USB hub, read from sysfs: the page orders the keying by it)
    if isinstance(modem, DirewolfModem) and radio is not None:
        holder = radio.id
        pick, keying = await asyncio.to_thread(lambda: sound_card_proposal(cards, ports, left_out(ctx.ctl.config, holder), claims=claims, holder=holder))       # (which ports are the card's is read from sysfs)
    else:
        pick, keying = ("", "") if radio is None else proposal(cards, ports, ctx.ctl.config, claims=claims, holder=radio.id)
    ctx.conn.send({"type": "ports", "radio": cmd.radio, "search": can_search(), "find": can_find(), "keying": keying,
                   "ports": [{"device": p.device, "description": p.description, "hwid": p.hwid, "vid": p.vid, "pid": p.pid, "held_by": _holder(claims, "serial", claim_value(p.device)), "usb_group": on_port.get(p.device)} for p in ports],
                   "sound_cards": [{"id": c.id, "name": c.name, "numbered": c.numbered, "default": c.default, "pick": c.id == pick, "held_by": _holder(claims, "sound_card", c.id), "usb_group": on_card.get(c.id)} for c in cards]})


@command(FindRadio)
async def find_radio(ctx: Ctx, cmd: FindRadio) -> None:
    """Find my radio for the radio named (radio 1 when none is): only a radio whose type has a serial line is searched for (`radio.no_line`, with its name), and never one that only receives
    (`radio.receive_only`, with its name): its line is written nothing, and Find my radio writes a carriage return and the KISS entries to the ports it tries. The finder lets go of the radio it is given alone."""
    finder = ctx.ctl.radiofinder
    radio = FM_ID if cmd.radio is None else cmd.radio
    named = named_radio(ctx, cmd.cmd, radio)                         # (radio 1 when none is named, refused as `radio.unknown` once it is removed)
    if not named.rtype.can.transmit:
        raise UserError(f"{cmd.cmd}: radio {named.name} only receives: nothing is written to its line", "radio.receive_only", params={"name": named.name, "radio": named.id})
    if cmd.radio is not None and not named.rtype.can.find:
        raise UserError(f"{cmd.cmd}: radio {named.name} has no serial line to look for", "radio.no_line", params={"name": named.name, "radio": named.id})
    base = {"radio": cmd.radio, "radio_type": "", "profile": "", "number": 0, "total": 0}

    def trying(step: Trying) -> None:
        if ctx.conn.closed:                                          # (the page that asked left: nobody will put the answer in the settings)
            finder.cancel()
        ctx.conn.send({**base, "type": "radio_search", "state": "trying", "port": step.port, "baud": step.baud, "number": step.number, "total": step.total})

    try:
        found = await finder.find(trying, radio)
    except CodedError as e:
        raise UserError(f"find_radio: {e}", e.code, params={**e.params, "radio": radio}) from None
    if found is None:
        ctx.conn.send({**base, "type": "radio_search", "state": "cancelled", "port": "", "baud": None})
    else:
        ctx.conn.send({**base, "type": "radio_search", "state": "found", "port": found.port, "baud": found.baud, "profile": found.profile, "radio_type": found.profile})


@command(FindRadioCancel)
async def find_radio_cancel(ctx: Ctx, cmd: FindRadioCancel) -> None:
    if not ctx.ctl.radiofinder.cancel():
        raise UserError(f"{cmd.cmd}: no search for the radio is running", "radio.not_running")


@command(BeaconNow)
async def beacon_now(ctx: Ctx, cmd: BeaconNow) -> None:
    """A beacon on every radio the beacon goes out on (each by its own rules: the Mercury one direct, the FM one by the path; Send on: RadioRegistry.beaconing); refused with the reason when none went out."""
    beacons = [radio.beacon for radio in ctx.ctl.radios.beaconing()]
    if not beacons and ctx.ctl.config.listens_only:
        raise UserError("beacon_now: RX only: nothing is sent", "transmit.off")          # (every radio that is on only receives)
    if not beacons:
        raise UserError("beacon_now: there is no radio: add one, or turn one on", "radio.none")
    sent = [b.send_now("request") for b in beacons]
    if not any(sent):
        beacon = beacons[0]
        why, params = code_of(beacon.problem)
        if why == "transmit.off":
            raise UserError("beacon_now: RX only: nothing is sent", "transmit.off")
        raise UserError(f"beacon_now: nothing was sent: {beacon.problem}", "beacon.not_sent", params={"why": why, **params})      # (the page says the reason by `why`, error.<why>)


@command(StatusNow)
async def status_now(ctx: Ctx, cmd: StatusNow) -> None:
    if problem := await ctx.ctl.rigstatus.send_now():
        why, params = code_of(problem)
        if why == "transmit.off":
            raise UserError("status_now: RX only: nothing is sent", "transmit.off")
        raise UserError(f"status_now: nothing was sent: {problem}", "status.not_sent", params={"why": why, **params})


@command(SendMessage)
async def send_message(ctx: Ctx, cmd: SendMessage) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.messaging.send(cmd.to, cmd.text, locked=cmd.locked)


@command(SendKey)
async def send_key(ctx: Ctx, cmd: SendKey) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.messaging.send_key(cmd.to)


@command(ForgetStationKey)
async def forget_station_key(ctx: Ctx, cmd: ForgetStationKey) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.keyring.forget(cmd.call)


@command(NewMessageKey)
async def message_key_new(ctx: Ctx, cmd: NewMessageKey) -> None:
    """The new key's fingerprint goes to the page that asked with the status it is answered with."""
    with refused(cmd.cmd):
        ctx.ctl.keyring.refuse_unless_on()
        ctx.ctl.keyring.renew()
    ctx.conn.send(await ctx.status())


@command(QueryStation)
async def query_station(ctx: Ctx, cmd: QueryStation) -> None:
    """A query goes to a station that is in the book and takes messages (else there is nobody to ask: the station is no object, item or ourselves, and not one whose position says it takes none)."""
    with refused(cmd.cmd):
        try:
            call = normal_name(cmd.call)
        except CallsignError as e:
            raise MessagingError.of(e) from None
        station = ctx.ctl.stationbook.get(call)
        if station is None:
            raise UserError(f"{cmd.cmd}: there is no station {call!r}", "station.unknown", params={"call": call})
        if not station.can_message:
            raise UserError(f"{cmd.cmd}: {call} does not take messages: there is nobody to ask", "query.not_capable", params={"call": call})
        await ctx.ctl.messaging.asking.ask(call, cmd.kind, cmd.text)


@command(AskQru)
async def qru_ask(ctx: Ctx, cmd: AskQru) -> None:
    """Local info is asked of the stations near us: one request to QRU, once, by radio only."""
    radio = sending_radio(ctx, cmd.cmd, cmd.radio)
    with refused(cmd.cmd):
        ctx.ctl.qruask.ask(cmd.text, cmd.path, cmd.rf_only, radio=radio)


@command(GeneralQuery)
async def general_query(ctx: Ctx, cmd: GeneralQuery) -> None:
    """The stations in radio range are asked a general query (?APRS?, ?IGATE?, ?WX?): one frame on each radio of asking around's Send on, once, by the path given (else each radio's own), RF only unless told otherwise."""
    sending_radio(ctx, cmd.cmd, None)
    with refused(cmd.cmd):
        ctx.ctl.generalask.ask(cmd.kind, cmd.path, cmd.rf_only)


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
    radio = named_radio(ctx, cmd.cmd, FM_ID if cmd.radio is None else cmd.radio).id          # (radio 1 when none is named: `radio.unknown` once it is removed, and no row names a radio that is gone)
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.set_path(cmd.call, cmd.path, radio)


@command(ClearStationPath)
async def clear_station_path(ctx: Ctx, cmd: ClearStationPath) -> None:
    radio = named_radio(ctx, cmd.cmd, FM_ID if cmd.radio is None else cmd.radio).id
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.clear_path(cmd.call, radio)


@command(SetStationRfOnly)
async def set_station_rf_only(ctx: Ctx, cmd: SetStationRfOnly) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.prefbook.set_rf_only(cmd.call, cmd.on)


@command(SetStationAlert)
async def set_station_alert(ctx: Ctx, cmd: SetStationAlert) -> None:
    with refused(cmd.cmd):
        await ctx.ctl.stationalerts.set(cmd.call, Alert(cmd.on_air, cmd.within_km, cmd.direct))


@command(CheckUpdate)
async def update_check(ctx: Ctx, cmd: CheckUpdate) -> None:
    result = await ctx.ctl.updatecheck.check_now()
    ctx.conn.send({"type": "update_result", "outcome": result.outcome, "version": result.version, "reason": result.why})
    ctx.conn.send(await ctx.status())                                   # (the other pages have it at the next status, within 10 s)


@command(ReleaseNotes)
async def release_notes(ctx: Ctx, cmd: ReleaseNotes) -> None:
    found, problem = await ctx.ctl.updatecheck.release_notes(cmd.version, cmd.since)
    ctx.conn.send({"type": "release_notes", "version": cmd.version, "since": cmd.since, "sections": [asdict(section) for section in found], "problem": problem})


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


@command(BulletinDelete)
async def bulletin_delete(ctx: Ctx, cmd: BulletinDelete) -> None:
    if not ctx.ctl.bulletins.delete(cmd.sender, cmd.slot):
        raise UserError(f"bulletin_delete: there is no entry {cmd.sender}/{cmd.slot} on the board", "bulletin.not_on_board", params={"sender": cmd.sender, "slot": cmd.slot})


def start_map_job(ctx: Ctx, job: Job, name: str) -> None:
    try:
        ctx.ctl.mapfetch.begin(job)
    except MapError as e:
        if e.problem == "busy":
            raise UserError(f"{name}: a map job is running already", "map.busy") from None
        raise UserError(f"{name}: the station has no position yet: set Latitude and Longitude (the map is cut round them)", "map.no_position") from None


@command(ObjectSet)
async def object_set(ctx: Ctx, cmd: ObjectSet) -> None:
    for id in cmd.radios:
        named_radio(ctx, cmd.cmd, id)
    with refused(cmd.cmd):
        ctx.ctl.ownobjects.set(cmd.name, cmd.kind, cmd.lat, cmd.lon, cmd.symbol_table, cmd.symbol_code, cmd.comment, cmd.course_deg, cmd.speed_kmh, cmd.path, cmd.qru_group, cmd.on_request, radios=cmd.radios)


@command(ObjectKill)
async def object_kill(ctx: Ctx, cmd: ObjectKill) -> None:
    with refused(cmd.cmd):
        ctx.ctl.ownobjects.kill(cmd.name)


@command(BulletinPost)
async def bulletin_post(ctx: Ctx, cmd: BulletinPost) -> None:
    for id in cmd.radios or ():
        named_radio(ctx, cmd.cmd, id)
    with refused(cmd.cmd):
        ctx.ctl.ownbulletins.post(cmd.slot, cmd.text, cmd.radios)


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


@command(MapWanted)
async def map_wanted(ctx: Ctx, cmd: MapWanted) -> None:
    ctx.ctl.mapauto.wanted()


@command(MapCancel)
async def map_cancel(ctx: Ctx, cmd: MapCancel) -> None:
    if not ctx.ctl.mapfetch.cancel():
        raise UserError(f"{cmd.cmd}: no map job is running", "map.no_job")


@command(PageError)
async def page_error(ctx: Ctx, cmd: PageError) -> None:
    """The page tells of an error of its own: it is logged and kept for the support bundle (neoaprs/web/pageerrors.py). Not answered."""
    if ctx.page_errors is not None:
        ctx.page_errors.note(ctx.conn, cmd)
