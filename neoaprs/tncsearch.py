"""The search for the radio: every port that matches the pattern is listened to at the same time, for as long as it takes, and the one whose bytes look like the radio's is the answer. It runs as a task
of the Tnc that asks (so that the Tnc's stop() ends it) and says which ports it has open while it runs. Where it may not run (not Linux: `serialprobe.can_search`) it answers with the reason, and the radio is the port
that was named or remembered.

With radios side by side (plan §2, "Resources"), the station's table of claims (claims.py) is the Tnc's too: the search leaves out every serial device another radio or the GPS receiver holds (a keying line among
them) or another enabled radio is set to (`Claims.others`, read again at every listing and whenever a port has spoken: a search that has such a port open closes it then, and never answers with it), a
port that was named and is held by another is not opened at all (`held_elsewhere`: the radio waits for it, HeldError; the port radio 1's search only remembered is searched past instead: `may_open`), a named
port another radio's search has open is let go by that search at once (`let_go`), and the port the search found is held for its radio (`hold_port`) before the next radio's search may start, and kept until the
Tnc stops (`release_port`). One radio searches at a time: the search waits for its turn on the station's lock (RadioRegistry.search_lock) and says meanwhile that it waits. A turn is bounded: a search that has
listened for its nudge and one listing after it (`turn_sec`) gives the turn up at its next listing while another radio's search, or Find my radio, waits for it (`take_turn`, `turn_wanted`), closes its ports and
waits for the turn again, so that a radio that never finds its port keeps no other from its own. Over all its turns one search writes its carriage return to a port once, and says its turns at INFO once (at
DEBUG after). Without the table and the lock it is the search of one radio, as it always was."""
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

WAITING = "waiting while another radio looks for its port"           # the status of a radio whose search waits for its turn

_QUEUED: "WeakKeyDictionary[asyncio.Lock, int]" = WeakKeyDictionary()     # how many wait for the station's turn, by its lock (`take_turn`)


class _TurnOver(Exception):
    """The search gives its turn to a radio that waits for it (raised from its listing, which ends the listening and closes its ports)."""


async def take_turn(lock: asyncio.Lock) -> None:
    """Waits for the station's one search (the lock is acquired; the caller releases it). While it waits, the search that has the turn gives it up at its next listing (`turn_wanted`); asyncio's lock is first come,
    first served, so the one that waited longest goes next."""
    _QUEUED[lock] = _QUEUED.get(lock, 0) + 1
    try:
        await lock.acquire()
    finally:
        _QUEUED[lock] -= 1


def turn_wanted(lock: asyncio.Lock) -> bool:
    """Whether another radio's search, or Find my radio, waits for the turn."""
    return _QUEUED.get(lock, 0) > 0


def turn_sec(nudge: bool, nudge_sec: float) -> float:
    """How long a search keeps the turn at least while another waits: its nudge (a TNC in command mode answers it within a second or two) and one listing after it."""
    return (nudge_sec if nudge else 0.0) + serialprobe.RELIST_SEC


def claimed(claims: Claims | None, holder: RadioId, named: bool = True) -> dict[str, str]:
    """The serial devices that are others' (another radio's port or keying line, held or, with `named`, only set in its settings; the GPS receiver's port), by their claim's value, with the words of who holds each:
    what the search of `holder` leaves out (`Claims.others`, the station's one rule)."""
    return {} if claims is None else {value: f"held by {claims.words(other)}" for value, other in claims.others(holder, "serial", named).items()}


class Others(Mapping[str, str]):
    """`claimed` as the search asks it, read from the table each time: a search that listens for long leaves out what is held meanwhile (the port another radio opened while this one waited for its turn)."""

    def __init__(self, claims: Claims | None, holder: RadioId) -> None:
        self._claims, self._holder = claims, holder

    def __getitem__(self, value: str) -> str:
        return claimed(self._claims, self._holder)[value]

    def __iter__(self) -> Iterator[str]:
        return iter(claimed(self._claims, self._holder))

    def __len__(self) -> int:
        return len(claimed(self._claims, self._holder))


def held_elsewhere(claims: Claims | None, holder: RadioId, path: str) -> str:
    """Why the radio may not open the port it is set to: "held by FM 2" when another radio of the station, or the GPS receiver, holds the device; "" when none does, for a KISS TCP address, and without the table.
    Only what is held counts: a port that another radio is set to as well and has not opened is not refused (two radios stored with one port would otherwise wait for each other for ever); the first that opens it holds it."""
    value = serialprobe.claim_value(path) if claims is not None else None
    return "" if value is None else claimed(claims, holder, named=False).get(value, "")


def let_go(path: str) -> None:
    """Another radio's search that has the device open closes it at once (serialprobe.LISTENING): the radio whose settings name it opens it now, so it is not told that another program has its port, and
    the search leaves it out from then on (`Others`). Find my radio's try of the port ends too (radioprobe.Ear), and it looks again before each port it tries (radiofinder.py)."""
    listener = serialprobe.LISTENING.get(serialprobe.port_key(path))
    if listener is not None and listener.is_open:
        log.info("probe: %s is let go: a radio is set to it", listener.path)
        listener.let_go()


async def may_open(claims: Claims | None, holder: RadioId, path: str, remembered: bool = False) -> None:
    """Raises why the radio may not open this port: HeldError when another radio of ours or the GPS receiver holds it and the radio's settings name it (the radio waits for it and takes no other port
    meanwhile), a plain SerialError when it is only the port the search remembered (the search goes on: fallback_probe) and when another program has it open (not asked under the no-devices switch: the
    port is not there). A search of ours that listens to a port the settings name lets go of it first (`let_go`)."""
    if ours := held_elsewhere(claims, holder, path):
        raise (SerialError if remembered else HeldError)(f"{path}: {ours}")
    if claims is not None and not remembered:
        let_go(path)
    if not nodevices.on() and (held := await asyncio.to_thread(serialprobe.held_by, path)):
        raise SerialError(f"{path}: {held}")


def taken(claims: Claims | None, holder: RadioId, path: str) -> str:
    """Why the radio may not take this port in the place of the one it is set to (its USB adapter seems to be there now: tncfollow.py): another radio holds it or is set to it, or the GPS receiver holds it; ""
    when it may."""
    value = serialprobe.claim_value(path)
    return "" if value is None else claimed(claims, holder).get(value, "")


def hold_port(claims: Claims | None, holder: RadioId, path: str, close: Callable[[], None] = lambda: None) -> None:
    """The port the radio has found or opened, held for it in the place of the one it held before. When another took the device between the look and the hold, the port is closed (`close`) and SerialError says who
    holds it. Nothing for a KISS TCP address and without the table (the Tnc gives none for the Dummy radio). A port the search found stays held when its open fails: it is the value in force, remembered from the
    search, until the next search finds another or the Tnc stops."""
    value = serialprobe.claim_value(path) if claims is not None else None
    if claims is None or value is None:
        return
    mine = Claim("serial", value, holder)
    if [c for c in claims.all() if c.holder == holder and c.kind == "serial"] == [mine]:
        return                                                           # (held already, and nothing else: the search held it, the Tnc opened it)
    claims.release(holder, "serial")
    if (other := claims.hold(mine)) is not None:
        close()
        raise HeldError(f"{path}: held by {claims.words(other.holder)}")


def release_port(claims: Claims | None, holder: RadioId) -> None:
    """The radio's port is let go (its Tnc stopped)."""
    if claims is not None:
        claims.release(holder, "serial")


class PortSearch:
    def __init__(self, spawn: Callable[[Coroutine[Any, Any, None]], "asyncio.Task[None]"], note: Callable[[str], None], nudge: bytes, label: Callable[[], str] = lambda: "tnc") -> None:
        self._spawn = spawn
        self._nudge = nudge                                              # written to every port that has been quiet for nudge_sec: a TNC in command mode answers
        self._note = note
        self._label = label                                              # what the log calls the radio (Tnc.label)
        self.waiting = False                                             # the search waits for its turn: another radio's search runs
        self.listening: list[str] = []                                   # the ports the search has open, while it runs
        self._searched: list[str] = []                                   # the ports the latest search opened
        self._told: set[str] = set()                                     # the boards that were logged as skipped (once each, however often the search runs)
        self._said: set[str] = set()                                     # what one search (`find`, over all its turns) has said at INFO and in the Terminal: said again, it goes to the debug log only
        self._nudged: set[str] = set()                                   # the ports (by port_key) one search has nudged, over all its turns: each is written its carriage return once

    @property
    def possible(self) -> bool:
        return serialprobe.can_search()

    @property
    def words(self) -> str:
        """The search in a few words, for the radio's status line: the ports it listens to, or that it waits for its turn; "" while none is under way."""
        return f"listening on {', '.join(self.listening)} for the radio" if self.listening else WAITING if self.waiting else ""

    async def find(self, pattern: str, baud: int, seconds: float, looks_valid: Callable[[bytes], bool], nudge: bool, nudge_sec: float, skip: tuple[str, ...], wanted: Callable[[], bool], also: str = "", *,
                   claims: Claims | None = None, holder: RadioId = FM_ID, lock: asyncio.Lock | None = None) -> tuple[str, bytes]:
        """The port of the radio and what it was heard to say (the Tnc tells from it whether the TNC it found is in command mode). Raises SerialError with the reason when there is none; returns ("", b"")
        when `wanted()` turned false (the Tnc was stopped) meanwhile. `nudge`: whether a carriage return may be written to the quiet ports (a profile that cannot be asked is only listened to). `also`: a
        port listened to as well whenever it exists, whether or not it matches the pattern (the named port the search stands in for while that cannot be opened). The ports are listed again every
        `serialprobe.RELIST_SEC` while the search listens, so a radio plugged back in is found while another port keeps talking. The devices that others hold in `claims` are left out for the radio `holder`, and
        the port found is held for it before the turn is given back; with a `lock` the search waits for its turn (one radio searches at a time) and gives it up for a while when another waits (`turn_sec`)."""
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
                    left = seconds if deadline is None else max(deadline - loop.time(), 0.001)      # (what is left of the whole wait, never 0: that is no limit)
                    found = await self._find(pattern, baud, left, looks_valid, nudge, nudge_sec, skip, wanted, also, others, lock) if wanted() else ("", b"")
                    if found is not None and found[0] and serialprobe.claim_value(found[0]) in others:
                        found = None                                     # (another radio's since a save a moment ago: the next turn's listing leaves it out)
                    if found is not None and found[0]:
                        hold_port(claims, holder, found[0])              # (before the turn is given back: the next radio's search leaves it out)
                finally:
                    if lock is not None:
                        lock.release()
        finally:
            self._said, self._nudged = set(), set()
        return found

    def _say(self, text: str, note: bool = False) -> None:
        """A line of the search: at INFO (and in the Terminal, `note`) the first time this search says it, at DEBUG when a later turn says it again."""
        first = text not in self._said
        self._said.add(text)
        log.log(logging.INFO if first else logging.DEBUG, "%s: %s", self._label(), text)
        if note and first:
            self._note(text)

    async def _turn(self, lock: asyncio.Lock) -> None:
        """Waits for the station's one search to be this radio's, and says meanwhile that it waits (in the Terminal, the status line and the log)."""
        if lock.locked() or turn_wanted(lock):
            self._say(WAITING, note=True)
        self.waiting = True
        try:
            await take_turn(lock)
        finally:
            self.waiting = False

    async def _find(self, pattern: str, baud: int, seconds: float, looks_valid: Callable[[bytes], bool], nudge: bool, nudge_sec: float, skip: tuple[str, ...], wanted: Callable[[], bool], also: str,
                    others: Mapping[str, str], lock: asyncio.Lock | None) -> tuple[str, bytes] | None:
        """One turn of the search: the port and what it said, ("", b"") when the Tnc no longer wants it, None when the turn was given to a radio that waits for it. Raises SerialError."""
        paths, boards = await self._listing(pattern, also)
        if not paths:
            if boards:
                raise SerialError(f"no port to listen to: {'; '.join(f'{path} is {what}' for path, what in boards.items())}, which the search leaves alone; choose the port by its name in the settings to use it")
            raise SerialError(f"no port matches {pattern}")
        outcome: list[tuple[str, bytes] | None] = []
        given: list[bool] = []                                           # (the turn was given up)
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
        return None if given else self._answer(outcome, paths, others, skip)      # (the turn given up: the ports are closed, the search goes on in its next turn)

    def _answer(self, outcome: list[tuple[str, bytes] | None], paths: list[str], others: Mapping[str, str], skip: tuple[str, ...]) -> tuple[str, bytes]:
        """What the listening came to: the port and what it said, or SerialError with why there is none (with no port opened at all, why each was not: another radio's or the GPS receiver's, on the skip
        list, else another program's or not openable)."""
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
        """The ports the search listens to now and the boards it leaves out (told once each); `also` is added when it is a device file that exists. The system's list is read from files: not on the loop."""
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
