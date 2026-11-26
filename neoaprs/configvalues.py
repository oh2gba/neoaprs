"""Parsers of the settings that are more than a number, word or text.

Each maps the text of a value to the value, raising CodedError. The table of settings is in
config.py."""

import ipaddress
import re
from urllib.parse import urlsplit

from .coded import CodedError
from .configstatus import hostport
from .configtypes import text_of
from .mercury import keying_of
from .message import path_choice
from .route import DIRECT_ONLY
from .tncprofile import hf_profile_of, profile_of
from .versions import is_dial

MAX_SERIAL_PATTERN = 500
MAX_MAP_SOURCE = 500
MAX_PASSCODE = 32767  # an APRS-IS passcode has 15 bits
SYMBOL_TABLES = "/\\" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
PORT_SCHEMES = ("socket", "tcp", "bt", "ble")
# In the order of the spec's directivity digit: 0 omni, 1 NE ... 7 NW, 8 N.
ANTENNA_DIRECTIONS = ("omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N")


def device_globs(text: str) -> str:
    """Return absolute device globs separated by single spaces."""
    parts = text.split()
    if not parts or any(not part.startswith("/") for part in parts):
        raise CodedError(
            f"{text!r} is not one or more absolute patterns separated by spaces, such as /dev/ttyUSB*",
            "setting.not_globs",
            value=text,
        )
    return text_of(MAX_SERIAL_PATTERN)(" ".join(parts))


def port_scheme(address: str) -> str:
    """Return the address if it is a device path or a socket, tcp, bt or ble URL, else raise.

    Other pyserial schemes (`spy://` writes a file) must never be reached."""
    if "://" in address and address.lower().split("://", 1)[0] not in PORT_SCHEMES:
        raise CodedError(f"{address!r} is not an address or a name", "setting.not_host", value=address)
    return address


def port_address(text: str) -> str:
    return port_scheme(text_of(255)(text))


def digipeater_path(text: str) -> str:
    """Return comma-separated digipeater calls; empty is the recommended path, DIRECT none."""
    calls = path_choice(text)
    return "" if calls is None else DIRECT_ONLY if not calls else ",".join(calls)


def antenna_direction(text: str) -> str:
    """Return "omni" or a compass point (N NE E SE S SW W NW) as kept."""
    word = text.strip()
    if word.lower() == "omni":
        return "omni"
    if word.upper() in ANTENNA_DIRECTIONS:
        return word.upper()
    raise CodedError(f"{text!r} is not omni or one of N NE E SE S SW W NW", "setting.not_direction", value=text)


def symbol_table(text: str) -> str:
    if len(text) != 1 or text not in SYMBOL_TABLES:
        raise CodedError(
            f"{text!r} is not / or \\ or an overlay character A-Z, 0-9", "setting.not_symbol_table", value=text
        )
    return text


def symbol_code(text: str) -> str:
    if len(text) != 1 or not "!" <= text <= "~":
        raise CodedError(f"{text!r} is not one printable ASCII character", "setting.not_symbol_code", value=text)
    return text


def host_name(text: str) -> str:
    value = text.strip()
    if not value or any(c.isspace() for c in value) or not value.isprintable():
        raise CodedError(f"{text!r} is not an address or a name", "setting.not_host", value=text)
    return value


# Underscores allowed: local names have them.
DNS_LABEL = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?")
MAX_DNS_NAME = 253
MAX_HOSTS = 500


def is_host(text: str) -> bool:
    name = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    try:
        ipaddress.ip_address(name)
        return "%" not in name
    except ValueError:
        pass
    return len(text) <= MAX_DNS_NAME and all(DNS_LABEL.fullmatch(label) for label in text.split("."))


def host_list(text: str) -> str:
    value = text.strip()
    if len(value) > MAX_HOSTS:
        raise CodedError(f"{text!r} is not a list of addresses or names", "setting.not_host", value=text)
    names = [name.strip() for name in value.split(",")] if value else []
    for name in names:
        if not is_host(name):
            raise CodedError(f"{name!r} is not an address or a name", "setting.not_host", value=text)
    return value


def map_source(text: str) -> str:
    """Return map/source: empty, an http(s) address or a PMTiles file path."""
    value = text.strip()
    if value == "":
        return ""
    if len(value) > MAX_MAP_SOURCE or not value.isprintable() or value.startswith("-"):
        raise CodedError(
            f"{text!r} is not a web address or the path of a PMTiles file", "setting.not_map_source", value=text
        )
    if "://" in value and (urlsplit(value).scheme not in ("http", "https") or " " in value):
        raise CodedError(f"{text!r} is not an http or https address", "setting.not_web_address", value=text)
    return value


def tnc_profile(text: str) -> str:
    return profile_of(text).key


def hf_profile(text: str) -> str:
    return hf_profile_of(text).key


def mercury_keying(text: str) -> str:
    """Return how the modem keys the radio (`vox`, `cm108`, `rts:PORT`, `dtr:PORT`); empty: auto."""
    return keying_of(text).text if text.strip() else ""


def dial_or_empty(text: str) -> str:
    """Return a dial as the sked board writes it (`28.1800 MHz USB`), or empty."""
    value = text.strip()
    if value and not is_dial(value):
        raise CodedError(f"{value!r} is not a dial such as 28.1800 MHz USB", "setting.not_dial", value=value)
    return value


def aprsis_server(text: str) -> str:
    try:
        return hostport(text)
    except CodedError:
        raise CodedError(
            f"{text!r} is not host:port (14580 is the usual port of an APRS-IS server)",
            "setting.not_server",
            value=text,
        ) from None


def passcode(text: str) -> str:
    """Return the APRS-IS passcode as digits, or "" for none; refuse -1 (read-only login)."""
    value = text.strip()
    if value == "-1":
        raise CodedError(
            "-1 is the passcode for reading only; an iGate needs the passcode of its call",
            "setting.passcode_read_only",
            value=text,
        )
    if value and not (value.isascii() and value.isdigit() and int(value) <= MAX_PASSCODE):
        raise CodedError(
            f"the passcode of your call is a number from 0 to {MAX_PASSCODE}", "setting.not_passcode", max=MAX_PASSCODE
        )
    return str(int(value)) if value else ""
