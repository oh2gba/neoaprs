"""The commands that change the settings (`set_config`) and run the alert command's Test (`alert_test`). Registered with the dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there.

A page of another device changes every setting but those that name a program or an address the daemon runs or fetches from (`LOCAL_ONLY` of neoaprs/web/access.py), and does not run the Test: the
connection knows whether its page is on this computer itself (`Connection.local`).
"""
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from neoaprs.claims import PORT_KINDS, Claims
from neoaprs.cli.redaction import shown_value
from neoaprs.coded import CodedError
from neoaprs.config import BY_KEY, Config, SettingError, radio_key_of
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
SHOWN_VALUE = 200                    # the longest value a line of the log shows
ALERT_COMMAND = "messages/alert_command"


def shown(key: str, value: str) -> str:
    """A setting's value as the log shows it: a secret only as `(set, N characters)`, an empty value as such, a long one cut."""
    text = one_line(shown_value(key, value), SHOWN_VALUE)
    return text or "(empty)"


def local_only(key: str) -> bool:
    """Whether the key is one of LOCAL_ONLY; a radio's own key (`radio/<id>/<key>`) is one as `radio/*/<key>`, whatever the radio."""
    own = radio_key_of(key)
    return key in LOCAL_ONLY or (own is not None and f"radio/*/{own[1]}" in LOCAL_ONLY)


def refuse_from_afar(conn: Connection, keys: Iterable[str]) -> None:
    """A SettingError for the first of `keys` that is one of LOCAL_ONLY (`local_only`), when the page is not on this computer itself; nothing for a page that is."""
    if conn.local:
        return
    key = next((k for k in keys if local_only(k)), None)
    if key is not None:
        log.warning("a page of another device (%s) was refused %s: it is set on this computer itself", conn.ip, key)
        raise SettingError(key, "setting.local_only", {}, f"{key}: only a page on the computer NeoAPRS runs on can do this")


def no_radio(key: str, id: RadioId, specs: Sequence[RadioSpec]) -> SettingError:
    """`radio.unknown` for the key: a radio the settings keep as removed is said to be removed, with its `name` and `removed` 1; any other is "there is no radio N"."""
    removed = removed_name(id, specs)
    if removed is not None:
        return SettingError(key, "radio.unknown", {"radio": id, "name": removed, "removed": 1}, f"{key}: radio {removed} is removed")
    return SettingError(key, "radio.unknown", {"radio": id}, f"{key}: there is no radio {id}")


def radio_of_key(key: str | None) -> RadioId | None:
    """The radio a key of the settings is of (`radio/<id>/<key>`); None for a key of no radio."""
    found = None if key is None else radio_key_of(key)
    return None if found is None else found[0]


def flat_refusal(key: str, config: Config) -> SettingError | None:
    """`setting.unknown` for a key that names a radio's setting without the radio, in the one sentence of configradios.flat_moved, which names where it is now; None for any other key."""
    setting = BY_KEY.get(key)
    moved = None if setting is None else flat_moved(setting.attr, config.radios)
    return None if moved is None else SettingError(key, moved.code, moved.params, f"{key}: {moved}")


def refuse_flat(keys: Iterable[str], config: Config) -> None:
    """The refusal of the first key that names a radio's setting without the radio (flat_refusal)."""
    for key in keys:
        if (error := flat_refusal(key, config)) is not None:
            raise error


def with_radio_values(base: Config, values: Mapping[str, str]) -> Config:
    """The settings with the radios' own values (`radio/<id>/<key>`) put in, each checked by the field of its radio's kind and kept as the program writes it, and `email/radio` naming a radio of the
    settings; a SettingError naming the key for the first that is wrong: `radio.unknown` for a radio that is none or removed (or an email radio that is none), `radio.no_setting` for a key its kind has not, and the
    field's own code for a value that is not one of it."""
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
            raise SettingError(key, "radio.no_setting", {"name": name, "radio": id}, f"{key}: radio {name} has no such setting")
        try:
            value = Config.check_radio(spec, field, text)
        except RadioError as e:
            raise SettingError(key, e.code, e.params, str(e)) from None
        if value != spec.settings.get(field, own_field.default):
            own.setdefault(id, {})[field] = value                # (a value that is the one in force is not written: a default sent back stays the default)
    radios = tuple(replace(spec, settings={**spec.settings, **own[spec.id]}) if spec.id in own else spec for spec in base.radios)
    return replace(base, radios=radios)


def _gps_device(config: Config) -> str:
    """The GPS receiver's serial device as the station's table holds it; "" when the GPS reads none (gps/source is not serial, or its device is a TCP address)."""
    return (claim_value(config.gps_device) or "") if config.gps_source == "serial" else ""


def _same(kind: ResourceKind, a: str, b: str, names: Mapping[int, str]) -> bool:
    """Whether two values name one device: a sound card by its number or by its name is one card (`plughw:1,0` and `plughw:CARD=CODEC,DEV=0` while card 1 is CODEC), as a Mercury holds it (mercuryclaims)."""
    return a == b or (kind == "sound_card" and stable_alsa_id(a, names) == stable_alsa_id(b, names))


def _holder(spec: RadioSpec, kind: ResourceKind, value: str, after: Config, claims: Claims, moved: set[RadioId | None], names: Mapping[int, str]) -> tuple[str, RadioId] | None:
    """Who else holds the device once the save is in force, by name and id (`GPS` and 0 for the GPS receiver): another radio that is on and names it in its settings, the GPS receiver that reads it, else whoever
    holds it in the station's table now (a radio, or the GPS, this save changes is judged by its new settings alone, so that two radios can swap their devices in one save); None for nobody. `names` are ALSA's
    names of the sound cards (alsa_card_names), so that a card named by its number and by its name is one card."""
    for other in after.enabled_radios:
        if other.id != spec.id and any(one_device(k, kind) and _same(kind, v, value, names) for _, k, v in devices(other)):
            return log_name(other, after.radios), other.id
    if one_device(kind, "gps") and value == _gps_device(after):
        return "GPS", 0
    held = next((c for c in claims.all() if c.holder != spec.id and c.holder not in moved and _same(kind, c.value, value, names) and one_device(c.kind, kind)), None)
    return None if held is None else (holder_name(held.holder, after.radios), holder_id(held.holder, after.radios))


def refuse_held(before: Config, after: Config, claims: Claims) -> None:
    """A SettingError (`radio.resource_held`, with the kind of device and the holder's name) when a save names for a radio a device another radio or the GPS receiver holds, or another radio that is on is set
    to (a port, a sound card, a keying line), or the GPS receiver reads; a device a radio named before the save is not looked at again. The key is the radio's own (`radio/<id>/<key>`); a new device of the GPS
    receiver that a radio is set to or holds is refused under `gps/device`, with that radio as the holder."""
    moved: set[RadioId | None] = {s.id for s in after.radios if (was := before.radio(s.id)) is None or (was.type, was.enabled, was.removed, dict(was.settings)) != (s.type, s.enabled, s.removed, dict(s.settings))}
    if (gps := _gps_device(after)) != _gps_device(before):
        moved.add(None)                                                  # (the GPS receiver this save changes: judged by its new device alone)
        if gps and (found := _gps_holder(gps, after, claims, moved)) is not None:
            raise SettingError("gps/device", "radio.resource_held", {"resource": "gps", "holder": found[0], "held_by": found[1]}, f"gps/device: that device is in use by {found[0]}: choose another")
    names = alsa_card_names()                                            # (read once: a sound card is one card by its number or its name)
    for spec in after.live_radios:
        was = before.radio(spec.id)
        had = set() if was is None else {(key, value) for key, _, value in devices(was)}
        for field, kind, value in devices(spec) if spec.id in moved else ():
            if (field, value) in had or (found := _holder(spec, kind, value, after, claims, moved, names)) is None:
                continue
            holder, held_by = found
            key = f"radio/{spec.id}/{field}"
            by = "the GPS receiver" if held_by == 0 else f"radio {holder}"      # (the GPS receiver holds it as 0)
            raise SettingError(key, "radio.resource_held", {"resource": kind, "holder": holder, "held_by": held_by}, f"{key}: the device is in use by {by}: choose another")


def _gps_holder(gps: str, after: Config, claims: Claims, moved: set[RadioId | None]) -> tuple[str, RadioId] | None:
    """The radio that is on and is set to the GPS receiver's new device, else the one that holds it in the station's table now and that this save does not change; None for none."""
    for other in after.enabled_radios:
        if any(one_device(k, "gps") and v == gps for _, k, v in devices(other)):
            return log_name(other, after.radios), other.id
    held = next((c for c in claims.all() if c.holder is not None and c.holder not in moved and c.value == gps and c.kind in PORT_KINDS), None)
    return None if held is None or held.holder is None else (holder_name(held.holder, after.radios), holder_id(held.holder, after.radios))


def _own_value(config: Config, key: str) -> str | None:
    """The radio's own setting the key names (`radio/<id>/<key>`) as these settings have it, its kind's default where it has none of its own; None for a radio they do not have."""
    id, field = radio_key_of(key) or (0, "")
    spec = config.radio(id)
    return None if spec is None else spec.settings.get(field, getattr(kind_field(spec.kind, field), "default", None))


CHOICES_OF_A_RADIO = {"email/radio": "email_choice"}      # the station's settings that name one radio by its id, each with its field of Config


def _name_radios(base: Config, config: Config, keys: Iterable[str]) -> None:
    """Refused with `radio.unknown` (under its key, the first of CHOICES_OF_A_RADIO among `keys`) when a radio chosen (the email radio) is no radio of the settings that is not removed; a
    choice that is the one stored is let through (a form that sends back what it was given, after that radio was removed)."""
    sent = set(keys)
    for key, attr in CHOICES_OF_A_RADIO.items():
        chosen = getattr(config, attr)
        if key in sent and chosen is not None and chosen != getattr(base, attr) and all(spec.id != chosen for spec in config.live_radios):
            raise no_radio(key, chosen, config.radios)


@command(SetConfig)
async def set_config(ctx: Ctx, cmd: SetConfig) -> None:
    """Every value is checked before anything is stored (the first wrong one is the answer, with its key), and the settings in force are the base: a key that is left out keeps its value. A radio's own setting
    (`radio/<id>/<key>`) is put into its radio and stored with the rest in one write. A page of another device that would change one of LOCAL_ONLY is refused, and nothing is stored (a value it sends that is the
    one in force changes nothing and is let through)."""
    before = after = ctx.ctl.config
    flat = {key: text for key, text in cmd.values.items() if radio_key_of(key) is None}
    own = {key: text for key, text in cmd.values.items() if radio_key_of(key) is not None}

    def checked(base: Config) -> Config:
        nonlocal before, after
        before = base
        refuse_flat(flat, base)
        after = with_radio_values(Config.checked(base, flat), own)
        _name_radios(base, after, flat)
        refuse_held(base, after, ctx.ctl.radios.claims)
        refuse_from_afar(ctx.conn, [*base.changed(after), *(key for key in own if _own_value(base, key) != _own_value(after, key))])
        return after

    try:
        stored = await ctx.ctl.change_config(checked)
    except SettingError as e:
        if e.code == "radio.last_enabled" and (id := radio_of_key(e.key)) is not None:          # (the radio that would be switched off, by its id: the words are R1's and name none)
            raise UserError("set_config: " + str(e), "radio.last_enabled", e.key, {**e.params, "radio": id}) from None
        raise UserError(f"set_config: {e}", e.code, e.key, e.params) from None
    except ValueError as e:
        raise UserError(f"set_config: {e}", "failed") from None          # (a check without a code: nothing the page lets the operator mend; the log has it)
    if not stored:
        raise UserError("set_config: the settings could not be stored (the database would not take them); nothing changed", "setting.not_stored")
    old, new = before.to_data(), after.to_data()
    for key in before.changed(after):
        log.info("settings: %s = %s (was %s)", key, shown(key, new[key]), shown(key, old[key]))
    for key in own:
        id, field = radio_key_of(key) or (0, "")
        was, now = before.radio(id), after.radio(id)
        if was is not None and now is not None and was.settings.get(field) != now.settings.get(field):
            default = getattr(kind_field(was.kind, field), "default", "")
            log.info("settings: %s = %s (was %s)", key, shown(key, now.settings.get(field, default)), shown(key, was.settings.get(field, default)))


@command(AlertTest)
async def alert_test(ctx: Ctx, cmd: AlertTest) -> None:
    """The saved alert command, run at once (neoaprs/services/alerts.py); only for a page on this computer itself."""
    try:
        refuse_from_afar(ctx.conn, [ALERT_COMMAND])
        outcome = await ctx.ctl.alerts.test()
    except SettingError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, e.key, e.params) from None
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, None, e.params) from None
    ctx.conn.send({"type": "alert_result", "ok": outcome.ok, "outcome": outcome.kind, "status": outcome.status, "seconds": float(ctx.ctl.alerts.timeout_sec), "line": outcome.first_line if outcome.kind == "exit" else ""})
