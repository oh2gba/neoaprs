"""One try of Find my radio: a port that is open at one speed, and what its TNC says. The line is listened to, then a carriage return is written, which is all the search for the radio (serialprobe.py) writes too:
a TNC in KISS mode ignores it, one in command mode answers "cmd:". A KISS frame is a KISS TNC (the profile `kiss`). Text is a TNC in command mode, and it is put into KISS the way the profiles that can be asked do it
(tncprofile.py), one profile after the other, until the carriage return that follows is no longer answered with text. Nothing here is sent to the air: the TNC's commands only change the TNC."""
import asyncio
from dataclasses import dataclass

from neoaprs.serialport import SerialPort
from neoaprs.tncmode import Mode, ModeDetector
from neoaprs.tncprofile import KISS, PROFILES

CR = b"\r"
ASKABLE = tuple(p for p in PROFILES if p.can_probe)         # the profiles that put a TNC in command mode into KISS, in the order they are tried


@dataclass(frozen=True)
class Timing:
    listen_sec: float = 1.0          # a line is listened to this long before the carriage return is written
    answer_sec: float = 1.5          # and this long after each carriage return
    pace: float = 1.0                # the factor on the pauses of a profile's entry (the tests make them short)


class Ear(SerialPort):
    """A port that keeps what it hears."""

    def __init__(self, path: str, baud: int) -> None:
        super().__init__(path, baud)
        self.heard = bytearray()

    def _deliver(self, chunk: bytes) -> None:
        self.heard.extend(chunk)


def mode_of(heard: bytes) -> Mode:
    return ModeDetector().feed(heard)


async def put_in_kiss(ear: Ear, profile_key: str, timing: Timing) -> bool:
    """The profile's steps are written with their pauses, and then a carriage return: a TNC that is in KISS now says nothing to it, one that is still in command mode answers with text."""
    profile = next(p for p in ASKABLE if p.key == profile_key)
    for data, pause in profile.enter:
        ear.write(data)
        await asyncio.sleep(pause * timing.pace)
    ear.heard.clear()
    ear.write(CR)
    await asyncio.sleep(timing.answer_sec)
    return mode_of(bytes(ear.heard)) is not Mode.MONITOR


async def try_line(ear: Ear, timing: Timing) -> str | None:
    """The key of the profile that fits the TNC behind this open line, or None when it says nothing a TNC would."""
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
