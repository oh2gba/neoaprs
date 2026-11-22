"""Old settings rows that are read as their current equivalents while the new row is absent.

`web/bind` is read until the first save writes `web/network`. The radio rules are applied to a
database by a migration; here they serve only `Config.from_data` without stored radios."""
from collections.abc import Mapping

from .configtypes import boolean

ENTER_KISS = "tnc/enter_kiss"
WEB_BIND = "web/bind"
LOOPBACK_BINDS = ("", "127.0.0.1", "localhost", "::1")


def with_profile(rows: Mapping[str, str]) -> Mapping[str, str]:
    """Return the rows with the Kenwood TNC-2 profile if `tnc/enter_kiss` is on and none is set."""
    try:
        entered = "tnc/profile" not in rows and boolean(rows.get(ENTER_KISS, "false"))
    except ValueError:
        entered = False
    return {**rows, "tnc/profile": "kenwood-tnc2"} if entered else rows


def with_network(rows: Mapping[str, str]) -> Mapping[str, str]:
    """Return the rows with `web/network` true if it has no row and `web/bind` is not loopback."""
    if "web/network" in rows or rows.get(WEB_BIND, "").strip().lower() in LOOPBACK_BINDS:
        return rows
    return {**rows, "web/network": "true"}


def with_radios(rows: Mapping[str, str]) -> Mapping[str, str]:
    """Return the rows with the HF radio on and the FM radio off when `tnc/profile` is `mercury`.

    Applies only when neither `hf/enabled` nor `fm/enabled` has a row."""
    if rows.get("tnc/profile", "").strip() != "mercury" or "hf/enabled" in rows or "fm/enabled" in rows:
        return rows
    return {**{key: value for key, value in rows.items() if key != "tnc/profile"}, "hf/enabled": "true", "fm/enabled": "false"}


def with_legacy(rows: Mapping[str, str]) -> Mapping[str, str]:
    return with_network(with_profile(with_radios(rows)))
