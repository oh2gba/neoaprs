"""Command handlers for `set_config` and `alert_test`.

A page on another device may change every setting except those in `LOCAL_ONLY` (access.py) and may
not run the alert test; `Connection.local` says whether the page is on this computer.
"""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from neoaprs.claims import PORT_KINDS, Claims
from neoaprs.cli.redaction import shown_value
from neoaprs import pairsetting
from neoaprs.coded import CodedError
from neoaprs.config import BY_KEY, EMAIL_RADIO, Config, SettingError, radio_key_of
from neoaprs.configlayers import MASK, MASKED_KEYS
from neoaprs.configradios import flat_moved
from neoaprs.mercurycards import stable_alsa_id
from neoaprs.mercuryhelper import alsa_card_names
from neoaprs.radiospec import RadioError, RadioId, RadioSpec, log_name
from neoaprs.radiotype import ResourceKind
from neoaprs.radiotypes import kind_field
from neoaprs.serialprobe import claim_value

from .access import LOCAL_ONLY
from .configwire import SetConfig
from .dispatch import Ctx, UserError, command
from .messagewire import AlertTest
from .pageerrors import one_line
from .session import Connection
from .radioview import devices, holder_id, holder_name, one_device, removed_name

log = logging.getLogger("neoaprs.web")
SHOWN_VALUE = 200  # longest value a log line shows
ALERT_COMMAND = "messages/alert_command"


def shown(key: str, value: str) -> str:
    """Return a value as logged.

    A secret is shown as `(set, N characters)`, an empty value as "(empty)", a long one cut.
    """
    text = one_line(shown_value(key, value), SHOWN_VALUE)
    return text or "(empty)"


def local_only(key: str) -> bool:
    """Return True if the key is in LOCAL_ONLY; `radio/<id>/<key>` matches `radio/*/<key>`."""
    own = radio_key_of(key)
    return key in LOCAL_ONLY or (own is not None and f"radio/*/{own[1]}" in LOCAL_ONLY)


def refuse_from_afar(conn: Connection, keys: Iterable[str]) -> None:
    """Raise SettingError for the first LOCAL_ONLY key when the page is not on this computer."""
    if conn.local:
        return
    key = next((k for k in keys if local_only(k)), None)
    if key is not None:
        log.warning("a page of another device (%s) was refused %s: it is set on this computer itself", conn.ip, key)
        raise SettingError(
            key, "setting.local_only", {}, f"{key}: only a page on the computer NeoAPRS runs on can do this"
        )


def no_radio(key: str, id: RadioId, specs: Sequence[RadioSpec]) -> SettingError:
    """Return `radio.unknown` for the key.

    A removed radio is reported as removed with its `name`, else as "there is no radio N".
    """
    removed = removed_name(id, specs)
    if removed is not None:
        return SettingError(
            key, "radio.unknown", {"radio": id, "name": removed, "removed": 1}, f"{key}: radio {removed} is removed"
        )
    return SettingError(key, "radio.unknown", {"radio": id}, f"{key}: there is no radio {id}")


def radio_of_key(key: str | None) -> RadioId | None:
    """Return the radio id of a `radio/<id>/<key>` key, or None."""
    found = None if key is None else radio_key_of(key)
    return None if found is None else found[0]


def flat_refusal(key: str, config: Config) -> SettingError | None:
    """Return `setting.unknown` for a key naming a radio setting without the radio, else None."""
    setting = BY_KEY.get(key)
    moved = None if setting is None else flat_moved(setting.attr, config.radios)
    return None if moved is None else SettingError(key, moved.code, moved.params, f"{key}: {moved}")


def refuse_flat(keys: Iterable[str], config: Config) -> None:
    """Raise the refusal for the first key that names a radio's setting without the radio."""
    for key in keys:
        if (error := flat_refusal(key, config)) is not None:
            raise error


def with_radio_values(base: Config, values: Mapping[str, str]) -> Config:
    """Return the settings with the radios' own values put in, each checked by its kind's field.

    Raise SettingError naming the first wrong key.
    """
    own: dict[RadioId, dict[str, str]] = {}
    for key, text in values.items():
        found = radio_key_of(key)
        assert found is not None, key
        id, field = found
        spec = base.radio(id)
        if spec is None or spec.removed:
            raise no_radio(key, id, base.radios)
        if (own_field := kind_field(spec.kind, field)) is None:
            name = log_name(spec, base.radios)
            raise SettingError(
                key, "radio.no_setting", {"name": name, "radio": id}, f"{key}: radio {name} has no such setting"
            )
        try:
            value = Config.check_radio(spec, field, text)
        except RadioError as e:
            raise SettingError(key, e.code, e.params, str(e)) from None
        if value != spec.settings.get(field, own_field.default):
            # A value equal to the one in force is not written, so a default stays default.
            own.setdefault(id, {})[field] = value
    radios = tuple(
        replace(spec, settings={**spec.settings, **own[spec.id]}) if spec.id in own else spec for spec in base.radios
    )
    return replace(base, radios=radios)


def _gps_device(config: Config) -> str:
    """Return the GPS serial device as the resource table has it.

    Empty if the GPS is not serial or uses a TCP address.
    """
    return (claim_value(config.gps_device) or "") if config.gps_source == "serial" else ""


def _same(kind: ResourceKind, a: str, b: str, names: Mapping[int, str]) -> bool:
    """Return True if two values name one device; a sound card by number or name is one card."""
    return a == b or (kind == "sound_card" and stable_alsa_id(a, names) == stable_alsa_id(b, names))


def _holder(
    spec: RadioSpec,
    kind: ResourceKind,
    value: str,
    after: Config,
    claims: Claims,
    moved: set[RadioId | None],
    names: Mapping[int, str],
) -> tuple[str, RadioId] | None:
    """Return (name, id) of who else holds the device once the save applies (`GPS`, 0), else None.

    A radio or GPS changed by this save is judged by its new settings alone, so radios can swap devices.
    """
    for other in after.enabled_radios:
        if other.id != spec.id and any(
            one_device(k, kind) and _same(kind, v, value, names) for _, k, v in devices(other)
        ):
            return log_name(other, after.radios), other.id
    if one_device(kind, "gps") and value == _gps_device(after):
        return "GPS", 0
    held = next(
        (
            c
            for c in claims.all()
            if c.holder != spec.id
            and c.holder not in moved
            and _same(kind, c.value, value, names)
            and one_device(c.kind, kind)
        ),
        None,
    )
    return None if held is None else (holder_name(held.holder, after.radios), holder_id(held.holder, after.radios))


def refuse_held(before: Config, after: Config, claims: Claims) -> None:
    """Raise `radio.resource_held` when a save gives a radio a device another holds.

    A device a radio already named before the save is not rechecked.
    """
    moved: set[RadioId | None] = {
        s.id
        for s in after.radios
        if (was := before.radio(s.id)) is None
        or (was.type, was.enabled, was.removed, dict(was.settings)) != (s.type, s.enabled, s.removed, dict(s.settings))
    }
    if (gps := _gps_device(after)) != _gps_device(before):
        # The GPS is changed by this save: judged by its new device alone.
        moved.add(None)
        if gps and (found := _gps_holder(gps, after, claims, moved)) is not None:
            raise SettingError(
                "gps/device",
                "radio.resource_held",
                {"resource": "gps", "holder": found[0], "held_by": found[1]},
                f"gps/device: that device is in use by {found[0]}: choose another",
            )
    names = alsa_card_names()  # read once: a sound card is one card by number or name
    for spec in after.live_radios:
        was = before.radio(spec.id)
        had = set() if was is None else {(key, value) for key, _, value in devices(was)}
        for field, kind, value in devices(spec) if spec.id in moved else ():
            if (field, value) in had or (found := _holder(spec, kind, value, after, claims, moved, names)) is None:
                continue
            holder, held_by = found
            key = f"radio/{spec.id}/{field}"
            by = "the GPS receiver" if held_by == 0 else f"radio {holder}"  # held_by 0 is the GPS receiver
            raise SettingError(
                key,
                "radio.resource_held",
                {"resource": kind, "holder": holder, "held_by": held_by},
                f"{key}: the device is in use by {by}: choose another",
            )


def _gps_holder(gps: str, after: Config, claims: Claims, moved: set[RadioId | None]) -> tuple[str, RadioId] | None:
    """Return the enabled radio set to the GPS's new device.

    Otherwise return the unchanged holder in the resource table, else None.
    """
    for other in after.enabled_radios:
        if any(one_device(k, "gps") and v == gps for _, k, v in devices(other)):
            return log_name(other, after.radios), other.id
    held = next(
        (
            c
            for c in claims.all()
            if c.holder is not None and c.holder not in moved and c.value == gps and c.kind in PORT_KINDS
        ),
        None,
    )
    return (
        None
        if held is None or held.holder is None
        else (holder_name(held.holder, after.radios), holder_id(held.holder, after.radios))
    )


def _own_value(config: Config, key: str) -> str | None:
    """Return the radio setting the key names, or None for an unknown radio.

    A missing setting takes its kind's default.
    """
    id, field = radio_key_of(key) or (0, "")
    spec = config.radio(id)
    return None if spec is None else spec.settings.get(field, getattr(kind_field(spec.kind, field), "default", None))


def split_values(values: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Split a save's values into station, radio and pair keys.

    Unknown keys stay with the station settings, which refuse them.
    """
    flat: dict[str, str] = {}
    own: dict[str, str] = {}
    pairs: dict[str, str] = {}
    for key, text in values.items():
        if key in MASKED_KEYS and text == MASK:
            continue  # the page sent back what it was shown: the key stays
        (own if radio_key_of(key) is not None else pairs if pairsetting.pair_key_of(key) is not None else flat)[key] = (
            text
        )
    return flat, own, pairs


def with_pairs(base: Config, after: Config, pairs: Mapping[str, str], flat: Mapping[str, str]) -> Config:
    """Return the settings with the pairs' values put in; raise SettingError on the first wrong key."""
    for key in pairs:
        for id in (pairsetting.pair_key_of(key) or ())[:2]:
            if (spec := base.radio(id)) is None or spec.removed:
                raise no_radio(key, id, base.radios)
    try:
        config = replace(
            after,
            pairs=pairsetting.with_pair_values(
                after.station_call, after.radios, after.pairs, pairs, was_call=base.station_call
            ),
        )
        if (
            "station/call" in flat
            and (refusal := pairsetting.call_refusal(config.station_call, config.pairs)) is not None
        ):
            raise refusal
    except pairsetting.PairError as e:
        raise SettingError(e.key, e.code, e.params, str(e)) from None
    return config


def log_pair_changes(before: Config, after: Config) -> None:
    """Log the pair rows a save changed."""
    was = pairsetting.rows_of(before.pairs)
    for key, text in pairsetting.changed_rows(before.pairs, after.pairs).items():
        log.info(
            "settings: %s = %s (was %s)", key, shown(key, text), shown(key, was.get(key, pairsetting.default_of(key)))
        )


# Station settings that name one radio by id, each with its Config field.
CHOICES_OF_A_RADIO = {EMAIL_RADIO: "email_choice"}


def _name_radios(base: Config, config: Config, keys: Iterable[str]) -> None:
    """Raise `radio.unknown` when a chosen radio is not live; the stored choice always passes."""
    sent = set(keys)
    for key, attr in CHOICES_OF_A_RADIO.items():
        chosen = getattr(config, attr)
        if (
            key in sent
            and chosen is not None
            and chosen != getattr(base, attr)
            and all(spec.id != chosen for spec in config.live_radios)
        ):
            raise no_radio(key, chosen, config.radios)


@command(SetConfig)
async def set_config(ctx: Ctx, cmd: SetConfig) -> None:
    # Every value is checked before anything is stored, then all is stored in one write.
    # A LOCAL_ONLY key from another device is refused; a value equal to the one in force passes.
    before = after = ctx.ctl.config
    flat, own, pairs = split_values(cmd.values)

    def checked(base: Config) -> Config:
        nonlocal before, after
        before = base
        refuse_flat(flat, base)
        after = with_pairs(base, with_radio_values(Config.checked(base, flat), own), pairs, flat)
        _name_radios(base, after, flat)
        refuse_held(base, after, ctx.ctl.radios.claims)
        refuse_from_afar(
            ctx.conn,
            [
                *base.changed(after),
                *(key for key in own if _own_value(base, key) != _own_value(after, key)),
                *pairsetting.changed_rows(base.pairs, after.pairs),
            ],
        )
        return after

    try:
        stored = await ctx.ctl.change_config(checked)
    except SettingError as e:
        # The radio that would be switched off is named by id; the sentence names none.
        if e.code == "radio.last_enabled" and (id := radio_of_key(e.key)) is not None:
            raise UserError("set_config: " + str(e), "radio.last_enabled", e.key, {**e.params, "radio": id}) from None
        raise UserError(f"set_config: {e}", e.code, e.key, e.params) from None
    except ValueError as e:
        # A check without a code: nothing the operator can mend; the log has it.
        raise UserError(f"set_config: {e}", "failed") from None
    if not stored:
        raise UserError(
            "set_config: the settings could not be stored (the database would not take them); nothing changed",
            "setting.not_stored",
        )
    old, new = before.to_data(), after.to_data()
    for key in before.changed(after):
        log.info("settings: %s = %s (was %s)", key, shown(key, new[key]), shown(key, old[key]))
    for key in own:
        id, field = radio_key_of(key) or (0, "")
        was, now = before.radio(id), after.radio(id)
        if was is not None and now is not None and was.settings.get(field) != now.settings.get(field):
            default = getattr(kind_field(was.kind, field), "default", "")
            log.info(
                "settings: %s = %s (was %s)",
                key,
                shown(key, now.settings.get(field, default)),
                shown(key, was.settings.get(field, default)),
            )
    log_pair_changes(before, after)
    if "map/ships_key" in flat:
        ctx.ctl.layers.key_saved()
    if cmd.id is not None:
        ctx.conn.send({"type": "saved", "id": cmd.id})


@command(AlertTest)
async def alert_test(ctx: Ctx, cmd: AlertTest) -> None:
    # Runs the saved alert command at once; only for a page on this computer.
    try:
        refuse_from_afar(ctx.conn, [ALERT_COMMAND])
        outcome = await ctx.ctl.alerts.test()
    except SettingError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, e.key, e.params) from None
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, None, e.params) from None
    ctx.conn.send(
        {
            "type": "alert_result",
            "ok": outcome.ok,
            "outcome": outcome.kind,
            "status": outcome.status,
            "seconds": float(ctx.ctl.alerts.timeout_sec),
            "line": outcome.first_line if outcome.kind == "exit" else "",
        }
    )
