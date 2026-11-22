"""One try of Find my radio: an open port at one speed, and what its TNC says.

The line is listened to, then a carriage return is written: a TNC in KISS mode ignores it, one in
command mode answers with text and is put into KISS by each askable profile. Nothing goes on air."""
import asyncio
from dataclasses import dataclass

from neoaprs.serialport import SerialError, SerialPort
from neoaprs.serialprobe import LISTENING, port_key
from neoaprs.tncmode import Mode, ModeDetector
from neoaprs.tncprofile import KISS, PROFILES

CR = b"\r"
# profiles that put a TNC in command mode into KISS, in the order tried
ASKABLE = tuple(p for p in PROFILES if p.can_probe)


@dataclass(frozen=True)
class Timing:
    # listen this long before the first carriage return
    listen_sec: float = 1.0
    # and this long after each carriage return
    answer_sec: float = 1.5
    # factor on the pauses of a profile's entry
    pace: float = 1.0


class Ear(SerialPort):
    """A port that keeps what it hears; while open it is in serialprobe.LISTENING so a radio can take it."""

    def __init__(self, path: str, baud: int) -> None:
        super().__init__(path, baud)
        self.heard = bytearray()
        # set when let go for a radio whose settings name the port
        self.given_up = False

    async def open(self) -> None:
        key = port_key(self.path)
        if (held := LISTENING.get(key)) is None or not (held.is_open or held.is_opening):
            LISTENING[key] = self
        await super().open()
        LISTENING[key] = self

    def let_go(self) -> None:
        self.given_up = True
        super().let_go()

    def _deliver(self, chunk: bytes) -> None:
        self.heard.extend(chunk)


def mode_of(heard: bytes) -> Mode:
    return ModeDetector().feed(heard)


async def put_in_kiss(ear: Ear, profile_key: str, timing: Timing) -> bool:
    """Write the profile's steps with their pauses, then a carriage return.

    Return True if the TNC stays silent (KISS); one still in command mode answers with text."""
    profile = next(p for p in ASKABLE if p.key == profile_key)
    for data, pause in profile.enter:
        ear.write(data)
        await asyncio.sleep(pause * timing.pace)
    ear.heard.clear()
    ear.write(CR)
    await asyncio.sleep(timing.answer_sec)
    return mode_of(bytes(ear.heard)) is not Mode.MONITOR


async def try_line(ear: Ear, timing: Timing) -> str | None:
    """Return the key of the profile that fits the TNC on this line, or None.

    Raise SerialError if the line was let go for a radio set to the port, whatever it said."""
    try:
        found = await _profile_of(ear, timing)
    except SerialError:
        if not ear.given_up:
            raise
        found = None
    if ear.given_up:
        raise SerialError(f"{ear.path}: a radio is set to it")
    return found


async def _profile_of(ear: Ear, timing: Timing) -> str | None:
    await asyncio.sleep(timing.listen_sec)
    mode = mode_of(bytes(ear.heard))
    if mode is Mode.UNKNOWN:
        ear.write(CR)
        await asyncio.sleep(timing.answer_sec)
        mode = mode_of(bytes(ear.heard))
    if mode is Mode.KISS:
        return KISS.key
    if mode is Mode.MONITOR:
        for profile in ASKABLE:
            if await put_in_kiss(ear, profile.key, timing):
                return profile.key
    return None
