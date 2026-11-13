"""The sked board and how it is understood: a sked is a call, two instants, a dial and a short note, and the board is the file `skeds.json` of the project's server (server/neo/api/v1/skeds.php writes it, services/skeds.py reads it).

Nothing the server says is believed: `parse_board` checks every row again as the server does and more, and a row that is not right is dropped alone, the rest of the board stands. A row is right when its id is 12 lowercase hex digits, its call is an
amateur call as `callsign.py` writes it (upper case, no `-0`), its times are `2026-11-14T18:00:00Z` and real instants with the end after the start by 24 hours at most, its dial is `7.0541 MHz USB` and its note is at most 80 characters of letters,
marks, digits, punctuation, symbols and plain spaces (no control or invisible character, no other kind of space). A board holds at most 100 rows and ten of one call; what has ended by the reader's own clock, or begins more than a month ahead of it, is dropped.
What the daemon posts is made here too (`request_body`), so that the form of both directions is in one place."""
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

SKEDS_URL = "https://neo.oh2gba.eu/skeds.json"                # the board, a static file (no PHP) that the endpoint writes at every accepted change
ENDPOINT_PATH = "/api/v1/skeds.php"                           # where a sked is posted and deleted, on the server the board is read from
SKEDS_ROW = "update/skeds"                                    # the last board as it was understood, kept by the daemon in the settings table (not a setting)
SKED_TOKEN = "update/sked_token"  # noqa: S105  (the name of a row, not a secret)  # the random secret of this installation that goes with each sked it posts, so that only it can delete them (services/skeds.py); never the installation's number, never sent when reading, never shown in the log or the support bundle (its name says token)
OURS_ROW = "update/sked_ids"                                  # the ids of the skeds this installation was answered, a JSON list (not a setting)
VERSION = 1                                                   # the `v` of the board
MAX_ROWS = 100                                                # the most rows a board holds (the server's own limit)
MAX_PER_CALL = 10                                             # the most rows of one call, whatever its SSID (the server's own limit)
MAX_NOTE = 80
MAX_LENGTH = timedelta(hours=24)                              # the longest a sked is
MAX_AHEAD = timedelta(days=31)                                # how far ahead a row may begin for the reader to believe it (the server holds it to 30 days by its own clock)
MAX_ENTRIES = 1000                                            # how many entries of a board's list are looked at at all
TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID = re.compile(r"^[0-9a-f]{12}$")
TOKEN = re.compile(r"^[0-9a-f]{32}$")
NOTE_KINDS = frozenset("LMNPS")                               # the first letters of the Unicode categories a note may hold, besides the plain space


@dataclass(frozen=True)
class Sked:
    """A call on the air at a dial from one instant to another."""
    id: str
    call: str
    start: datetime
    end: datetime
    dial: str
    note: str


@dataclass(frozen=True)
class Board:
    """What the project's server says: the skeds in the order of their start, and whether the board is closed to new ones."""
    closed: bool
    skeds: tuple[Sked, ...]


EMPTY = Board(False, ())


def endpoint_url(board_url: str) -> str:
    """The address skeds are posted to: the same server as the board, at its fixed path."""
    return urljoin(board_url, ENDPOINT_PATH)


def when(text: object) -> datetime | None:
    """A time as the board writes it, `2026-11-14T18:00:00Z`, or None for anything else (a text that is not of that form, or not a real instant)."""
    if not isinstance(text, str) or TIME.fullmatch(text) is None:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def plain_note(text: object) -> bool:
    """Whether the note is one that may be on the board: at most MAX_NOTE characters, each a letter, mark, digit, punctuation or symbol or a plain space."""
    return isinstance(text, str) and len(text) <= MAX_NOTE and all(c == " " or unicodedata.category(c)[0] in NOTE_KINDS for c in text)


def clean_note(text: str) -> str:
    """The note as the operator's text makes it for the board: a control, invisible or odd space character is a space, runs of spaces are one, and the ends are cut."""
    kept = "".join(c if unicodedata.category(c)[0] in NOTE_KINDS else " " for c in text)
    return " ".join(kept.split())[:MAX_NOTE].strip()


def our_call(text: str) -> str:
    """The call as it is posted (upper case, no `-0`); '' when it is not an amateur call that may be used."""
    try:
        call = format_call(*parse_call(text.strip()))
    except CallsignError:
        return ""
    return "" if call_problem(call) else call


def sked_of(entry: object, now: datetime) -> Sked | None:
    """One row of a board as a Sked, or None when it is not right (see the module's text); `now` is the reader's own clock."""
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
    """The board in the server's answer, or None when it is not one (see `board_of`)."""
    try:
        return board_of(json.loads(body), now)
    except (ValueError, RecursionError):               # (a board nested thousands deep is one too)
        return None


def board_of(data: Any, now: datetime) -> Board | None:
    """The board in a JSON value, or None when it is not one (not an object, not version 1, no list of skeds, a `closed` that is not true or false: the last board stands then). Each row that is not right is dropped alone."""
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
    """The rows in order with the limits of a board put on them: at most MAX_PER_CALL of one call (its base, whatever the SSID) and MAX_ROWS in all; the later rows are the ones left out."""
    per_call: dict[str, int] = {}
    kept: list[Sked] = []
    for sked in skeds:
        base = sked.call.split("-")[0]
        if per_call.get(base, 0) < MAX_PER_CALL and len(kept) < MAX_ROWS:
            per_call[base] = per_call.get(base, 0) + 1
            kept.append(sked)
    return tuple(kept)


def to_come(skeds: tuple[Sked, ...], now: datetime) -> tuple[Sked, ...]:
    """What has not ended by the clock."""
    return tuple(s for s in skeds if s.end > now)


def board_text(board: Board, fetched: datetime) -> str:
    """The board as the settings table keeps it: the server's own form, with the time it was read."""
    return json.dumps({"v": VERSION, "closed": board.closed, "fetched": iso(fetched), "skeds": [row_of(s) for s in board.skeds]})


def row_of(sked: Sked) -> dict[str, str]:
    """A sked in the server's own form."""
    return {"id": sked.id, "call": sked.call, "from": iso(sked.start) or "", "to": iso(sked.end) or "", "dial": sked.dial, "note": sked.note}


def kept_board(text: str, now: datetime) -> tuple[Board, datetime | None] | None:
    """(the board, when it was read) from the row `board_text` made, checked again as an answer is; None for a row that is not one (a row someone edited by hand is as good as none)."""
    board = parse_board(text, now)
    if board is None:
        return None
    try:
        fetched = when(json.loads(text).get("fetched"))
    except (ValueError, RecursionError, AttributeError):
        fetched = None
    return board, fetched


def ids_text(ids: list[str]) -> str:
    """The ids of our skeds as the settings table keeps them."""
    return json.dumps(ids)


def kept_ids(text: str | None) -> list[str]:
    """The ids of the row `ids_text` made, those that are ids; [] for anything else."""
    try:
        data: Any = json.loads(text or "[]")
    except (ValueError, RecursionError):
        return []
    return [i for i in data if isinstance(i, str) and ID.fullmatch(i)][:MAX_ROWS] if isinstance(data, list) else []


def request_body(action: str, token: str, fields: dict[str, str]) -> bytes:
    """The body of a request to the endpoint: `{"action": "add", "token": ..., ...}` as JSON."""
    return json.dumps({"action": action, "token": token, **fields}, ensure_ascii=False).encode("utf-8")
