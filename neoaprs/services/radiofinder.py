"""Find my radio: try the listed serial ports in turn until one has a TNC that talks KISS.

Runs only on a click of the page. The result is the port, speed and profile, which the page puts
into the settings. The search is one asyncio task, so a cancel ends it and closes the open port.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from contextlib import asynccontextmanager
from typing import cast

from neoaprs import serialprobe
from neoaprs.claims import Claims
from neoaprs.coded import CodedError
from neoaprs.radiotype import FM_ID, RadioId
from neoaprs.radiosearch import Found, Trying
from neoaprs.serialholders import held_by, port_key
from neoaprs.serialport import SerialError, is_socket
from neoaprs.tasks import TaskSet
from neoaprs.tncprofile import LINE_SPEED
from neoaprs.tncsearch import WAITING, take_turn, turn_wanted

from .radioprobe import Ear, Timing, try_line

log = logging.getLogger("neoaprs.tnc")

# usual TNC serial speeds, the likeliest first
SPEEDS = (9600, 57600, 19200, 38400, 115200, 4800, 1200)
# lets go of the whole station's line, or of the radio `find` is given
Hold = Callable[[], Awaitable[None]] | Callable[[RadioId], Awaitable[None]]
Release = Callable[[], None] | Callable[[RadioId], None]


class RadioSearchError(CodedError):
    """`find_radio` or `find_radio_cancel` cannot be done, or nothing answered."""


def speeds_for(path: str, speedless: Collection[str] = ()) -> tuple[int, ...]:
    """Return the speeds to try on a port; a socket or a `speedless` port has no speed."""
    return (LINE_SPEED,) if is_socket(path) or port_key(path) in speedless else SPEEDS


def candidates(pattern: str, skip: tuple[str, ...]) -> list[str]:
    """Return the ports to try, none where Find my radio is unavailable. Blocks: use a thread."""
    if not serialprobe.can_find():
        return []
    never = {port_key(p) for p in skip}
    # Windows, macOS: the system's list; the globs are Linux paths, so only the default applies
    if not serialprobe.can_search():
        if pattern != serialprobe.DEFAULT_PATTERN:
            return []
        ports = serialprobe.system_ports() + serialprobe.paired_bluetooth_ports()
        return [p.device for p in ports if port_key(p.device) not in never]
    paths, _ = serialprobe.searchable_ports(pattern)
    found = [p for p in paths if port_key(p) not in never and not held_by(p)]
    if pattern == serialprobe.DEFAULT_PATTERN:
        found += [p.device for p in serialprobe.paired_bluetooth_ports()]
    return found


class RadioFinder:
    def __init__(
        self,
        ports: Callable[[], Awaitable[list[str]]],
        hold: Hold,
        release: Release,
        timing: Timing | None = None,
        line: Callable[[str, int], Ear] = Ear,
        *,
        claims: Claims | None = None,
        search_lock: asyncio.Lock | None = None,
    ) -> None:
        self.ports = ports
        # given the radio's id when `find` is given one, else called without arguments
        self._hold, self._release = hold, release
        self.claims, self.search_lock = claims, search_lock
        self.timing = timing or Timing()
        self._line = line
        self._tasks = TaskSet(log, "radio search")
        self._task: asyncio.Task[None] | None = None
        self._busy = False
        # Bluetooth COM ports of the running search
        self._speedless: set[str] = set()

    @property
    def running(self) -> bool:
        return self._busy

    async def find(self, trying: Callable[[Trying], None], radio: RadioId | None = None) -> Found | None:
        """Return the first port with a TNC behind it, or None if cancelled; `trying` runs per try.

        Raise RadioSearchError if busy, if no port is listed or if none answered."""
        if self._busy:
            raise RadioSearchError("a search for the radio is running already", "radio.busy")
        self._busy = True
        try:
            paths = self._unclaimed(await self.ports(), radio)
            log.info("find the radio: trying %s", ", ".join(paths) or "no port")
            if not paths:
                raise RadioSearchError(
                    "there is no port to try: none is listed that the search looks at", "radio.no_ports"
                )
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
                raise RadioSearchError(
                    "no radio answered on the ports tried (a KISS TNC says nothing until it hears a packet: try again when the channel is busy)",
                    "radio.not_found",
                )
            log.info(
                "find the radio: found on %s at %s, profile %s",
                outcome[0].port,
                outcome[0].baud or "no speed",
                outcome[0].profile,
            )
            return outcome[0]
        finally:
            self._busy = False
            self._task = None

    def cancel(self) -> bool:
        """End the running search; return False if none is running."""
        task = self._task
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    def _unclaimed(self, paths: list[str], radio: RadioId | None) -> list[str]:
        """Return the ports minus devices claimed elsewhere (`Claims.others`), logging each skip."""
        claims = self.claims
        if claims is None:
            return paths
        held = claims.others(FM_ID if radio is None else radio, "serial")
        for path in (p for p in paths if port_key(p) in held):
            log.info("find the radio: passing over %s: held by %s", path, claims.words(held[port_key(path)]))
        return [p for p in paths if port_key(p) not in held]

    async def _run(
        self, paths: list[str], trying: Callable[[Trying], None], outcome: list[Found | None], radio: RadioId | None
    ) -> None:
        self._speedless = await asyncio.to_thread(serialprobe.bluetooth_com_keys)
        try:
            await self._let_go(radio)
            async with self._turn():
                # another radio's search may have claimed a port while this one waited
                paths = self._unclaimed(paths, radio)
                total, number = sum(len(speeds_for(p, self._speedless)) for p in paths), 0
                for path in paths:
                    # a port that a save gave another radio meanwhile is passed over
                    found = (
                        await self._try_port(path, number, total, trying) if self._unclaimed([path], radio) else None
                    )
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
        """Let go of the line for the search: the station's without a radio, else the radio's."""
        if radio is None:
            await cast(Callable[[], Awaitable[None]], self._hold)()
        else:
            await cast(Callable[[RadioId], Awaitable[None]], self._hold)(radio)

    @asynccontextmanager
    async def _turn(self) -> AsyncIterator[None]:
        """Hold the station's search lock for the tries, logging a wait; no-op without a lock."""
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
        """Try the port at each speed until a TNC answers; skip a port that cannot be opened."""
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
