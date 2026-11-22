"""Windows: the WinMM sound devices Direwolf opens, and the one input and output of a sound card.

Direwolf opens a device by number, and a number that matches nothing falls back to the default
device, which could key the wrong radio. So the daemon finds the numbers itself.
"""

import sys
from collections.abc import Sequence

from .mercurycards import unnumbered

# szPname holds 32 bytes including the zero (MAXPNAMELEN).
NAME_MAX = 31


def names_card(device: str, card: str, numbered: bool = True) -> bool:
    """Return whether a WinMM device name is "<kind> (<card>)", whole or cut at NAME_MAX.

    With `numbered` False, the number Windows may put before the name is ignored.
    """
    plain = (lambda name: name) if numbered else unnumbered
    want = f"{plain(card)})"
    for at in range(len(device)):
        if device.startswith(" (", at):
            rest = plain(device[at + 2 :])
            whole = rest == want
            cut = len(device) >= NAME_MAX and len(rest) > 0 and want.startswith(rest)
            if whole or cut:
                return True
    return False


def match(card: str, inputs: Sequence[str], outputs: Sequence[str]) -> tuple[int, int] | None:
    """Return the WinMM (input, output) numbers of the card; None unless exactly one each way."""
    found_in, found_out = _named(card, inputs), _named(card, outputs)
    return (found_in[0], found_out[0]) if len(found_in) == 1 and len(found_out) == 1 else None


def _named(card: str, names: Sequence[str]) -> list[int]:
    return [n for n, name in enumerate(names) if names_card(name, card)] or [
        n for n, name in enumerate(names) if names_card(name, card, numbered=False)
    ]


def devices() -> tuple[list[str], list[str]]:
    """Return the WinMM input and output device names by number; empty off Windows."""
    return _winmm_devices() if sys.platform == "win32" else ([], [])


def _winmm_devices() -> tuple[list[str], list[str]]:
    import ctypes
    from ctypes import wintypes

    # WAVEINCAPSA and WAVEOUTCAPSA share their head: manufacturer, product, driver version, name.
    class Caps(ctypes.Structure):
        _fields_ = [
            ("wMid", wintypes.WORD),
            ("wPid", wintypes.WORD),
            ("vDriverVersion", wintypes.UINT),
            ("szPname", ctypes.c_char * (NAME_MAX + 1)),
            ("dwFormats", wintypes.DWORD),
            ("wChannels", wintypes.WORD),
            ("wReserved1", wintypes.WORD),
            ("dwSupport", wintypes.DWORD),
        ]

    try:
        winmm = ctypes.WinDLL("winmm")  # type: ignore[attr-defined, unused-ignore]
    except OSError:
        return [], []

    def listed(count: str, caps: str) -> list[str]:
        names: list[str] = []
        for number in range(getattr(winmm, count)()):
            found = Caps()
            if getattr(winmm, caps)(number, ctypes.byref(found), ctypes.sizeof(found)) == 0:
                names.append(found.szPname.decode("mbcs", "replace"))
            else:
                names.append("")
        return names

    return listed("waveInGetNumDevs", "waveInGetDevCapsA"), listed("waveOutGetNumDevs", "waveOutGetDevCapsA")
