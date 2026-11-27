"""Settings of the map's traffic layers: aircraft and ship sources and own receivers.

A stored source not offered at the station's position stays stored and counts as none."""

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .coded import CodedError
from .configtypes import web_address, word_among
from .layerthing import AIRCRAFT_SOURCES as AIRCRAFT_SOURCES, AIS_HOST, AIS_PORT, SHIP_SOURCES as SHIP_SOURCES

MAX_ADDRESS = 500
MAX_KEY = 200  # an AISStream key is 40 hexadecimal characters
# A key a page is never sent once saved: it gets MASK in its place, and MASK sent back keeps the key.
MASKED_KEYS = frozenset({"map/ships_key"})
MASK = "********"
# Host name or IPv4 address.
_NAME = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?")


def _refused(text: str) -> CodedError:
    return CodedError(f"{text!r} is not the address of a receiver", "setting.not_receiver", value=text)


def _host_ok(host: str) -> bool:
    if host.startswith("[") and host.endswith("]"):
        try:
            return ipaddress.ip_address(host[1:-1].partition("%")[0]).version == 6
        except ValueError:
            return False
    return _NAME.fullmatch(host) is not None and ".." not in host


def _host_port_ok(value: str) -> bool:
    host, colon, port = value.rpartition(":") if not value.endswith("]") else ("", "", value)
    if not colon:
        return _host_ok(value)
    return _host_ok(host) and port.isascii() and port.isdigit() and 1 <= int(port) <= 65535


def _plain(text: str) -> str:
    """Return the stripped text; refuse it if too long, not printable or containing a blank."""
    value = text.strip()
    if len(value) > MAX_ADDRESS or not value.isprintable() or any(c.isspace() for c in value):
        raise _refused(text)
    return value


def receiver_address(text: str) -> str:
    """Return an aircraft receiver address: empty, host[:port] or an http(s) URL."""
    value = _plain(text)
    if not value:
        return ""
    if "://" in value:
        try:
            parts = urlsplit(value)
            _ = parts.port
            # Credentials would be stored and shown as a setting.
            if parts.hostname and parts.username is None and parts.password is None:
                return web_address(value)
        except (ValueError, CodedError):
            pass
        raise _refused(text)
    if not _host_port_ok(value):
        raise _refused(text)
    return value


def ais_address(text: str) -> str:
    """Return an AIS receiver address: empty (this computer), host or host:port."""
    value = _plain(text)
    if value and ("://" in value or not _host_port_ok(value)):
        raise _refused(text)
    return value


def ais_host_port(value: str) -> tuple[str, int]:
    """Return (host, port) for a stored `map/ships_host`; empty gives the defaults."""
    if not value:
        return AIS_HOST, AIS_PORT
    host, colon, port = value.rpartition(":") if not value.endswith("]") else ("", "", value)
    if not colon:
        host, port = value, str(AIS_PORT)
    return host.removeprefix("[").removesuffix("]"), int(port)


def service_key(text: str) -> str:
    """Return a service's key (`map/ships_key`): empty, or printable characters with no blank."""
    value = text.strip()
    if len(value) > MAX_KEY or not value.isprintable() or any(c.isspace() for c in value):
        raise CodedError("That is not a key the service gives", "setting.not_key")
    return value


@dataclass(frozen=True)
class LayerFields:
    """The `Config` fields of the layer settings."""

    map_aircraft: str = "none"
    map_aircraft_host: str = ""
    map_ships: str = "none"
    map_ships_host: str = ""
    map_ships_key: str = ""


# (attr, key, parser), in settings form order
LAYER_ROWS: tuple[tuple[str, str, Callable[[str], Any]], ...] = (
    ("map_aircraft", "map/aircraft", word_among(AIRCRAFT_SOURCES)),
    ("map_aircraft_host", "map/aircraft_host", receiver_address),
    ("map_ships", "map/ships", word_among(SHIP_SOURCES)),
    ("map_ships_host", "map/ships_host", ais_address),
    ("map_ships_key", "map/ships_key", service_key),
)
