"""The types a setting can have (config.py has the table of the settings): each is a function from the text of a value to the value, raising ValueError with the reason, and `over_the_air_problem`, the rule for text that goes
on the air."""
from collections.abc import Callable
from urllib.parse import urlsplit

from .message import normal_call

TNC_SWITCH_CHARS = "|~"              # the characters a TNC takes for its channel switch: the spec keeps them out of a comment and a status (1129)
_TRUE, _FALSE = ("1", "true", "yes", "on"), ("0", "false", "no", "off")


def int_in(low: int, high: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        try:
            value = int(text.strip())
        except ValueError:
            raise ValueError(f"{text!r} is not a whole number") from None
        if not low <= value <= high:
            raise ValueError(f"{value} is not between {low} and {high}")
        return value
    return parse


def int_or_off(low: int, high: int) -> Callable[[str], int]:
    """A whole number from `low` to `high`, or 0 for off."""
    whole = int_in(0, high)

    def parse(text: str) -> int:
        value = whole(text)
        if 0 < value < low:
            raise ValueError(f"{value} is not 0 (off) or between {low} and {high}")
        return value
    return parse


def optional_int(low: int, high: int) -> Callable[[str], int | None]:
    """A whole number, or nothing: an empty text is None."""
    whole = int_in(low, high)

    def parse(text: str) -> int | None:
        return None if text.strip() == "" else whole(text)
    return parse


def float_in(low: float, high: float) -> Callable[[str], float]:
    def parse(text: str) -> float:
        try:
            value = float(text.strip())
        except ValueError:
            raise ValueError(f"{text!r} is not a number") from None
        if not low <= value <= high:                         # (also false for NaN)
            raise ValueError(f"{value:g} is not between {low:g} and {high:g}")
        return value
    return parse


def boolean(text: str) -> bool:
    word = text.strip().lower()
    if word in _TRUE:
        return True
    if word in _FALSE:
        return False
    raise ValueError(f"{text!r} is not true or false")


def text_of(max_length: int = 200, ascii_only: bool = False) -> Callable[[str], str]:
    def parse(text: str) -> str:
        value = text.strip()
        if len(value) > max_length:
            raise ValueError(f"{len(value)} characters is more than the {max_length} allowed")
        if ascii_only and (problem := over_the_air_problem(value)):
            raise ValueError(problem)
        if not value.isprintable():
            raise ValueError("it has characters that are not printable")
        return value
    return parse


def over_the_air_problem(text: str) -> str:
    """Why this text may not be sent as a comment or a status: it must be printable ASCII without `|` and `~`. Empty when it may."""
    if not text.isprintable() or not text.isascii():
        return "it has characters that are not printable ASCII"
    bad = next((c for c in text if c in TNC_SWITCH_CHARS), "")
    return f"{bad!r} is a character a TNC takes for a command and may not be in it" if bad else ""


def call_or_empty(text: str) -> str:
    """A call as normal_call writes it, or nothing: an empty text is the empty call, which transmits nothing (can_transmit)."""
    return "" if text.strip() == "" else normal_call(text)


def optional_float(low: float, high: float) -> Callable[[str], float | None]:
    """A number from `low` to `high`, or nothing: an empty text is None."""
    number = float_in(low, high)

    def parse(text: str) -> float | None:
        return None if text.strip() == "" else number(text)
    return parse


def web_address(text: str) -> str:
    """An http or https address with a host and no blanks."""
    value = text.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or any(c.isspace() for c in value) or not value.isprintable() or len(value) > 500:
        raise ValueError(f"{text!r} is not an http or https address")
    return value


KEY_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"       # digits and lower case letters without 0, 1, i, l and o, which look alike
KEY_GROUPS, KEY_GROUP_SIZE = 3, 4


def access_key(text: str) -> str:
    """The access key a device on the network types (`web/key`) the way it is kept, three groups of four with dashes: capitals, blanks and dashes in what was typed do not matter. Empty for none."""
    letters = "".join(c for c in text.lower() if c not in " -")
    if letters == "":
        return ""
    if len(letters) != KEY_GROUPS * KEY_GROUP_SIZE or any(c not in KEY_ALPHABET for c in letters):
        raise ValueError("it is not an access key (three groups of four digits and letters, such as k7m2-x9pq-4hrt)")
    return "-".join(letters[i:i + KEY_GROUP_SIZE] for i in range(0, len(letters), KEY_GROUP_SIZE))
