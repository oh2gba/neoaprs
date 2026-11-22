"""Command handlers for the commands that name a radio, and the suggested frequencies.

`named_radio` and `sending_radio` give the refusals shared by every command that names a radio.
A refusal that names a radio also carries its id (`radio`).
"""
import logging
import re
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from neoaprs.callsign import CallsignError, normal_name
from neoaprs.coded import CodedError, code_of
from neoaprs.config import can_transmit
from neoaprs.radioregistry import LiveRadio
from neoaprs.direwolfmodem import DirewolfModem
from neoaprs.mercurymodem import Mercury
from neoaprs.radiospec import KIND_WORDS, RadioError, RadioId, RadioSpec, live, log_name
from neoaprs.radiotype import RadioTypeError

from .dispatch import Ctx, UserError, command
from .radiowire import RadioAdd, RadioChange, RadioKeyTest, RadioLevel, RadioRemove, RadioScope, RadioTune, StationRadio
from .radioview import removed_name
from .tncwire import Frequencies
from .views import on_their_way

log = logging.getLogger("neoaprs.web")

# What a radio with no name of its own is called, case folded ("fm", "mercury 2").
LABEL = re.compile("(?:" + "|".join(re.escape(word.casefold()) for word in KIND_WORDS.values()) + ")(?: [0-9]+)?")


@contextmanager
def radio_refused(name: str, id: RadioId | None = None, specs: Sequence[RadioSpec] = ()) -> Iterator[None]:
    """Turn RadioError and RadioTypeError into the page's error, with code and values.

    An error about the radio `id` carries the id; a removed radio (in `specs`) is said to be removed.
    """
    try:
        yield
    except RadioError as e:
        if e.code == "radio.name_taken":
            raise UserError(f"{name}: the name {e.params['name']!r} is another radio's already: give this one another", "radio.name_taken", None, e.params) from None
        if id is None:
            raise UserError(f"{name}: {e}", e.code, None, e.params) from None
        if e.code == "radio.type_kind":  # the CLI sentence names the key and type key typed
            raise UserError(f"{name}: radio {e.params['name']} takes only a type of its own kind ({e.params['kind']})", "radio.type_kind", None, {**e.params, "radio": id}) from None
        if e.code == "radio.last_enabled":
            raise UserError(name + ": " + str(e), "radio.last_enabled", None, {**e.params, "radio": id}) from None
        if e.code == "radio.unknown" and removed_name(id, specs) is not None:
            raise no_radio(name, id, specs) from None
        raise UserError(f"{name}: {e}", e.code, None, e.params) from None
    except RadioTypeError as e:
        raise UserError(f"{name}: {e}", e.code, None, e.params) from None


def no_radio(name: str, id: RadioId, specs: Sequence[RadioSpec]) -> UserError:
    """Return `radio.unknown` for the id, saying so when the radio is removed."""
    removed = removed_name(id, specs)
    if removed is not None:
        return UserError(f"{name}: radio {removed} is removed", "radio.unknown", params={"radio": id, "name": removed, "removed": 1})
    return UserError(f"{name}: there is no radio {id}", "radio.unknown", params={"radio": id})


def named_radio(ctx: Ctx, name: str, id: RadioId) -> LiveRadio[Any]:
    """Return the radio of the id that is not removed; raise `radio.unknown` otherwise."""
    radio = ctx.ctl.radios.get(id)
    if radio is None:
        raise no_radio(name, id, ctx.ctl.config.radios)
    return radio


def sending_radio(ctx: Ctx, name: str, id: RadioId | None) -> RadioId | None:
    """Check the radio a sending command names and return its id, or None for the default radios.

    Raise a `radio.*` refusal for the named radio; with none named, `transmit.off` or `radio.none`.
    """
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
    """Raise `setting.not_stored` when the change was not stored; the reason is in the log."""
    if not done:
        raise UserError(f"{name}: the radio could not be stored; nothing changed", "setting.not_stored")


def refuse_label(name: str, typed: str | None, specs: Sequence[RadioSpec], own: RadioId | None) -> None:
    """Refuse a name shaped like a default radio label ("FM", "mercury 2").

    Raise `radio.name_taken` if another radio has it now, else `radio.name_label`.
    """
    wanted = (typed or "").strip()
    if not LABEL.fullmatch(wanted.casefold()) or any(s.id == own and s.name.casefold() == wanted.casefold() for s in specs):
        return
    other = next((s for s in live(specs) if s.id != own and not s.name and log_name(s, specs).casefold() == wanted.casefold()), None)
    if other is not None:
        raise UserError(f"{name}: the name {wanted!r} is another radio's already: give this one another", "radio.name_taken", params={"name": wanted, "radio": other.id})
    raise UserError(f"{name}: the name {wanted!r} is how a radio without a name of its own is called: give this one another", "radio.name_label", params={"name": wanted})


@command(RadioAdd)
async def radio_add(ctx: Ctx, cmd: RadioAdd) -> None:
    # The row follows in the next `radios` patch; the page waits for it.
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
    # Only the fields the command gives are changed.
    columns = {column: value for column in ("name", "type", "enabled", "position") if (value := getattr(cmd, column)) is not None}
    refuse_label(cmd.cmd, cmd.name, ctx.ctl.config.radios, cmd.radio)
    with radio_refused(cmd.cmd, cmd.radio, ctx.ctl.config.radios):
        _stored(cmd.cmd, await ctx.ctl.change_radio(cmd.radio, **columns))


def may_transmit(ctx: Ctx, name: str) -> None:
    """Apply the transmit interlock: RX only and a usable call.

    A tone without identification is a transmission too.
    """
    config = ctx.ctl.config
    if not config.station_transmit or config.listens_only:
        raise UserError(f"{name}: RX only: nothing is sent", "transmit.off")
    if reason := can_transmit(config):
        why, params = code_of(reason)
        # the page words it from `why`
        raise UserError(f"{name}: nothing is sent: {reason}", "transmit.call", params={"why": why, **params})


def _no_modem(name: str, radio: LiveRadio[Any]) -> UserError:
    return UserError(f"{name}: radio {radio.name} has no modem running", "radio.no_modem", params={"name": radio.name, "radio": radio.id})


def _modem(ctx: Ctx, name: str, id: RadioId) -> tuple[LiveRadio[Any], Any]:
    """Return the radio and its modem; raise `radio.unknown` or `radio.no_modem`."""
    radio = named_radio(ctx, name, id)
    if radio.driver.modem is None:
        raise _no_modem(name, radio)
    return radio, radio.driver.modem


async def _on_the_modem(name: str, radio: LiveRadio[Any], begin: Callable[[], Awaitable[None]]) -> None:
    """Begin the modem's tone or test, passing on refusal codes.

    The modem's `hf.not_running` becomes `radio.no_modem`.
    """
    try:
        await begin()
    except CodedError as e:
        if e.code == "hf.not_running":
            raise _no_modem(name, radio) from None
        raise UserError(f"{name}: {e}", e.code, params=e.params) from None


@command(RadioTune)
async def radio_tune(ctx: Ctx, cmd: RadioTune) -> None:
    radio, modem = _modem(ctx, cmd.cmd, cmd.radio)
    if not cmd.on:
        await modem.tune_stop()
        return
    # the Dummy HF radio's modem is a speaker, which tunes nothing
    if not radio.rtype.can.tune:
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
    # Stopping is never refused; starting is refused for an unknown radio or a type without a scope.
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


@command(RadioLevel)
async def radio_level(ctx: Ctx, cmd: RadioLevel) -> None:
    # Stopping is never refused.
    if ctx.levels is None:
        return
    if not cmd.on:
        ctx.levels.stop(ctx.conn, cmd.radio)
        return
    radio = named_radio(ctx, cmd.cmd, cmd.radio)
    modem = radio.driver.modem
    if not isinstance(modem, DirewolfModem) or not radio.rtype.can.rx_level:
        raise _no_modem(cmd.cmd, radio)
    ctx.levels.ask(ctx.conn, radio.id, modem)


@command(StationRadio)
async def station_radio(ctx: Ctx, cmd: StationRadio) -> None:
    # None leaves the choice to the daemon.
    try:
        call = normal_name(cmd.call)
    except CallsignError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None
    # a receive-only radio is no radio for messages
    if cmd.radio is not None and not (radio := named_radio(ctx, cmd.cmd, cmd.radio)).rtype.can.transmit:
        raise UserError(f"{cmd.cmd}: radio {radio.name} only receives: nothing can be sent on it", "radio.receive_only", params={"name": radio.name, "radio": radio.id})
    if not ctx.ctl.radios.choose(call, cmd.radio) and cmd.radio is not None:  # None (daemon's choice) always succeeds
        raise no_radio(cmd.cmd, cmd.radio, ctx.ctl.config.radios)
    station = ctx.ctl.stationbook.get(call)
    for key in on_their_way(ctx.ctl.messaging.records(), call if station is None else station.call):
        ctx.hub.changed("messages", key)


@command(Frequencies)
async def frequencies(ctx: Ctx, cmd: Frequencies) -> None:
    # The service itself limits how often the list is asked for.
    ctx.ctl.frequencies.wanted()
