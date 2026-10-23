"""The rules of a call sign with its SSID: parsing, the printable form, what is valid on AX.25.

A call here is the base (1 to 6 characters of A-Z and 0-9) and an SSID from 0 to 15, the way an AX.25 address holds them. That is also what the generic APRS destinations
(APRS, APK102, WIDE1-1, RELAY, TCPIP, BEACON) are, so they are valid; whether a call belongs to a licensed operator is not asked here."""
import re

from .coded import CodedError

MAX_SSID = 15
BASE_MAX = 6                         # the most characters of a call's base
AMATEUR_BASE_MIN = 3                 # the fewest characters of an amateur call's base
_CALL = re.compile(rf"([A-Z0-9]{{1,{BASE_MAX}}})(?:-([0-9]{{1,2}}))?")
PLACEHOLDER_CALLS = frozenset({"N0CALL", "NOCALL", "MYCALL"})        # what a program's example settings say: not the call of anybody, never transmitted under
_AMATEUR_CALL = re.compile(rf"(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{{{AMATEUR_BASE_MIN},{BASE_MAX}}}")      # 3 to 6 characters with a digit and a letter; the ITU's rules for a prefix are not asked
SET_CALL_FIRST = "set your call first"


class CallsignError(CodedError):
    pass


def parse_call(text: str) -> tuple[str, int]:
    """'oh2gba-7' gives ('OH2GBA', 7), 'OH2GBA' gives ('OH2GBA', 0). Anything else raises CallsignError naming the text."""
    if not text.isascii():
        raise CallsignError(f"call {text!r} has characters other than A-Z, 0-9 and a '-SSID'", "call.characters", value=text)
    match = _CALL.fullmatch(text.upper())
    if match is None:
        raise CallsignError(f"call {text!r} is not 1 to 6 characters of A-Z and 0-9 with an optional '-SSID'", "call.shape", value=text)
    base, ssid_text = match.groups()
    ssid = 0 if ssid_text is None else int(ssid_text)
    if ssid > MAX_SSID:
        raise CallsignError(f"call {text!r} has an SSID above {MAX_SSID}", "call.ssid", value=text, max=MAX_SSID)
    return base, ssid


def format_call(call: str, ssid: int) -> str:
    """'OH2GBA-7'; 'OH2GBA' when the SSID is 0."""
    return call if ssid == 0 else f"{call}-{ssid}"


def call_problem(call: str) -> str:
    """Why we may not transmit under this call, empty when we may: it is empty, a placeholder (N0CALL, NOCALL, MYCALL: what an example says) or not an amateur call (3 to 6 characters with a digit
    and a letter, and an SSID if any)."""
    if not call:
        return SET_CALL_FIRST
    try:
        base, _ = parse_call(call)
    except CallsignError:
        return f"{call!r} is not a call: {SET_CALL_FIRST}"
    if base in PLACEHOLDER_CALLS:
        return f"{base} is a placeholder, not a call: {SET_CALL_FIRST}"
    if _AMATEUR_CALL.fullmatch(base) is None:
        return f"{call} is not an amateur call: {SET_CALL_FIRST}"
    return ""
