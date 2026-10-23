"""A look at Hamlib's rigctld: the frequency and the mode of the radio, from a fresh short connection each time.

The text protocol: `f` is answered with the frequency in Hz on a line, `m` with the mode and then the passband on two lines; a command that fails is answered with `RPRT -n` (a radio that is
off gives -5 or -6, say). Everything that can go wrong is a `RigError` whose text says what, ready for the log: "connection refused", "no answer in time", "rigctld answered RPRT -5".
"""
import asyncio
from dataclasses import dataclass

TIMEOUT_SEC = 5.0


class RigError(Exception):
    """The radio cannot be read: rigctld is not there, does not answer, or says the radio is off."""


@dataclass(frozen=True)
class Reading:
    hz: int
    mode: str


def _line(raw: bytes) -> str:
    if not raw:
        raise RigError("rigctld hung up")
    line = raw.decode("latin-1").strip()
    if line.startswith("RPRT"):
        raise RigError(f"rigctld answered {line}")
    return line


def _hz(line: str) -> int:
    try:
        hz = round(float(line))
    except ValueError:
        raise RigError(f"rigctld gave {line!r} for the frequency") from None
    if hz <= 0:
        raise RigError(f"rigctld gave {line!r} for the frequency")
    return hz


async def read_rig(host: str, port: int, timeout_sec: float = TIMEOUT_SEC) -> Reading:
    """The frequency and the mode in one go: `f` and `m` on one connection that is closed again. Raises RigError."""
    try:
        async with asyncio.timeout(timeout_sec):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                writer.write(b"f\nm\n")
                hz = _hz(_line(await reader.readline()))
                mode = _line(await reader.readline())                # (the passband that follows is not read: the connection is dropped)
                if not mode:
                    raise RigError("rigctld gave no mode")
                return Reading(hz, mode)
            finally:
                writer.transport.abort()
    except TimeoutError:
        raise RigError("no answer in time") from None
    except ConnectionRefusedError:
        raise RigError("connection refused") from None
    except OSError as e:
        raise RigError(e.strerror or str(e)) from None
