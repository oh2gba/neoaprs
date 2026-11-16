"""The handlers of the commands that name a radio (neoaprs/web/radiowire.py): add, remove and change a radio, Tune, the keying test and the scope of its modem, the radio of a station's messages, and the station's
suggested frequencies. Registered with the dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there; `named_radio` and `sending_radio` are the refusals every command that names a radio
gives (`radio.unknown`, `radio.off`, `radio.receive_only`, `radio.not_connected`, `radio.none`), for the handlers of the other areas too. A refusal that names a radio by the daemon's English name carries its id too (`radio`), by which a page
says that radio in its own words.

A handler asks the controller (`add_radio`, `change_radio`, `remove_radio`), which stores the change before it is put in force; what the pages are told of it comes from the signals (neoaprs/web/topics.py). A refusal
of the radios' rules is a coded `RadioError` (neoaprs/radiospec.py), passed on with its code; a change the database would not take is `setting.not_stored`, with the reason in the log."""
import logging
import re
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from neoaprs.callsign import CallsignError, normal_name
from neoaprs.coded import CodedError, code_of
from neoaprs.config import can_transmit
from neoaprs.radioregistry import LiveRadio
from neoaprs.mercurymodem import Mercury
from neoaprs.radiospec import KIND_WORDS, RadioError, RadioId, RadioSpec, live, log_name
from neoaprs.radiotype import RadioTypeError

from .dispatch import Ctx, UserError, command
from .radiowire import RadioAdd, RadioChange, RadioKeyTest, RadioRemove, RadioScope, RadioTune, StationRadio
from .radioview import removed_name
from .tncwire import Frequencies
from .views import on_their_way

log = logging.getLogger("neoaprs.web")

LABEL = re.compile("(?:" + "|".join(re.escape(word.casefold()) for word in KIND_WORDS.values()) + ")(?: [0-9]+)?")      # what a radio with no name of its own is called, case folded ("fm", "mercury 2")


@contextmanager
def radio_refused(name: str, id: RadioId | None = None, specs: Sequence[RadioSpec] = ()) -> Iterator[None]:
    """A refusal of the radios' rules (RadioError, RadioTypeError) as the page's error, after the name of the command, with its code and values; one about the radio `id` names it by its id too, and a removed
    radio (`specs`, the settings' radios) is said to be removed."""
    try:
        yield
    except RadioError as e:
        if e.code == "radio.name_taken":                    # (the page names a radio by its name: the command line's sentence names the other radio by the id it lists)
            raise UserError(f"{name}: the name {e.params['name']!r} is another radio's already: give this one another", "radio.name_taken", None, e.params) from None
        if id is None:
            raise UserError(f"{name}: {e}", e.code, None, e.params) from None
        if e.code == "radio.type_kind":                     # (the command line's sentence names the key and the type's key it typed)
            raise UserError(f"{name}: radio {e.params['name']} takes only a type of its own kind ({e.params['kind']})", "radio.type_kind", None, {**e.params, "radio": id}) from None
        if e.code == "radio.last_enabled":
            raise UserError(name + ": " + str(e), "radio.last_enabled", None, {**e.params, "radio": id}) from None
        if e.code == "radio.unknown" and removed_name(id, specs) is not None:
            raise no_radio(name, id, specs) from None
        raise UserError(f"{name}: {e}", e.code, None, e.params) from None
    except RadioTypeError as e:
        raise UserError(f"{name}: {e}", e.code, None, e.params) from None


def no_radio(name: str, id: RadioId, specs: Sequence[RadioSpec]) -> UserError:
    """`radio.unknown` for the id: a radio the settings keep as removed is said to be removed, with its `name` and `removed` 1; any other is "there is no radio N"."""
    removed = removed_name(id, specs)
    if removed is not None:
        return UserError(f"{name}: radio {removed} is removed", "radio.unknown", params={"radio": id, "name": removed, "removed": 1})
    return UserError(f"{name}: there is no radio {id}", "radio.unknown", params={"radio": id})


def named_radio(ctx: Ctx, name: str, id: RadioId) -> LiveRadio[Any]:
    """The radio of the id that is not removed; `radio.unknown` when there is none."""
    radio = ctx.ctl.radios.get(id)
    if radio is None:
        raise no_radio(name, id, ctx.ctl.config.radios)
    return radio


def sending_radio(ctx: Ctx, name: str, id: RadioId | None) -> RadioId | None:
    """The radio a command that sends names, checked: `radio.unknown` for none, `radio.off` (with its name) for one that is switched off, `radio.receive_only` (with its name) for one of a type that only
    receives (`Can.transmit` false), `radio.not_connected` (with its name) for one that does not take frames now; with no radio named, `transmit.off` while every enabled radio is one that only receives,
    and `radio.none` while no radio that can send is on. The id, or None for the radios the command's own rule gives."""
    if id is None:
        if ctx.ctl.config.listens_only:
            raise UserError(f"{name}: RX only: nothing is sent", "transmit.off")
        if not ctx.ctl.radios.senders():
            raise UserError(f"{name}: there is no radio: add one, or turn one on", "radio.none")
        return None
    radio = named_radio(ctx, name, id)
    if not radio.spec.enabled:
        raise UserError(f"{name}: radio {radio.name} is off: turn it on first", "radio.off", params={"name": radio.name, "radio": id})
    if not radio.rtype.can.transmit:
        raise UserError(f"{name}: radio {radio.name} only receives: nothing can be sent on it", "radio.receive_only", params={"name": radio.name, "radio": id})
    if not radio.usable:
        raise UserError(f"{name}: radio {radio.name} is not connected", "radio.not_connected", params={"name": radio.name, "radio": id})
    return id


def _stored(name: str, done: bool) -> None:
    """`setting.not_stored` when the change was not stored (the reason is in the log: the database, or a start that could not read the radios)."""
    if not done:
        raise UserError(f"{name}: the radio could not be stored; nothing changed", "setting.not_stored")


def refuse_label(name: str, typed: str | None, specs: Sequence[RadioSpec], own: RadioId | None) -> None:
    """A name typed in the form of what a radio with no name of its own is called (a kind's word, alone or with a number: "FM", "mercury 2", "LoRa 3") is refused: such a name is, or becomes when a radio is added, has its
    name cleared or the radios are numbered again after a remove, another radio's too. `radio.name_taken` with the radio that is called so now, else `radio.name_label`. The radio's own name of before, sent again, is
    taken (a name stored before this rule)."""
    wanted = (typed or "").strip()
    if not LABEL.fullmatch(wanted.casefold()) or any(s.id == own and s.name.casefold() == wanted.casefold() for s in specs):
        return
    other = next((s for s in live(specs) if s.id != own and not s.name and log_name(s, specs).casefold() == wanted.casefold()), None)
    if other is not None:
        raise UserError(f"{name}: the name {wanted!r} is another radio's already: give this one another", "radio.name_taken", params={"name": wanted, "radio": other.id})
    raise UserError(f"{name}: the name {wanted!r} is how a radio without a name of its own is called: give this one another", "radio.name_label", params={"name": wanted})


@command(RadioAdd)
async def radio_add(ctx: Ctx, cmd: RadioAdd) -> None:
    """The radio is added; the page that asked is told its id at once, and its row comes with the next patch of `radios` (a topic told at most four times a second): a page waits for the row."""
    refuse_label(cmd.cmd, cmd.name, ctx.ctl.config.radios, None)
    with radio_refused(cmd.cmd):
        id = await ctx.ctl.add_radio(cmd.type, cmd.name)
    if id is None:
        _stored(cmd.cmd, False)
    ctx.conn.send({"type": "radio_added", "id": id})


@command(RadioRemove)
async def radio_remove(ctx: Ctx, cmd: RadioRemove) -> None:
    with radio_refused(cmd.cmd, cmd.radio, ctx.ctl.config.radios):
        _stored(cmd.cmd, await ctx.ctl.remove_radio(cmd.radio))


@command(RadioChange)
async def radio_change(ctx: Ctx, cmd: RadioChange) -> None:
    """What the command gives of the radio, and nothing else; a command that gives nothing changes nothing."""
    columns = {column: value for column in ("name", "type", "enabled", "position") if (value := getattr(cmd, column)) is not None}
    refuse_label(cmd.cmd, cmd.name, ctx.ctl.config.radios, cmd.radio)
    with radio_refused(cmd.cmd, cmd.radio, ctx.ctl.config.radios):
        _stored(cmd.cmd, await ctx.ctl.change_radio(cmd.radio, **columns))


def may_transmit(ctx: Ctx, name: str) -> None:
    """The transmit interlock as every other transmission has it: receive only, and a call that may be sent under (a tone with no identification is a transmission too)."""
    config = ctx.ctl.config
    if not config.station_transmit or config.listens_only:
        raise UserError(f"{name}: RX only: nothing is sent", "transmit.off")
    if reason := can_transmit(config):
        why, params = code_of(reason)
        raise UserError(f"{name}: nothing is sent: {reason}", "transmit.call", params={"why": why, **params})          # (the page says the reason by `why`, error.<why>)


def _no_modem(name: str, radio: LiveRadio[Any]) -> UserError:
    return UserError(f"{name}: radio {radio.name} has no modem running", "radio.no_modem", params={"name": radio.name, "radio": radio.id})


def _modem(ctx: Ctx, name: str, id: RadioId) -> tuple[LiveRadio[Any], Any]:
    """The radio and its Mercury modem; `radio.unknown` for a radio that is none, `radio.no_modem` (with its name) for one whose type has no modem."""
    radio = named_radio(ctx, name, id)
    if radio.driver.modem is None:
        raise _no_modem(name, radio)
    return radio, radio.driver.modem


async def _on_the_modem(name: str, radio: LiveRadio[Any], begin: Callable[[], Awaitable[None]]) -> None:
    """The modem's tone or test begun, its refusals passed on with their codes; a modem that is not running (the modem's own `hf.not_running`) is `radio.no_modem` with this radio's name."""
    try:
        await begin()
    except CodedError as e:
        if e.code == "hf.not_running":
            raise _no_modem(name, radio) from None
        raise UserError(f"{name}: {e}", e.code, params=e.params) from None


@command(RadioTune)
async def radio_tune(ctx: Ctx, cmd: RadioTune) -> None:
    """The tune tone on or off on the radio's modem: refused while RX only is ticked, while the modem is not running and while a frame is on the air or the channel is busy."""
    radio, modem = _modem(ctx, cmd.cmd, cmd.radio)
    if not cmd.on:
        await modem.tune_stop()
        return
    if not radio.rtype.can.tune:                     # (the type says what the radio may do: the Dummy HF radio's modem is a speaker, which tunes nothing)
        raise _no_modem(cmd.cmd, radio)
    may_transmit(ctx, cmd.cmd)
    await _on_the_modem(cmd.cmd, radio, modem.tune)


@command(RadioKeyTest)
async def radio_key_test(ctx: Ctx, cmd: RadioKeyTest) -> None:
    radio, modem = _modem(ctx, cmd.cmd, cmd.radio)
    if not radio.rtype.can.key_test:
        raise _no_modem(cmd.cmd, radio)
    may_transmit(ctx, cmd.cmd)
    await _on_the_modem(cmd.cmd, radio, modem.key_test)


@command(RadioScope)
async def radio_scope(ctx: Ctx, cmd: RadioScope) -> None:
    """This page wants the rows of the radio's waterfall, in frames that name the radio, or no more of them. A radio that is none, or whose type has no scope, is refused when it is asked for, never when it is
    stopped."""
    if ctx.scopes is None:
        return
    if not cmd.on:
        ctx.scopes.stop(ctx.conn, cmd.radio)
        return
    radio = named_radio(ctx, cmd.cmd, cmd.radio)
    modem = radio.driver.modem
    if not isinstance(modem, Mercury) or not radio.rtype.can.scope:
        raise UserError(f"{cmd.cmd}: radio {radio.name} has no scope", "radio.no_scope", params={"name": radio.name, "radio": radio.id})
    ctx.scopes.feed(radio.id, modem).ask(ctx.conn, True)


@command(StationRadio)
async def station_radio(ctx: Ctx, cmd: StationRadio) -> None:
    """The radio of the station's messages: a radio that is not removed and can send, or none (the daemon's choice). The call is kept in its normal form, as a message names it (a text that is no call is refused with its code)."""
    try:
        call = normal_name(cmd.call)
    except CallsignError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None
    if cmd.radio is not None and not (radio := named_radio(ctx, cmd.cmd, cmd.radio)).rtype.can.transmit:      # (a radio that only receives is no radio for messages: the page offers it not)
        raise UserError(f"{cmd.cmd}: radio {radio.name} only receives: nothing can be sent on it", "radio.receive_only", params={"name": radio.name, "radio": radio.id})
    if not ctx.ctl.radios.choose(call, cmd.radio) and cmd.radio is not None:            # (a radio the store cannot choose: none is always taken)
        raise no_radio(cmd.cmd, cmd.radio, ctx.ctl.config.radios)
    station = ctx.ctl.stationbook.get(call)
    for key in on_their_way(ctx.ctl.messaging.records(), call if station is None else station.call):
        ctx.hub.changed("messages", key)            # (a message on its way takes the radio chosen from its next attempt: its `radio_now`)


@command(Frequencies)
async def frequencies(ctx: Ctx, cmd: Frequencies) -> None:
    """The page shows the suggested frequencies: the project's list is asked for again if it is time (the service keeps the 15 minutes between two questions)."""
    ctx.ctl.frequencies.wanted()
