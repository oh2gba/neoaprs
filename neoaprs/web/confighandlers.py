"""The commands that change the settings (`set_config`) and run the alert command's Test (`alert_test`). Registered with the dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there.

A page of another device changes every setting but those that name a program or an address the daemon runs or fetches from (`LOCAL_ONLY` of neoaprs/web/access.py), and does not run the Test: the
connection knows whether its page is on this computer itself (`Connection.local`).
"""
import logging
from collections.abc import Iterable

from neoaprs.cli.redaction import shown_value
from neoaprs.config import Config, SettingError

from .access import LOCAL_ONLY
from .configwire import SetConfig
from .dispatch import Ctx, UserError, command
from .messagewire import AlertTest
from .pageerrors import one_line
from .session import Connection

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


@command(SetConfig)
async def set_config(ctx: Ctx, cmd: SetConfig) -> None:
    """Every value is checked before anything is stored (the first wrong one is the answer, with its key), and the settings in force are the base: a key that is left out keeps its value. A page of another
    device that would change one of LOCAL_ONLY is refused, and nothing is stored (a value it sends that is the one in force changes nothing and is let through)."""
    before = after = ctx.ctl.config

    def checked(base: Config) -> Config:
        nonlocal before, after
        before = base
        after = Config.checked(base, cmd.values)
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
