"""Setting value types: each parser maps the text of a value to the value, raising ValueError.

Also the rule for text that goes on the air (`over_the_air_refusal`). The table of settings is in
config.py."""

import re
from collections.abc import Callable
from urllib.parse import urlsplit

from .coded import CodedError
from .message import normal_call

# TNC channel-switch characters; kept out of comments and statuses (spec 1129).
TNC_SWITCH_CHARS = "|~"
_TRUE, _FALSE = ("1", "true", "yes", "on"), ("0", "false", "no", "off")


def int_in(low: int, high: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        try:
            value = int(text.strip())
        except ValueError:
            raise CodedError(f"{text!r} is not a whole number", "setting.not_whole", value=text) from None
        if not low <= value <= high:
            raise CodedError(
                f"{value} is not between {low} and {high}", "setting.range", value=value, min=low, max=high
            )
        return value

    return parse


def int_or_off(low: int, high: int) -> Callable[[str], int]:
    """Return a parser for an integer from `low` to `high`, or 0 for off."""
    whole = int_in(0, high)

    def parse(text: str) -> int:
        value = whole(text)
        if 0 < value < low:
            raise CodedError(
                f"{value} is not 0 (off) or between {low} and {high}",
                "setting.off_or_range",
                value=value,
                min=low,
                max=high,
            )
        return value

    return parse


def int_among(choices: tuple[int, ...]) -> Callable[[str], int]:
    """Return a parser for one of a short list of integers."""
    listed = ", ".join(str(c) for c in choices)

    def parse(text: str) -> int:
        try:
            value = int(text.strip())
        except ValueError:
            raise CodedError(f"{text!r} is not a whole number", "setting.not_whole", value=text) from None
        if value not in choices:
            raise CodedError(f"{value} is not one of {listed}", "setting.not_among", value=value, choices=listed)
        return value

    return parse


def word_among(words: tuple[str, ...]) -> Callable[[str], str]:
    """Return a parser for one of a short list of words, in lower case."""
    listed = ", ".join(words)

    def parse(text: str) -> str:
        value = text.strip().lower()
        if value not in words:
            raise CodedError(f"{text!r} is not one of {listed}", "setting.not_among", value=text, choices=listed)
        return value

    return parse


def optional_int(low: int, high: int) -> Callable[[str], int | None]:
    """Return a parser for an integer, or None for empty text."""
    whole = int_in(low, high)

    def parse(text: str) -> int | None:
        return None if text.strip() == "" else whole(text)

    return parse


def float_in(low: float, high: float) -> Callable[[str], float]:
    def parse(text: str) -> float:
        try:
            value = float(text.strip())
        except ValueError:
            raise CodedError(f"{text!r} is not a number", "setting.not_number", value=text) from None
        if not low <= value <= high:  # also false for NaN
            raise CodedError(
                f"{value:g} is not between {low:g} and {high:g}", "setting.range", value=value, min=low, max=high
            )
        return value

    return parse


def boolean(text: str) -> bool:
    word = text.strip().lower()
    if word in _TRUE:
        return True
    if word in _FALSE:
        return False
    raise CodedError(f"{text!r} is not true or false", "setting.not_boolean", value=text)


def text_of(max_length: int = 200, ascii_only: bool = False) -> Callable[[str], str]:
    def parse(text: str) -> str:
        value = text.strip()
        if len(value) > max_length:
            raise CodedError(
                f"{len(value)} characters is more than the {max_length} allowed",
                "setting.too_long",
                length=len(value),
                max=max_length,
            )
        if ascii_only and (refusal := over_the_air_refusal(value)):
            raise refusal
        if not value.isprintable():
            raise CodedError("it has characters that are not printable", "setting.not_printable")
        return value

    return parse


def over_the_air_refusal(text: str) -> CodedError | None:
    """Return why the text may not be sent as a comment or status (printable ASCII without `|` and
    `~`), or None."""
    if not text.isprintable() or not text.isascii():
        return CodedError("it has characters that are not printable ASCII", "setting.not_ascii")
    bad = next((c for c in text if c in TNC_SWITCH_CHARS), "")
    return (
        CodedError(
            f"{bad!r} is a character a TNC takes for a command and may not be in it", "setting.tnc_char", char=bad
        )
        if bad
        else None
    )


def over_the_air_problem(text: str) -> str:
    """Return the text of over_the_air_refusal, or "" if none."""
    return str(refusal) if (refusal := over_the_air_refusal(text)) else ""


def call_or_empty(text: str) -> str:
    """Return the call as normal_call writes it; empty text is the empty call (nothing is
    transmitted)."""
    return "" if text.strip() == "" else normal_call(text)


def optional_float(low: float, high: float) -> Callable[[str], float | None]:
    """Return a parser for a number from `low` to `high`, or None for empty text."""
    number = float_in(low, high)

    def parse(text: str) -> float | None:
        return None if text.strip() == "" else number(text)

    return parse


def web_address(text: str) -> str:
    """Return an http or https address with a host and no blanks."""
    value = text.strip()
    refused = CodedError(f"{text!r} is not an http or https address", "setting.not_web_address", value=text)
    try:
        parts = urlsplit(value)
    except ValueError:  # an IPv6 address without its closing ]
        raise refused from None
    if (
        parts.scheme not in ("http", "https")
        or not parts.netloc
        or any(c.isspace() for c in value)
        or not value.isprintable()
        or len(value) > 500
    ):
        raise refused
    return value


KEY_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # without look-alikes 0, 1, i, l and o
KEY_GROUPS, KEY_GROUP_SIZE = 3, 4


def access_key(text: str) -> str:
    """Return `web/key` as kept: three dash-separated groups of four; case, blanks and dashes are
    ignored."""
    letters = "".join(c for c in text.lower() if c not in " -")
    if letters == "":
        return ""
    if len(letters) != KEY_GROUPS * KEY_GROUP_SIZE or any(c not in KEY_ALPHABET for c in letters):
        raise CodedError(
            "it is not an access key (three groups of four digits and letters, such as k7m2-x9pq-4hrt)",
            "setting.not_access_key",
        )
    return "-".join(letters[i : i + KEY_GROUP_SIZE] for i in range(0, len(letters), KEY_GROUP_SIZE))


SECRET_WORDS = ("key", "secret", "password", "token")


def is_secret(key: str) -> bool:
    """Return whether the setting is a secret: a word of its name is key, secret, password or token.

    `mercury/keying` is not one."""
    return any(word in SECRET_WORDS for word in re.split(r"[^a-z0-9]+", key.lower()))


def redacted(key: str, value: str) -> str:
    """Return the value as the log and support bundle may show it; a secret shows only `(set, N
    characters)` or `(empty)`."""
    if not is_secret(key):
        return value
    return f"(set, {len(value)} characters)" if value else "(empty)"
