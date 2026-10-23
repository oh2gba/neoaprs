"""The settings of the status report that need more than a type: the text a status may carry, the rigctld address, where the status comes from, and the template that the radio's frequency and mode are filled into."""
import re
from collections.abc import Callable

from .coded import CodedError
from .configtypes import over_the_air_refusal

MAX_STATUS = 55                      # the most characters of the text of a status report: ours always carries a day-hour-minute time, which leaves 55 of the spec's 62 (62 only without a time)
DEFAULT_STATUS_TEMPLATE = "QRV {freq} {mode}"
STATUS_SOURCES = ("off", "text", "rig")      # where our status report comes from: nowhere, the text of station/status, or the radio (status/rigctld and status/template)
STATUS_FIELDS = ("freq", "mode")     # what status/template may name in braces
_LONGEST_FREQ, _LONGEST_MODE = "1296.000 MHz", "PKTUSB"       # the widest a frequency and a mode come out, to check that a template can fit MAX_STATUS
_BRACES = re.compile(r"\{([^{}]*)\}")


def status_text(max_length: int) -> Callable[[str], str]:
    """Printable ASCII, without `|` and `~`, of at most `max_length` characters."""
    def parse(text: str) -> str:
        value = text.strip()
        if refusal := over_the_air_refusal(value):
            raise refusal
        if len(value) > max_length:
            raise CodedError(f"{len(value)} characters is more than the {max_length} allowed", "setting.too_long", length=len(value), max=max_length)
        return value
    return parse


def hostport(text: str) -> str:
    """"host:port" of a rigctld, or empty for none; the port 1 to 65535 (the name may be an IPv6 address in brackets)."""
    value = text.strip()
    if value == "":
        return ""
    host, _, port = value.rpartition(":")
    if not host.strip("[]") or not port.isdigit() or not 1 <= int(port) <= 65535 or any(c.isspace() for c in value) or not value.isprintable():
        raise CodedError(f"{text!r} is not host:port (4532 is rigctld's port)", "setting.not_hostport", value=text)
    return value


def fill_template(template: str, freq: str, mode: str) -> str:
    """The template with {freq} and {mode} replaced; any other text, braces too, stays."""
    return _BRACES.sub(lambda m: {"freq": freq, "mode": mode}.get(m.group(1), m.group(0)), template)


def status_source(text: str) -> str:
    """Empty (as the other settings say: a radio when status/rigctld is set, else the text when there is one, else none), or one of off, text, rig."""
    value = text.strip().lower()
    if value and value not in STATUS_SOURCES:
        raise CodedError(f"{text!r} is not off, text or rig (empty: as status/rigctld and station/status say)", "setting.status_source", value=text)
    return value


def status_template(text: str) -> str:
    """Printable ASCII that names only {freq} and {mode} in braces and, with the widest values, is at most MAX_STATUS characters."""
    value = status_text(MAX_STATUS * 2)(text)
    unknown = [name for name in _BRACES.findall(value) if name not in STATUS_FIELDS]
    if unknown:
        raise CodedError(f"{{{unknown[0]}}} is not a field of the template (the fields are {{freq}} and {{mode}})", "setting.template_field", field=unknown[0])
    size = len(fill_template(value, _LONGEST_FREQ, _LONGEST_MODE))
    if size > MAX_STATUS:
        raise CodedError(f"{size} characters with a long frequency and mode is more than the {MAX_STATUS} allowed", "setting.template_long", length=size, max=MAX_STATUS)
    return value
