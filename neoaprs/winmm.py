"""Windows: the WinMM sound devices Direwolf opens, and the one input and the one output of a sound card among them. Direwolf opens a WinMM device by its number, and a number that names no device, or a name that
matches none, leaves it on the system's default device (audio_win.c:336-338, 386-390), which could key the wrong radio or the computer's speakers; so the daemon finds the numbers itself and writes them, and anything
other than exactly one input and one output of the card is no start at all.

A card of the Sound card type is the one id the HF modem's list gives it (mercurycards.py: the pair of its WASAPI recording and playing devices, named after the card), so one card is one claim whichever type uses
it. WinMM names a device with the ANSI calls Direwolf uses (`waveInGetDevCapsA`, `waveOutGetDevCapsA`), at most 31 characters: the WASAPI device's friendly name, "Microphone (USB Audio CODEC)", cut short there. That the
two are the same name is what docs/direwolf.md says is proven on a Windows machine, not by a source."""
import sys
from collections.abc import Sequence

NAME_MAX = 31                          # WinMM's szPname holds 32 bytes with the terminating zero (MAXPNAMELEN)


def names_card(device: str, card: str) -> bool:
    """Whether a WinMM device name is a device of the sound card `card`: its friendly name "<kind> (<card>)", whole, or cut at NAME_MAX characters."""
    for at in range(len(device)):
        if device.startswith(" (", at):
            rest = device[at + 2:]
            whole = rest == f"{card})"
            cut = len(device) >= NAME_MAX and len(rest) > 0 and f"{card})".startswith(rest)
            if whole or cut:
                return True
    return False


def match(card: str, inputs: Sequence[str], outputs: Sequence[str]) -> tuple[int, int] | None:
    """The WinMM numbers of the card's input and output: exactly one of each way whose name is the card's (`names_card`); None for anything else (none, or more than one either way)."""
    found_in = [n for n, name in enumerate(inputs) if names_card(name, card)]
    found_out = [n for n, name in enumerate(outputs) if names_card(name, card)]
    return (found_in[0], found_out[0]) if len(found_in) == 1 and len(found_out) == 1 else None


def devices() -> tuple[list[str], list[str]]:
    """The names of the WinMM input and output devices, by number, as Direwolf sees them; none off Windows, or where WinMM cannot be asked."""
    return _winmm_devices() if sys.platform == "win32" else ([], [])


def _winmm_devices() -> tuple[list[str], list[str]]:
    import ctypes
    from ctypes import wintypes

    class Caps(ctypes.Structure):           # WAVEINCAPSA and WAVEOUTCAPSA share their head: the manufacturer, the product, the driver's version and the name
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT), ("szPname", ctypes.c_char * (NAME_MAX + 1)),
                    ("dwFormats", wintypes.DWORD), ("wChannels", wintypes.WORD), ("wReserved1", wintypes.WORD), ("dwSupport", wintypes.DWORD)]

    try:
        winmm = ctypes.WinDLL("winmm")                                    # type: ignore[attr-defined, unused-ignore]
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
