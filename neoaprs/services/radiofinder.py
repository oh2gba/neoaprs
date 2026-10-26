"""Find my radio: on a click of the page (the command `find_radio`), and never by itself, the ports that the daemon lists are tried one after the other, each at the usual speeds, until one has a TNC behind it that talks
KISS or can be put into KISS the way a profile does (radioprobe.py). The answer is the port, the speed and the profile; the page puts them in the settings like any other change.

The ports are those of the search for the radio (serialprobe.py): on Linux the globs of the search pattern, without the boards the search leaves alone, the ports on the skip list and those another program holds; and,
when the pattern is the default one, the Bluetooth devices that are paired. On Windows and macOS (the pattern's globs are paths of Linux) they are the ports the system lists (`serialprobe.system_ports`: the COM ports,
the paired Bluetooth serial ports among them, or the `/dev/cu.*` devices), USB adapters first, without the boards and the ports on the skip list; one that another program has open cannot be opened, which the open says
("in use by another program"), and it is passed over. A KISS TCP address is not a port of the machine and is never tried. The TNC's own line is closed
for the time (`hold`) and opened again after it (`release`), found or not. The search is one asyncio task, so a cancel (from the page, or the daemon's stop) ends it between two awaits and the port that was open is closed.
A speed is not tried on a port that has none (a Bluetooth port, of Linux or a COM port of Windows). Each try takes `listen_sec` + `answer_sec` (2.5 s) when nothing answers, so a port costs 7 tries, about 18 s; a command-mode TNC is found at 9600 in a few seconds."""
import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection

from neoaprs import serialprobe
from neoaprs.coded import CodedError
from neoaprs.radiosearch import Found, Trying
from neoaprs.serialholders import held_by, port_key
from neoaprs.serialport import SerialError, is_socket
from neoaprs.tasks import TaskSet

from .radioprobe import Ear, Timing, try_line

log = logging.getLogger("neoaprs.tnc")

SPEEDS = (9600, 57600, 19200, 38400, 115200, 4800, 1200)          # the usual speeds of a TNC on a serial line, the likeliest first
NO_SPEED = 9600                                                      # what a port with no speed is opened at (pyserial wants a number)


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
    def __init__(self, ports: Callable[[], Awaitable[list[str]]], hold: Callable[[], Awaitable[None]], release: Callable[[], None], timing: Timing | None = None,
                 line: Callable[[str, int], Ear] = Ear) -> None:
        self.ports = ports                              # the ports to try, in order
        self._hold, self._release = hold, release        # the TNC lets go of its line, and takes it again
        self.timing = timing or Timing()
        self._line = line
        self._tasks = TaskSet(log, "radio search")
        self._task: asyncio.Task[None] | None = None
        self._busy = False
        self._speedless: set[str] = set()                   # the Bluetooth COM ports of the search that runs

    @property
    def running(self) -> bool:
        return self._busy

    async def find(self, trying: Callable[[Trying], None]) -> Found | None:
        """The first port with a TNC behind it; None when the search was cancelled. RadioSearchError when a search is running already, when there is no port to try (`radio.no_ports`) and when none answered (`radio.not_found`).
        `trying` is told before each try."""
        if self._busy:
            raise RadioSearchError("a search for the radio is running already", "radio.busy")
        self._busy = True
        try:
            paths = await self.ports()
            if not paths:
                raise RadioSearchError("there is no port to try: none is listed that the search looks at", "radio.no_ports")
            outcome: list[Found | None] = []
            self._task = self._tasks.spawn(self._run(paths, trying, outcome), "radio-search")
            try:
                await asyncio.wait([self._task])
            finally:
                if not self._task.done():
                    self._task.cancel()
                    await asyncio.gather(self._task, return_exceptions=True)
            if self._task.cancelled():
                return None
            if not outcome:
                raise RadioSearchError("the search for the radio failed", "radio.failed")
            if outcome[0] is None:
                raise RadioSearchError("no radio answered on the ports tried (a KISS TNC says nothing until it hears a packet: try again when the channel is busy)", "radio.not_found")
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

    async def _run(self, paths: list[str], trying: Callable[[Trying], None], outcome: list[Found | None]) -> None:
        self._speedless = await asyncio.to_thread(serialprobe.bluetooth_com_keys)
        total = sum(len(speeds_for(p, self._speedless)) for p in paths)
        number = 0
        await self._hold()
        try:
            for path in paths:
                found = await self._try_port(path, number, total, trying)
                number += len(speeds_for(path, self._speedless))
                if found is not None:
                    outcome.append(found)
                    return
            outcome.append(None)
        finally:
            self._release()

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
