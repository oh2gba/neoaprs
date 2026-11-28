"""Why a port would not open, as a reason with a code: only what the system's answer proves.

Windows' numbers were measured on Bluetooth serial ports: 5 at once when another program has the
port, 121 after about 5 s when the device does not answer; for a direct RFCOMM socket 10060 (no
answer), 10051 (not paired) and 10064 (the device refused). The raw number stays in the text.
"""

import re

from .coded import Reason

ACCESS_DENIED, SEMAPHORE_TIMEOUT = 5, 121
WSA_NET_UNREACHABLE, WSA_TIMED_OUT, WSA_HOST_DOWN = 10051, 10060, 10064
# a connect to a device by name while another program on this computer holds its COM port (measured)
WSA_ADDR_IN_USE = 10048
NO_ANSWER = frozenset({SEMAPHORE_TIMEOUT, WSA_TIMED_OUT})
# pyserial writes the system's error as its repr: `PermissionError(13, 'Access is denied.', None, 5)`
_REPR_NUMBER = re.compile(r", None, (\d+)\)")
_WINERROR = re.compile(r"\[WinError (\d+)\]")


def _chain(e: BaseException) -> list[BaseException]:
    """Return the error and the errors it was raised from, outermost first."""
    found: list[BaseException] = []
    at: BaseException | None = e
    while at is not None and at not in found:
        found.append(at)
        at = at.__cause__ or at.__context__
    return found


def windows_error(e: BaseException) -> int | None:
    """Return Windows' own error number of a failed open, from the error or its text; None elsewhere."""
    for error in _chain(e):
        number = getattr(error, "winerror", None)
        if isinstance(number, int):
            return number
        if found := _REPR_NUMBER.search(str(error)) or _WINERROR.search(str(error)):
            return int(found.group(1))
    return None


def timed_out(e: BaseException) -> bool:
    return any(isinstance(error, TimeoutError) for error in _chain(e))


def _numbered(reason: Reason, number: int | None) -> Reason:
    return reason if number is None else Reason(f"{reason} (Windows error {number})", reason.code, **reason.params)


def failure(path: str, e: BaseException, words: str, *, in_use: bool, bluetooth: bool) -> Reason:
    """Return why `path` did not open; `words` is the system's, said for a cause the error does not prove."""
    number = windows_error(e)
    if in_use or (bluetooth and number == WSA_ADDR_IN_USE):
        why = Reason(
            f"{path}: in use by another program (close it: a terminal, Direwolf, a rig program)", "radio.port_in_use"
        )
    elif not bluetooth:
        why = Reason(words)
    elif number in NO_ANSWER or (number is None and timed_out(e)):
        why = Reason(f"{path}: the device does not answer (switched off, asleep or out of range)", "radio.no_answer")
    elif number == WSA_NET_UNREACHABLE:
        why = Reason(f"{path}: the device is not paired with this computer", "radio.not_paired")
    elif number == WSA_HOST_DOWN:
        why = Reason(
            f"{path}: the device refused the connection (its serial port is busy or not offered)", "radio.refused"
        )
    else:
        why = Reason(f"{path}: the port could not be opened", "radio.open_failed")
        why = Reason(f"{why}: {words.removeprefix(f'{path}: ')}", why.code)
    return _numbered(why, number)
