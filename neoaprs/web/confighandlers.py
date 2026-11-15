"""The commands that change the settings (`set_config`) and run the alert command's Test (`alert_test`). Registered with the dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there.

A page of another device changes every setting but those that name a program or an address the daemon runs or fetches from (`LOCAL_ONLY` of neoaprs/web/access.py), and does not run the Test: the
connection knows whether its page is on this computer itself (`Connection.local`).
"""
import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace

from neoaprs.claims import Claims
from neoaprs.cli.redaction import shown_value
from neoaprs.config import BY_KEY, Config, SettingError, radio_key_of
from neoaprs.configradios import FLAT_HOMES, FLAT_KINDS
from neoaprs.radiospec import RadioError, RadioId, RadioSpec, log_name
from neoaprs.radiotype import ResourceKind
from neoaprs.radiotypes import kind_field

from .access import LOCAL_ONLY
from .configwire import SetConfig
from .dispatch import Ctx, UserError, command
from .messagewire import AlertTest
from .pageerrors import one_line
from .session import Connection
from .radioview import devices, holder_name, one_device

log = logging.getLogger("neoaprs.web")
SHOWN_VALUE = 200                    # the longest value a line of the log shows
ALERT_COMMAND = "messages/alert_command"


def shown(key: str, value: str) -> str:
    """A setting's value as the log shows it: a secret only as `(set, N characters)`, an empty value as such, a long one cut."""
    text = one_line(shown_value(key, value), SHOWN_VALUE)
    return text or "(empty)"


def refuse_from_afar(conn: Connection, keys: Iterable[str]) -> None:
    """A SettingError for the first of `keys` that is one of LOCAL_ONLY, when the page is not on this computer itself; nothing for a page that is."""
    if conn.local:
        return
    key = next((k for k in keys if k in LOCAL_ONLY), None)
    if key is not None:
        log.warning("a page of another device (%s) was refused %s: it is set on this computer itself", conn.ip, key)
        raise SettingError(key, "setting.local_only", {}, f"{key}: only a page on the computer NeoAPRS runs on can do this")


def with_radio_values(base: Config, values: Mapping[str, str]) -> Config:
    """The settings with the radios' own values (`radio/<id>/<key>`) put in, each checked by the field of its radio's kind and kept as the program writes it, and `station/main_radio` naming a radio of the
    settings; a SettingError naming the key for the first that is wrong: `radio.unknown` for a radio that is none or removed (or a main radio that is none), `radio.no_setting` for a key its kind has not, and the
    field's own code for a value that is not one of it."""
    own: dict[RadioId, dict[str, str]] = {}
    for key, text in values.items():
        found = radio_key_of(key)
        assert found is not None, key
        id, field = found
        spec = base.radio(id)
        if spec is None or spec.removed:
            raise SettingError(key, "radio.unknown", {"radio": id}, f"{key}: there is no radio {id}")
        if (own_field := kind_field(spec.kind, field)) is None:
            name = log_name(spec, base.radios)
            raise SettingError(key, "radio.no_setting", {"name": name}, f"{key}: the {name} radio has no such setting")
        try:
            value = Config.check_radio(spec, field, text)
        except RadioError as e:
            raise SettingError(key, e.code, e.params, str(e)) from None
        if value != spec.settings.get(field, own_field.default):
            own.setdefault(id, {})[field] = value                # (a value that is the one in force is not written: a default sent back stays the default)
    radios = tuple(replace(spec, settings={**spec.settings, **own[spec.id]}) if spec.id in own else spec for spec in base.radios)
    return replace(base, radios=radios)


def refuse_removed_flat(base: Config, flat: Mapping[str, str]) -> None:
    """`radio.unknown` (the key) for a key of the form of before (`serial/port`, `hf/enabled`, ...) whose radio, 1 or 2, is removed or of another kind, when it would change what the key shows: the view says
    that radio's defaults, and a form that sends back every key it was given (the page of before) still saves. A value that is no value is left to Config.checked, which names what is wrong with it."""
    for key, text in flat.items():
        setting = BY_KEY.get(key)
        if setting is None or setting.attr not in FLAT_HOMES:
            continue
        id = FLAT_HOMES[setting.attr][0]
        spec = base.radio(id)
        if spec is None or (not spec.removed and spec.kind == FLAT_KINDS[id]):
            continue
        try:
            value = Config.parse(key, text)
        except ValueError:
            continue
        if value != getattr(base, setting.attr):
            raise SettingError(key, "radio.unknown", {"radio": id}, f"{key}: there is no radio {id}")


def _holder(spec: RadioSpec, kind: ResourceKind, value: str, after: Config, claims: Claims, moved: set[RadioId]) -> str | None:
    """Who else holds the device once the save is in force, by name: another radio that is on and names it in its settings, else whoever holds it in the station's table now (a radio this save changes is
    judged by its new settings alone, so that two radios can swap their devices in one save); None for nobody."""
    for other in after.enabled_radios:
        if other.id != spec.id and any(one_device(k, kind) and v == value for _, k, v in devices(other)):
            return log_name(other, after.radios)
    held = next((c for c in claims.all() if c.holder != spec.id and c.holder not in moved and c.value == value and one_device(c.kind, kind)), None)
    return None if held is None else holder_name(held.holder, after.radios)


def refuse_held(before: Config, after: Config, claims: Claims, flat: Mapping[str, str] | None = None) -> None:
    """A SettingError (`radio.resource_held`, with the kind of device and the holder's name) when a save names for a radio a device another radio or the GPS receiver holds, or another radio that is on is set
    to (a port, a sound card, a keying line); a device a radio named before the save is not looked at again. The key is the one of the save: a key of the form of before (`flat`, `serial/port`) where it set it."""
    moved = {s.id for s in after.radios if (was := before.radio(s.id)) is None or (was.type, was.enabled, was.removed, dict(was.settings)) != (s.type, s.enabled, s.removed, dict(s.settings))}
    for spec in after.live_radios:
        was = before.radio(spec.id)
        had = set() if was is None else {(key, value) for key, _, value in devices(was)}
        for field, kind, value in devices(spec) if spec.id in moved else ():
            if (field, value) in had or (holder := _holder(spec, kind, value, after, claims, moved)) is None:
                continue
            key = next((k for k in flat or {} if k in BY_KEY and FLAT_HOMES.get(BY_KEY[k].attr) == (spec.id, field)), f"radio/{spec.id}/{field}")
            raise SettingError(key, "radio.resource_held", {"resource": kind, "holder": holder}, f"{key}: that device is in use by {holder}: choose another")


def _main_radio(base: Config, config: Config) -> Config:
    """The settings, refused with `radio.unknown` (the key `station/main_radio`) when the main radio chosen is no radio of them that is not removed; a choice that is the one stored is let through (a form that
    sends back what it was given, after the main radio was removed)."""
    chosen = config.main_choice
    if chosen is not None and chosen != base.main_choice and all(spec.id != chosen for spec in config.live_radios):
        raise SettingError("station/main_radio", "radio.unknown", {"radio": chosen}, f"station/main_radio: there is no radio {chosen}")
    return config


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
        refuse_removed_flat(base, flat)
        after = with_radio_values(Config.checked(base, flat), own)
        if "station/main_radio" in flat:
            _main_radio(base, after)
        refuse_held(base, after, ctx.ctl.radios.claims, flat)
        refuse_from_afar(ctx.conn, base.changed(after))
        return after

    try:
        stored = await ctx.ctl.change_config(checked)
    except SettingError as e:
        raise UserError(f"set_config: {e}", e.code, e.key, e.params) from None
    except ValueError as e:
        raise UserError(f"set_config: {e}") from None
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
        ok, text = await ctx.ctl.alerts.test()
    except SettingError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, e.key, e.params) from None
    except ValueError as e:
        raise UserError(f"{cmd.cmd}: {e}") from None
    ctx.conn.send({"type": "alert_result", "ok": ok, "text": text})
