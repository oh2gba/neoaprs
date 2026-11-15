"""Which serial ports are part of a sound card's interface, from where the kernel places both on the USB (Linux: sysfs). A Digirig, an IC-7300 or an IC-9700 carries its sound chip and its serial chip behind
a hub of its own, so the two sit on one hub that is not the computer's; an all-in-one chip is one USB device with both. A port elsewhere on the USB (a programming cable, another radio's interface) is not the card's,
and keying it would key nothing, or another radio. Read for the keying Direwolf is given when the settings leave it to the daemon (direwolf.choose_keying)."""
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from . import nodevices

SYS = Path("/sys")
_DEVICE = re.compile(r"^\d+-\d+(?:\.\d+)*$")                 # a USB device's place as sysfs names it: bus 1, port 2, then port 3 of the hub there ("1-2.3"); an interface adds ":1.0", the root hub is "usb1"
_CARD_NUMBER = re.compile(r"^(?:plug)?hw:(\d+)")
_CARD_NAME = re.compile(r"CARD=([^,]+)")


def _usb_place(path: Path) -> tuple[str, str] | None:
    """The USB device a sysfs path lies under and the hub it hangs on, as their paths ("" for the hub when it is the computer's own); None when the path is not on the USB."""
    parts = path.parts
    found = [i for i, part in enumerate(parts) if _DEVICE.match(part)]
    if not found:
        return None
    device = found[-1]
    hub = str(Path(*parts[:device])) if _DEVICE.match(parts[device - 1]) else ""
    return str(Path(*parts[:device + 1])), hub


def _card_number(card_id: str, sys_root: Path) -> int | None:
    """The number of the ALSA card of this id (`plughw:1,0`, `plughw:CARD=CODEC,DEV=0`), by the names sysfs gives the cards; None when it is none of them."""
    if (m := _CARD_NUMBER.match(card_id)) is not None:
        return int(m.group(1))
    if (m := _CARD_NAME.search(card_id)) is None:
        return None
    for folder in sorted((sys_root / "class" / "sound").glob("card[0-9]*")):
        try:
            if folder.name[4:].isdigit() and (folder / "id").read_text(encoding="utf-8", errors="replace").strip() == m.group(1):
                return int(folder.name[4:])
        except OSError:
            continue
    return None


def tied(card_id: str, devices: Sequence[str], sys_root: Path = SYS) -> list[str] | None:
    """The serial devices of `devices` (`/dev/ttyUSB0`, a by-id link to one) that are part of the sound card's interface: on the card's own USB device, or beside it on one hub that is not the computer's own.
    None when that cannot be told: the card is not found on the USB. Reads sysfs: for a thread."""
    number = _card_number(card_id, sys_root)
    card = None if number is None else _usb_place((sys_root / "class" / "sound" / f"card{number}" / "device").resolve())
    if card is None:
        return None
    found: list[str] = []
    for device in devices:
        try:
            name = Path(device).resolve().name                         # (a by-id link is followed to its ttyUSB0)
        except OSError:
            continue
        place = _usb_place((sys_root / "class" / "tty" / name / "device").resolve())
        if place is not None and (place[0] == card[0] or (card[1] and place[1] == card[1])):
            found.append(device)
    return found


def beside(card_id: str, devices: Sequence[str]) -> list[str] | None:
    """`tied` on this computer; None where it cannot be told (not Linux, no card) and under the no-devices switch, which lists no device. NEOAPRS_SYS_ROOT names another folder than /sys (the tests point it
    at none: no test reads the machine's devices)."""
    root = Path(os.environ.get("NEOAPRS_SYS_ROOT") or SYS)
    return tied(card_id, devices, root) if sys.platform.startswith("linux") and card_id and not nodevices.on() else None
