"""The switch NEOAPRS_NO_DEVICES=1: a daemon that opens no real device and talks to no real service.

Under the switch no real device is opened and no connection leaves this computer.
"""

import errno
import ipaddress
import logging
import os
import urllib.request
from urllib.parse import urlsplit

from . import direwolf, mercury
from .tncprofile import names_tcp

log = logging.getLogger("neoaprs.nodevices")

ENV = "NEOAPRS_NO_DEVICES"
# every other value, a typing slip included, sets the switch
OFF_VALUES = frozenset({"", "0"})
# names that are this computer without a lookup
LOCAL_NAMES = frozenset({"", "localhost"})
TOLD_MAX = 500  # doors remembered as told; the memory restarts beyond that

_told: set[str] = set()


def sets(value: str | None) -> bool:
    return (value or "").strip() not in OFF_VALUES


def on() -> bool:
    return sets(os.environ.get(ENV))


def announce() -> None:
    if on():
        log.info(
            "%s is set: no serial port, Bluetooth device or sound card is opened, the Mercury modem is not started, nothing but this computer is connected to, and the default alert command is not run "
            "(the variable is %r: every value but an empty one and 0 sets it)",
            ENV,
            os.environ.get(ENV, ""),
        )


def refused(door: str, level: int = logging.WARNING) -> bool:
    """Return whether the switch shuts this door; log it the first time."""
    if not on():
        return False
    if door not in _told:
        if len(_told) >= TOLD_MAX:
            _told.clear()
        _told.add(door)
        log.log(level, "%s is set: %s", ENV, door)
    return True


def this_computer(host: str) -> bool:
    """Return whether `host` is localhost or a loopback address (no lookup)."""
    name = host.strip().strip("[]").lower().rstrip(".")
    if name in LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    return (mapped or address).is_loopback


def host_refused(host: str, what: str = "", level: int = logging.WARNING) -> bool:
    return (
        on() and not this_computer(host) and refused(f"no connection to {host}" + (f" ({what})" if what else ""), level)
    )


def check_host(host: str, what: str = "", level: int = logging.WARNING) -> None:
    if host_refused(host, what, level):
        raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))


def url_refused(url: str, what: str = "", level: int = logging.INFO) -> bool:
    if not on():
        return False
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        # an unreadable address is not shown to be this computer
        return refused(f"no connection to {url!r}", level)
    return host is not None and host_refused(host, what, level)


def check_url(url: str, what: str = "", level: int = logging.INFO) -> None:
    if url_refused(url, what, level):
        raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))


def direct() -> list[urllib.request.BaseHandler]:
    """Return extra opener handlers: under the switch one without a proxy."""
    return [urllib.request.ProxyHandler({})] if on() else []


def modem_port(number: int) -> bool:
    if (
        number in (direwolf.OWN_PORT, direwolf.OWN_AGW_PORT, mercury.OWN_UI_PORT)
        or direwolf.FIRST_PORT <= number < direwolf.FIRST_PORT + direwolf.PORT_TRIES
    ):
        return True
    return any(
        mercury.BROADCAST_PORT <= number - offset < mercury.BROADCAST_PORT + mercury.PORT_TRIES
        for offset in (0, mercury.CONTROL_OFFSET, mercury.CONTROL_OFFSET + 1, mercury.UI_OFFSET)
    )


def _tcp_port_refused(port: str, level: int) -> bool:
    try:
        number = urlsplit(port).port
    except ValueError:
        number = None
    return (number is None or modem_port(number)) and refused(
        f"the port {port} is not opened: a modem of this computer may listen there", level
    )


def check_port(path: str, level: int = logging.WARNING) -> None:
    """Raise FileNotFoundError for a refused device, ConnectionRefusedError for other ports."""
    if not on():
        return
    port = path.strip()
    if names_tcp(port):
        check_url(port, "a KISS TCP port", level)
        if _tcp_port_refused(port, level):
            raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
    elif "://" in port:
        if refused(f"the port {port} is not opened", level):
            raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
    elif refused(f"the serial port {port} is not opened", level):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT))
