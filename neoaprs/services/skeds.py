"""The sked board: when people will be on the air, as the project's server keeps it.

Read at most every SKEDS_EVERY_SEC, posted to only on the operator's press; the update-check
switch turns both off. A secret token lets only this installation delete its skeds."""

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
from neoaprs.services.updatecheck import ENV_SWITCH, FIRST_SEC
from neoaprs.signal import Signal
from neoaprs.skeds import (
    EMPTY,
    HIDDEN_ROW,
    MAX_LENGTH,
    MAX_PAST_ROWS,
    MAX_ROWS,
    OURS_ROW,
    SKED_TOKEN,
    SKEDS_ROW,
    SKEDS_URL,
    TOKEN,
    Board,
    Sked,
    board_of,
    board_text,
    endpoint_url,
    ids_text,
    kept_board,
    kept_ids,
    our_call,
    past_of,
    past_tests,
    past_url,
    request_body,
    to_come,
)
from neoaprs.tasks import TaskSet, every
from neoaprs.updatefetch import fetch_answer, post_board
from neoaprs.versions import Frequency, on_this_computer

log = logging.getLogger("neoaprs.update")

EVERY_SEC = 6 * 3600.0
# least time between two reads of the board, whoever asks
SKEDS_EVERY_SEC = 15 * 60.0
# least wait after a read or post that did not reach the server; not counted as a read
RETRY_SEC = 60.0
EXPIRE_SEC = 30.0
# a full board is about 30 KB, up to twice that with every character escaped
MAX_BYTES = 131072
# how far ahead the server lets a sked begin
MAX_AHEAD = timedelta(days=30)
# development and tests: a server on this computer, instead of SKEDS_URL
ENV_URL = "NEOAPRS_SKEDS_URL"
State = Literal["ok", "offline", "off", "closed"]
# (address, version, platform, max bytes) -> (status, body)
Fetch = Callable[[str, str, str, int], Awaitable[tuple[int, bytes] | None]]
# (address, JSON body, version, platform, max bytes) -> (status, body)
Post = Callable[[str, bytes, str, str, int], Awaitable[tuple[int, bytes] | None]]


class SkedError(CodedError):
    """A sked cannot be posted or deleted now, for a reason the operator can do something about."""


class Skeds:
    def __init__(
        self,
        version: str,
        platform: str,
        config: ConfigSource,
        frequencies: Callable[[], list[Frequency]] = list,
        fetch: Fetch = fetch_answer,
        post: Post = post_board,
        first_sec: float = FIRST_SEC,
        every_sec: float = EVERY_SEC,
        environ: Mapping[str, str] = os.environ,
        memory: Memory | None = None,
        clock: Clock = utcnow,
        monotonic: Callable[[], float] = time.monotonic,
        expire_sec: float = EXPIRE_SEC,
    ) -> None:
        self.version, self.platform = version, platform
        self._config = config
        # dials suggested for the HF radio; in the topic so the tab need not depend on a radio
        self._frequencies = frequencies
        self._fetch, self._post = fetch, post
        self.first_sec, self.every_sec, self.expire_sec = first_sec, every_sec, expire_sec
        self._environ = environ
        self._memory = memory
        self._clock, self._monotonic = clock, monotonic
        # last board as understood, ended skeds included; `rows` drops them and `past` takes them
        self._board = EMPTY
        # the past tests the server last told; never stored
        self._past: tuple[Sked, ...] = ()
        self.fetched_at: datetime | None = None
        # whether the last try reached and understood the server; None before the first
        self._reached: bool | None = None
        self._ours: list[str] = []
        # past tests taken off this installation's list, newest first; never more than the server lists
        self._hidden: list[str] = []
        # call refused as `closed` while the board then read said open: blocked until the next read
        self._shut = ""
        # kept in the row SKED_TOKEN; without a memory it lasts as long as this object
        self._token: str | None = None
        self._told = (0, 0)
        self.changed: Signal[[]] = Signal("skeds.changed")
        self.asked = 0
        self._last: float | None = None
        # one exchange with the server at a time, so a late read cannot undo a post
        self._busy = asyncio.Lock()
        self._tasks = TaskSet(log, "skeds")

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    @property
    def url(self) -> str:
        """The board's address: the project's, or `NEOAPRS_SKEDS_URL` if that is on this host."""
        given = self._environ.get(ENV_URL, "").strip()
        return given if on_this_computer(given) else SKEDS_URL

    @property
    def state(self) -> State:
        """`off` if the check is off, `offline` if unreachable, `closed` if full, else `ok`."""
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
        """Return the skeds still to come by the daemon's clock, nearest first; none if off."""
        if not self.enabled:
            return []
        ended = {s.id for s in self._past}
        return [s for s in to_come(self._board.skeds, self._clock()) if s.id not in ended]

    def past(self) -> list[Sked]:
        """Return the past tests, newest first (`past_tests`), less those taken off here; none if off."""
        hidden = set(self._hidden)
        return [s for s in self._all_past() if s.id not in hidden] if self.enabled else []

    def _all_past(self) -> tuple[Sked, ...]:
        return past_tests(self._board.skeds, self._past, self._clock())

    async def hide(self, ids: list[str]) -> bool:
        """Take past tests off this installation's list (the server keeps them); False, and nothing
        taken off, unless every id is a past test shown now."""
        shown = {s.id for s in self.past()}
        if not ids or not shown.issuperset(ids):
            return False
        self._hidden = [*dict.fromkeys(ids), *(i for i in self._hidden if i not in ids)][:MAX_PAST_ROWS]
        if self._memory is not None:
            await self._memory.put_settings({HIDDEN_ROW: ids_text(self._hidden)})
        self._tell()
        return True

    async def start(self) -> None:
        if not self._tasks and self.enabled:
            self._tasks.spawn(self._run(), "skeds")
            self._tasks.spawn(every(self.expire_sec, self._expire, "the HF test board's ends"), "skeds-expire")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _run(self) -> None:
        await self._kept()
        await every(self.every_sec, self.ask, "the HF test board", first=self.first_sec)

    async def _kept(self) -> None:
        """Tell the kept board and ids before asking the server."""
        if self._memory is None or self.fetched_at is not None or self._board is not EMPTY:
            return
        found = kept_board(await self._memory.setting(SKEDS_ROW) or "", self._clock())
        if found is not None:
            self._board, self.fetched_at = found
        self._ours = kept_ids(await self._memory.setting(OURS_ROW))
        self._hidden = kept_ids(await self._memory.setting(HIDDEN_ROW))
        self._tell()

    def _tell(self) -> None:
        self._told = (len(self.rows()), len(self.past()))
        self.changed.emit()

    def _expire(self) -> None:
        if (len(self.rows()), len(self.past())) != self._told:
            self._tell()

    # ---- reading
    def wanted(self) -> None:
        """Read the board now, unless it was read within SKEDS_EVERY_SEC or the check is off."""
        if self._begin():
            self._tasks.spawn(self._read(), "skeds-ask")

    async def ask(self) -> None:
        """Read the board under the same rule as `wanted`."""
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
            log.debug("the HF test board could not be fetched from %s", self.url)
            self._unreached()
            return
        status, body = answer
        # a 404 is a board nobody has posted to yet, or one briefly away: our ids are kept
        board = EMPTY if status == 404 else None if status != 200 else self._parsed(body)
        if board is None:
            log.debug("the HF test board at %s is not usable (status %s)", self.url, status)
            self._unreached()
            return
        told = await self._read_past()
        await self._take(board, prune=status == 200, past_told=told)

    async def _read_past(self) -> bool:
        """Take the server's past tests; a 404 is none (a server without them), any other failure keeps the last.

        Return whether the server told them."""
        address = past_url(self.url)
        answer = await self._fetch(address, self.version, self.platform, MAX_BYTES)
        if answer is not None and answer[0] == 404:
            self._past = ()
            return True
        found = self._parsed_past(answer[1]) if answer is not None and answer[0] == 200 else None
        if found is None:
            log.debug("the past HF tests at %s could not be read; the last ones stand", address)
            return False
        self._past = found
        return True

    def _parsed_past(self, body: bytes) -> tuple[Sked, ...] | None:
        try:
            return past_of(json.loads(body), self._clock())
        except (ValueError, RecursionError):
            return None

    def _parsed(self, body: bytes) -> Board | None:
        try:
            return board_of(json.loads(body), self._clock())
        except (ValueError, RecursionError):
            return None

    def _unreached(self) -> None:
        """Mark the server unreached (`offline`); the board may be read again after RETRY_SEC."""
        self._last = self._monotonic() - SKEDS_EVERY_SEC + RETRY_SEC
        if self._reached is not False:
            self._reached = False
            self._tell()

    async def _take(self, board: Board, prune: bool = True, past_told: bool = False) -> None:
        """Keep and tell the server's board; drop our ids no longer on it (not on 404), and the
        hidden ids no longer among the past tests once the server told them."""
        self._board, self._reached, self.fetched_at, self._shut = board, True, self._clock(), ""
        rows = {SKEDS_ROW: board_text(board, self.fetched_at)}
        if prune:
            on_board = {s.id for s in board.skeds}
            self._ours = [i for i in self._ours if i in on_board]
        rows[OURS_ROW] = ids_text(self._ours)
        listed = {s.id for s in self._all_past()}
        if prune and past_told and any(i not in listed for i in self._hidden):
            self._hidden = [i for i in self._hidden if i in listed]
            rows[HIDDEN_ROW] = ids_text(self._hidden)
        if self._memory is not None:
            await self._memory.put_settings(rows)
        self._tell()

    # ---- posting
    async def post(self, start: datetime, end: datetime, dial: str, note: str) -> None:
        """Post a sked of our call.

        Raise SkedError for a refusal the operator can act on or an unreachable board."""
        call, now = our_call(self._config().station_call), self._clock()
        if not call or end - start > MAX_LENGTH or end <= start:
            # the form cannot make one: a page bug, so the log has it
            raise ValueError(f"a sked of {call or 'no call'} from {iso(start)} to {iso(end)} cannot be posted")
        if end <= now:
            raise SkedError("that test has ended already", "sked.past")
        if start > now + MAX_AHEAD:
            # the page's clock may be ahead of ours
            raise SkedError("that test begins more than 30 days ahead", "sked.far")
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
        """Delete a sked of ours; one the server says is not ours is only dropped from our ids."""
        async with self._busy:
            data = await self._send("remove", {"id": ident}, "")
            self._ours = [i for i in self._ours if i != ident]
            if data is not None:
                await self._answered(data)

    async def _answered(self, data: dict[str, Any]) -> None:
        """Take the answer's board as read, and its past tests when it has them (an older server's has none);
        if the board is missing or invalid, read the board again."""
        board = board_of(data.get("board"), self._clock())
        if board is None:
            log.warning("the HF test board's answer had no usable board; it is read again")
            await self._get()
            return
        past = past_of(data["past"], self._clock()) if "past" in data else None
        if past is not None:
            self._past = past
        self._last = self._monotonic()
        await self._take(board, past_told=past is not None)

    async def _send(self, action: str, fields: dict[str, str], call: str) -> dict[str, Any] | None:
        """Return the endpoint's answer when it says ok; None for a refusal needing no message."""
        if not self.enabled:
            raise SkedError("the HF test board could not be reached just now; try again later", "sked.unreachable")
        got = await self._post(
            endpoint_url(self.url),
            request_body(action, await self._secret(), fields),
            self.version,
            self.platform,
            MAX_BYTES,
        )
        if got is None:
            self._unreached()
            raise SkedError("the HF test board could not be reached just now; try again later", "sked.unreachable")
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
            raise SkedError("too many tests were posted from here lately; try again later", "sked.rate")
        if reason == "full":
            raise SkedError("the board has no room for another test now", "sked.full")
        if reason == "past":
            raise SkedError("that test has ended already", "sked.past")
        if reason == "too_far":
            raise SkedError("that test begins more than 30 days ahead", "sked.far")
        if reason == "closed" and action == "add":
            # the board says whether it is closed to everyone; if open, only this call is blocked
            await self._get()
            if self._reached:
                self._last = self._monotonic()
            if self._reached and not self._board.closed:
                log.info("the HF test board is closed to %s", call)
                self._shut = call.split("-")[0]
                self._tell()
        elif reason == "not_yours" and action == "remove":
            log.info(
                "the HF test is not ours: it was posted by another installation, or the data folder is another one"
            )
            await self._get()
        else:
            log.warning("the HF test board refused the %s (status %s, reason %r)", action, status, reason)
            raise SkedError("the HF test board could not be reached just now; try again later", "sked.unreachable")

    async def token(self) -> str:
        """The installation's token, which the chat sends too."""
        return await self._secret()

    async def _secret(self) -> str:
        """Return the sked token (32 hex characters), made on first use and kept in the database."""
        if self._token is None:
            kept = None if self._memory is None else await self._memory.setting(SKED_TOKEN)
            if kept is not None and TOKEN.fullmatch(kept):
                self._token = kept
            else:
                self._token = secrets.token_hex(16)
                if self._memory is not None:
                    await self._memory.put_settings({SKED_TOKEN: self._token})
        return self._token
