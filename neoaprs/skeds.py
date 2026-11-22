"""The sked board: a sked is a call, two instants, a dial and a short note.

Nothing the server says is trusted: `parse_board` checks every row and drops a bad row alone.
`request_body` builds what the daemon posts, so both directions are defined here.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from neoaprs.callsign import CallsignError, call_problem, format_call, parse_call
from neoaprs.clock import iso
from neoaprs.versions import is_dial

SKEDS_URL = "https://neo.oh2gba.eu/skeds.json"
ENDPOINT_PATH = "/api/v1/skeds.php"
# settings rows (not settings): the last board, and the ids of this installation's skeds
SKEDS_ROW = "update/skeds"
# secret sent with each posted sked so only this installation can delete it; never logged
SKED_TOKEN = "update/sked_token"  # noqa: S105  (the name of a row, not a secret)
OURS_ROW = "update/sked_ids"
VERSION = 1
# server limits: rows on a board, and rows of one call whatever its SSID
MAX_ROWS = 100
MAX_PER_CALL = 10
MAX_NOTE = 80
MAX_LENGTH = timedelta(hours=24)
# the server holds a row to 30 days by its own clock
MAX_AHEAD = timedelta(days=31)
MAX_ENTRIES = 1000
TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", re.ASCII)
ID = re.compile(r"^[0-9a-f]{12}$")
TOKEN = re.compile(r"^[0-9a-f]{32}$")
# Unicode category letters a note may hold, besides the plain space
NOTE_KINDS = frozenset("LMNPS")


@dataclass(frozen=True)
class Sked:
    id: str
    call: str
    start: datetime
    end: datetime
    dial: str
    note: str


@dataclass(frozen=True)
class Board:
    """The skeds in start order, and whether the board is closed to new ones."""
    closed: bool
    skeds: tuple[Sked, ...]


EMPTY = Board(False, ())


def endpoint_url(board_url: str) -> str:
    return urljoin(board_url, ENDPOINT_PATH)


def when(text: object) -> datetime | None:
    """Parse a time like `2026-11-14T18:00:00Z`; return None for anything else."""
    if not isinstance(text, str) or TIME.fullmatch(text) is None:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def plain_note(text: object) -> bool:
    return isinstance(text, str) and len(text) <= MAX_NOTE and all(c == " " or unicodedata.category(c)[0] in NOTE_KINDS for c in text)


def clean_note(text: str) -> str:
    """Make the operator's text fit the board: odd characters become spaces, runs collapse."""
    kept = "".join(c if unicodedata.category(c)[0] in NOTE_KINDS else " " for c in text)
    return " ".join(kept.split())[:MAX_NOTE].strip()


def our_call(text: str) -> str:
    """Return the call as posted (upper case, no `-0`), or '' if it is not a usable amateur call."""
    try:
        call = format_call(*parse_call(text.strip()))
    except CallsignError:
        return ""
    return "" if call_problem(call) else call


def sked_of(entry: object, now: datetime) -> Sked | None:
    if not isinstance(entry, dict):
        return None
    ident, call, dial, note = entry.get("id"), entry.get("call"), entry.get("dial"), entry.get("note", "")
    start, end = when(entry.get("from")), when(entry.get("to"))
    if not (isinstance(ident, str) and ID.fullmatch(ident) and isinstance(call, str) and isinstance(dial, str) and is_dial(dial) and plain_note(note)):
        return None
    if start is None or end is None or not start < end <= start + MAX_LENGTH or end <= now or start > now + MAX_AHEAD or not call or our_call(call) != call:
        return None
    return Sked(ident, call, start, end, dial, str(note))


def parse_board(body: bytes | str, now: datetime) -> Board | None:
    try:
        return board_of(json.loads(body), now)
    except (ValueError, RecursionError):  # RecursionError: JSON nested thousands deep
        return None


def board_of(data: Any, now: datetime) -> Board | None:
    """Return the board in a JSON value, or None if it is malformed; a bad row is dropped alone."""
    if not isinstance(data, dict) or data.get("v") != VERSION or isinstance(data.get("v"), bool) or not isinstance(data.get("skeds"), list):
        return None
    closed = data.get("closed", False)
    if not isinstance(closed, bool):
        return None
    found: dict[str, Sked] = {}
    for entry in data["skeds"][:MAX_ENTRIES]:
        if (sked := sked_of(entry, now)) is not None and sked.id not in found:
            found[sked.id] = sked
    return Board(closed, limited(sorted(found.values(), key=lambda s: (s.start, s.id))))


def limited(skeds: list[Sked]) -> tuple[Sked, ...]:
    per_call: dict[str, int] = {}
    kept: list[Sked] = []
    for sked in skeds:
        base = sked.call.split("-")[0]
        if per_call.get(base, 0) < MAX_PER_CALL and len(kept) < MAX_ROWS:
            per_call[base] = per_call.get(base, 0) + 1
            kept.append(sked)
    return tuple(kept)


def to_come(skeds: tuple[Sked, ...], now: datetime) -> tuple[Sked, ...]:
    return tuple(s for s in skeds if s.end > now)


def board_text(board: Board, fetched: datetime) -> str:
    return json.dumps({"v": VERSION, "closed": board.closed, "fetched": iso(fetched), "skeds": [row_of(s) for s in board.skeds]})


def row_of(sked: Sked) -> dict[str, str]:
    return {"id": sked.id, "call": sked.call, "from": iso(sked.start) or "", "to": iso(sked.end) or "", "dial": sked.dial, "note": sked.note}


def kept_board(text: str, now: datetime) -> tuple[Board, datetime | None] | None:
    board = parse_board(text, now)
    if board is None:
        return None
    try:
        fetched = when(json.loads(text).get("fetched"))
    except (ValueError, RecursionError, AttributeError):
        fetched = None
    return board, fetched


def ids_text(ids: list[str]) -> str:
    return json.dumps(ids)


def kept_ids(text: str | None) -> list[str]:
    try:
        data: Any = json.loads(text or "[]")
    except (ValueError, RecursionError):
        return []
    return [i for i in data if isinstance(i, str) and ID.fullmatch(i)][:MAX_ROWS] if isinstance(data, list) else []


def request_body(action: str, token: str, fields: dict[str, str]) -> bytes:
    return json.dumps({"action": action, "token": token, **fields}, ensure_ascii=False).encode("utf-8")
