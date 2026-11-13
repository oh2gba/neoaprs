"""The sked board: when people will be on the air, as the project's server keeps it (server/neo/api/v1/skeds.php; the board is the static file `SKEDS_URL`, neoaprs/skeds.py says how every row of it is checked). It is shaped like services/frequencies.py and is part of the
update check's kind of traffic: `NEOAPRS_UPDATE_CHECK=0` in the environment (the tests, the demo) reads and posts nothing and the board is `off`, and a test or a bench that needs a server names one on this computer with `NEOAPRS_SKEDS_URL`.

Reading: the board is fetched a minute after the start, every six hours, and when a page shows the Skeds tab (`wanted`), and never more often than every SKEDS_EVERY_SEC however many pages ask. The GET carries nothing about the station. A board that cannot be fetched or is
not one leaves the last board as it was and the state `offline`; a 404 is a board nobody has posted to yet. The last board is kept in the settings table (the row SKEDS_ROW) and told at the start before the server is asked, and what has ended by the daemon's own clock is dropped
every time the rows are told.

Posting is on the operator's press only: the call, the two times, the dial and the note go to the endpoint with this installation's sked token, 16 random bytes made the first time one is needed and kept in a row of its own (SKED_TOKEN: secret, never the installation's number and never
sent when reading); the server keeps its hash with the sked, so only this installation can delete it. The answer carries the new board, which is taken as read. The ids the server answered are `ours` (kept in the row OURS_ROW). A refusal of the server that the operator can
do something about (`rate`, `full`, `past`, `too_far`) is an error with a code; one they can do nothing about is told in the log, and the job is done as far as it can be (a closed board, or a call that is blocked, is the state `closed` until the board is read again; a delete of what is not ours is dropped from `ours`)."""
import asyncio
import json
import logging
import os
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from neoaprs.clock import Clock, iso, utcnow
from neoaprs.coded import CodedError
from neoaprs.services.common import ConfigSource
from neoaprs.services.memory import Memory
from neoaprs.signal import Signal
from neoaprs.skeds import (EMPTY, MAX_LENGTH, MAX_ROWS, OURS_ROW, SKED_TOKEN, SKEDS_ROW, SKEDS_URL, TOKEN, Board, Sked, board_of, board_text, endpoint_url, ids_text, kept_board, kept_ids, our_call, request_body, to_come)
from neoaprs.tasks import TaskSet, every
from neoaprs.updatefetch import fetch_answer, post_board
from neoaprs.versions import Frequency, on_this_computer

log = logging.getLogger("neoaprs.update")

FIRST_SEC = 60.0
EVERY_SEC = 6 * 3600.0
SKEDS_EVERY_SEC = 15 * 60.0                     # the least time between two reads of the board, whoever asks
RETRY_SEC = 60.0                                # the least time after a read or a post that did not reach the server: it is not counted as a read
EXPIRE_SEC = 30.0                               # how often what has ended is looked for
MAX_BYTES = 131072                              # a full board is some 30 KB (a hundred rows with notes), and up to twice that with every character escaped
MAX_AHEAD = timedelta(days=30)                  # how far ahead the server lets a sked begin
ENV_SWITCH = "NEOAPRS_UPDATE_CHECK"
ENV_URL = "NEOAPRS_SKEDS_URL"                   # development and tests: a server on this computer, instead of SKEDS_URL
State = Literal["ok", "offline", "off", "closed"]
Fetch = Callable[[str, str, str, int], Awaitable[tuple[int, bytes] | None]]      # (address, version, platform, the most bytes wanted) to the status and body
Post = Callable[[str, bytes, str, str, int], Awaitable[tuple[int, bytes] | None]]    # (address, the JSON body, version, platform, the most bytes wanted) to the status and body


class SkedError(CodedError):
    """A sked cannot be posted or deleted now, for a reason the operator can do something about."""


class Skeds:
    def __init__(self, version: str, platform: str, config: ConfigSource, frequencies: Callable[[], list[Frequency]] = list, fetch: Fetch = fetch_answer, post: Post = post_board, first_sec: float = FIRST_SEC,
                 every_sec: float = EVERY_SEC, environ: Mapping[str, str] = os.environ, memory: Memory | None = None, clock: Clock = utcnow, monotonic: Callable[[], float] = time.monotonic,
                 expire_sec: float = EXPIRE_SEC) -> None:
        self.version, self.platform = version, platform
        self._config = config
        self._frequencies = frequencies                 # the dials the project suggests for the HF radio, which the tab offers (the topic carries them, so that the tab does not depend on a radio's state)
        self._fetch, self._post = fetch, post
        self.first_sec, self.every_sec, self.expire_sec = first_sec, every_sec, expire_sec
        self._environ = environ
        self._memory = memory
        self._clock, self._monotonic = clock, monotonic
        self._board = EMPTY                              # the last board as understood (the kept one until the server has answered), ended skeds and all: `rows` drops them
        self.fetched_at: datetime | None = None          # when the board was last taken, by the daemon's clock
        self._reached: bool | None = None                # whether the last try reached the server and understood it; None before the first
        self._ours: list[str] = []                       # the ids the server answered this installation, the newest first
        self._shut = ""                                  # the call the server refused with `closed` while the board read just after said open: it is blocked, and the board is closed to it until the next read
        self._token: str | None = None                   # kept in the row SKED_TOKEN; without a memory (the tests) it lasts as long as this object
        self._told = 0                                   # how many rows were told last
        self.changed: Signal[[]] = Signal("skeds.changed")
        self.asked = 0                                   # how many times the server was asked for the board
        self._last: float | None = None                  # when it was last asked, by `monotonic`
        self._busy = asyncio.Lock()                      # one exchange with the server at a time, so that a late read cannot undo a post
        self._tasks = TaskSet(log, "skeds")

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    @property
    def url(self) -> str:
        """The board's address: the project's, or, for development and tests, the one of `NEOAPRS_SKEDS_URL` when it is a server on this computer."""
        given = self._environ.get(ENV_URL, "").strip()
        return given if on_this_computer(given) else SKEDS_URL

    @property
    def state(self) -> State:
        """`off` while the check is off, `offline` while the server cannot be reached, `closed` while the board is closed to new skeds (by the moderator, or for our call), else `ok`."""
        if not self.enabled:
            return "off"
        if self._reached is False:
            return "offline"
        mine = our_call(self._config().station_call).split("-")[0]
        return "closed" if self._board.closed or (self._shut != "" and self._shut == mine) else "ok"

    @property
    def ours(self) -> frozenset[str]:
        return frozenset(self._ours)

    def frequencies(self) -> list[Frequency]:
        return self._frequencies()

    def rows(self) -> list[Sked]:
        """The skeds to come by the daemon's clock, the nearest first (none while the check is off)."""
        return list(to_come(self._board.skeds, self._clock())) if self.enabled else []

    async def start(self) -> None:
        if not self._tasks and self.enabled:
            self._tasks.spawn(self._run(), "skeds")
            self._tasks.spawn(every(self.expire_sec, self._expire, "the sked board's ends"), "skeds-expire")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await self._kept()
        await every(self.every_sec, self.ask, "the sked board", first=self.first_sec)

    async def _kept(self) -> None:
        """The board and our ids kept by an earlier run, told before the server is asked (inside the task: the start of the daemon does not wait for the database)."""
        if self._memory is None or self.fetched_at is not None or self._board is not EMPTY:
            return
        found = kept_board(await self._memory.setting(SKEDS_ROW) or "", self._clock())
        if found is not None:
            self._board, self.fetched_at = found
        self._ours = kept_ids(await self._memory.setting(OURS_ROW))
        self._tell()

    def _tell(self) -> None:
        self._told = len(self.rows())
        self.changed.emit()

    def _expire(self) -> None:
        if len(self.rows()) != self._told:
            self._tell()

    # ---- reading
    def wanted(self) -> None:
        """A page shows the Skeds tab: the board is read now, unless it was read less than SKEDS_EVERY_SEC ago or the check is off."""
        if self._begin():
            self._tasks.spawn(self._read(), "skeds-ask")

    async def ask(self) -> None:
        """Reads the board, with the same rule as `wanted`."""
        if self._begin():
            await self._read()

    def _begin(self) -> bool:
        if not self.enabled or (self._last is not None and self._monotonic() - self._last < SKEDS_EVERY_SEC):
            return False
        self._last = self._monotonic()
        self.asked += 1
        return True

    async def _read(self) -> None:
        async with self._busy:
            await self._get()

    async def _get(self) -> None:
        answer = await self._fetch(self.url, self.version, self.platform, MAX_BYTES)
        if answer is None:
            log.debug("the sked board could not be fetched from %s", self.url)
            self._unreached()
            return
        status, body = answer
        board = EMPTY if status == 404 else None if status != 200 else self._parsed(body)         # (a 404 is a board that nobody has posted to yet, or one that is away for a moment: our ids are kept)
        if board is None:
            log.debug("the sked board at %s is not usable (status %s)", self.url, status)
            self._unreached()
        else:
            await self._take(board, prune=status == 200)

    def _parsed(self, body: bytes) -> Board | None:
        try:
            return board_of(json.loads(body), self._clock())
        except (ValueError, RecursionError):
            return None

    def _unreached(self) -> None:
        """The server was not reached: the state is `offline`, and the board may be read again after RETRY_SEC, not only after SKEDS_EVERY_SEC."""
        self._last = self._monotonic() - SKEDS_EVERY_SEC + RETRY_SEC
        if self._reached is not False:
            self._reached = False
            self._tell()

    async def _take(self, board: Board, prune: bool = True) -> None:
        """The board as the server's answer has it: kept, and told. Our ids that are not on it any more are dropped, unless `prune` is false (the board was a 404). A call the server refused
        with `closed` is closed to it until a board is taken again: the moderator may have let it in since."""
        self._board, self._reached, self.fetched_at, self._shut = board, True, self._clock(), ""
        if prune:
            on_board = {s.id for s in board.skeds}
            self._ours = [i for i in self._ours if i in on_board]
        if self._memory is not None:
            await self._memory.put_settings({SKEDS_ROW: board_text(board, self.fetched_at), OURS_ROW: ids_text(self._ours)})
        self._tell()

    # ---- posting
    async def post(self, start: datetime, end: datetime, dial: str, note: str) -> None:
        """Posts a sked of our call. SkedError when the operator can do something about the refusal (`sked.rate`, `sked.full`, `sked.past`, `sked.far`) or the board cannot be reached (`sked.unreachable`); a closed board is no error (the state says it)."""
        call, now = our_call(self._config().station_call), self._clock()
        if not call or end - start > MAX_LENGTH or end <= start:
            raise ValueError(f"a sked of {call or 'no call'} from {iso(start)} to {iso(end)} cannot be posted")          # (the form cannot make one: the page's problem, the log has it)
        if end <= now:
            raise SkedError("that sked has ended already", "sked.past")
        if start > now + MAX_AHEAD:
            raise SkedError("that sked begins more than 30 days ahead", "sked.far")          # (the page's clock may be ahead of ours, and a row of the board may begin a little later than the server lets one be posted)
        fields = {"call": call, "from": iso(start) or "", "to": iso(end) or "", "dial": dial, "note": note}
        async with self._busy:
            data = await self._send("add", fields, call)
            if data is None:
                return
            ident = data.get("id")
            if isinstance(ident, str):
                self._ours = [ident, *(i for i in self._ours if i != ident)][:MAX_ROWS]
            await self._answered(data)

    async def delete(self, ident: str) -> None:
        """Deletes a sked of ours. What is not ours (the server says so) is only dropped from our ids: the operator can do nothing about it."""
        async with self._busy:
            data = await self._send("remove", {"id": ident}, "")
            self._ours = [i for i in self._ours if i != ident]
            if data is not None:
                await self._answered(data)

    async def _answered(self, data: dict[str, Any]) -> None:
        """The board of an answer is taken as read; one that is missing or is not a board is read again."""
        board = board_of(data.get("board"), self._clock())
        if board is None:
            log.warning("the sked board's answer had no usable board; it is read again")
            await self._get()
            return
        self._last = self._monotonic()
        await self._take(board)

    async def _send(self, action: str, fields: dict[str, str], call: str) -> dict[str, Any] | None:
        """The answer of the endpoint to the request when it says ok; None when the refusal is one nothing is to be said of (the board is closed to the call, a sked that is not ours); SkedError for the others."""
        if not self.enabled:
            raise SkedError("the sked board could not be reached just now; try again later", "sked.unreachable")
        got = await self._post(endpoint_url(self.url), request_body(action, await self._secret(), fields), self.version, self.platform, MAX_BYTES)
        if got is None:
            self._unreached()
            raise SkedError("the sked board could not be reached just now; try again later", "sked.unreachable")
        try:
            data = json.loads(got[1])
        except (ValueError, RecursionError):
            data = None
        if isinstance(data, dict) and data.get("ok") is True:
            return data
        reason = data.get("reason") if isinstance(data, dict) else None
        await self._refused(action, reason if isinstance(reason, str) else "", got[0], call)
        return None

    async def _refused(self, action: str, reason: str, status: int, call: str) -> None:
        if reason == "rate":
            raise SkedError("too many skeds were posted from here lately; try again later", "sked.rate")
        if reason == "full":
            raise SkedError("the sked board has no room for another sked now", "sked.full")
        if reason == "past":
            raise SkedError("that sked has ended already", "sked.past")
        if reason == "too_far":
            raise SkedError("that sked begins more than 30 days ahead", "sked.far")
        if reason == "closed" and action == "add":
            await self._get()                                       # (the board says whether it is closed to everyone; when it says open, the call is blocked)
            if self._reached:
                self._last = self._monotonic()
            if self._reached and not self._board.closed:
                log.info("the sked board is closed to %s", call)
                self._shut = call.split("-")[0]
                self._tell()
        elif reason == "not_yours" and action == "remove":
            log.info("the sked is not ours: it was posted by another installation, or the data folder is another one")
            await self._get()
        else:
            log.warning("the sked board refused the %s (status %s, reason %r)", action, status, reason)
            raise SkedError("the sked board could not be reached just now; try again later", "sked.unreachable")

    async def _secret(self) -> str:
        """The sked token: 32 lowercase hex characters from 16 random bytes, made the first time it is needed and kept in the database. A row that is not of that form is made again."""
        if self._token is None:
            kept = None if self._memory is None else await self._memory.setting(SKED_TOKEN)
            if kept is not None and TOKEN.fullmatch(kept):
                self._token = kept
            else:
                self._token = secrets.token_hex(16)
                if self._memory is not None:
                    await self._memory.put_settings({SKED_TOKEN: self._token})
        return self._token
