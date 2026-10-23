"""Rows of the settings table that are read as another setting while that one has no row of its own, so that a database keeps meaning what it meant: `tnc/enter_kiss` (true selects the Kenwood TNC-2
profile) and `web/bind` (an address other than the loopback means `web/network` is on). The first save writes the setting itself, and from then on the row is not looked at."""
from collections.abc import Mapping

from .configtypes import boolean

ENTER_KISS = "tnc/enter_kiss"                                          # the radio is put in KISS with KISS ON and RESTART
WEB_BIND = "web/bind"                                                  # the address the page listens on
LOOPBACK_BINDS = ("", "127.0.0.1", "localhost", "::1")


def with_profile(rows: Mapping[str, str]) -> Mapping[str, str]:
    """The rows with the profile that `tnc/enter_kiss` implies: no `tnc/profile` row and a `tnc/enter_kiss` row that says true mean entering KISS with KISS ON and RESTART (the Kenwood TNC-2
    profile); false, or no row at all, is the default profile, which sends nothing."""
    try:
        entered = "tnc/profile" not in rows and boolean(rows.get(ENTER_KISS, "false"))
    except ValueError:
        entered = False
    return {**rows, "tnc/profile": "kenwood-tnc2"} if entered else rows


def with_network(rows: Mapping[str, str]) -> Mapping[str, str]:
    """The rows with `web/network` true when there is none and `web/bind` names anything but the loopback."""
    if "web/network" in rows or rows.get(WEB_BIND, "").strip().lower() in LOOPBACK_BINDS:
        return rows
    return {**rows, "web/network": "true"}


def with_legacy(rows: Mapping[str, str]) -> Mapping[str, str]:
    return with_network(with_profile(rows))
