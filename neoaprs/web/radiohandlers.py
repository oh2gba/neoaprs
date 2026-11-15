"""The handlers of the commands that name a radio (neoaprs/web/radiowire.py): add, remove and change a radio, Tune, the keying test and the scope of its modem, the radio of a station's messages, and the station's
suggested frequencies. Registered with the dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there; `named_radio` and `sending_radio` are the refusals every command that names a radio
gives (`radio.unknown`, `radio.not_connected`, `radio.none`), for the handlers of the other areas too.

A handler asks the controller (`add_radio`, `change_radio`, `remove_radio`), which stores the change before it is put in force; what the pages are told of it comes from the signals (neoaprs/web/topics.py). A refusal
of the radios' rules is a coded `RadioError` (neoaprs/radiospec.py), passed on with its code; a change the database would not take is `setting.not_stored`, with the reason in the log."""
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from neoaprs.coded import CodedError
from neoaprs.radioregistry import LiveRadio
from neoaprs.radiospec import RadioError, RadioId
from neoaprs.radiotype import RadioTypeError

from .dispatch import Ctx, UserError, command
from .hfhandlers import may_transmit
from .radiowire import RadioAdd, RadioChange, RadioKeyTest, RadioRemove, RadioScope, RadioTune, StationRadio
from .tncwire import Frequencies
from .views import on_their_way

log = logging.getLogger("neoaprs.web")


@contextmanager
def radio_refused(name: str) -> Iterator[None]:
    """A refusal of the radios' rules (RadioError, RadioTypeError) as the page's error, after the name of the command, with its code and values."""
    try:
        yield
    except RadioError as e:
        if e.code == "radio.name_taken":                    # (the page names a radio by its name: the command line's sentence names the other radio by the id it lists)
            raise UserError(f"{name}: the name {e.params['name']!r} is another radio's already: give this one another", "radio.name_taken", None, e.params) from None
        if e.code == "radio.type_kind":                     # (the command line's sentence names the key and the type's key it typed)
            raise UserError(f"{name}: the {e.params['name']} radio takes only a type of its own kind ({e.params['kind']})", "radio.type_kind", None, e.params) from None
        raise UserError(f"{name}: {e}", e.code, None, e.params) from None
    except RadioTypeError as e:
        raise UserError(f"{name}: {e}", e.code, None, e.params) from None


def named_radio(ctx: Ctx, name: str, id: RadioId) -> LiveRadio[Any]:
    """The radio of the id that is not removed; `radio.unknown` when there is none."""
    radio = ctx.ctl.radios.get(id)
    if radio is None:
        raise UserError(f"{name}: there is no radio {id}", "radio.unknown", params={"radio": id})
    return radio


def sending_radio(ctx: Ctx, name: str, id: RadioId | None) -> RadioId | None:
    """The radio a command that sends names, checked: `radio.unknown` for none, `radio.off` (with its name) for one that is switched off, `radio.not_connected` (with its name) for one that does not take
    frames now; with no radio named, `radio.none` while the station has no main radio (no radio is enabled). The id, or None for the main radio."""
    if id is None:
        if ctx.ctl.radios.main is None:
            raise UserError(f"{name}: there is no radio: add one, or turn one on", "radio.none")
        return None
    radio = named_radio(ctx, name, id)
    if not radio.spec.enabled:
        raise UserError(f"{name}: the {radio.name} radio is off: turn it on first", "radio.off", params={"name": radio.name})
    if not radio.usable:
        raise UserError(f"{name}: the {radio.name} radio is not connected", "radio.not_connected", params={"name": radio.name})
    return id


def _stored(name: str, done: bool) -> None:
    """`setting.not_stored` when the change was not stored (the reason is in the log: the database, or the stand-in settings of a database that could not be read)."""
    if not done:
        raise UserError(f"{name}: the radio could not be stored; nothing changed", "setting.not_stored")


@command(RadioAdd)
async def radio_add(ctx: Ctx, cmd: RadioAdd) -> None:
    """The radio is added; the page that asked is told its id at once, and its row comes with the next patch of `radios` (a topic told at most four times a second): a page waits for the row."""
    with radio_refused(cmd.cmd):
        id = await ctx.ctl.add_radio(cmd.type, cmd.name)
    if id is None:
        _stored(cmd.cmd, False)
    ctx.conn.send({"type": "radio_added", "id": id})


@command(RadioRemove)
async def radio_remove(ctx: Ctx, cmd: RadioRemove) -> None:
    with radio_refused(cmd.cmd):
        _stored(cmd.cmd, await ctx.ctl.remove_radio(cmd.radio))


@command(RadioChange)
async def radio_change(ctx: Ctx, cmd: RadioChange) -> None:
    """What the command gives of the radio, and nothing else; a command that gives nothing changes nothing."""
    columns = {column: value for column in ("name", "type", "enabled", "position") if (value := getattr(cmd, column)) is not None}
    with radio_refused(cmd.cmd):
        _stored(cmd.cmd, await ctx.ctl.change_radio(cmd.radio, **columns))


def _modem(ctx: Ctx, name: str, id: RadioId) -> Any:
    """The Mercury modem of the radio; `radio.unknown` for a radio that is none, `radio.no_modem` (with its name) for one whose type has no modem or whose modem is not running."""
    radio = named_radio(ctx, name, id)
    if radio.driver.modem is None:
        raise UserError(f"{name}: the {radio.name} radio has no modem running", "radio.no_modem", params={"name": radio.name})
    return radio.driver.modem


@command(RadioTune)
async def radio_tune(ctx: Ctx, cmd: RadioTune) -> None:
    """The tune tone on or off on the radio's modem, with the refusals of `hf_tune`."""
    modem = _modem(ctx, cmd.cmd, cmd.radio)
    if not cmd.on:
        await modem.tune_stop()
        return
    may_transmit(ctx, cmd.cmd)
    try:
        await modem.tune()
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None


@command(RadioKeyTest)
async def radio_key_test(ctx: Ctx, cmd: RadioKeyTest) -> None:
    modem = _modem(ctx, cmd.cmd, cmd.radio)
    may_transmit(ctx, cmd.cmd)
    try:
        await modem.key_test()
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None


@command(RadioScope)
async def radio_scope(ctx: Ctx, cmd: RadioScope) -> None:
    """This page wants the rows of the radio's waterfall, or no more of them: those of the modem the page's scope feed follows (radio 2's); nothing for another radio, and nothing is refused."""
    radio = ctx.ctl.radios.get(cmd.radio)
    if ctx.scope is not None and radio is not None and ctx.scope.follows(radio.driver.modem):
        ctx.scope.ask(ctx.conn, cmd.on)


@command(StationRadio)
async def station_radio(ctx: Ctx, cmd: StationRadio) -> None:
    """The radio of the station's messages: a radio that is not removed, or none (the daemon's choice)."""
    if cmd.radio is not None:
        named_radio(ctx, cmd.cmd, cmd.radio)
    if not ctx.ctl.radios.choose(cmd.call, cmd.radio):
        raise UserError(f"{cmd.cmd}: there is no station {cmd.call!r}", "station.unknown", params={"call": cmd.call})
    station = ctx.ctl.stationbook.get(cmd.call)
    for key in on_their_way(ctx.ctl.messaging.records(), cmd.call if station is None else station.call):
        ctx.hub.changed("messages", key)            # (a message on its way takes the radio chosen from its next attempt: its `radio_now`)


@command(Frequencies)
async def frequencies(ctx: Ctx, cmd: Frequencies) -> None:
    """The page shows the suggested frequencies: the project's list is asked for again if it is time (the service keeps the 15 minutes between two questions)."""
    ctx.ctl.frequencies.wanted()
