"""Find my radio: on a click of the page (the command `find_radio`), and never by itself, the ports that the daemon lists are tried one after the other, each at the usual speeds, until one has a TNC behind it that talks
KISS or can be put into KISS the way a profile does (radioprobe.py). The answer is the port, the speed and the profile; the page puts them in the settings like any other change.

The ports are those of the search for the radio (serialprobe.py): on Linux the globs of the search pattern, without the boards the search leaves alone, the ports on the skip list and those another program holds; and,
when the pattern is the default one, the Bluetooth devices that are paired. On Windows and macOS (the pattern's globs are paths of Linux) they are the ports the system lists (`serialprobe.system_ports`: the COM ports,
the paired Bluetooth serial ports among them, or the `/dev/cu.*` devices), USB adapters first, without the boards and the ports on the skip list; one that another program has open cannot be opened, which the open says
("in use by another program"), and it is passed over. A KISS TCP address is not a port of the machine and is never tried. The TNC's own line is closed
for the time (`hold`) and opened again after it (`release`), found or not. The search is one asyncio task, so a cancel (from the page, or the daemon's stop) ends it between two awaits and the port that was open is closed.
A speed is not tried on a port that has none (a Bluetooth port, of Linux or a COM port of Windows). Each try takes `listen_sec` + `answer_sec` (2.5 s) when nothing answers, so a port costs 7 tries, about 18 s; a command-mode TNC is found at 9600 in a few seconds.

With radios side by side the search is for one radio (`find(trying, radio)`): that radio's line is let go and taken again (`hold(radio)`, `release(radio)`), the serial devices another radio or the GPS receiver holds in
the station's table (`claims`) are not tried (looked at again once the turn is this search's), and the search takes the station's one search at a time (`search_lock`, RadioRegistry's), waiting for its turn while
another radio's search runs (which gives it up for a while: tncsearch.take_turn); the Tnc of the radio itself lets go of its turn when it is held. Without a radio the search is the one radio's of before, its hold and
release called with nothing."""
import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from contextlib import asynccontextmanager
from typing import cast

from neoaprs import serialprobe
from neoaprs.claims import PORT_KINDS, Claims
from neoaprs.coded import CodedError
from neoaprs.radiotype import FM_ID, RadioId
from neoaprs.radiosearch import Found, Trying
from neoaprs.serialholders import held_by, port_key
from neoaprs.serialport import SerialError, is_socket
from neoaprs.tasks import TaskSet
from neoaprs.tncsearch import WAITING, take_turn, turn_wanted

from .radioprobe import Ear, Timing, try_line

log = logging.getLogger("neoaprs.tnc")

SPEEDS = (9600, 57600, 19200, 38400, 115200, 4800, 1200)          # the usual speeds of a TNC on a serial line, the likeliest first
NO_SPEED = 9600                                                      # what a port with no speed is opened at (pyserial wants a number)
Hold = Callable[[], Awaitable[None]] | Callable[[RadioId], Awaitable[None]]      # the radio's line let go: of the one radio of before (app.py's call today), or of the radio `find` is given
Release = Callable[[], None] | Callable[[RadioId], None]


class RadioSearchError(CodedError):
    """`find_radio` or `find_radio_cancel` cannot be done, or nothing answered."""


def speeds_for(path: str, speedless: Collection[str] = ()) -> tuple[int, ...]:
    """The speeds a port is tried at: none to choose for a port that is not a serial line (a socket, a Bluetooth port, a COM port of a Bluetooth device: `speedless` holds their `port_key`)."""
    return (NO_SPEED,) if is_socket(path) or port_key(path) in speedless else SPEEDS


def candidates(pattern: str, skip: tuple[str, ...]) -> list[str]:
    """The ports to try (reads the system's lists: not on the loop). Where Find my radio is not made, none."""
    if not serialprobe.can_find():
        return []
    never = {port_key(p) for p in skip}
    if not serialprobe.can_search():                                  # Windows, macOS: the system's list (the globs of the pattern are paths of Linux, so only the default one stands for "the ports")
        ports = serialprobe.system_ports() if pattern == serialprobe.DEFAULT_PATTERN else []
        return [p.device for p in ports if port_key(p.device) not in never]
    paths, _ = serialprobe.searchable_ports(pattern)
    found = [p for p in paths if port_key(p) not in never and not held_by(p)]
    if pattern == serialprobe.DEFAULT_PATTERN:
        found += [p.device for p in serialprobe.paired_bluetooth_ports()]
    return found


class RadioFinder:
    def __init__(self, ports: Callable[[], Awaitable[list[str]]], hold: Hold, release: Release, timing: Timing | None = None,
                 line: Callable[[str, int], Ear] = Ear, *, claims: Claims | None = None, search_lock: asyncio.Lock | None = None) -> None:
        self.ports = ports                              # the ports to try, in order
        self._hold, self._release = hold, release        # the radio's line is let go, and taken again: given the radio's id when `find` is given one (`hold(radio)`), called with nothing when it is not (one radio's search, as before)
        self.claims, self.search_lock = claims, search_lock      # the station's table of resources and its one search at a time (claims.py, RadioRegistry.search_lock)
        self.timing = timing or Timing()
        self._line = line
        self._tasks = TaskSet(log, "radio search")
        self._task: asyncio.Task[None] | None = None
        self._busy = False
        self._speedless: set[str] = set()                   # the Bluetooth COM ports of the search that runs

    @property
    def running(self) -> bool:
        return self._busy

    async def find(self, trying: Callable[[Trying], None], radio: RadioId | None = None) -> Found | None:
        """The first port with a TNC behind it, for the radio `radio` (None: the one radio of before); None when the search was cancelled. RadioSearchError when a search is running already, when there is no port to try
        (`radio.no_ports`) and when none answered (`radio.not_found`). `trying` is told before each try."""
        if self._busy:
            raise RadioSearchError("a search for the radio is running already", "radio.busy")
        self._busy = True
        try:
            paths = self._unclaimed(await self.ports(), radio)
            log.info("find the radio: trying %s", ", ".join(paths) or "no port")
            if not paths:
                raise RadioSearchError("there is no port to try: none is listed that the search looks at", "radio.no_ports")
            outcome: list[Found | None] = []
            self._task = self._tasks.spawn(self._run(paths, trying, outcome, radio), "radio-search")
            try:
                await asyncio.wait([self._task])
            finally:
                if not self._task.done():
                    self._task.cancel()
                    await asyncio.gather(self._task, return_exceptions=True)
            if self._task.cancelled():
                log.info("find the radio: cancelled")
                return None
            if not outcome:
                raise RadioSearchError("the search for the radio failed", "radio.failed")
            if outcome[0] is None:
                log.info("find the radio: no radio answered on %s", ", ".join(paths))
                raise RadioSearchError("no radio answered on the ports tried (a KISS TNC says nothing until it hears a packet: try again when the channel is busy)", "radio.not_found")
            log.info("find the radio: found on %s at %s, profile %s", outcome[0].port, outcome[0].baud or "no speed", outcome[0].profile)
            return outcome[0]
        finally:
            self._busy = False
            self._task = None

    def cancel(self) -> bool:
        """Ends the search that is running; False when none is."""
        task = self._task
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    def _unclaimed(self, paths: list[str], radio: RadioId | None) -> list[str]:
        """The ports without the serial devices that another radio or the GPS receiver holds (each said in the log as it is passed over)."""
        mine = FM_ID if radio is None else radio
        held = {c.value: c.holder for c in (self.claims.all() if self.claims is not None else ()) if c.holder != mine and c.kind in PORT_KINDS}
        for path in (p for p in paths if port_key(p) in held):
            log.info("find the radio: passing over %s: held by %s", path, serialprobe.holder_words(held[port_key(path)]))
        return [p for p in paths if port_key(p) not in held]

    async def _run(self, paths: list[str], trying: Callable[[Trying], None], outcome: list[Found | None], radio: RadioId | None) -> None:
        self._speedless = await asyncio.to_thread(serialprobe.bluetooth_com_keys)
        try:
            await self._let_go(radio)
            async with self._turn():
                paths = self._unclaimed(paths, radio)                    # (what another radio's search found and holds while this one waited for its turn)
                total, number = sum(len(speeds_for(p, self._speedless)) for p in paths), 0
                for path in paths:
                    found = await self._try_port(path, number, total, trying)
                    number += len(speeds_for(path, self._speedless))
                    if found is not None:
                        outcome.append(found)
                        return
                outcome.append(None)
        finally:
            if radio is None:
                cast(Callable[[], None], self._release)()
            else:
                cast(Callable[[RadioId], None], self._release)(radio)

    async def _let_go(self, radio: RadioId | None) -> None:
        """The radio's line is let go for the search: the one radio's of before when there is no radio (app.py's call, which takes none), else the radio's."""
        if radio is None:
            await cast(Callable[[], Awaitable[None]], self._hold)()
        else:
            await cast(Callable[[RadioId], Awaitable[None]], self._hold)(radio)

    @asynccontextmanager
    async def _turn(self) -> AsyncIterator[None]:
        """The station's one search at a time, held for the tries (nothing to hold without the lock); waiting for it is said in the log."""
        lock = self.search_lock
        if lock is None:
            yield
            return
        if lock.locked() or turn_wanted(lock):
            log.info("find the radio: %s", WAITING)
        await take_turn(lock)
        try:
            yield
        finally:
            lock.release()

    async def _try_port(self, path: str, number: int, total: int, trying: Callable[[Trying], None]) -> Found | None:
        """The port at each of its speeds, until a TNC answers; a port that cannot be opened or whose line dies is passed over."""
        speeds = speeds_for(path, self._speedless)
        for at, baud in enumerate(speeds):
            shown = None if len(speeds) == 1 else baud
            trying(Trying(path, shown, number + at + 1, total))
            try:
                profile = await self._attempt(path, baud)
            except SerialError as e:
                log.info("find the radio: passing over %s: %s", path, e)
                return None
            if profile is not None:
                return Found(path, shown, profile)
        return None

    async def _attempt(self, path: str, baud: int) -> str | None:
        ear = self._line(path, baud)
        await ear.open()
        try:
            return await try_line(ear, self.timing)
        finally:
            ear.close()
