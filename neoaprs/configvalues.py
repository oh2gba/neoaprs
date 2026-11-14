"""The settings that are more than a number, a word or a text: the device globs of the search, the path of the beacon, the antenna's direction, the symbol, a host, the source of the map, the TNC profile. Each is a function from the text of a value to
the value, raising CodedError with the reason (config.py has the table of the settings)."""
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

MAX_SERIAL_PATTERN = 500
MAX_MAP_SOURCE = 500                 # the longest map/source
MAX_PASSCODE = 32767                 # an APRS-IS passcode is 15 bits
SYMBOL_TABLES = "/\\" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
PORT_SCHEMES = ("socket", "tcp", "bt", "ble")      # the address forms of a port that the program means (serialport.py); every other scheme pyserial knows is refused
ANTENNA_DIRECTIONS = ("omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N")      # in the order of the specification's directivity digit: 0 omni, 1 NE ... 7 NW, 8 N


def device_globs(text: str) -> str:
    """One or more device globs, each an absolute path, separated by spaces (written with single spaces)."""
    parts = text.split()
    if not parts or any(not part.startswith("/") for part in parts):
        raise CodedError(f"{text!r} is not one or more absolute patterns separated by spaces, such as /dev/ttyUSB*", "setting.not_globs", value=text)
    return text_of(MAX_SERIAL_PATTERN)(" ".join(parts))


def port_scheme(address: str) -> str:
    """The address of a port as it was given, when it is a device path (no `://` in it) or one of the four forms the program means (`socket://`, `tcp://`, `bt://`, `ble://`, in any case, as pyserial reads the scheme);
    else a CodedError. pyserial has more schemes (`spy://` writes a file of the sender's choice the moment the port is made), so a port is never handed to it unchecked."""
    if "://" in address and address.lower().split("://", 1)[0] not in PORT_SCHEMES:
        raise CodedError(f"{address!r} is not an address or a name", "setting.not_host", value=address)
    return address


def port_address(text: str) -> str:
    """The value of serial/port, serial/last_port and gps/device: empty, a device path or an address of a port (port_scheme), at most 255 printable characters."""
    return port_scheme(text_of(255)(text))


def digipeater_path(text: str) -> str:
    """A list of digipeater calls separated by commas, each checked as a call; written the way the frame carries it (capitals, no blanks). Empty is the recommended path of the station's symbol, DIRECT alone
    is no digipeaters at all."""
    calls = path_choice(text)
    return "" if calls is None else DIRECT_ONLY if not calls else ",".join(calls)


def antenna_direction(text: str) -> str:
    """"omni" or a point of the compass (N NE E SE S SW W NW), written the way the setting keeps it."""
    word = text.strip()
    if word.lower() == "omni":
        return "omni"
    if word.upper() in ANTENNA_DIRECTIONS:
        return word.upper()
    raise CodedError(f"{text!r} is not omni or one of N NE E SE S SW W NW", "setting.not_direction", value=text)


def symbol_table(text: str) -> str:
    if len(text) != 1 or text not in SYMBOL_TABLES:
        raise CodedError(f"{text!r} is not / or \\ or an overlay character A-Z, 0-9", "setting.not_symbol_table", value=text)
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


DNS_LABEL = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?")      # (an underscore too: a name of a local network may have one, and a browser sends it)
MAX_DNS_NAME = 253
MAX_HOSTS = 500                      # the longest web/allowed_hosts


def is_host(text: str) -> bool:
    """Whether `text` is a DNS name (labels of letters, digits, hyphens and underscores between dots, at most 253 characters), an IPv4 address or an IPv6 address, with or without the brackets a Host header puts round it."""
    name = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    try:
        ipaddress.ip_address(name)
        return "%" not in name
    except ValueError:
        pass
    return len(text) <= MAX_DNS_NAME and all(DNS_LABEL.fullmatch(label) for label in text.split("."))


def host_list(text: str) -> str:
    """The value of web/allowed_hosts: empty, or host names and IP addresses (is_host) separated by commas (blanks beside a comma stay as they were written), without blanks at the ends."""
    value = text.strip()
    if len(value) > MAX_HOSTS:
        raise CodedError(f"{text!r} is not a list of addresses or names", "setting.not_host", value=text)
    names = [name.strip() for name in value.split(",")] if value else []
    for name in names:
        if not is_host(name):
            raise CodedError(f"{name!r} is not an address or a name", "setting.not_host", value=text)
    return value


def map_source(text: str) -> str:
    """Empty (the latest daily build of build.protomaps.com), a web address (http or https) or a path of a PMTiles file, which may have blanks in it; never a
    control character, nor a value that starts with a dash."""
    value = text.strip()
    if value == "":
        return ""
    if len(value) > MAX_MAP_SOURCE or not value.isprintable() or value.startswith("-"):
        raise CodedError(f"{text!r} is not a web address or the path of a PMTiles file", "setting.not_map_source", value=text)
    if "://" in value and (urlsplit(value).scheme not in ("http", "https") or " " in value):
        raise CodedError(f"{text!r} is not an http or https address", "setting.not_web_address", value=text)
    return value


def tnc_profile(text: str) -> str:
    """The key of a TNC profile (tncprofile.py), written the way the setting keeps it."""
    return profile_of(text).key


def hf_profile(text: str) -> str:
    """The key of a type of the HF radio (tncprofile.py: HF_PROFILES), written the way the setting keeps it."""
    return hf_profile_of(text).key


def mercury_keying(text: str) -> str:
    """How the Mercury modem keys the radio (mercury.py): `vox`, `cm108`, `rts:PORT` or `dtr:PORT`, written the way the setting keeps it; empty for the daemon's own choice from what it finds."""
    return keying_of(text).text if text.strip() else ""


def aprsis_server(text: str) -> str:
    """"host:port" of an APRS-IS server (14580 is the port of the filtered feed that iGates use), or empty for none."""
    try:
        return hostport(text)
    except CodedError:
        raise CodedError(f"{text!r} is not host:port (14580 is the usual port of an APRS-IS server)", "setting.not_server", value=text) from None


def passcode(text: str) -> str:
    """The APRS-IS passcode of the call, as digits (0 to 32767), or empty for none yet (NeoAPRS does not work it out: the operator requests it). -1 is the login that only reads and puts nothing on APRS-IS, so an iGate does not take it."""
    value = text.strip()
    if value == "-1":
        raise CodedError("-1 is the passcode for reading only; an iGate needs the passcode of its call", "setting.passcode_read_only", value=text)
    if value and not (value.isascii() and value.isdigit() and int(value) <= MAX_PASSCODE):
        raise CodedError(f"the passcode of your call is a number from 0 to {MAX_PASSCODE}", "setting.not_passcode", max=MAX_PASSCODE)
    return str(int(value)) if value else ""
