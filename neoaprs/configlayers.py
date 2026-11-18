"""The settings of the map's layers of traffic (the group Settings, Map): where the aircraft and the ships come from, and the address of an own receiver of each. Their table rows (`LAYER_ROWS`) and fields
(`LayerFields`, a base of `Config`) are here so that config.py names them in one line; the sources and their rules are layerthing.py's.

A stored source the station is not offered now (Fintraffic after the station moved) stays stored and counts as none (layerthing.in_force)."""
import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .coded import CodedError
from .configtypes import web_address, word_among
from .layerthing import AIRCRAFT_SOURCES as AIRCRAFT_SOURCES, AIS_HOST, AIS_PORT, SHIP_SOURCES as SHIP_SOURCES

MAX_ADDRESS = 500                    # the longest address of a receiver
_NAME = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?")       # a host name or an IPv4 address


def _refused(text: str) -> CodedError:
    return CodedError(f"{text!r} is not the address of a receiver", "setting.not_receiver", value=text)


def _host_ok(host: str) -> bool:
    """A name (`pi.local`), an IPv4 address (`192.168.1.20`) or an IPv6 address in brackets (`[fe80::1]`)."""
    if host.startswith("[") and host.endswith("]"):
        try:
            return ipaddress.ip_address(host[1:-1].partition("%")[0]).version == 6
        except ValueError:
            return False
    return _NAME.fullmatch(host) is not None and ".." not in host


def _host_port_ok(value: str) -> bool:
    """`host` or `host:port`, the port 1 to 65535."""
    host, colon, port = value.rpartition(":") if not value.endswith("]") else ("", "", value)
    if not colon:
        return _host_ok(value)
    return _host_ok(host) and port.isascii() and port.isdigit() and 1 <= int(port) <= 65535


def _plain(text: str) -> str:
    """The text without its blanks at the ends; refused when it is too long, not printable or has a blank inside."""
    value = text.strip()
    if len(value) > MAX_ADDRESS or not value.isprintable() or any(c.isspace() for c in value):
        raise _refused(text)
    return value


def receiver_address(text: str) -> str:
    """The address of an own aircraft receiver (a Radarcape, or readsb's file): empty (this computer for readsb's file; a Radarcape is then not looked for), a name or address, the same with `:port`, or a whole http or https address (used as typed)."""
    value = _plain(text)
    if not value:
        return ""
    if "://" in value:
        try:
            parts = urlsplit(value)
            _ = parts.port
            if parts.hostname and parts.username is None and parts.password is None:          # (a name and a password in the address would be kept and shown as a setting: refused)
                return web_address(value)
        except (ValueError, CodedError):
            pass
        raise _refused(text)
    if not _host_port_ok(value):
        raise _refused(text)
    return value


def ais_address(text: str) -> str:
    """The address of an own AIS receiver: empty (this computer, port 10110), a name or address, or `host:port`."""
    value = _plain(text)
    if value and ("://" in value or not _host_port_ok(value)):
        raise _refused(text)
    return value


def ais_host_port(value: str) -> tuple[str, int]:
    """Where the daemon connects for a stored `map/ships_host`: the host (an IPv6 address without its brackets) and the port; this computer for an empty address, AIS_PORT when none is given."""
    if not value:
        return AIS_HOST, AIS_PORT
    host, colon, port = value.rpartition(":") if not value.endswith("]") else ("", "", value)
    if not colon:
        host, port = value, str(AIS_PORT)
    return host.removeprefix("[").removesuffix("]"), int(port)


@dataclass(frozen=True)
class LayerFields:
    """The fields of `Config` that the layers' settings are."""
    map_aircraft: str = "none"           # map/aircraft: none, adsbfi, adsblol, radarcape or receiver
    map_aircraft_host: str = ""          # map/aircraft_host: the own aircraft receiver's address (receiver_address)
    map_ships: str = "none"              # map/ships: none, fintraffic or receiver
    map_ships_host: str = ""             # map/ships_host: the own AIS receiver's address (ais_address)


LAYER_ROWS: tuple[tuple[str, str, Callable[[str], Any]], ...] = (        # (attr, key, parser), in the order of the settings form, straight after map/source
    ("map_aircraft", "map/aircraft", word_among(AIRCRAFT_SOURCES)),
    ("map_aircraft_host", "map/aircraft_host", receiver_address),
    ("map_ships", "map/ships", word_among(SHIP_SOURCES)),
    ("map_ships_host", "map/ships_host", ais_address),
)
