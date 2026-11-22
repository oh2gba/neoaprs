"""The search for the radio: every port that matches the pattern is listened to at once, for as
long as it takes, and the port whose bytes look like the radio's is the answer.

The search skips ports others hold (`Claims.others`) and gives its turn up while another waits.
"""
import asyncio
import logging
import os
from collections.abc import Callable, Coroutine, Iterator, Mapping
from typing import Any
from weakref import WeakKeyDictionary

from . import nodevices, serialprobe
from .claims import Claim, Claims
from .radiotype import FM_ID, RadioId
from .serialport import HeldError, NotChosenError, SerialError, is_url

log = logging.getLogger("neoaprs.tnc")

WAITING = "waiting while another radio looks for its port"

# radios waiting for the station's turn, by its lock
_QUEUED: "WeakKeyDictionary[asyncio.Lock, int]" = WeakKeyDictionary()


class _TurnOver(Exception):
    """The search gives its turn to a radio that waits."""


async def take_turn(lock: asyncio.Lock) -> None:
    """Wait for the station's one search (acquire the lock; the caller releases it)."""
    _QUEUED[lock] = _QUEUED.get(lock, 0) + 1
    try:
        await lock.acquire()
    finally:
        _QUEUED[lock] -= 1


def turn_wanted(lock: asyncio.Lock) -> bool:
    return _QUEUED.get(lock, 0) > 0


def turn_sec(nudge: bool, nudge_sec: float) -> float:
    return (nudge_sec if nudge else 0.0) + serialprobe.RELIST_SEC


def claimed(claims: Claims | None, holder: RadioId, named: bool = True) -> dict[str, str]:
    """Return the serial devices that are others' (what the search of `holder` leaves out)."""
    return {} if claims is None else {value: f"held by {claims.words(other)}" for value, other in claims.others(holder, "serial", named).items()}


class Others(Mapping[str, str]):

    def __init__(self, claims: Claims | None, holder: RadioId) -> None:
        self._claims, self._holder = claims, holder

    def __getitem__(self, value: str) -> str:
        return claimed(self._claims, self._holder)[value]

    def __iter__(self) -> Iterator[str]:
        return iter(claimed(self._claims, self._holder))

    def __len__(self) -> int:
        return len(claimed(self._claims, self._holder))


def held_elsewhere(claims: Claims | None, holder: RadioId, path: str) -> str:
    """Return why the radio may not open the port it is set to ("held by FM 2"), else "".

    Only what is held counts, or two radios set to one port would wait for each other for ever.
    """
    value = serialprobe.claim_value(path) if claims is not None else None
    return "" if value is None else claimed(claims, holder, named=False).get(value, "")


def let_go(path: str) -> None:
    """Close the device in another radio's search at once, so the radio set to it can open it."""
    listener = serialprobe.LISTENING.get(serialprobe.port_key(path))
    if listener is not None and (listener.is_open or listener.is_opening):
        log.info("probe: %s is let go: a radio is set to it", listener.path)
        listener.let_go()


async def may_open(claims: Claims | None, holder: RadioId, path: str, remembered: bool = False) -> None:
    """Raise why the radio may not open this port.

    HeldError if another radio or the GPS holds it (the radio waits), else SerialError.
    """
    if ours := held_elsewhere(claims, holder, path):
        raise (SerialError if remembered else HeldError)(f"{path}: {ours}")
    if claims is not None and not remembered:
        let_go(path)
    if not nodevices.on() and (held := await asyncio.to_thread(serialprobe.held_by, path)):
        raise SerialError(f"{path}: {held}")


def taken(claims: Claims | None, holder: RadioId, path: str) -> str:
    """Return why the radio may not take this port in place of its own (tncfollow.py), else ""."""
    value = serialprobe.claim_value(path)
    return "" if value is None else claimed(claims, holder).get(value, "")


def hold_port(claims: Claims | None, holder: RadioId, path: str, close: Callable[[], None] = lambda: None) -> None:
    """Hold the port the radio found or opened in place of the one it held before.

    If another took it meanwhile, call `close` and raise HeldError. It stays held if its open fails.
    """
    value = serialprobe.claim_value(path) if claims is not None else None
    if claims is None or value is None:
        return
    mine = Claim("serial", value, holder)
    if [c for c in claims.all() if c.holder == holder and c.kind == "serial"] == [mine]:
        # held already: the search held it, the Tnc opened it
        return
    claims.release(holder, "serial")
    if (other := claims.hold(mine)) is not None:
        close()
        raise HeldError(f"{path}: held by {claims.words(other.holder)}")


def release_port(claims: Claims | None, holder: RadioId) -> None:
    if claims is not None:
        claims.release(holder, "serial")


class PortSearch:
    def __init__(self, spawn: Callable[[Coroutine[Any, Any, None]], "asyncio.Task[None]"], note: Callable[[str], None], nudge: bytes, label: Callable[[], str] = lambda: "tnc") -> None:
        self._spawn = spawn
        self._nudge = nudge  # written to quiet ports: a TNC in command mode answers
        self._note = note
        self._label = label
        self.waiting = False  # another radio's search runs
        self.listening: list[str] = []
        self._searched: list[str] = []
        self._told: set[str] = set()  # boards logged as skipped, once each
        # said at INFO and in the Terminal once per search; later only at debug level
        self._said: set[str] = set()
        # ports (by port_key) nudged in this search: each gets its carriage return once
        self._nudged: set[str] = set()

    @property
    def possible(self) -> bool:
        return serialprobe.can_search()

    @property
    def words(self) -> str:
        return f"listening on {', '.join(self.listening)} for the radio" if self.listening else WAITING if self.waiting else ""

    async def find(self, pattern: str, baud: int, seconds: float, looks_valid: Callable[[bytes], bool], nudge: bool, nudge_sec: float, skip: tuple[str, ...], wanted: Callable[[], bool], also: str = "", *,
                   claims: Claims | None = None, holder: RadioId = FM_ID, lock: asyncio.Lock | None = None) -> tuple[str, bytes]:
        """Return the port of the radio and what it was heard to say.

        Raise SerialError if there is none; return ("", b"") when `wanted()` turned false.
        """
        if not self.possible:
            raise NotChosenError("no port is chosen: the radio is not looked for among the ports on this system, so choose its port in the settings")
        loop, others = asyncio.get_running_loop(), Others(claims, holder)
        deadline = loop.time() + seconds if seconds else None
        found: tuple[str, bytes] | None = None
        self._said, self._nudged = set(), set()
        try:
            while found is None:
                if lock is not None:
                    await self._turn(lock)
                try:
                    # what is left of the whole wait, never 0 (that is no limit)
                    left = seconds if deadline is None else max(deadline - loop.time(), 0.001)
                    found = await self._find(pattern, baud, left, looks_valid, nudge, nudge_sec, skip, wanted, also, others, lock) if wanted() else ("", b"")
                    if found is not None and found[0] and serialprobe.claim_value(found[0]) in others:
                        # another radio's since a save a moment ago
                        found = None
                    if found is not None and found[0]:
                        # held before the turn is given back, so the next radio's search skips it
                        hold_port(claims, holder, found[0])
                finally:
                    if lock is not None:
                        lock.release()
        finally:
            self._said, self._nudged = set(), set()
        return found

    def _say(self, text: str, note: bool = False) -> None:
        first = text not in self._said
        self._said.add(text)
        log.log(logging.INFO if first else logging.DEBUG, "%s: %s", self._label(), text)
        if note and first:
            self._note(text)

    async def _turn(self, lock: asyncio.Lock) -> None:
        if lock.locked() or turn_wanted(lock):
            self._say(WAITING, note=True)
        self.waiting = True
        try:
            await take_turn(lock)
        finally:
            self.waiting = False

    async def _find(self, pattern: str, baud: int, seconds: float, looks_valid: Callable[[bytes], bool], nudge: bool, nudge_sec: float, skip: tuple[str, ...], wanted: Callable[[], bool], also: str,
                    others: Mapping[str, str], lock: asyncio.Lock | None) -> tuple[str, bytes] | None:
        """Run one turn; return (port, bytes), ("", b"") if unwanted, or None if given up."""
        paths, boards = await self._listing(pattern, also)
        if not paths:
            if boards:
                raise SerialError(f"no port to listen to: {'; '.join(f'{path} is {what}' for path, what in boards.items())}, which the search leaves alone; choose the port by its name in the settings to use it")
            raise SerialError(f"no port matches {pattern}")
        outcome: list[tuple[str, bytes] | None] = []
        given: list[bool] = []
        self._searched = []
        until = asyncio.get_running_loop().time() + turn_sec(nudge, nudge_sec)

        async def relist() -> list[str]:
            if lock is not None and turn_wanted(lock) and asyncio.get_running_loop().time() >= until:
                raise _TurnOver
            return (await self._listing(pattern, also))[0]

        async def search() -> None:
            try:
                outcome.append(await serialprobe.probe_heard(paths, baud, seconds, looks_valid, self._nudge if nudge else None, nudge_sec, self._opened, skip, relist, others, self._nudged))
            except _TurnOver:
                given.append(True)
                self._say("the search gives its turn to another radio")

        task = self._spawn(search())
        try:
            await asyncio.wait([task])
        finally:
            self.listening = []
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if not wanted():
            return "", b""
        # turn given up: the ports are closed and the search goes on in its next turn
        return None if given else self._answer(outcome, paths, others, skip)

    def _answer(self, outcome: list[tuple[str, bytes] | None], paths: list[str], others: Mapping[str, str], skip: tuple[str, ...]) -> tuple[str, bytes]:
        """Return the port and what it said, else raise SerialError saying why each port failed."""
        if not outcome:
            raise SerialError("the search for the radio failed")
        if outcome[0] is None:
            if not self._searched:
                never = {serialprobe.port_key(p) for p in skip}
                why = [f"{path} {others.get(key) or ('on the skip list' if key in never else 'held by another program or not openable')}" for path in paths for key in (serialprobe.port_key(path),)]
                raise SerialError(f"no port could be listened to: {', '.join(why)}")
            raise SerialError(f"no port delivers KISS frames (tried {', '.join(self._searched)})")
        return outcome[0]

    async def _listing(self, pattern: str, also: str) -> tuple[list[str], dict[str, str]]:
        """Return the ports the search listens to now and the boards it leaves out.

        `also` is added when it is a device file that exists. Read in a thread, not on the loop.
        """
        paths, boards = await asyncio.to_thread(serialprobe.searchable_ports, pattern)
        self._tell_boards(boards)
        if also and not is_url(also) and also not in paths and os.path.exists(also):
            paths.append(also)
        return paths, boards

    def _tell_boards(self, boards: dict[str, str]) -> None:
        for path, what in boards.items():
            if path not in self._told:
                self._told.add(path)
                log.info("%s: skipping %s: %s", self._label(), path, what)

    def _opened(self, opened: list[str]) -> None:
        self.listening = opened
        self._searched = sorted(set(self._searched) | set(opened))
        if opened:
            self._say(f"listening on {', '.join(opened)} for the radio", note=True)
