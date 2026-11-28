"""The chat of the HF tests tab: one room on the project's server, a line is a call, a time and a text.

Nothing the server says is trusted: `chat_of` checks every line and drops a bad line alone.
`request_body` builds what the daemon posts, so both directions are defined here.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from neoaprs.skeds import NOTE_SPACE, our_call, when

CHAT_URL = "https://neo.oh2gba.eu/chat.json"
ENDPOINT_PATH = "/api/v1/chat.php"
# a settings row (not a setting): the id of the newest line seen, so that a restart does not tell it again
SEEN_ROW = "update/chat_seen"
VERSION = 1
MAX_TEXT = 200
# the server's history: the newest lines
MAX_LINES = 100
MAX_ID = 2**53


@dataclass(frozen=True)
class Line:
    id: int
    at: datetime
    call: str
    text: str


@dataclass(frozen=True)
class Chat:
    """The lines oldest first, whether the chat is closed, and when the server wrote it."""

    closed: bool
    lines: tuple[Line, ...]
    written: datetime | None = None


EMPTY = Chat(False, ())


def _kept(c: str) -> bool:
    return unicodedata.category(c)[0] != "C"


def clean_text(text: str) -> str:
    """Make a line of the chat as the server does: white space becomes one space, control and
    invisible characters go, cut to MAX_TEXT characters."""
    kept = "".join(c for c in NOTE_SPACE.sub(" ", text) if _kept(c))
    return re.sub(" {2,}", " ", kept).strip(" ")[:MAX_TEXT].strip(" ")


def plain_text(text: object) -> bool:
    """Whether a text is a line as the server writes it: cleaned already and not empty."""
    return isinstance(text, str) and text != "" and clean_text(text) == text


def line_of(entry: object) -> Line | None:
    """The line of an entry of the chat, or None for a bad one."""
    if not isinstance(entry, dict):
        return None
    ident, call, text, at = entry.get("id"), entry.get("call"), entry.get("text"), when(entry.get("at"))
    if not (isinstance(ident, int) and not isinstance(ident, bool) and 0 < ident < MAX_ID):
        return None
    if at is None or not isinstance(call, str) or not call:
        return None
    if our_call(call) != call or not plain_text(text):
        return None
    return Line(ident, at, call, str(text))


def chat_of(data: Any) -> Chat | None:
    """Return the chat in a JSON value, or None if it is malformed; a bad line is dropped alone.

    The newest MAX_LINES lines by id are kept, oldest first; an id given twice is kept once."""
    if (
        not isinstance(data, dict)
        or data.get("v") != VERSION
        or isinstance(data.get("v"), bool)
        or not isinstance(data.get("lines"), list)
        or not isinstance(data.get("closed", False), bool)
    ):
        return None
    found: dict[int, Line] = {}
    for entry in data["lines"][: MAX_LINES * 10]:
        if (line := line_of(entry)) is not None:
            found.setdefault(line.id, line)
    lines = sorted(found.values(), key=lambda line: line.id)[-MAX_LINES:]
    return Chat(data.get("closed", False), tuple(lines), when(data.get("written")))


def parse_chat(body: bytes | str) -> Chat | None:
    try:
        return chat_of(json.loads(body))
    except (ValueError, RecursionError):  # RecursionError: JSON nested thousands deep
        return None


def request_body(token: str, call: str, text: str) -> bytes:
    body = {"action": "say", "token": token, "call": call, "text": text}
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def seen_of(text: str | None) -> int | None:
    """The id kept in SEEN_ROW, or None when there is none."""
    return int(text) if text is not None and text.isascii() and text.isdigit() and 0 < int(text) < MAX_ID else None
