"""The settings that are more than a number, a word or a text: the device globs of the search, the path of the beacon, the antenna's direction, the symbol, a host, the source of the map, the TNC profile. Each is a function from the text of a value to
the value, raising CodedError with the reason (config.py has the table of the settings)."""
from urllib.parse import urlsplit

from .coded import CodedError
from .configtypes import text_of
from .message import path_choice
from .route import DIRECT_ONLY
from .tncprofile import profile_of

MAX_SERIAL_PATTERN = 500
MAX_MAP_SOURCE = 500                 # the longest map/source
SYMBOL_TABLES = "/\\" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
ANTENNA_DIRECTIONS = ("omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N")      # in the order of the specification's directivity digit: 0 omni, 1 NE ... 7 NW, 8 N


def device_globs(text: str) -> str:
    """One or more device globs, each an absolute path, separated by spaces (written with single spaces)."""
    parts = text.split()
    if not parts or any(not part.startswith("/") for part in parts):
        raise CodedError(f"{text!r} is not one or more absolute patterns separated by spaces, such as /dev/ttyUSB*", "setting.not_globs", value=text)
    return text_of(MAX_SERIAL_PATTERN)(" ".join(parts))


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


def map_source(text: str) -> str:
    """Empty (the latest daily build of build.protomaps.com), a web address (http or https) or a path of a PMTiles file; never a word that starts with a dash, which the extract tool would take for an option."""
    value = text.strip()
    if value == "":
        return ""
    if len(value) > MAX_MAP_SOURCE or any(c.isspace() for c in value) or not value.isprintable() or value.startswith("-"):
        raise CodedError(f"{text!r} is not a web address or the path of a PMTiles file", "setting.not_map_source", value=text)
    if "://" in value and urlsplit(value).scheme not in ("http", "https"):
        raise CodedError(f"{text!r} is not an http or https address", "setting.not_web_address", value=text)
    return value


def tnc_profile(text: str) -> str:
    """The key of a TNC profile (tncprofile.py), written the way the setting keeps it."""
    return profile_of(text).key
