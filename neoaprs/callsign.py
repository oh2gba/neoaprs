"""Call sign rules with SSID: parsing, the printable form, and what is valid on AX.25.

A call is a base (1 to 6 characters A-Z, 0-9) and an SSID 0 to 15. An internet station may
have a name that is no AX.25 call (`OH2XYZ-L`, `WINLINK`): 1 to 9 letters, digits and hyphens.
"""

import re

from .coded import CodedError, Reason

MAX_SSID = 15
BASE_MAX = 6  # most characters of a call's base
AMATEUR_BASE_MIN = 3  # fewest characters of an amateur call's base
# the SSID (0-15) is checked afterwards
AX25_CALL = re.compile(rf"([A-Z0-9]{{1,{BASE_MAX}}})(?:-([0-9]{{1,2}}))?")
# what a program's example settings say: nobody's call, never transmitted under
PLACEHOLDER_CALLS = frozenset({"N0CALL", "NOCALL", "MYCALL"})
# a station's name on APRS-IS: 1 to 9 letters, digits, hyphens
INTERNET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,8}")
# an APRS-IS path element: a name, starred if repeated
PATH_ELEMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,8}\*?")
# 3 to 6 characters with a digit and a letter; the ITU's prefix rules are not checked
_AMATEUR_CALL = re.compile(rf"(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{{{AMATEUR_BASE_MIN},{BASE_MAX}}}")
SET_CALL_FIRST = "set your call first"


class CallsignError(CodedError):
    pass


def parse_call(text: str) -> tuple[str, int]:
    """Return ('OH2GBA', 7) for 'oh2gba-7', ('OH2GBA', 0) for 'OH2GBA'; else raise CallsignError."""
    if not text.isascii():
        raise CallsignError(
            f"call {text!r} has characters other than A-Z, 0-9 and a '-SSID'", "call.characters", value=text
        )
    match = AX25_CALL.fullmatch(text.upper())
    if match is None:
        raise CallsignError(
            f"call {text!r} is not 1 to 6 characters of A-Z and 0-9 with an optional '-SSID'", "call.shape", value=text
        )
    base, ssid_text = match.groups()
    ssid = 0 if ssid_text is None else int(ssid_text)
    if ssid > MAX_SSID:
        raise CallsignError(f"call {text!r} has an SSID above {MAX_SSID}", "call.ssid", value=text, max=MAX_SSID)
    return base, ssid


def format_call(call: str, ssid: int) -> str:
    """Return 'OH2GBA-7', or 'OH2GBA' when the SSID is 0."""
    return call if ssid == 0 else f"{call}-{ssid}"


def normal_name(text: str) -> str:
    """Return a station as a message names it: a normal-form call, else an APRS-IS name.

    APRS-IS names are `OH2XYZ-L`, `OH2XYZ-20`, `WINLINK`. Raise CallsignError as parse_call does.
    """
    try:
        return format_call(*parse_call(text.strip()))
    except CallsignError:
        name = text.strip().upper()
        if text.isascii() and INTERNET_NAME.fullmatch(name):
            return name
        raise


def call_problem(call: str) -> str:
    """Return a Reason why we may not transmit under this call, empty if we may.

    Refused: empty, a placeholder (N0CALL, NOCALL, MYCALL), or not an amateur call.
    """
    if not call:
        return Reason("set your call first", "call.none")
    try:
        base, _ = parse_call(call)
    except CallsignError:
        return Reason(f"{call!r} is not a call: {SET_CALL_FIRST}", "call.not_call", call=call)
    if base in PLACEHOLDER_CALLS:
        return Reason(f"{base} is a placeholder, not a call: {SET_CALL_FIRST}", "call.placeholder", call=base)
    if _AMATEUR_CALL.fullmatch(base) is None:
        return Reason(f"{call} is not an amateur call: {SET_CALL_FIRST}", "call.not_amateur", call=call)
    return ""
