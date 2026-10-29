"""The rules of a call sign with its SSID: parsing, the printable form, what is valid on AX.25.

A call here is the base (1 to 6 characters of A-Z and 0-9) and an SSID from 0 to 15, the way an AX.25 address holds them. That is also what the generic APRS destinations
(APRS, APK102, WIDE1-1, RELAY, TCPIP, BEACON) are, so they are valid; whether a call belongs to a licensed operator is not asked here.

A station on the internet may have a name that is no AX.25 call: a D-STAR gateway's `OH2XYZ-L`, an SSID above 15, more than six characters (`WINLINK`). APRS-IS allows 1 to 9 letters, digits and
hyphens, and such a station can send us a message through an iGate (a third-party packet) and be answered: `normal_name` takes those, for the sender of a message and for whom we write to.
Our own call and every address of a frame on the air stay AX.25 calls.

Three shapes of name, each written once here: the AX.25 call (`AX25_CALL`), the name of a station on APRS-IS (`INTERNET_NAME`) and an element of an APRS-IS line's path, which is such a name with a star after it
if it has been repeated (`PATH_ELEMENT`). The path of a frame on the air has its own, stricter rule (igaterules.py)."""
import re

from .coded import CodedError

MAX_SSID = 15
BASE_MAX = 6                         # the most characters of a call's base
AMATEUR_BASE_MIN = 3                 # the fewest characters of an amateur call's base
AX25_CALL = re.compile(rf"([A-Z0-9]{{1,{BASE_MAX}}})(?:-([0-9]{{1,2}}))?")        # (the SSID is checked after: 0 to 15)
PLACEHOLDER_CALLS = frozenset({"N0CALL", "NOCALL", "MYCALL"})        # what a program's example settings say: not the call of anybody, never transmitted under
INTERNET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,8}")                 # a station's name on APRS-IS: 1 to 9 letters, digits and hyphens
PATH_ELEMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,8}\*?")                # an element of the path of an APRS-IS line: a name, with a star when it has been repeated
_AMATEUR_CALL = re.compile(rf"(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{{{AMATEUR_BASE_MIN},{BASE_MAX}}}")      # 3 to 6 characters with a digit and a letter; the ITU's rules for a prefix are not asked
SET_CALL_FIRST = "set your call first"


class CallsignError(CodedError):
    pass


def parse_call(text: str) -> tuple[str, int]:
    """'oh2gba-7' gives ('OH2GBA', 7), 'OH2GBA' gives ('OH2GBA', 0). Anything else raises CallsignError naming the text."""
    if not text.isascii():
        raise CallsignError(f"call {text!r} has characters other than A-Z, 0-9 and a '-SSID'", "call.characters", value=text)
    match = AX25_CALL.fullmatch(text.upper())
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


def normal_name(text: str) -> str:
    """A station as a message names it: a call in its normal form (upper case, no SSID of 0), else a name APRS-IS allows (`OH2XYZ-L`, `OH2XYZ-20`, `WINLINK`) in upper case. Raises CallsignError as parse_call does."""
    try:
        return format_call(*parse_call(text.strip()))
    except CallsignError:
        name = text.strip().upper()
        if text.isascii() and INTERNET_NAME.fullmatch(name):
            return name
        raise


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
