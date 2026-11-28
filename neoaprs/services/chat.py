"""The chat of the HF tests tab, as the project's server keeps it: read every EVERY_SEC while the daemon
runs, with the fingerprints of the last answer so that an unchanged chat costs no body, and posted to
only with a line the operator wrote. The update-check switch turns both off. Nothing goes on the air."""

import asyncio
import json
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal
from urllib.parse import urljoin

from neoaprs.chat import (
    CHAT_URL,
    EMPTY,
    ENDPOINT_PATH,
    MAX_ID,
    SEEN_ROW,
    Chat,
    Line,
    chat_of,
    clean_text,
    request_body,
    seen_of,
)
from neoaprs.coded import CodedError
from neoaprs.services.common import ConfigSource
from neoaprs.services.memory import Memory
from neoaprs.services.updatecheck import ENV_SWITCH
from neoaprs.signal import Signal
from neoaprs.skeds import our_call
from neoaprs.tasks import TaskSet
from neoaprs.updatefetch import Fresh, fetch_fresh, post_board
from neoaprs.versions import on_this_computer

log = logging.getLogger("neoaprs.chat")

EVERY_SEC = 15.0
# new lines notify at most once in this time, however many came
NOTIFY_SEC = 60.0
# a wait is drawn this share longer or shorter, so that installations do not ask in step
JITTER = 0.2
# while the server does not answer, the wait doubles up to this
MAX_WAIT_SEC = 600.0
# 100 lines of 200 characters, every one escaped
MAX_BYTES = 262144
# development and tests: a server on this computer, instead of CHAT_URL
ENV_URL = "NEOAPRS_CHAT_URL"
State = Literal["ok", "offline", "off", "closed"]
# (address, version, platform, etag, last modified, max bytes) -> the answer
Fetch = Callable[[str, str, str, str, str, int], Awaitable[Fresh | None]]
# (address, JSON body, version, platform, max bytes) -> (status, body)
Post = Callable[[str, bytes, str, str, int], Awaitable[tuple[int, bytes] | None]]


class ChatError(CodedError):
    """A line cannot be said now, for a reason the operator can do something about."""


class ChatRoom:
    def __init__(
        self,
        version: str,
        platform: str,
        config: ConfigSource,
        token: Callable[[], Awaitable[str]],
        fetch: Fetch = fetch_fresh,
        post: Post = post_board,
        environ: Mapping[str, str] = os.environ,
        memory: Memory | None = None,
        draw: Callable[[float, float], float] = random.uniform,
        every_sec: float = EVERY_SEC,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.version, self.platform = version, platform
        self._config, self._token = config, token
        self._fetch, self._post = fetch, post
        self._environ, self._memory, self._draw = environ, memory, draw
        self.every_sec = every_sec
        self._monotonic = monotonic
        self._read = False  # a read after the start brought its lines
        self._notified: float | None = None
        self._chat = EMPTY
        self._lines: dict[int, Line] = {}
        # whether the last try reached and understood the server; None before the first
        self._reached: bool | None = None
        self.failures = 0
        # what the last answer said of itself, sent back so that an unchanged chat is a 304
        self._etag = self._modified = ""
        # the newest id seen, kept in SEEN_ROW; None before the first read of a new installation
        self._seen: int | None = None
        self._loaded = False
        self._ours: set[int] = set()
        # the call base the server refused as `closed` while the chat said open
        self._shut = ""
        self.asked = 0
        self.changed: Signal[[]] = Signal("chat.changed")
        self.lines_changed: Signal[[list[int]]] = Signal("chat.lines_changed")
        self.fresh: Signal[[list[Line]]] = Signal("chat.fresh")
        self._tasks = TaskSet(log, "chat")

    @property
    def enabled(self) -> bool:
        return self._environ.get(ENV_SWITCH) != "0"

    @property
    def url(self) -> str:
        """The chat's address: the project's, or `NEOAPRS_CHAT_URL` if that is on this host."""
        given = self._environ.get(ENV_URL, "").strip()
        return given if on_this_computer(given) else CHAT_URL

    @property
    def state(self) -> State:
        if not self.enabled:
            return "off"
        if self._reached is False:
            return "offline"
        mine = our_call(self._config().station_call).split("-")[0]
        return "closed" if self._chat.closed or (self._shut != "" and self._shut == mine) else "ok"

    def lines(self) -> list[Line]:
        """The lines oldest first; none while the switch is off."""
        return list(self._lines.values()) if self.enabled else []

    def line(self, ident: int) -> Line | None:
        return self._lines.get(ident) if self.enabled else None

    def ours(self, line: Line) -> bool:
        """Whether this installation said the line, or it is under our call."""
        return line.id in self._ours or line.call == our_call(self._config().station_call)

    async def start(self) -> None:
        if not self._tasks and self.enabled:
            self._tasks.spawn(self._run(), "chat")

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    def wait_sec(self) -> float:
        """The wait before the next read: EVERY_SEC, doubled for each failure up to MAX_WAIT_SEC, jittered."""
        base = min(self.every_sec * 2.0 ** min(self.failures, 16), MAX_WAIT_SEC)
        return base * (1.0 + self._draw(-JITTER, JITTER))

    async def _run(self) -> None:
        await asyncio.sleep(self._draw(0.0, self.every_sec))
        while True:
            try:
                await self.poll()
            except Exception:
                log.exception("reading the chat failed")
            await asyncio.sleep(self.wait_sec())

    async def _load(self) -> None:
        if not self._loaded:
            self._loaded = True
            self._seen = None if self._memory is None else seen_of(await self._memory.setting(SEEN_ROW))

    # ---- reading
    async def poll(self) -> None:
        """Read the chat once; an unchanged one (304, or the same `written` and newest id) changes nothing."""
        if not self.enabled:
            return
        await self._load()
        self.asked += 1
        answer = await self._fetch(self.url, self.version, self.platform, self._etag, self._modified, MAX_BYTES)
        if answer is None or answer.status not in (200, 304, 404):
            self._unreached(None if answer is None else answer.status)
            return
        if answer.status == 304:
            self._reached_again()
            return
        chat = EMPTY if answer.status == 404 else self._parsed(answer.body)
        if chat is None:
            self._unreached(answer.status)
            return
        self._etag, self._modified = answer.etag, answer.modified
        # a host that sends neither fingerprint: the same `written` and newest id is the same chat
        await self._take(chat, unmarked=not (answer.etag or answer.modified))

    def _parsed(self, body: bytes) -> Chat | None:
        try:
            return chat_of(json.loads(body))
        except (ValueError, RecursionError):
            return None

    def _unreached(self, status: int | None) -> None:
        """One line in the log for each change of state, never an error: the operator can do nothing about it."""
        self.failures += 1
        if self._reached is not False:
            log.info(
                "the chat at %s could not be read (%s); it is asked again less often", self.url, status or "no answer"
            )
            self._reached = False
            self.changed.emit()

    def _reached_again(self) -> None:
        self.failures = 0
        if self._reached is not True:
            if self._reached is False:
                log.info("the chat at %s is read again", self.url)
            self._reached = True
            self.changed.emit()

    async def _take(self, chat: Chat, unmarked: bool = False) -> None:
        """Keep the server's chat; tell the lines that came or went, and the new ones of others once."""
        same = (
            unmarked
            and chat.written is not None
            and chat.written == self._chat.written
            and _newest(chat) == _newest(self._chat)
        )
        before = self.state
        self._chat, self._shut = chat, ""
        self._reached_again()
        if same:
            if self.state != before:
                self.changed.emit()
            return
        lines = {line.id: line for line in chat.lines}
        moved = sorted(set(lines) ^ set(self._lines) | {i for i in lines if self._lines.get(i, lines[i]) != lines[i]})
        self._lines = lines
        fresh = self._worth_telling(await self._mark(chat))
        if self.state != before:
            self.changed.emit()
        if moved:
            self.lines_changed.emit(moved)
        if fresh:
            self.fresh.emit(fresh)

    def _worth_telling(self, fresh: list[Line]) -> list[Line]:
        """None of what the first read after the start brings, and at most one notice in NOTIFY_SEC."""
        first, self._read = not self._read, True
        now = self._monotonic()
        if first or not fresh or (self._notified is not None and now - self._notified < NOTIFY_SEC):
            return []
        self._notified = now
        return fresh

    async def _mark(self, chat: Chat) -> list[Line]:
        """The lines of others newer than the newest seen before; the mark moves to the newest of now.

        A new installation and a chat whose ids went back (the server's was made anew) tell none."""
        newest = _newest(chat)
        if newest is None:
            return []
        fresh = (
            []
            if self._seen is None or newest < self._seen
            else [line for line in chat.lines if line.id > self._seen and not self.ours(line)]
        )
        if newest != self._seen:
            self._seen = newest
            if self._memory is not None:
                await self._memory.put_settings({SEEN_ROW: str(newest)})
        return fresh

    # ---- saying
    async def say(self, text: str) -> None:
        """Post a line of our call. Raise ChatError for a refusal or an unreachable server."""
        call, line = our_call(self._config().station_call), clean_text(text)
        if not call or not line:
            # the page sends neither: a page bug, so the log has it
            raise ValueError("a line of the chat needs a call and a text")
        if not self.enabled:
            raise ChatError("the chat could not be reached just now; try again later", "chat.unreachable")
        await self._load()
        got = await self._post(
            urljoin(self.url, ENDPOINT_PATH),
            request_body(await self._token(), call, line),
            self.version,
            self.platform,
            MAX_BYTES,
        )
        if got is None:
            self._unreached(None)
            raise ChatError("the chat could not be reached just now; try again later", "chat.unreachable")
        data = _json(got[1])
        if data.get("ok") is True:
            ident = data.get("id")
            if isinstance(ident, int) and 0 < ident < MAX_ID:
                self._ours.add(ident)
            chat = chat_of(data.get("chat"))
            if chat is None:
                await self.poll()
            else:
                await self._take(chat)
            return
        await self._refused(data.get("reason"), got[0], call)

    async def _refused(self, reason: object, status: int, call: str) -> None:
        if reason == "rate":
            raise ChatError("too many lines were said from here just now; try again in a minute", "chat.rate")
        if reason == "closed":
            await self.poll()
            if self._reached and not self._chat.closed:
                log.info("the chat is closed to %s", call)
                self._shut = call.split("-")[0]
                self.changed.emit()
            raise ChatError("the chat takes no lines now", "chat.closed")
        if status == 400:
            log.info("the chat did not take a line (reason %r)", reason)
            raise ChatError("the chat did not take that line", "chat.refused")
        log.warning("the chat refused a line (status %s, reason %r)", status, reason)
        raise ChatError("the chat could not be reached just now; try again later", "chat.unreachable")


def _newest(chat: Chat) -> int | None:
    return chat.lines[-1].id if chat.lines else None


def _json(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}
