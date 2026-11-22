"""Find which serial ports and sound cards belong to one radio, by USB place (Linux sysfs).

A USB radio carries its sound and serial chips behind a small hub of its own (`_Tree.group`);
keying a port elsewhere would key another radio. `together` gives each an opaque group token.
"""

import hashlib
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from . import nodevices

SYS = Path("/sys")
# a USB device's place as sysfs names it: bus 1, port 2, port 3 of the hub there ("1-2.3")
_DEVICE = re.compile(r"^\d+-\d+(?:\.\d+)*$")
_CARD_NUMBER = re.compile(r"^(?:plug)?hw:(\d+)")
_CARD_NAME = re.compile(r"CARD=([^,]+)")


def _usb_place(path: Path) -> tuple[str, str] | None:
    """Return the paths of the USB device a sysfs path lies under and of its hub ("" if root)."""
    parts = path.parts
    found = [i for i, part in enumerate(parts) if _DEVICE.match(part)]
    if not found:
        return None
    device = found[-1]
    hub = str(Path(*parts[:device])) if _DEVICE.match(parts[device - 1]) else ""
    return str(Path(*parts[: device + 1])), hub


def _card_number(card_id: str, sys_root: Path) -> int | None:
    if (m := _CARD_NUMBER.match(card_id)) is not None:
        return int(m.group(1))
    if (m := _CARD_NAME.search(card_id)) is None:
        return None
    for folder in sorted((sys_root / "class" / "sound").glob("card[0-9]*")):
        try:
            if folder.name[4:].isdigit() and (folder / "id").read_text(
                encoding="utf-8", errors="replace"
            ).strip() == m.group(1):
                return int(folder.name[4:])
        except OSError:
            continue
    return None


def _places(sys_root: Path, kind: str, pattern: str) -> list[tuple[str, str]]:
    try:
        folders = sorted((sys_root / "class" / kind).glob(pattern))
    except OSError:
        return []
    return [p for p in (_usb_place((f / "device").resolve()) for f in folders) if p is not None]


class _Tree:
    """The USB devices carrying a sound card or a serial port."""

    def __init__(self, sys_root: Path) -> None:
        self.root = sys_root
        cards, ttys = _places(sys_root, "sound", "card[0-9]*"), _places(sys_root, "tty", "*")
        self.sound = {device for device, _ in cards}
        self.members = self.sound | {device for device, _ in ttys}

    def _radio_hub(self, hub: str) -> bool:
        try:
            children = [str(Path(hub) / c.name) for c in Path(hub).iterdir() if _DEVICE.match(c.name)]
        except OSError:
            return False
        return (
            bool(children) and all(c in self.members for c in children) and sum(c in self.sound for c in children) == 1
        )

    def group(self, place: tuple[str, str] | None) -> str | None:
        if place is None:
            return None
        device, hub = place
        return hub if hub and self._radio_hub(hub) else device

    def card(self, card_id: str) -> str | None:
        number = _card_number(card_id, self.root)
        return (
            None
            if number is None
            else self.group(_usb_place((self.root / "class" / "sound" / f"card{number}" / "device").resolve()))
        )

    def port(self, device: str) -> str | None:
        try:
            # a by-id link is followed to its ttyUSB0
            name = Path(device).resolve().name
        except OSError:
            return None
        return self.group(_usb_place((self.root / "class" / "tty" / name / "device").resolve())) if name else None


def tied(card_id: str, devices: Sequence[str], sys_root: Path = SYS) -> list[str] | None:
    """Return the serial devices on the card's own USB device or beside it on its hub.

    None if the card is not on the USB. Reads sysfs: call from a thread.
    """
    number = _card_number(card_id, sys_root)
    card = None if number is None else _usb_place((sys_root / "class" / "sound" / f"card{number}" / "device").resolve())
    if card is None:
        return None
    found: list[str] = []
    for device in devices:
        if device.lower().startswith(("bt://", "ble://")):
            continue
        try:
            name = Path(device).resolve().name
        except OSError:
            continue
        place = _usb_place((sys_root / "class" / "tty" / name / "device").resolve()) if name else None
        if place is not None and (place[0] == card[0] or (card[1] and place[1] == card[1])):
            found.append(device)
    return found


def _token(group: str | None) -> str | None:
    return None if group is None else hashlib.sha256(group.encode()).hexdigest()[:12]


def groups(
    card_ids: Sequence[str], devices: Sequence[str], sys_root: Path = SYS
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Return the group token of each sound card and serial device; reads sysfs (use a thread)."""
    tree = _Tree(sys_root)
    return (
        {c: _token(tree.card(c)) for c in card_ids},
        {d: None if d.lower().startswith(("bt://", "ble://")) else _token(tree.port(d)) for d in devices},
    )


def _here() -> Path | None:
    """Return the sysfs of this computer, or None off Linux; NEOAPRS_SYS_ROOT is for tests."""
    return (
        Path(os.environ.get("NEOAPRS_SYS_ROOT") or SYS)
        if sys.platform.startswith("linux") and not nodevices.on()
        else None
    )


def beside(card_id: str, devices: Sequence[str]) -> list[str] | None:
    root = _here()
    return tied(card_id, devices, root) if root is not None and card_id else None


def together(card_ids: Sequence[str], devices: Sequence[str]) -> tuple[dict[str, str | None], dict[str, str | None]]:
    root = _here()
    return (
        groups(card_ids, devices, root)
        if root is not None
        else ({c: None for c in card_ids}, {d: None for d in devices})
    )
