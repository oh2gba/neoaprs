"""Which serial ports and sound cards are one radio's, from where the kernel places them on the USB (Linux: sysfs). A radio with USB (an FTX-1, an IC-7300), a Digirig or an IC-9700 carries its sound chip and its
serial chips behind a small hub of its own; an all-in-one chip (an AIOC) is one USB device with both. A port elsewhere on the USB (a programming cable, another radio's interface) is not the card's, and keying it
would key nothing, or another radio.

The rule (`_Tree.group`): a USB device is grouped with the others on its hub when that hub is not the computer's own (a root hub) and carries nothing but devices with a sound card or a serial port, exactly one of them
with a sound card; else it is a group alone. So the two radios of one computer, each a hub with its sound card and one or two serial chips, are two groups; a hub that also carries a keyboard, a memory stick,
another hub or a second sound card is no radio's, and each device on it stands alone; two devices straight on the computer are never grouped. A lone serial cable and a lone sound dongle on a small desktop hub
with nothing else on it look like a radio's hub, and are grouped: nothing in the tree tells them apart, and the cable is then the likely keying anyway.

Read for the keying Direwolf is given when the settings leave it to the daemon (direwolf.choose_keying), and for `usb_group` of the ports and the sound cards on the wire (`together`): an opaque token, equal
for the devices of one group, which the page orders the keying lines by. The token is never shown and never logged."""
import hashlib
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


def _places(sys_root: Path, kind: str, pattern: str) -> list[tuple[str, str]]:
    """The USB places of every member of a class of sysfs (`sound` cards, `tty` ports) that is on the USB."""
    try:
        folders = sorted((sys_root / "class" / kind).glob(pattern))
    except OSError:
        return []
    return [p for p in (_usb_place((f / "device").resolve()) for f in folders) if p is not None]


class _Tree:
    """The USB devices of this computer that carry a sound card or a serial port, read once from sysfs."""

    def __init__(self, sys_root: Path) -> None:
        self.root = sys_root
        cards, ttys = _places(sys_root, "sound", "card[0-9]*"), _places(sys_root, "tty", "*")
        self.sound = {device for device, _ in cards}
        self.members = self.sound | {device for device, _ in ttys}

    def _radio_hub(self, hub: str) -> bool:
        """Whether the hub carries nothing but devices with a sound card or a serial port, exactly one with a sound card."""
        try:
            children = [str(Path(hub) / c.name) for c in Path(hub).iterdir() if _DEVICE.match(c.name)]
        except OSError:
            return False
        return bool(children) and all(c in self.members for c in children) and sum(c in self.sound for c in children) == 1

    def group(self, place: tuple[str, str] | None) -> str | None:
        """The group of a USB place (the path of its hub or of the device itself); None off the USB."""
        if place is None:
            return None
        device, hub = place
        return hub if hub and self._radio_hub(hub) else device

    def card(self, card_id: str) -> str | None:
        number = _card_number(card_id, self.root)
        return None if number is None else self.group(_usb_place((self.root / "class" / "sound" / f"card{number}" / "device").resolve()))

    def port(self, device: str) -> str | None:
        try:
            name = Path(device).resolve().name                         # (a by-id link is followed to its ttyUSB0)
        except OSError:
            return None
        return self.group(_usb_place((self.root / "class" / "tty" / name / "device").resolve())) if name else None


def tied(card_id: str, devices: Sequence[str], sys_root: Path = SYS) -> list[str] | None:
    """The serial devices of `devices` (`/dev/ttyUSB0`, a by-id link to one) that are in the sound card's group (`_Tree.group`): part of the card's interface or of the radio it is in.
    None when that cannot be told: the card is not found on the USB. Reads sysfs: for a thread."""
    tree = _Tree(sys_root)
    if (card := tree.card(card_id)) is None:
        return None
    return [d for d in devices if not d.lower().startswith(("bt://", "ble://")) and tree.port(d) == card]


def _token(group: str | None) -> str | None:
    return None if group is None else hashlib.sha256(group.encode()).hexdigest()[:12]


def groups(card_ids: Sequence[str], devices: Sequence[str], sys_root: Path = SYS) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """The token of the group (`_Tree.group`) of each sound card and of each serial device, equal for the devices of one group; None where it is not known (not on the USB, not found). Reads sysfs: for a thread."""
    tree = _Tree(sys_root)
    return ({c: _token(tree.card(c)) for c in card_ids},
            {d: None if d.lower().startswith(("bt://", "ble://")) else _token(tree.port(d)) for d in devices})


def _here() -> Path | None:
    """The sysfs of this computer; None where nothing can be told (not Linux) and under the no-devices switch, which lists no device. NEOAPRS_SYS_ROOT names another folder than /sys (the tests point it
    at none: no test reads the machine's devices)."""
    return Path(os.environ.get("NEOAPRS_SYS_ROOT") or SYS) if sys.platform.startswith("linux") and not nodevices.on() else None


def beside(card_id: str, devices: Sequence[str]) -> list[str] | None:
    """`tied` on this computer; None where it cannot be told (not Linux, no card) and under the no-devices switch."""
    root = _here()
    return tied(card_id, devices, root) if root is not None and card_id else None


def together(card_ids: Sequence[str], devices: Sequence[str]) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """`groups` on this computer; every token None where nothing can be told (not Linux) and under the no-devices switch."""
    root = _here()
    return groups(card_ids, devices, root) if root is not None else ({c: None for c in card_ids}, {d: None for d in devices})
