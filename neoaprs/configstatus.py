"""Status report settings: the text, the rigctld address, the source and the template."""
import re
from collections.abc import Callable

from .coded import CodedError
from .configtypes import over_the_air_refusal

# 62 characters by the spec, less the 7-byte day-hour-minute time.
MAX_STATUS = 55
DEFAULT_STATUS_TEMPLATE = "QRV {freq} {mode}"
# Nowhere, station/status, or the radio (status/rigctld, status/template).
STATUS_SOURCES = ("off", "text", "rig")
STATUS_FIELDS = ("freq", "mode")     # names status/template may use in braces
# Widest values, to check a template fits MAX_STATUS (also the page's LIMITS.status).
LONGEST_FREQ, LONGEST_MODE = "1296.000 MHz", "PKTUSB"
_BRACES = re.compile(r"\{([^{}]*)\}")


def status_text(max_length: int) -> Callable[[str], str]:
    """Return a parser for printable ASCII without `|` and `~`, of at most `max_length`
    characters."""
    def parse(text: str) -> str:
        value = text.strip()
        if refusal := over_the_air_refusal(value):
            raise refusal
        if len(value) > max_length:
            raise CodedError(f"{len(value)} characters is more than the {max_length} allowed", "setting.too_long", length=len(value), max=max_length)
        return value
    return parse


def hostport(text: str) -> str:
    """Return a rigctld "host:port" (port 1 to 65535, IPv6 in brackets allowed), or "" for none."""
    value = text.strip()
    if value == "":
        return ""
    host, _, port = value.rpartition(":")
    if not host.strip("[]") or not port.isdigit() or not 1 <= int(port) <= 65535 or any(c.isspace() for c in value) or not value.isprintable():
        raise CodedError(f"{text!r} is not host:port (4532 is rigctld's port)", "setting.not_hostport", value=text)
    return value


def host_port(text: str) -> tuple[str, int] | None:
    """Return `host:port` as a pair, or None for empty text."""
    if not text:
        return None
    host, _, port = text.rpartition(":")
    return host.strip("[]"), int(port)


def fill_template(template: str, freq: str, mode: str) -> str:
    """Return the template with {freq} and {mode} replaced; other text stays."""
    return _BRACES.sub(lambda m: {"freq": freq, "mode": mode}.get(m.group(1), m.group(0)), template)


def status_source(text: str) -> str:
    """Return "" (decided by the other settings) or one of off, text, rig."""
    value = text.strip().lower()
    if value and value not in STATUS_SOURCES:
        raise CodedError(f"{text!r} is not off, text or rig (empty: as status/rigctld and station/status say)", "setting.status_source", value=text)
    return value


def status_template(text: str) -> str:
    """Return the template if it names only {freq} and {mode} and fits MAX_STATUS with the widest
    values."""
    value = status_text(MAX_STATUS * 2)(text)
    unknown = [name for name in _BRACES.findall(value) if name not in STATUS_FIELDS]
    if unknown:
        raise CodedError(f"{{{unknown[0]}}} is not a field of the template (the fields are {{freq}} and {{mode}})", "setting.template_field", field=unknown[0])
    size = len(fill_template(value, LONGEST_FREQ, LONGEST_MODE))
    if size > MAX_STATUS:
        raise CodedError(f"{size} characters with a long frequency and mode is more than the {MAX_STATUS} allowed", "setting.template_long", length=size, max=MAX_STATUS)
    return value
